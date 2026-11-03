"""Neira's voice: OpenAI-compatible TTS endpoint (POST /v1/audio/speech) for Open-LLM-VTuber.

Our Qwen3-TTS 1.7B taught Russian speech in RefVoice's timbre (D:\\AI\\qwentts\\train_lora.py, a custom-voice
checkpoint): every sentence is spoken in ONE pass, native Russian in her voice by itself. Neira's {tags} become
sounds in the text ("Ха-ха!", "Ох...") or are dropped; numbers become words. Settings: voice_config.json.
Two versions of the voice can share one GPU model: "model" (the best plain speech) and the sounds version (taught real
laughs, sighs...), given as "sounds_lora" (its difference from the main one, voice_lora.py: merged into the weights
in ~0.25 s) or "sounds_model" (its checkpoint; layer weights copied in place, 2.4-3.5 s). A sentence with a sound is
spoken by the sounds version, then the main one comes back for the next plain sentence (CUDA graphs keep working).
Small judges on the CPU check sentences with sounds: Vosk (are the words right?) and laugh_judge.py (does the sound
sound real?); the best of a few takes is spoken.
Usage (fastqwen venv): python neira_voice_server.py [port]
"""
import contextlib
import heapq
import io
import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf
import torch
from faster_qwen3_tts import FasterQwen3TTS
from safetensors import safe_open
from num2words import num2words

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.environ.get("NEIRA_VOICE_CONFIG", os.path.join(HERE, "voice_config.json")), encoding="utf-8"))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
FFMPEG = r"D:\Programs\ffmpeg\bin\ffmpeg.exe"
# Neira's {tag} -> the sound written into the text (None: the tag is just dropped).
# "Эх..." for a sigh makes this voice slip into Polish, "Ох..." doesn't (tools\tag_score.py).
TAGS = {"смех": "Ха-ха!", "хихикает": "Хи-хи.", "вздох": "Ох...", "хмф": "Хмф.", "ах": "Ах!", "хм?": "Хм?", "хм": "Хм?",
        "ворчит": None, "возмущается": None, "смущается": None, "ласково": None, "грустно": None, "радостно": None,
        "задумчиво": None, "строго": None}
ALIASES = {"смеётся": "смех", "смеется": "смех", "хаха": "смех", "смешок": "хихикает", "хихи": "хихикает",
           "вздыхает": "вздох", "фыркает": "хмф", "ой": "ах", "а?": "хм?", "чего?": "хм?", "ругается": "возмущается",
           "смутилась": "смущается", "нежно": "ласково", "грусть": "грустно",
           "устало": "грустно", "весело": "радостно", "восторженно": "радостно", "радуется": "радостно",
           "думает": "задумчиво", "задумалась": "задумчиво", "размышляет": "задумчиво", "серьёзно": "строго",
           "серьезно": "строго", "сдержанно": "строго"}
TAG_RE = re.compile(r"\{([^{}]*)\}")
# Neira's mood tags. "moods": "select" = of a few takes (the voice varies by itself: pitch ±1.9 semitones, tempo ±9%
# between takes of one sentence) speak the one that sounds most like the mood; "marks" = a mark in front of the line
# for a sounds version that learned them (tools\acoustic_moods.py; v13 and v17 did NOT learn them: <1 semitone)
MOODS = {"ласково": "soft", "смущается": "soft", "возмущается": "sharp", "ворчит": "sharp", "грустно": "sad",
         "радостно": "bright", "задумчиво": "thinking", "строго": "strict"}
MOOD_MARKS = {"bright": "😄", "soft": "🥰", "sharp": "😠", "sad": "😢", "thinking": "🤔", "strict": "😐"}
# direction of each mood in (pitch st, pitch spread st, loudness dB, log duration), per typical take-to-take spread
MOOD_SD = np.array([1.9, 0.79, 0.81, 0.085])
MOOD_DIRS = {"bright": np.array([1, 1, 0.5, 0]), "soft": np.array([-0.5, 0, -1, 0.3]),
             "sharp": np.array([0, -0.5, 1, -1]), "sad": np.array([0, -1, -0.5, 1]),
             # RefVoice's own manner (tools\refvoice_moods.py): muted and slower when thinking, flat and firm when serious
             "thinking": np.array([-0.5, -1, -1, 0.5]), "strict": np.array([-0.3, -1, 0.5, -0.3])}
# the sounds version was taught these spellings (tools\laugh_types.py): a snort, a chuckle, a giggle, a laugh whose
# length follows the number of "ха" (~2 a second) and laughing hard ("…")
SOUND_TAGS = {"смешок": "Хе-хе-хе.", "хихикает": "Хи-хи-хи!", "смех": "Ха-ха-ха-ха!",
              "хохот": "Ха" + "-ха" * 11 + "…", "фыркает": "Пф-хе.", "хмф": "Пф-хе.", "вздох": "Ох...", "ах": "Ах!"}
SOUND_ALIASES = {"хохочет": "хохот", "ржёт": "хохот", "заливается": "хохот", "смеётся": "смех", "смеется": "смех",
                 "хаха": "смех", "хихи": "хихикает", "пф": "фыркает", "хмыкает": "смешок"}
