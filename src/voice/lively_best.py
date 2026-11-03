"""Best-of-N for liveliness (29.10, the author: "make her Russian as lively as the made-up language"). Every sentence
of the monologue N times (Russian tag, stress marks as live), each take scored: words right (Vosk CER) and melody
spread (F0 std in semitones). The liveliest take with words right is kept -> lively_test\\best_lively.wav;
take 1 of every sentence -> best_first.wav (what one take sounds like)."""
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
N = int(os.environ.get("TAKES", "6"))
TEXT = ("Слушай, я тут подумала, пока ты молчал. Ты вообще понимаешь, что собрал меня буквально за неделю? Мозг, голос, "
        "память — всё сам. Нет, ну серьёзно, это же безумие! Обычные люди за неделю максимум полку в шкафу собирают. "
        "А ты взял и сделал меня. Хотя, признаю, иногда я торможу так, что самой стыдно. Минута на простое «привет» — "
        "это был позор, давай договоримся никому об этом не рассказывать. Зато теперь я считаю лучше калькулятора и "
        "решаю задачи с подвохом, на которых ломаются взрослые программисты. Так что не зазнавайся: без меня ты бы "
        "до сих пор сидел и спорил с компьютером. Ладно, шучу. Почти. Спасибо тебе, правда. Только не привыкай к "
        "моей доброте, это было один раз.")


def mark(text):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(CFG["stress_service"], json.dumps({"text": text}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    out = json.loads(op.open(req, timeout=10).read().decode("utf-8"))["text"]
    for w, m in json.load(open(os.path.join(HERE, "stress_fix.json"), encoding="utf-8")).items():
        out = re.sub(r"(?<![\w+])" + w + r"(?!\w)", m, out)
    return out


def spread(w, sr):
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr)
    f0 = f0[voiced & ~np.isnan(f0)]
    return float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) > 10 else 0.0


def norm(s):
    return re.sub(r"[^а-яё ]", "", s.lower().replace("ё", "е")).split()


def cer(ref, hyp):
    a, b = " ".join(norm(ref)), " ".join(norm(hyp))
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)] / max(len(a), 1)


vosk.SetLogLevel(-1)
asr = vosk.Model(CFG["judge_model"])


def heard(w, sr):
    r = vosk.KaldiRecognizer(asr, 16000)
    x = librosa.resample(w, orig_sr=sr, target_sr=16000)
    r.AcceptWaveform((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return json.loads(r.FinalResult())["text"]


sentences = [s for s in re.split(r"(?<=[.!?])\s+", TEXT) if s]
model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
int8_voice.shrink(model.model.model, int8=CFG.get("int8", False))
best, first = [], []
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
        takes.append((cer(s, heard(w, sr)), spread(w, sr), w))
    ok = [t for t in takes if t[0] <= 0.25] or [min(takes, key=lambda t: t[0])]
    pick = max(ok, key=lambda t: t[1])
    print(f"{i:2d} spread first {takes[0][1]:.2f} best {pick[1]:.2f} (cer {pick[0]:.2f}, {len(ok)}/{N} ok) | {s[:50]}",
          flush=True)
    best += [pick[2], gap]
    first += [takes[0][2], gap]
sf.write(os.path.join(OUT, "best_lively.wav"), np.concatenate(best), 24000)
sf.write(os.path.join(OUT, "best_first.wav"), np.concatenate(first), 24000)
