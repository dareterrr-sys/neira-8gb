"""Stress organ (prototype, 04.11.2026, department «Обучение Нейры»; author's register item 10).

For a sentence Neira's voice said: was the stress right in the doubtful words?
  WHAT to check and HOW it must sound - stress_text.py (the author's Russian library: accents.txt, fipi_stress.txt,
    OpenCorpora) run in the russkiy venv; the sounds of a stressed / unstressed vowel follow the reduction rules of
    neira-tools/knowledge/russkiy/ref_orth_phonetics.md: stressed = full vowel; first pretonic (and word-initial)
    о/а -> [ʌ] (espeak ɐ); other unstressed о/а -> [ъ] (ə); е/я after a soft consonant -> [и^] (ɪ) («иканье»);
    Potebnya: stressed 3 units of strength, first pretonic 2, the rest 1 (lines 37-38, 167, 199).
  HOW the voice said it - a ready phoneme recogniser (facebook/wav2vec2-xlsr-53-espeak-cv-ft, CPU): the sentence is
    force-aligned once; in each vowel's window the recogniser's mass of vowel classes (О, А, Е, И, У) is compared
    with what every possible stress predicts (stressed о = О, unstressed о = А; stressed е = Е, unstressed = И).
    Vosk word boundaries (the voice's own judge model) and each vowel's length / loudness / pitch are kept as hints.
    Decision rule now: ONLY the О/А contrast decides (O_ONLY, see check()); measurement 04.11 in
    stress_organ\\runs\\report*.txt and the department's notes.
Output per checked word: «верно» / «неверно» / «не уверен», the stress heard, the margin.

Runs in the fastqwen venv (torch, transformers, vosk, librosa); never touches the voice server.
Usage: python stress_organ.py <wav> "<text with or without + marks>" [more wav text pairs...]
       or python stress_organ.py --json list.json out.json   (list = [{"wav":..., "text":...}, ...])
"""
import difflib
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# nothing on C: (author, 04.11: «на С ничё не надо записывать, есть же папка D AI»): temp files and the Hugging Face
# state go to D:, also for the subprocesses (russkiy / ruaccent venvs)
TMP = os.path.join(HERE, "tmp")
os.makedirs(TMP, exist_ok=True)
for _k in ("TMP", "TEMP", "TMPDIR"):
    os.environ[_k] = TMP
tempfile.tempdir = TMP
os.environ.setdefault("HF_HOME", r"D:/AI/models/hf_cache")
RUSSKIY_PY = os.path.join(os.path.dirname(HERE), "russkiy", ".venv", "Scripts", "python.exe")
PHONE_MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
HF_CACHE = r"D:/AI/models/hf_cache"
VOSK = r"D:/AI/models/vosk-model-small-ru-0.22"
VOW = "аеёиоуыэюя"

# ---------------------------------------------------------------- letters -> espeak-style phonemes (model vocab)
HARD = {"б": "b", "в": "v", "г": "ɡ", "д": "d", "ж": "ʐ", "з": "z", "к": "k", "л": "l", "м": "m", "н": "n", "п": "p",
        "р": "r", "с": "s", "т": "t", "ф": "f", "х": "x", "ц": "ts", "ч": "tʃ", "ш": "ʃ", "щ": "ɕ", "й": "j"}
# ч/ш/ж as the recogniser actually writes them on her voice (greedy decode of 1_как_есть.wav, runs/debug_1.txt)
HARD["ж"] = "ʒ"
SOFT = {"б": "bʲ", "в": "vʲ", "г": "ɡʲ", "д": "dʲ", "з": "ʑ", "к": "kʲ", "л": "ʎ", "м": "mʲ", "н": "nʲ", "п": "pʲ",
        "р": "rʲ", "с": "sʲ", "т": "tʲ", "ф": "fʲ", "х": "xʲ"}
DEVOICE = {"b": "p", "v": "f", "ɡ": "k", "d": "t", "ʒ": "ʃ", "z": "s", "bʲ": "pʲ", "vʲ": "fʲ", "dʲ": "tʲ", "ʑ": "sʲ"}
ALWAYS_SOFT = set("чщй")
ALWAYS_HARD = set("жшц")
STRESSED = {"а": "a", "о": "o", "у": "u", "ы": "ɨ", "э": "ɛ", "и": "i", "е": "e", "ё": "o", "ю": "u", "я": "a"}