LAUGH_RE = re.compile(r"\b(?:[Хх][аеи]|Пф)(?:-[Хх][аеи])+")
LIVELY_RE = re.compile(r"\b[Хх][аеи](?:-[Хх][аеи])+")   # the laughs the small tagger can judge (not the snort)
SOUND_RE = re.compile(LAUGH_RE.pattern + r"|\bОх\.\.\.|\bАх!")
SOUND_WORD = re.compile(r"^(?:пф|хмф|[хк]?[хаеиоуэ]+х?|х?м+)(?:-(?:[хк]?[хаеиоуэ]+х?|м+))*$")   # laughs/sounds, not words (for the judge)
model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
# the talker's text embedding table on the CPU: -594 MiB of VRAM for the brain, same sound bit for bit (int8_voice.py,
# int8_probe.py 28.10). "int8": true also makes the talker layers int8 (-1.9 GB more) but the voice drops to 0.9x real time.
sys.path.insert(0, HERE)
import int8_voice  # noqa: E402
print(f"voice VRAM freed: {int8_voice.shrink(model.model.model, int8=CFG.get('int8', False)):.0f} MiB", flush=True)


REQUESTS, REQUESTS_LOCK = {"served": 0, "inflight": 0}, threading.Lock()


class GpuTurns:
    """One generation on the GPU at a time, and the sentence that came EARLIER goes first (a retake of sentence 1
    before sentence 3): Neira plays them in order, so the earliest one is always the one she is waiting for."""

    def __init__(self):
        self.cv, self.busy, self.waiting = threading.Condition(), False, []

    @contextlib.contextmanager
    def turn(self, seq):
        with self.cv:
            heapq.heappush(self.waiting, seq)
            while self.busy or self.waiting[0] != seq:
                self.cv.wait()
            heapq.heappop(self.waiting)
            self.busy = True
        try:
            yield
        finally:
            with self.cv:
                self.busy = False
                self.cv.notify_all()


class Playback:
    """When will Neira's playback reach a sentence of the current answer? She plays them in order, each as soon as it
    is ready and the one before has ended. A retake that fits in that time is free; one that doesn't makes a pause."""

    def __init__(self):
        self.lock, self.start, self.ready = threading.Lock(), 0, {}   # seq -> (time ready, seconds of audio)

    def new_answer(self, seq):
        with self.lock:
            self.start, self.ready = seq, {}

    def finished(self, seq, seconds):
        with self.lock:
            self.ready[seq] = (time.time(), seconds)

    def needed_at(self, seq):
        with self.lock:
            end = None
            for s in range(self.start, seq):
                if s not in self.ready:
                    return float("inf")   # an earlier sentence is still being made
                t, d = self.ready[s]
                end = t + d if end is None else max(end, t) + d
            return time.time() if end is None else end


gpu, arrivals, playback = GpuTurns(), itertools.count(), Playback()
flight = threading.Condition()   # sentences in progress, and when the last one finished
flight.count, flight.last_done, flight.sounds_used = 0, 0.0, 0


sys.path.insert(0, HERE)
from voice_lora import LoraVoices, MergeVoices  # noqa: E402  (the sounds version as a LoRA of the main one)

# "sounds_lora": merged into the weights for a sentence with a sound and taken out again (~0.25 s, no slowdown,
# the main voice stays bit-exact); "sounds_lora_mode": "toggle" keeps it as extra layers instead (instant, +36% time)
lora_voices = None
if CFG.get("sounds_lora"):
    kind = LoraVoices if CFG.get("sounds_lora_mode") == "toggle" else (int8_voice.Int8MergeVoices if CFG.get("int8") else MergeVoices)
    lora_voices = kind(model.model.model, CFG["sounds_lora"])
model.warmup()   # the CUDA graphs are captured now (a toggle LoRA must already be inside)


class TwoVoices:
    """Switch the GPU model between the main and the sounds version by copying the talker's layer weights in place
    from the checkpoint files (memory-mapped; the OS keeps them cached). Only those weights differ: both versions
    were trained from the main one with LoRA on these layers."""

    def __init__(self, root, main_dir, sounds_dir):
        self.files = {"main": os.path.join(main_dir, "model.safetensors"),
                      "sounds": os.path.join(sounds_dir, "model.safetensors")}
        params = dict(root.named_parameters())
        with safe_open(self.files["sounds"], framework="pt") as f:
            self.params = {n: params[n] for n in f.keys()
                           if n in params and re.search(r"(q|k|v|o|gate|up|down)_proj\.weight$", n)}
        self.active = "main"

    @torch.inference_mode()
    def use(self, which):
        if which == self.active:
            return 0.0
        t0 = time.time()
        with safe_open(self.files[which], framework="pt", device="cpu") as f:
            for n, p in self.params.items():
                p.copy_(f.get_tensor(n))
        torch.cuda.synchronize()
        self.active = which
        return time.time() - t0


voices = lora_voices or (TwoVoices(model.model.model, CFG["model"], CFG["sounds_model"]) if CFG.get("sounds_model") else None)
# "colleague_lora": another main voice as a LoRA on this one (extract_lora.py of the two checkpoints, rank 64; k5 on k7:
# its slips on fresh sentences 7%, the real k5 4%), merged in only to retry a sentence the main voice got wrong.
# Never at the same time as the sounds version: set_voice() takes one back to the main weights before the other.
colleague = (int8_voice.Int8MergeVoices if CFG.get("int8") else MergeVoices)(model.model.model, CFG["colleague_lora"]) if CFG.get("colleague_lora") else None


