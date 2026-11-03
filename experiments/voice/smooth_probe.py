"""What makes her real-text melody jumpy (29.10, the author: "smoothness is the whole point")? The monologue sentence
by sentence, direct model (as нейробред), 2 seeds per variant: stress marks on/off x temperature 0.9/0.7.
Measured: pitch jumps > 1.2 semitones per second of voice (нейробред: 3.1; real text so far: 4.6-5.5)."""
import json
import os
import re
import urllib.request

import librosa
import numpy as np
import soundfile as sf
import torch
from faster_qwen3_tts import FasterQwen3TTS

import int8_voice

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
OUT = r"D:\AI\voices\lively_test\smooth"
os.makedirs(OUT, exist_ok=True)
TEXT = ("Слушай, я тут подумала, пока ты молчал. Ты вообще понимаешь, что собрал меня буквально за неделю? Мозг, голос, "
        "память — всё сам. Нет, ну серьёзно, это же безумие! Обычные люди за неделю максимум полку в шкафу собирают. "
        "А ты взял и сделал меня. Хотя, признаю, иногда я торможу так, что самой стыдно. Минута на простое «привет» — "
        "это был позор, давай договоримся никому об этом не рассказывать. Зато теперь я считаю лучше калькулятора и "
        "решаю задачи с подвохом, на которых ломаются взрослые программисты. Так что не зазнавайся: без меня ты бы "
        "до сих пор сидел и спорил с компьютером. Ладно, шучу. Почти. Спасибо тебе, правда. Только не привыкай к "
        "моей доброте, это было один раз.")
sentences = [s for s in re.split(r"(?<=[.!?])\s+", TEXT) if s]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def mark(text):
    req = urllib.request.Request(CFG["stress_service"], json.dumps({"text": text}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    return json.loads(op.open(req, timeout=10).read().decode("utf-8"))["text"]


def jumps(w, sr):
    hop = 256
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr, frame_length=1024, hop_length=hop)
    st = 12 * np.log2(np.where(voiced, f0, np.nan) / np.nanmedian(f0))
    d = np.abs(np.diff(st))
    both = ~np.isnan(st[1:]) & ~np.isnan(st[:-1])
    n_voiced = (~np.isnan(st)).sum()
    return (d[both] > 1.2).sum() / (n_voiced * hop / sr), float(np.nanstd(st)), float(np.nanmedian(f0))


marked = [mark(s) for s in sentences]
model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
int8_voice.shrink(model.model.model, int8=CFG.get("int8", False))
for tag, texts, temp in (("marks_t09", marked, 0.9), ("plain_t09", sentences, 0.9),
                         ("marks_t07", marked, 0.7), ("plain_t07", sentences, 0.7)):
    res = []
    for seed in (1, 2):
        parts = []
        for i, s in enumerate(texts):
            torch.manual_seed(1000 * seed + i)
            wavs, sr = model.generate_custom_voice(text=s, speaker=CFG["speaker"], language="Russian",
                                                   temperature=temp, top_k=CFG["top_k"],
                                                   max_new_tokens=int(min(2048, 60 + 2.0 * len(s))))
            parts += [np.asarray(wavs[0], dtype=np.float32), np.zeros(int(0.25 * sr), dtype=np.float32)]
        w = np.concatenate(parts)
        sf.write(os.path.join(OUT, f"{tag}_{seed}.wav"), w, sr)
        res.append(jumps(w, sr))
    j, sp, hz = np.mean(res, 0)
    print(f"{tag}: jumps/s {j:.2f} ({res[0][0]:.2f}, {res[1][0]:.2f}), spread {sp:.2f} st, pitch {hz:.0f} Hz", flush=True)