def word_phones(w, stress):
    """Phonemes of word w with the stress on vowel number `stress` (0-based); returns (phones, vowel_slots) where
    vowel_slots[k] = index in phones of vowel k."""
    out, slots = [], []
    vi = 0
    letters = list(w)
    for i, c in enumerate(letters):
        nxt = letters[i + 1] if i + 1 < len(letters) else "#"
        prev = letters[i - 1] if i > 0 else "#"
        if c in "ьъ":
            continue
        if c in VOW:
            iotated = c in "еёюя" and (i == 0 or prev in VOW or prev in "ьъ")
            if iotated:
                out.append("j")
            soft_before = iotated or c in "еёиюя" or prev in ALWAYS_SOFT
            after_hard_sib = prev in ALWAYS_HARD
            if vi == stress:
                v = STRESSED[c]
                if c == "и" and after_hard_sib:
                    v = "ɨ"
            else:
                pre1 = vi == stress - 1 or i == 0   # first pretonic, or word-initial (Potebnya: = first pretonic)
                last = i == len(letters) - 1
                if c in "уюу":
                    v = "ʊ"
                elif c == "ы" or (c == "и" and after_hard_sib):
                    v = "ɨ"
                elif c == "и":
                    v = "ɪ"
                elif c in "оа" and not soft_before:
                    v = "ɐ" if pre1 else "ə"
                elif c in "еёя" or (c in "оа" and soft_before):
                    if after_hard_sib:
                        v = "ɨ" if c == "е" else "ɐ"
                    elif last and vi > stress:
                        v = "ə" if c in "яа" else "ɪ"
                    else:
                        v = "ɪ"
                elif c == "э":
                    v = "ɛ" if pre1 else "ɪ"
                else:
                    v = "ə"
            slots.append(len(out))
            out.append(v)
            vi += 1
            continue
        if c in HARD:
            soft = c in ALWAYS_SOFT or (c not in ALWAYS_HARD and (nxt in "еёиюяь"))
            p = SOFT.get(c, HARD[c]) if soft else HARD[c]
            if c == "г" and i >= 2 and w.endswith(("ого", "его")) and i == len(w) - 2:
                p = "v"
            if i == len(letters) - 1 or (i == len(letters) - 2 and nxt in "ьъ"):
                p = DEVOICE.get(p, p)
            out.append(p)
    return out, slots


# ---------------------------------------------------------------- models (lazy, CPU)
_PH = {}


def phone_model():
    if not _PH:
        import torch
        from transformers import Wav2Vec2ForCTC
        from huggingface_hub import snapshot_download
        path = snapshot_download(PHONE_MODEL, cache_dir=HF_CACHE, local_files_only=True)
        # STRESS_THREADS: the live judge shares the CPU with the brain's experts and the voice judges
        torch.set_num_threads(int(os.environ.get("STRESS_THREADS", max(1, (os.cpu_count() or 4) - 2))))
        _PH["model"] = Wav2Vec2ForCTC.from_pretrained(path).eval()
        _PH["vocab"] = json.load(open(os.path.join(path, "vocab.json"), encoding="utf-8"))
    return _PH["model"], _PH["vocab"]


_VOSK = {}


def vosk_words(audio16):
    from vosk import KaldiRecognizer, Model, SetLogLevel
    if not _VOSK:
        SetLogLevel(-1)
        _VOSK["m"] = Model(VOSK)
    rec = KaldiRecognizer(_VOSK["m"], 16000)
    rec.SetWords(True)
    pcm = (np.clip(audio16, -1, 1) * 32767).astype(np.int16).tobytes()
    rec.AcceptWaveform(pcm)
    res = json.loads(rec.FinalResult())
    return [(r["word"], r["start"], r["end"]) for r in res.get("result", [])]


def load16(path):
    import librosa
    a, sr = librosa.load(path, sr=16000, mono=True)
    return a.astype(np.float32)