def set_voice(who):
    """"main", "sounds" or "colleague" -> the seconds spent switching."""
    t = 0.0
    if colleague and who != "colleague" and colleague.active != "main":
        t += colleague.use("main")
    if voices and who != "sounds" and voices.active != "main":
        t += voices.use("main")
    if who == "sounds" and voices:
        t += voices.use("sounds")
    if who == "colleague" and colleague:
        t += colleague.use("sounds")
    return t


class MoodVector:
    """A mood tag moves Neira's voice vector (her speaker's row of the talker's codec embedding) for that sentence:
    speaker + alpha * (mean x-vector of Char2's lines that sound like the mood - mean of the neutral ones; "thinking" and
    "strict" from RefVoice's own Japanese lines vs her average, tools\refvoice_moods.py), as in
    arXiv 2606.05367 (in Qwen3-TTS 1.7B the x-vector carries most of the emotional prosody). Measured on b3 (ft_sweep27):
    bright x1-2 +2.5 st, wider, faster; sharp x2 +2 dB, faster, flatter; soft x2 -2 st, quieter; sad x2 -12% tempo;
    thinking x2 -2.5 dB, -1.9 st, flatter; strict x2 +1.6 dB, flatter, faster (ft_sweep28); her voice kept (WavLM
    0.96-0.97 to her centre) except bright x3. The row is read per call, outside the CUDA graphs."""

    def __init__(self, root, speaker, path, alpha):
        self.emb = root.talker.get_input_embeddings().weight
        self.row = root.config.talker_config.spk_id[speaker.lower()]
        self.base = self.emb[self.row].detach().clone()
        d = np.load(path)
        self.vec = {k: (self.base.float() + a * torch.from_numpy(d[k]).to(self.base.device)).to(self.base.dtype)
                    for k, a in alpha.items() if k in d.files and a}

    @contextlib.contextmanager
    def use(self, mood):
        v = self.vec.get(mood)
        if v is None:
            yield
            return
        with torch.inference_mode():
            self.emb[self.row].copy_(v)
        try:
            yield
        finally:
            with torch.inference_mode():
                self.emb[self.row].copy_(self.base)


# "mood_vector": the mood directions file; "mood_alpha": how far to move for each mood (only with "moods": "select")
# "voice_shift": {"file", "key", "alpha"}: a lasting move of Neira's voice vector, e.g. toward the confirmed RefVoice
# (mean Base x-vector of her lines minus that of the voice's training data, ft_sweep31; the user picked alpha 1 by ear:
# closer to her, +1.5 st, more melodic). It also makes the voice quieter, which even_loudness() takes back out.
if CFG.get("voice_shift"):
    _vs = CFG["voice_shift"]
    _emb = model.model.model.talker.get_input_embeddings().weight
    _row = model.model.model.config.talker_config.spk_id[CFG["speaker"].lower()]
    _d = torch.from_numpy(np.load(os.path.join(HERE, _vs["file"]))[_vs.get("key", "refvoice")]).to(_emb.device)
    with torch.inference_mode():
        _emb[_row].copy_((_emb[_row].float() + _vs.get("alpha", 1.0) * _d).to(_emb.dtype))
    print(f"voice shifted toward {_vs.get('key', 'refvoice')} x{_vs.get('alpha', 1.0)}", flush=True)

mood_vector = (MoodVector(model.model.model, CFG["speaker"], os.path.join(HERE, CFG["mood_vector"]),
                          CFG.get("mood_alpha", {"bright": 1.5, "soft": 2, "sharp": 2, "sad": 2.5, "thinking": 2, "strict": 2}))
               if CFG.get("mood_vector") and CFG.get("moods") == "select" else None)


