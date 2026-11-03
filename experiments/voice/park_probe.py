"""Checks park.py (28.10): VRAM freed by parking, time to come back, and that the voice still speaks after it
(first sentence after unpark includes capturing the CUDA graphs again)."""
import json
import os
import subprocess
import time

import numpy as np
import soundfile as sf
import torch
from faster_qwen3_tts import FasterQwen3TTS

import int8_voice
from park import Parking

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
TEXT = "Ну и что ты на меня так смотришь? Это обычный эксперимент."


def free():
    return subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader"], capture_output=True,
                          text=True).stdout.strip()


def say(tag):
    torch.manual_seed(1234)
    t = time.time()
    wavs, sr = model.generate_custom_voice(text=TEXT, speaker=CFG["speaker"], language=CFG["language"],
                                           temperature=CFG["temperature"], top_k=CFG["top_k"])
    torch.cuda.synchronize()
    w = np.asarray(wavs[0], dtype=np.float32)
    sf.write(rf"D:\AI\voices\int8_test\park_{tag}.wav", w, sr)
    print(f"{tag}: {len(w) / sr:.1f} s speech in {time.time() - t:.1f} s, free VRAM {free()}", flush=True)


model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=2048)
int8_voice.shrink(model.model.model, int8=True)
lora = int8_voice.Int8MergeVoices(model.model.model, CFG["sounds_lora"])
say("before")
say("before2")
p = Parking(model)
s, mib = p.park()
print(f"park: {s:.2f} s, {mib:.0f} MiB freed, free VRAM {free()}", flush=True)
time.sleep(2)
print(f"unpark: {p.unpark():.2f} s", flush=True)
say("after")
say("after2")
lora.use("sounds")
say("sounds")
lora.use("main")
s, mib = p.park()
print(f"park again: {s:.2f} s, {mib:.0f} MiB freed, free VRAM {free()}", flush=True)
print(f"unpark: {p.unpark():.2f} s", flush=True)
say("after3")