def emissions(audio16):
    import torch
    m, _ = phone_model()
    x = (audio16 - audio16.mean()) / (audio16.std() + 1e-7)
    with torch.inference_mode():
        lg = m(torch.from_numpy(x)[None]).logits[0]
    return torch.log_softmax(lg, -1)   # [T, V], 20 ms frames


def ids(phones, vocab):
    return [vocab[p] for p in phones if p in vocab]


def ctc_ll(lp, target_ids):
    import torch
    import torch.nn.functional as F
    t = torch.tensor(target_ids)[None]
    return -float(F.ctc_loss(lp[:, None, :], t, torch.tensor([lp.shape[0]]), torch.tensor([t.shape[1]]),
                             blank=0, reduction="sum", zero_infinity=True))


def align(lp, target_ids):
    """Frame spans of each target token: list of (start_frame, end_frame)."""
    import torch
    import torchaudio.functional as AF
    ali, _ = AF.forced_align(lp[None], torch.tensor([target_ids], dtype=torch.int32), blank=0)
    ali = ali[0].tolist()
    spans = []
    # a new token starts where a non-blank label differs from the previous frame's label (a blank in between
    # separates two equal tokens)
    starts = []
    last = 0
    for f, tok in enumerate(ali):
        if tok == 0:
            last = 0
            continue
        if tok != last:
            starts.append(f)
        last = tok
    starts = starts[:len(target_ids)]
    for j, s in enumerate(starts):
        e = starts[j + 1] if j + 1 < len(starts) else len(ali)
        spans.append((s, e))
    return spans