class Judge:
    """After a laugh the voice sometimes drifts into another language. A small Russian recogniser (Vosk, CPU, a few
    hundred ms) listens to a sentence with a sound and says whether its words came out right; if not, another take."""

    def __init__(self, model_dir):
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        self.model, self.Rec = Model(model_dir), KaldiRecognizer

    def words(self, text):
        ws = re.sub(r"[^а-яё\- ]", " ", text.lower().replace("ё", "е")).split()
        return " ".join(w for w in ws if not SOUND_WORD.match(w.strip("-")))

    def ok(self, wav, sr, text, max_cer=0.35):
        want = self.words(text)
        if not want:
            return True, 0.0
        y = np.asarray(wav, dtype=np.float32)
        if sr != 16000:
            y = np.interp(np.arange(0, len(y), sr / 16000), np.arange(len(y)), y).astype(np.float32)
        rec = self.Rec(self.model, 16000)
        rec.AcceptWaveform((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
        heard = self.words(json.loads(rec.FinalResult()).get("text", ""))
        a, b = want.replace(" ", ""), heard.replace(" ", "")
        # character edit distance of the wanted words to the best-matching stretch of what was heard: what the
        # recogniser makes of a laugh before or after them ("а а а") costs nothing, wrong or missing words do
        d = [0] * (len(b) + 1)
        for i in range(1, len(a) + 1):
            prev, d[0] = d[0], i
            for j in range(1, len(b) + 1):
                prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
        cer = min(d) / max(1, len(a))
        # in a short line one missed little word ("ну") is already 0.2; a real slip garbles far more than 2 letters
        return cer <= max_cer or min(d) <= 2, cer


judge = Judge(CFG["judge_model"]) if CFG.get("judge_model") and voices else None
class VoiceJudge:
    """After a laugh the sounds version sometimes goes on in the voice (and the hissy recording) of the woman whose
    laugh it learned — "не Нейра". A speaker model (WavLM-SV, CPU, ~0.2 s) compares the words after the sound with
    Neira's own voice (the average of her main voice's takes; her takes score >0.92, such slips <0.85)."""

    def __init__(self, centroid_path, model_dir=r"D:\AI\models\wavlm-base-plus-sv"):
        from transformers import AutoFeatureExtractor, WavLMForXVector
        self.fe = AutoFeatureExtractor.from_pretrained(model_dir)
        self.model = WavLMForXVector.from_pretrained(model_dir).eval()
        self.centroid = np.load(centroid_path)

    @torch.inference_mode()
    def same(self, wav, sr, words):
        """Similarity of the take's last part (about as long as the words) to Neira's voice."""
        vowels = len(re.findall(r"[аеёиоуыэюя]", words))
        y = np.asarray(wav, dtype=np.float32)
        y = y[-int(min(len(y) / sr, max(1.0, 0.2 * vowels + 0.3)) * sr):]
        y = np.interp(np.arange(0, len(y), sr / 16000), np.arange(len(y)), y).astype(np.float32)
        e = self.model(**self.fe(y, sampling_rate=16000, return_tensors="pt")).embeddings[0].float().numpy()
        return float(e @ self.centroid / np.linalg.norm(e))


voice_judge = VoiceJudge(CFG["voice_centroid"]) if CFG.get("voice_centroid") and judge else None
# "refvoice_judge": reference npz -> among the takes of a sentence prefer the one closer to the real RefVoice (the model's
# own speaker encoder, CPU, ~17 ms per second of audio; take-to-take SD ~0.003, so it is a fine-tuning of the choice
# and a guard: "refvoice_min" makes a take that drifted to another voice a failed one). "refvoice_tries": takes for a
# plain sentence (each one only if there is time before playback reaches it); "refvoice_weight": its weight next to
# the mood (1 = one take-to-take SD of RefVoice-likeness counts as much as one SD of the mood's sound)
refvoice_judge = None
if CFG.get("refvoice_judge"):
    from refvoice_judge import RefVoiceJudge
    refvoice_judge = RefVoiceJudge(os.path.join(HERE, CFG["refvoice_judge"]))
# "intonation_judge": weights learned from the user's ratings of intonation (intonation_judge.py, CPU ~60 ms per audio
# second): among the takes of a sentence prefer the melody he would call right; "intonation_weight" next to the mood
# and the RefVoice judge (1 = one usual take-to-take difference); "intonation_tries": takes for a plain sentence
intonation_judge = None
if CFG.get("intonation_judge"):
    from intonation_judge import IntonationJudge
    intonation_judge = IntonationJudge(os.path.join(HERE, CFG["intonation_judge"]))
# how real a sentence's laugh/sigh sounds: a small AudioSet tagger on the CPU (laugh_judge.py, ~20 ms per take)
laugh_judge = None
if CFG.get("laugh_judge") and judge:
    from laugh_judge import LaughJudge  # noqa: E402
    laugh_judge = LaughJudge()


LOG = os.path.join(HERE, "voice.log")   # every sentence: which version spoke, judge decisions, timings


def log(msg):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # -I ignores PYTHONIOENCODING
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# Words the voice says wrong only in one spelling, measured (intonation\pron, Whisper, 8 takes each): "Ошибка" with a
# capital О -> "ахука", "а куба" (0/8 right), "ошибка" 8/8. Same sound, safer spelling. Stress marks / "+" don't work.
PRON_FIXES = {r"\bОшибк": "ошибк"}


def pron_fixes(text):
    # the brain sometimes writes a spaced ellipsis ("но. . . он", "и.. . она", "? »"): one plain "..." instead
    text = re.sub(r"\.(?:\s*\.){2,}", "...", text)
    if not CFG.get("normal_mode"):   # normal mode keeps "…" like Mercury's "normal" series (29.10)
        text = text.replace("…", "...")   # the voice learned "..." (texts by Whisper)
    text = re.sub(r"\s+([?!.,»])", r"\1", text)
    for pat, rep in {**PRON_FIXES, **CFG.get("pron_fixes", {})}.items():
        text = re.sub(pat, rep, text)
    return text


def numbers_to_words(text):
    def repl(m):
        s = m.group(0).replace(",", ".")
        return num2words(float(s) if "." in s else int(s), lang="ru")
    return re.sub(r"\d+(?:[.,]\d+)?", repl, text)


def calm_laughs(text):
    """The voice says "Ха-ха!" and "Хи-хи." well, but on "Ха-ха-ха" or "Хе-хе" it often slips into another language
    (measured, 8 takes each): long laughs become "Ха-ха", "хе-хе" becomes "хи-хи"."""
    text = re.sub(r"\b([Хх])а(?:-[Хх]а){2,}", r"\1а-ха", text)
    return re.sub(r"\b([Хх])е-[Хх]е(?:-[Хх]е)*", r"\1и-хи", text)


def prepare(text, allow_sounds=True):
    """Neira's text with {tags} -> (the text to speak, whether the sounds version should say it, the mood to choose
    the take by or None). allow_sounds=False drops sound tags (the answer already had its sound), moods stay."""
    sounds, mood = False, None

    def repl(m):
        nonlocal sounds, mood
        tag = m.group(1).strip().lower().rstrip("?!.").strip()
        if voices:   # the sounds version's own tags first, then their aliases
            t = tag if tag in SOUND_TAGS else SOUND_ALIASES.get(tag, tag)
            if t in SOUND_TAGS:
                if not allow_sounds:
                    return " "
                sounds = True
                return f" {SOUND_TAGS[t]} "
        if CFG.get("moods") and ALIASES.get(tag, tag) in MOODS:
            mood = mood or MOODS[ALIASES.get(tag, tag)]
            return " "
        sound = TAGS.get(ALIASES.get(tag, tag)) or TAGS.get(ALIASES.get(tag + "?", tag + "?"))
        if sound and not allow_sounds:
            return " "
        return f" {sound} " if sound else " "

    # Open-LLM-VTuber cuts sentences at "?"/"!", sometimes inside a tag ("{хм?" + "} Сосиска?"): a tag left open at the
    # end is still a tag, a stray "}" at the start is dropped
    text = re.sub(r"\{([^{}]*)$", r"{\1}", text.strip())
    text = re.sub(r"^\s*\}", " ", text)
    text = re.sub(r"\s+", " ", numbers_to_words(TAG_RE.sub(repl, text)).replace("*", " ").replace("{", " ").replace("}", " ")).strip()
    text = pron_fixes(text)
    sounds = sounds or bool(voices and SOUND_RE.search(text))   # a laugh written by Neira herself
    if sounds:
        return text, True, None   # a laugh says enough (and marks were taught on lines without laughs only)
    if mood and CFG.get("moods") == "marks" and voices and re.search(r"\w", text):
        return f"{MOOD_MARKS[mood]} {text}", True, None   # a sounds version that learned the marks
    return (text if CFG.get("normal_mode") else calm_laughs(text)), False, (mood if CFG.get("moods") == "select" else None)


def synthesize(text):
    """Text -> (wav, sr), or None when there is nothing to say (only tags or punctuation)."""
    t0 = time.time()
    with flight:
        # nothing else in progress and the last sentence finished a while ago: this one starts Neira's answer and
        # the listener is waiting for it, so it gets at most 2 takes; later ones are spoken while she talks
        first = flight.count == 0 and t0 - flight.last_done > 2.0
        if first:
            flight.sounds_used = 0
        # at most "max_sounds_per_answer" sounds (default 1) in one answer: the brain sprinkled sighs into stories
        spoken, sounds, mood = prepare(text, flight.sounds_used < CFG.get("max_sounds_per_answer", 1))
        if not re.search(r"\w", spoken):
            return None
        flight.sounds_used += bool(sounds)
        seq = next(arrivals)
        flight.count += 1
        if first:
            playback.new_answer(seq)
    if CFG.get("stress_service"):   # "+" before the stressed vowel of doubtful words (the voice k7 learned them)
        spoken = stress_marks(spoken)
    spoken = stress_fix(spoken)
    limit = int(min(2048, 60 + 2.0 * len(spoken)))  # ~12 codec frames per second, runaway guard
    try:
        wav, sr = _synthesize(spoken, sounds, limit, t0, seq, first, mood)
        playback.finished(seq, len(wav) / sr)
        if CFG.get("save_dir"):   # a log of what Neira really said, to mark wrong intonation / sounds later by ear
            _journal(text, spoken, sounds, mood, wav, sr)
        return wav, sr
    finally:
        with flight:
            flight.count -= 1
            flight.last_done = time.time()


_journal_lock = threading.Lock()


_stress_warned = [False]


# words the author heard stressed wrong and the stress service leaves unmarked (it marks only doubtful words):
# stress_fix.json {"шучу": "шуч+у"}, read at every sentence - add a word, no restart (29.10)
STRESS_FIX = os.path.join(HERE, "stress_fix.json")


def stress_fix(text):
    try:
        fix = json.load(open(STRESS_FIX, encoding="utf-8"))
    except Exception:
        return text
    for word, marked in fix.items():
        text = re.sub(r"(?<![\w+])" + re.escape(word) + r"(?!\w)",
                      lambda m: marked if m.group(0).islower() else marked[0].upper() + marked[1:], text, flags=re.I)
    return text


def stress_marks(text):
    """RUAccent's selective stress marks from the local stress service (D:\\AI\\ruaccent\\stress_service.py, ~0.1 s);
    if it is not running or slow, the text goes unmarked (the voice still speaks, as k5 did)."""
    import urllib.request
    try:
        req = urllib.request.Request(CFG["stress_service"], data=json.dumps({"text": text}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=CFG.get("stress_timeout", 1.5)).read().decode("utf-8"))["text"]
    except Exception as e:
        if not _stress_warned[0]:
            log(f"stress service unavailable ({e!r}): speaking without stress marks")
            _stress_warned[0] = True
        return text


def _journal(text, spoken, sounds, mood, wav, sr):
    """<save_dir>/<day>/<time>_<n>.wav + journal.jsonl (Neira's text with tags, what was spoken, sounds version, mood)."""
    try:
        day = time.strftime("%Y-%m-%d")
        d = os.path.join(CFG["save_dir"], day)
        os.makedirs(d, exist_ok=True)
        with _journal_lock:
            name = time.strftime("%H%M%S") + f"_{len(os.listdir(d)):04d}.wav"
            sf.write(os.path.join(d, name), wav, sr)
            with open(os.path.join(d, "journal.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"audio": name, "text": text, "spoken": spoken, "sounds": bool(sounds), "mood": mood},
                                   ensure_ascii=False) + "\n")
    except Exception as e:   # the log must never cost Neira her voice
        log(f"journal: {e}")


def mood_features(wav, sr):
    """(median pitch st, pitch spread st, loudness dB, log duration) of a take — cheap (librosa yin, ~20 ms on the CPU)."""
    import librosa
    y = np.asarray(wav, dtype=np.float32)
    y = np.interp(np.arange(0, len(y), sr / 16000), np.arange(len(y)), y).astype(np.float32)
    y, _ = librosa.effects.trim(y, top_db=35)
    if len(y) < 3200:
        return None
    f0 = librosa.yin(y, fmin=80, fmax=900, sr=16000, frame_length=1024, hop_length=320)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=320)[0]
    n = min(len(f0), len(rms))
    f0, rms = f0[:n], rms[:n]
    f = f0[rms > rms.max() * 0.15]
    med = float(np.median(f))
    return np.array([12 * np.log2(med), float(np.std(12 * np.log2(f / med))),
                     20 * np.log10(float(np.sqrt(np.mean(rms[rms > rms.max() * 0.15] ** 2))) + 1e-9),
                     np.log(len(y) / 16000)])


def _synthesize(spoken, sounds, limit, t0, seq, first, mood=None):
    # the main voice was trained on the "Auto" layout, the sounds version with the Russian language token
    language = CFG.get("sounds_language", "Russian") if sounds else CFG.get("language", "Auto")
    if sounds and judge:
        tries, max_cer = CFG.get("judge_tries", 3), CFG.get("judge_max_cer", 0.25)
    elif judge and CFG.get("judge_plain"):   # plain sentences: catch the rare slip into another language
        tries, max_cer = CFG.get("judge_plain_tries", 2), CFG.get("judge_plain_max_cer", 0.25)
    else:
        tries, max_cer = 1, None
    if mood and not first:   # takes to choose the mood from (each one only if there is time, see _takes)
        tries = max(tries, CFG.get("mood_tries", 3))
    if refvoice_judge and not first and not sounds:   # takes to choose the most RefVoice-like from (same rule)
        tries = max(tries, CFG.get("refvoice_tries", 2))
    if intonation_judge and not first and not sounds:   # takes to choose the right melody from (same rule)
        tries = max(tries, CFG.get("intonation_tries", 2))
    if first:
        tries = min(tries, CFG.get("first_tries", 2))
    # only "ха/хе/хи" laughs are measured against real ones (the tagger hears a snort "Пф-хе", a sigh or "Ах!" as
    # something else even in real recordings), and a laugh gets at most one retake for liveliness
    realness = laugh_judge if (sounds and laugh_judge and LIVELY_RE.search(spoken)) else None
    # the sentence the listener is waiting for keeps the GPU while it is judged (a retake starts at once instead of
    # after the next sentence); later ones let the next sentence use the GPU meanwhile
    laugh_min = CFG.get("laugh_min_first", 0.3) if first else CFG.get("laugh_min", 0.6)
    hold = gpu.turn(seq) if first else contextlib.nullcontext()
    with hold:
        return _takes(spoken, sounds, limit, t0, seq, first, language, tries, max_cer, realness, laugh_min, mood)


def _takes(spoken, sounds, limit, t0, seq, first, language, tries, max_cer, realness, laugh_min, mood=None):
    # (rank, wav, sr): words right first, then the more real laugh, then the take most like the mood; the best is spoken
    plain = spoken.replace("+", "")   # the judges compare words, without the stress marks
    best = None
    # "help from a colleague" (the user's idea): when every take of the main voice failed the word judge, the other
    # voice (k5, merged in as a LoRA, unmarked text) tries the same sentence once and the judges pick among all takes
    plan, attempt = ["own"] * tries, -1
    while attempt + 1 < len(plan):
        attempt += 1
        who = "colleague" if plan[attempt] == "colleague" else ("sounds" if sounds else "main")
        with (contextlib.nullcontext() if first else gpu.turn(seq)):  # plain text only (trained without instructions)
            switch = set_voice(who)
            if switch:
                log(f"voice -> {who} in {switch:.1f}s")
            with (mood_vector.use(mood) if mood_vector else contextlib.nullcontext()):
                wavs, sr = model.generate_custom_voice(text=plain if who == "colleague" else spoken, speaker=CFG["speaker"],
                                                       language=language, max_new_tokens=limit,
                                                       temperature=CFG.get("temperature", 0.9), top_k=CFG.get("top_k", 50))
        wav = np.asarray(wavs[0], dtype=np.float32)
        if tries == 1:
            best = (None, wav, sr)
            break
        # the judges run on the CPU outside the GPU turn (but the first sentence's): the GPU speaks the next sentence
        good, cer = judge.ok(wav, sr, plain, max_cer) if (judge and max_cer is not None) else (True, 0.0)
        # words after a sound: still Neira's voice? (a take in another woman's voice is a failed take, like wrong words)
        words = judge.words(plain) if (sounds and voice_judge) else ""
        same = voice_judge.same(wav, sr, words) if words else None
        if same is not None and same < CFG.get("voice_min", 0.85):
            good = False
        real = realness.score(wav, sr) / CFG.get("laugh_real", 1.0) if realness else None
        # a laugh unlike a real one: one more take, if it can be made before playback reaches this sentence
        # (~0.5 s per second of audio + the judges + a generation that may be running); a clearly flat laugh in the
        # first sentence is redone anyway
        lively = real is None or real >= laugh_min or attempt + 1 >= CFG.get("laugh_tries", 2)
        if not lively and not first:
            slack = playback.needed_at(seq) - time.time()
            lively = slack < 0.55 * len(wav) / sr + 2.0
            if lively:
                log(f"judge: no time for a livelier take ({slack:.1f}s before playback)")
        feats = mood_features(wav, sr) if mood else None
        mood_score = float((feats / MOOD_SD) @ MOOD_DIRS[mood]) if feats is not None else 0.0
        kur = refvoice_judge.score(wav, sr) if refvoice_judge else None
        if kur is not None and kur < CFG.get("refvoice_min", 0.0):
            good = False
        inton = intonation_judge.score(wav, sr, plain) if (intonation_judge and not sounds) else None
        style = (mood_score + (CFG.get("refvoice_weight", 1.0) * kur / 0.003 if kur is not None else 0.0)
                 + (CFG.get("intonation_weight", 1.0) * inton if inton is not None else 0.0))
        rank = (good, same if same is not None else 1.0, min(real, 1.0) if real is not None else 0.0, style, -cer)
        if best is None or rank > best[0]:
            best = (rank, wav, sr)
        # a mood (or the RefVoice judge): another take to choose from while there is time before playback reaches it
        more = False
        if (mood or ((refvoice_judge or intonation_judge) and not sounds)) and good and attempt + 1 < len(plan):
            slack = playback.needed_at(seq) - time.time()
            more = slack >= 0.55 * len(wav) / sr + 2.0
        log(f"judge: take {attempt + 1}{' (colleague)' if who == 'colleague' else ''} "
            f"{'ok' if good and lively else 'retry'} (words off by {cer:.2f}"
            + (f", Neira's voice {same:.2f}" if same is not None else "")
            + (f", sound {real:.0%} of real" if real is not None else "")
            + (f", RefVoice {kur:.3f}" if kur is not None else "")
            + (f", intonation {inton:+.2f}" if inton is not None else "")
            + (f", {mood}: pitch {2 ** (feats[0] / 12):.0f} Hz ±{feats[1]:.1f} st, {feats[2]:.1f} dB, "
               f"{np.exp(feats[3]):.1f}s" if feats is not None else "") + ")")
        if good and lively and not more:
            break
        if (attempt + 1 == len(plan) and colleague and not sounds and "colleague" not in plan
                and not best[0][0]):   # all own takes got the words wrong: ask the colleague
            plan.append("colleague")
    _, wav, sr = best
    if sounds and CFG.get("denoise_sounds"):   # a hiss bed some laughs bring along (left alone if the pauses are clean)
        from denoise_bed import clean
        wav, bed = clean(wav, sr)
        if bed:
            log(f"hiss bed {bed:.0f} dB below the loudest: lowered")
    log(f"{len(wav) / sr:4.1f}s in {time.time() - t0:4.1f}s{' (first)' if first else ''} | {spoken[:80]}")
    return wav, sr


def even_loudness(wav, sr, target_db=-20.0):
    """Same speech loudness for every sentence (RMS of the voiced part, peak-safe)."""
    frame = int(sr * 0.02)
    frames = wav[: len(wav) // frame * frame].reshape(-1, frame) if len(wav) >= frame else wav[None]
    rms = np.sqrt((frames ** 2).mean(axis=1))
    voiced = rms[rms > rms.max() * 0.1] if rms.max() > 0 else rms
    level = float(np.sqrt((voiced ** 2).mean())) if len(voiced) else 0.0
    if level <= 1e-5:
        return wav
    gain = min(10 ** (target_db / 20) / level, 0.97 / (np.abs(wav).max() + 1e-9))
    return wav * gain


# Pauses after a sentence by how it ends (the takes end with a random 0-0.3 s of silence; Open-LLM-VTuber plays the
# sentences back to back, so a story sounded hurried). CFG "sentence_pauses": {end: seconds} overrides, false = off.
PAUSES = {"...": 0.65, "…": 0.65, "?": 0.45, "!": 0.35, ".": 0.4, ",": 0.15, ":": 0.3, "—": 0.25, "": 0.3}


def with_pause(wav, sr, text):
    pauses = CFG.get("sentence_pauses", PAUSES)
    if not pauses:
        return wav
    frame = int(sr * 0.02)
    n = len(wav) // frame
    if n < 3:
        return wav
    rms = np.sqrt((wav[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
    loud = np.where(rms > rms.max() * 10 ** (-40 / 20))[0]
    end = min(len(wav), (loud[-1] + 1) * frame + int(0.05 * sr)) if len(loud) else len(wav)
    t = re.sub(r"[\s»\"')\]}]+$", "", TAG_RE.sub("", text))
    key = next((k for k in ("...", "…", "?", "!", ".", ",", ":", "—") if t.endswith(k)), "")
    return np.concatenate([wav[:end], np.zeros(int(pauses.get(key, pauses.get("", 0.3)) * sr), dtype=wav.dtype)])


def wav_bytes(wav, sr):
    buf = io.BytesIO()
    # loudness_db: the level every sentence is brought to (-20 before 29.10: 5-7 dB below the bare model; null = as
    # generated, only peak-safe)
    db = CFG.get("loudness_db", -20.0)
    out = even_loudness(wav, sr, db) if db is not None else wav * min(1.0, 0.97 / (np.abs(wav).max() + 1e-9))
    sf.write(buf, out, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.endswith("/state"):   # "<served> <in flight>": Neira waits for her last sentence before /quit
            body = f"{REQUESTS['served']} {REQUESTS['inflight']}".encode()
        elif self.path.endswith("/health"):
            body = b"ok"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.rstrip("/").endswith(("/park", "/unpark")):
            # Neira lends the GPU to the brain for a hard task (voice_swap.py): the weights wait in RAM (park.py)
            t0 = time.time()
            while REQUESTS["inflight"] and time.time() - t0 < 60:
                time.sleep(0.1)
            with REQUESTS_LOCK:
                if self.path.rstrip("/").endswith("/park") and REQUESTS["inflight"]:
                    msg = "busy: not parked"
                elif self.path.rstrip("/").endswith("/park"):
                    set_voice("main")   # the parked copy is the main voice
                    sec, mib = PARKING.park()
                    msg = f"parked in {sec:.2f} s, {mib:.0f} MiB freed"
                else:
                    msg = f"back in {PARKING.unpark():.2f} s"
            log(msg)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(msg.encode())
            return
        if self.path.rstrip("/").endswith("/quit"):
            # Neira frees the GPU for a hard task (voice_swap.py): leave once nothing is being spoken; start-voice.bat
            # brings the voice back (~15 s)
            t0 = time.time()
            while REQUESTS["inflight"] and time.time() - t0 < 60:
                time.sleep(0.1)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"bye")
            self.wfile.flush()
            log("quit: the GPU goes to the brain")
            os._exit(0)
        if not self.path.rstrip("/").endswith("/audio/speech"):
            self.send_response(404)
            self.end_headers()
            return
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        log(f"request: {req.get('input', '')[:90]!r}")
        canned = PHRASES.get(req.get("input", "").strip())
        if canned and os.path.exists(canned):   # a ready phrase (Neira's "I need to think"): instant, even parked
            with REQUESTS_LOCK:
                REQUESTS["inflight"] += 1
            audio = open(canned, "rb").read()
            log(f"canned: {req.get('input', '')[:60]!r}")
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
            self._done()
            return
        with REQUESTS_LOCK:
            REQUESTS["inflight"] += 1
            if PARKING.parked:   # never speak from an empty model: a sentence brings the voice back itself
                log(f"unparked by a sentence in {PARKING.unpark():.2f} s")
        try:
            speech = synthesize(req.get("input", ""))
            # nothing to say: a short silence
            audio = (wav_bytes(with_pause(speech[0], speech[1], req.get("input", "")), speech[1]) if speech
                     else wav_bytes(np.zeros(2400, dtype=np.float32), 24000))
        except Exception as e:  # never leave Neira hanging: answer with an error she can log
            log(f"error: {e!r}")
            self._done()
            self.send_response(500)
            self.end_headers()
            return
        if req.get("response_format", "wav") == "mp3":
            audio = subprocess.run([FFMPEG, "-v", "error", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
                                   input=audio, capture_output=True).stdout
            ctype = "audio/mpeg"
        else:
            ctype = "audio/wav"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)
        self._done()

    @staticmethod
    def _done():
        with REQUESTS_LOCK:
            REQUESTS["inflight"] -= 1
            REQUESTS["served"] += 1


from park import Parking  # noqa: E402
PARKING = Parking(model)

# Ready phrases (28.10): the sentences of Neira's "I need to think" warnings (neira-tools/voice_swap.py, as the
# sentence divider cuts them) are spoken once and kept as files: a hard turn must not wait for the GPU to say them.
PHRASES_DIR = os.path.join(HERE, "phrases")
PHRASES = {}
for _i, _text in enumerate(json.load(open(os.path.join(HERE, "phrases.json"), encoding="utf-8"))
                           if os.path.exists(os.path.join(HERE, "phrases.json")) else []):
    PHRASES[_text] = os.path.join(PHRASES_DIR, f"{_i:02d}.wav")


if __name__ == "__main__":
    _beep = np.sin(np.arange(24000) * 2 * np.pi * 300 / 24000).astype(np.float32) * 0.3
    if CFG.get("moods") == "select":   # the pitch tracker's first call compiles (~4 s): not on a real sentence
        mood_features(_beep, 24000)
    if intonation_judge:   # pyin's first call compiles (numba) for seconds: not during a conversation
        intonation_judge.score(_beep, 24000, "Проверка связи.")
    _save = CFG.pop("save_dir", None)   # the warm-up sentence is not part of the journal
    synthesize("Проверка связи.")  # the first generation is slower: do it now, not on Neira's first sentence
    os.makedirs(PHRASES_DIR, exist_ok=True)
    for _text, _path in PHRASES.items():   # first start only: then they are files
        if not os.path.exists(_path):
            _sp = synthesize(_text)
            if _sp:
                with open(_path, "wb") as _f:
                    _f.write(wav_bytes(with_pause(_sp[0], _sp[1], _text), _sp[1]))
                log(f"ready phrase: {_text}")
    # loading leaves ~4.8 GB of RAM the voice never touches again (the model passes through RAM on its way to the
    # GPU); while it stays resident Windows pages the BRAIN's experts out instead (its reading fell ~10x). Give those
    # pages back: what the voice uses comes back on its own, the pinned buffers cannot leave anyway.
    import ctypes
    _k = ctypes.windll.kernel32
    _k.SetProcessWorkingSetSize(_k.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    import psutil
    log(f"RAM: resident {psutil.Process().memory_info().rss / 2 ** 30:.1f} GB after trimming")
    if _save:
        CFG["save_dir"] = _save
    log(f"Neira voice on 127.0.0.1:{PORT} ({CFG['model']})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
