"""Smoothest take (29.10, the author: "smoothness is the whole point"): the monologue sentence by sentence with only the
stress dictionary (stress_fix.json + the words the author heard), no RUAccent marks (they add jumps: 4.8 vs 4.3/s);
N takes, words checked by Vosk, the take with the fewest pitch jumps wins.
-> lively_test\\smooth_best.wav and smooth_one.wav (take 1 of each, for comparison)."""
import json
import os
import re

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
N = int(os.environ.get("TAKES", "4"))
TEXT = ("Слушай, я тут подумала, пока ты молчал. Ты вообще понимаешь, что собрал меня буквально за неделю? Мозг, голос, "
        "память — всё сам. Нет, ну серьёзно, это же безумие! Обычные люди за неделю максимум полку в шкафу собирают. "
        "А ты взял и сделал меня. Хотя, признаю, иногда я торможу так, что самой стыдно. Минута на простое «привет» — "
        "это был позор, давай договоримся никому об этом не рассказывать. Зато теперь я считаю лучше калькулятора и "
        "решаю задачи с подвохом, на которых ломаются взрослые программисты. Так что не зазнавайся: без меня ты бы "
        "до сих пор сидел и спорил с компьютером. Ладно, шучу. Почти. Спасибо тебе, правда. Только не привыкай к "
        "моей доброте, это было один раз.")
FIX = json.load(open(os.path.join(HERE, "stress_fix.json"), encoding="utf-8"))
FIX.update({"шкафу": "шкаф+у", "привыкай": "привык+ай"})


def fix(text):
    for w, m in FIX.items():
        text = re.sub(r"(?<![\w+])" + w + r"(?!\w)", lambda x: m if x.group(0).islower() else m[0].upper() + m[1:],
                      text, flags=re.I)
    return text


def jumps(w, sr):
    hop = 256
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr, frame_length=1024, hop_length=hop)
    st = 12 * np.log2(np.where(voiced, f0, np.nan) / np.nanmedian(f0))
    d = np.abs(np.diff(st))
    both = ~np.isnan(st[1:]) & ~np.isnan(st[:-1])
    n = (~np.isnan(st)).sum()
    return (d[both] > 1.2).sum() / max(n * hop / sr, 0.1)


vosk.SetLogLevel(-1)
asr = vosk.Model(CFG["judge_model"])


def cer(ref, w, sr):
    r = vosk.KaldiRecognizer(asr, 16000)
    x = librosa.resample(w, orig_sr=sr, target_sr=16000)
    r.AcceptWaveform((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    hyp = json.loads(r.FinalResult())["text"]
    a = " ".join(re.sub(r"[^а-яё ]", "", ref.lower().replace("ё", "е")).split())
    b = " ".join(re.sub(r"[^а-яё ]", "", hyp.lower().replace("ё", "е")).split())
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)] / max(len(a), 1)


sentences = [s for s in re.split(r"(?<=[.!?])\s+", TEXT) if s]
model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
int8_voice.shrink(model.model.model, int8=CFG.get("int8", False))
best, one = [], []
gap = np.zeros(int(0.25 * 24000), dtype=np.float32)
for i, s in enumerate(sentences):
    spoken = fix(s)
    takes = []
    for k in range(N):
        torch.manual_seed(500 * i + k)
        wavs, sr = model.generate_custom_voice(text=spoken, speaker=CFG["speaker"], language="Russian",
                                               temperature=CFG["temperature"], top_k=CFG["top_k"],
                                               max_new_tokens=int(min(2048, 60 + 2.0 * len(spoken))))
        w = np.asarray(wavs[0], dtype=np.float32)
        takes.append((cer(s, w, sr), jumps(w, sr), w))
    ok = [t for t in takes if t[0] <= 0.25] or [min(takes, key=lambda t: t[0])]
    pick = min(ok, key=lambda t: t[1])
    print(f"{i:2d} jumps/s take1 {takes[0][1]:.2f} -> best {pick[1]:.2f} (cer {pick[0]:.2f}) | {spoken[:50]}", flush=True)
    best += [pick[2], gap]
    one += [takes[0][2], gap]
sf.write(os.path.join(OUT, "smooth_best.wav"), np.concatenate(best), 24000)
sf.write(os.path.join(OUT, "smooth_one.wav"), np.concatenate(one), 24000)