# ---------------------------------------------------------------- the organ
def text_analysis(texts, check_all=False):
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "in.json"), os.path.join(d, "out.json")
        json.dump(texts, open(i, "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run([RUSSKIY_PY, os.path.join(HERE, "stress_text.py"), i, o] + (["--all"] if check_all else []),
                       check=True)
        return json.load(open(o, encoding="utf-8"))


# vowel QUALITY classes of the recogniser's phonemes; reduction (ref_orth_phonetics.md): unstressed о -> [ʌ]/[ъ]
# (A class), unstressed е/э/я after a soft consonant -> [и^] (I class). а/и/ы/у/ю keep their class unstressed, so for
# them only length / loudness / pitch can tell the stress.
VCLASS = {"O": ["o", "oː", "ɔ", "ɔː", "o̞", "oʊ", "ɵ", "o:"],
          "A": ["a", "aː", "ɐ", "ə", "ʌ", "ɑ", "ɑː", "æ", "ä", "ɐɐ", "ɜ", "a:"],
          "E": ["e", "eː", "ɛ", "ɛː", "e̞", "eɪ", "e:"],
          "I": ["i", "iː", "ɪ", "ɨ", "ᵻ", "ɪː", "i:"],
          "U": ["u", "uː", "ʊ", "ʉ", "ʊː", "u:"]}
Q_SURE = 1.5    # log-ratio of vowel-class evidence: quality alone decides
Q_LEAN = 0.5    # decides only if the vowel's prosody agrees
P_SURE = 1.0    # z-score lead of the stressed vowel's length+loudness+pitch when quality cannot tell
O_ONLY = True   # decide only on the О/А contrast (chosen AFTER seeing the 04.11 data - not yet validated)


def vowel_letters(w):
    return [(i, c) for i, c in enumerate(w) if c in VOW]


def vclass(w, k, stress):
    """Expected quality class of vowel k of w under stress `stress` (None = quality does not tell)."""
    vl = vowel_letters(w)
    i, c = vl[k]
    st = k == stress
    if c == "о":
        return "O" if st else "A"
    if c in "еэ":
        return "E" if st else "I"
    if c == "я":
        if st:
            return "A"
        return "A" if (k > stress and i == len(w) - 1) else "I"
    return None


def class_post(lp, a, b, vocab):
    """Normalised vowel-class mass over frames [a, b)."""
    import torch
    p = torch.exp(lp[a:max(b, a + 1)])
    mass = {}
    for c, toks in VCLASS.items():
        idx = [vocab[t] for t in toks if t in vocab]
        mass[c] = float(p[:, idx].sum())
    tot = sum(mass.values()) + 1e-6
    return {c: (v + 0.01 * tot) / (1.05 * tot) for c, v in mass.items()}


def check(wav, info):
    """info = one item of stress_text output. Returns a list of verdicts for the checked words."""
    return check_audio(load16(wav), info)


def check_audio(audio, info, use_vosk=True, only_norm=False):
    """audio = float32 mono 16 kHz. use_vosk=False: no Vosk word times (only a hint; the live judge skips them).
    only_norm=True: judge only the words that have a norm (expected stress), the live judge's case."""
    m, vocab = phone_model()
    lp = emissions(audio)
    words = info["words"]
    if only_norm:
        words = [dict(w, check=w["check"] and w["expected"] is not None) for w in words]
    vw = vosk_words(audio) if use_vosk else []
    sm = difflib.SequenceMatcher(a=[w["w"].replace("ё", "е") for w in words], b=[v[0].replace("ё", "е") for v in vw])
    vosk_of = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            vosk_of[a + k] = vw[b + k]
    nwords = len(words)
    # one alignment of the whole sentence with the expected / dictionary stresses: the consonants fix where each
    # vowel sits; every stress candidate is then judged on the same vowel windows
    ph_all, slot_at = [], {}
    for k, w in enumerate(words):
        p, slots = word_phones(w["w"], w["stress"])
        slot_at[k] = [len(ph_all) + sl for sl in slots]
        ph_all += p
    tid = ids(ph_all, vocab)
    try:
        spans = align(lp, tid)
    except Exception:
        spans = []
    T = lp.shape[0]
    results = []
    for wi, w in enumerate(words):
        if not w["check"]:
            continue
        nv = sum(c in VOW for c in w["w"])
        if len(spans) != len(tid):
            results.append({"word": w["w"], "verdict": "не уверен", "why": w["why"], "error": "alignment failed",
                            "expected": w["expected"], "heard": None, "basis": "нет выравнивания"})
            continue
        wins = []
        for j in slot_at[wi]:
            s0 = spans[j - 1][0] + (spans[j][0] - spans[j - 1][0]) // 2 if j > 0 else max(0, spans[j][0] - 3)
            s1 = spans[j + 1][0] if j + 1 < len(spans) else T
            wins.append((s0, min(s1, spans[j][0] + 15)))   # <= 0.3 s after the vowel starts: no trailing pause
        post = [class_post(lp, a, b, vocab) for a, b in wins]
        qs = []
        for s in range(nv):
            q = 0.0
            for k in range(nv):
                c = vclass(w["w"], k, s)
                if c is not None:
                    q += float(np.log(post[k][c]))
            qs.append(q)
        order = [int(x) for x in np.argsort(qs)[::-1]]
        qbest = order[0]
        qmargin = float(qs[order[0]] - qs[order[1]]) if nv > 1 else 0.0
        informative = nv > 1 and any(vclass(w["w"], k, order[0]) != vclass(w["w"], k, order[1]) for k in range(nv))
        # prosody of each vowel window: length (s), loudness (dB), pitch (Hz)
        feats = prosody_w(audio, wins)
        final = wi == nwords - 1   # phrase-final lengthening: length and pitch of the last word are unreliable
        pz = prosody_z(feats, loud_only=final)
        ppick = int(np.argmax(pz)) if pz is not None else None
        plead = float(sorted(pz)[-1] - sorted(pz)[-2]) if pz is not None and nv > 1 else 0.0
        # Only the О/А contrast decides (measurement 04.11 on the author's 160 rated dubs: false alarms on phrases he
        # called right - О/А 11/189 words, Е/И 23/82, length/loudness/pitch alone 18/84). Е/И and prosody stay in the
        # output as hints. O_ONLY=False restores the first rule (stress_organ.py.before-oonly).
        # The contrast and the margin are judged for the pair that matters: the best stress against the expected one
        # (or, when the best IS the expected one, against the runner-up).
        # several stresses can be the norm (RAN: св+ерлит and сверл+ит): the best is compared with the closest norm when
        # it is not one, else with the best stress that is not a norm
        exp = w["expected"]
        ok = set(w.get("expected_any") or ([exp] if exp is not None else []))
        cmp = order[1] if nv > 1 else order[0]
        if ok and qbest not in ok:
            cmp = max(ok, key=lambda s: qs[s])
        elif ok:
            cmp = next((s for s in order if s not in ok), cmp)
        qmargin = float(qs[qbest] - qs[cmp])
        vl = vowel_letters(w["w"])
        o_contrast = nv > 1 and any(vl[k][1] == "о" and vclass(w["w"], k, qbest) != vclass(w["w"], k, cmp)
                                    for k in range(nv))
        decisive = o_contrast if O_ONLY else informative
        if decisive and qmargin >= Q_SURE:
            heard, basis = qbest, "качество гласных (О/А)" if O_ONLY else "качество гласных"
        elif decisive and qmargin >= Q_LEAN and ppick == qbest:
            heard, basis = qbest, "качество (О/А) + длительность/громкость/высота"
        elif not O_ONLY and not informative and ppick is not None and plead >= P_SURE:
            heard, basis = ppick, "длительность/громкость/высота"
        else:
            heard, basis = None, "нет контраста О/А или признаки слабые" if O_ONLY else "признаки слабые"
        if exp is None:
            verdict = "не уверен"
            basis += "; как надо — не решено (омограф)"
        elif heard is None:
            verdict = "не уверен"
        else:
            verdict = "верно" if heard in ok else "неверно"
        guess = heard if heard is not None else (qbest if informative else ppick)
        results.append({
            "word": w["w"], "expected": exp, "heard": heard, "guess": guess, "verdict": verdict, "basis": basis,
            "o_contrast": bool(o_contrast), "q_margin": round(qmargin, 2), "q": [round(x, 2) for x in qs], "prosody_pick": ppick,
            "prosody_lead": round(plead, 2), "phrase_final": final, "why": w["why"],
            "post": [{c: round(v, 2) for c, v in p.items()} for p in post],
            "vowels": [{"dur": round(f[0], 3), "db": round(f[1], 1), "f0": None if f[2] != f[2] else round(f[2])}
                       for f in feats],
            "vosk": vosk_of.get(wi),
            "heard_form": stressed(w["w"], guess) if guess is not None else None,
            "expected_form": " / ".join(stressed(w["w"], s) for s in sorted(ok)) if ok else None,
        })
    return results


def prosody_w(audio16, wins):
    import librosa
    feats = []
    for a, b in wins:
        x = audio16[a * 320:max(b * 320, a * 320 + 320)]
        dur = (b - a) * 0.02
        db = 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-6)
        f0 = np.nan
        if len(x) >= 1024:
            f = librosa.yin(x, fmin=120, fmax=700, sr=16000, frame_length=1024)
            f = f[f < 680]   # yin returns ~fmax on unvoiced frames
            f0 = float(np.median(f)) if len(f) else np.nan
        feats.append((dur, float(db), f0))
    return feats


