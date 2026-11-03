"""Can Neira speak Russian as lively as her English (29.10, the author)? Same Russian sentences under different
language tags and a style instruction; liveliness = spread of the melody (F0 std in semitones, pyin), as in the
voice journal. Wavs to D:\\AI\\voices\\lively_test\\<mode>_<n>.wav"""
import json
import os

import librosa
import numpy as np
import soundfile as sf
import torch
from faster_qwen3_tts import FasterQwen3TTS

import int8_voice

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
OUT = r"D:\AI\voices\lively_test"
os.makedirs(OUT, exist_ok=True)
TEXTS = ["Ну наконец-то! Я уже думала, ты про меня совсем забыл.",
         "Подожди, ты серьёзно? Ты правда собрал меня за три дня?",
         "Ладно, признаю, это было довольно забавно.",
         "Знаешь, иногда мне кажется, что я понимаю тебя лучше, чем ты сам."]
MODES = [("russian", "Russian", None), ("auto", "Auto", None), ("english", "English", None),
         ("instruct", "Russian", "Говори очень живо и выразительно, с яркими эмоциями и выразительной интонацией.")]


def f0_spread(w, sr):
    f0, voiced, _ = librosa.pyin(w, fmin=80, fmax=600, sr=sr)
    f0 = f0[voiced & ~np.isnan(f0)]
    return float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) > 10 else 0.0


model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
int8_voice.shrink(model.model.model, int8=CFG.get("int8", False))
for tag, lang, instruct in MODES:
    spreads = []
    for i, text in enumerate(TEXTS):
        torch.manual_seed(7 + i)
        wavs, sr = model.generate_custom_voice(text=text, speaker=CFG["speaker"], language=lang, instruct=instruct,
                                               temperature=CFG["temperature"], top_k=CFG["top_k"])
        w = np.asarray(wavs[0], dtype=np.float32)
        sf.write(os.path.join(OUT, f"{tag}_{i}.wav"), w, sr)
        spreads.append(f0_spread(w, sr))
    print(f"{tag:9s} melody spread {np.mean(spreads):.2f} st  ({', '.join(f'{s:.2f}' for s in spreads)})", flush=True)
