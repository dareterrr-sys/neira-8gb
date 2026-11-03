"""Checks int8_voice.py (28.10): VRAM, speed and the sound against the plain bf16 voice on the same seeds.
Usage: python int8_probe.py plain|emb|int8   -> wavs in D:\\AI\\voices\\int8_test\\<mode>_<n>.wav"""
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch
from faster_qwen3_tts import FasterQwen3TTS

import int8_voice

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
MODE = sys.argv[1]
OUT = r"D:\AI\voices\int8_test"
os.makedirs(OUT, exist_ok=True)
TEXTS = ["Ну и что ты на меня так смотришь? Это обычный эксперимент.",
         "Если подумать как следует, то в этой задаче нет ничего сложного, просто нужно внимательно прочитать условие "
         "и не торопиться с выводами, как ты обычно делаешь.",
         "Хе-хе-хе. Ладно, признаю, это было довольно забавно."]
MIB = 2 ** 20

model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
root = model.model.model
if MODE != "plain":
    print(f"freed {int8_voice.shrink(root, int8=MODE == 'int8'):.0f} MiB", flush=True)
lora = None
if CFG.get("sounds_lora"):
    kind = int8_voice.Int8MergeVoices if MODE == "int8" else __import__("voice_lora").MergeVoices
    lora = kind(root, CFG["sounds_lora"])
print(f"after load: allocated {torch.cuda.memory_allocated() / MIB:.0f} MiB, reserved {torch.cuda.memory_reserved() / MIB:.0f}", flush=True)
torch.cuda.reset_peak_memory_stats()
for i, text in enumerate(TEXTS):
    sw = lora.use("sounds" if i == 2 else "main") if lora else 0.0
    torch.manual_seed(1234)
    t = time.time()
    wavs, sr = model.generate_custom_voice(text=text, speaker=CFG["speaker"], language=CFG["language"],
                                           temperature=CFG["temperature"], top_k=CFG["top_k"])
    torch.cuda.synchronize()
    el = time.time() - t
    w = np.asarray(wavs[0], dtype=np.float32)
    sf.write(os.path.join(OUT, f"{MODE}_{i}.wav"), w, sr)
    print(f"{i}: {len(w) / sr:4.1f} s speech in {el:4.1f} s (x{len(w) / sr / el:.2f} realtime), switch {sw:.2f} s", flush=True)
    torch.cuda.empty_cache(); print(f"   reserved after empty_cache {torch.cuda.memory_reserved() / MIB:.0f}", flush=True)
if lora:
    lora.use("main")
print(f"peak allocated {torch.cuda.max_memory_allocated() / MIB:.0f} MiB, reserved {torch.cuda.memory_reserved() / MIB:.0f}")