def prosody_z(feats, loud_only=False):
    arr = np.array(feats, dtype=float)
    if len(arr) < 2:
        return None
    z = np.zeros(len(arr))
    for c in ([1] if loud_only else [0, 1, 2]):
        col = arr[:, c]
        if np.isnan(col).any() or col.std() < 1e-6:
            continue
        z += (col - col.mean()) / col.std()
    return z


def stressed(w, vi):
    k = -1
    for i, c in enumerate(w):
        if c in VOW:
            k += 1
            if k == vi:
                return w[:i] + c.upper() + w[i + 1:]
    return w


def run(items, check_all=False):
    infos = text_analysis([it["text"] for it in items], check_all)
    out = []
    for it, info in zip(items, infos):
        out.append({"wav": it["wav"], "text": it["text"], "words": check(it["wav"], info)})
    return out


if __name__ == "__main__":
    if sys.argv[1] == "--json":
        items = json.load(open(sys.argv[2], encoding="utf-8"))
        json.dump(run(items, "--all" in sys.argv), open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        args = sys.argv[1:]
        res = run([{"wav": args[i], "text": args[i + 1]} for i in range(0, len(args), 2)])
        sys.stdout.reconfigure(encoding="utf-8")
        for r in res:
            print(r["wav"])
            for w in r["words"]:
                print(f"  {w['word']}: {w['verdict']}  слышу {w.get('heard_form')}, надо {w.get('expected_form')}"
                      f"  ({w.get('basis')}; {w['why']})")
