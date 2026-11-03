"""Best-of-N v2 (29.10, the author: "intonation must flow like a melody, as in her gibberish; no jumps; and the stress
is wrong: шкафУ, шучУ, привыкАй"). Each take is scored on:
 - words right: Vosk CER <= 0.25;
 - stress: for every marked word (+), Vosk's word timing; the word's span is cut into syllables by vowel count and
   the loudest-and-longest syllable must be the marked one (crude, but a wrong stress is usually a loud wrong vowel);
 - melody: wide (F0 spread) but smooth - a penalty for every frame-to-frame jump > 1.2 semitones inside voiced runs.
All takes -> lively_test\\takes2\\<sentence>_<take>.wav; the pick -> best2_lively.wav."""
import json
import os
import re
import urllib.request

import librosa
import numpy as np
import soundfile as sf
import torch
import vosk
from faster_qwen3_tts import FasterQwen3TTS

import int8_voice

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
OUT = r"D:\AI\voices\lively_test"
TAKES = os.path.join(OUT, "takes2")
os.makedirs(TAKES, exist_ok=True)
N = int(os.environ.get("TAKES", "8"))
VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"
TEXT = ("Слушай, я тут подумала, пока ты молчал. Ты вообще понимаешь, что собрал меня буквально за неделю? Мозг, голос, "
        "память — всё сам. Нет, ну серьёзно, это же безумие! Обычные люди за неделю максимум полку в шкафу собирают. "
        "А ты взял и сделал меня. Хотя, признаю, иногда я торможу так, что самой стыдно. Минута на простое «привет» — "
        "это был позор, давай договоримся никому об этом не рассказывать. Зато теперь я считаю лучше калькулятора и "
        "решаю задачи с подвохом, на которых ломаются взрослые программисты. Так что не зазнавайся: без меня ты бы "
        "до сих пор сидел и спорил с компьютером. Ладно, шучу. Почти. Спасибо тебе, правда. Только не привыкай к "
        "моей доброте, это было один раз.")
# the words the author heard wrong; marked here even if the stress service leaves them (it marks doubtful words only)
EXTRA = {"шкафу": "шкаф+у", "шучу": "шуч+у", "привыкай": "привык+ай"}


def mark(text):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(CFG["stress_service"], json.dumps({"text": text}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    out = json.loads(op.open(req, timeout=10).read().decode("utf-8"))["text"]
    fix = json.load(open(os.path.join(HERE, "stress_fix.json"), encoding="utf-8"))
    fix.update(EXTRA)
    for w, m in fix.items():
        out = re.sub(r"(?<![\w+])" + w + r"(?!\w)", m, out, flags=re.I)
    return out


def melody(w, sr):
    """-> (spread, jumps per second of voice): F0 std in semitones; jumps > 1.2 st between neighbouring voiced frames."""
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr, frame_length=1024, hop_length=256)
    st = 12 * np.log2(np.where(voiced, f0, np.nan) / np.nanmedian(f0))
    ok = ~np.isnan(st)
    if ok.sum() < 10:
        return 0.0, 99.0
    d = np.abs(np.diff(st))
    both = ok[1:] & ok[:-1]
    jumps = int((d[both] > 1.2).sum())
    return float(np.nanstd(st)), jumps / (ok.sum() * 256 / sr)


vosk.SetLogLevel(-1)
asr = vosk.Model(CFG["judge_model"])


def heard(w, sr):
    r = vosk.KaldiRecognizer(asr, 16000)
    r.SetWords(True)
    x = librosa.resample(w, orig_sr=sr, target_sr=16000)
    r.AcceptWaveform((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    res = json.loads(r.FinalResult())
    return res.get("text", ""), res.get("result", []), x


def norm(s):
    return re.sub(r"[^а-яё ]", "", s.lower().replace("ё", "е").replace("+", "")).split()


def cer(ref, hyp):
    a, b = " ".join(norm(ref)), " ".join(norm(hyp))
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)] / max(len(a), 1)


def stress_ok(marked, words, x16):
    """-> (right, checked): marked words whose loudest*longest syllable is the marked one."""
    right = checked = 0
    for tok in re.findall(r"[\w+]+", marked):
        if "+" not in tok:
            continue
        plain = tok.replace("+", "").lower().replace("ё", "е")
        vow = [i for i, c in enumerate(tok.replace("+", "")) if c in VOWELS]
        if len(vow) < 2:
            continue
        target = sum(1 for c in tok[:tok.index("+")] if c in VOWELS)   # index of the stressed vowel
        hit = next((w for w in words if w["word"].replace("ё", "е") == plain), None)
        if not hit:
            continue
        seg = x16[int(hit["start"] * 16000):int(hit["end"] * 16000)]
        if len(seg) < 400:
            continue
        parts = np.array_split(seg, len(vow))
        score = [np.sqrt(np.mean(p ** 2)) * len(p) for p in parts]
        checked += 1
        right += int(np.argmax(score) == target)
    return right, checked


sentences = [s for s in re.split(r"(?<=[.!?])\s+", TEXT) if s]
model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
int8_voice.shrink(model.model.model, int8=CFG.get("int8", False))
best = []
gap = np.zeros(int(0.25 * 24000), dtype=np.float32)
for i, s in enumerate(sentences):
    spoken = mark(s)
    takes = []
    for k in range(N):
        torch.manual_seed(100 * i + k)
        wavs, sr = model.generate_custom_voice(text=spoken, speaker=CFG["speaker"], language="Russian",
                                               temperature=CFG["temperature"], top_k=CFG["top_k"],
                                               max_new_tokens=int(min(2048, 60 + 2.0 * len(spoken))))
        w = np.asarray(wavs[0], dtype=np.float32)
        sf.write(os.path.join(TAKES, f"{i:02d}_{k}.wav"), w, sr)
        text, words, x16 = heard(w, sr)
        sp, jumps = melody(w, sr)
        right, checked = stress_ok(spoken, words, x16)
        takes.append({"k": k, "cer": cer(s, text), "spread": sp, "jumps": jumps, "stress": (right, checked), "w": w})
    ok = [t for t in takes if t["cer"] <= 0.25] or [min(takes, key=lambda t: t["cer"])]
    top = max(t["stress"][0] - t["stress"][1] for t in ok)   # fewest stress misses first
    ok = [t for t in ok if t["stress"][0] - t["stress"][1] == top]
    pick = max(ok, key=lambda t: t["spread"] - 0.6 * t["jumps"])   # wide and smooth
    print(f"{i:2d} take {pick['k']} spread {pick['spread']:.2f} jumps/s {pick['jumps']:.2f} stress {pick['stress']} "
          f"cer {pick['cer']:.2f} | {spoken[:60]}", flush=True)
    best += [pick["w"], gap]
sf.write(os.path.join(OUT, "best2_lively.wav"), np.concatenate(best), 24000)
