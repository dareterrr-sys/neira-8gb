"""Where the voice's VRAM goes (28.10): the fine-tuned Qwen3-TTS as the server loads it, at a given max_seq_len -
weights after load, then the peak after warm-up generations (CUDA graphs, cache). Usage: python vram_probe.py [max_seq_len]"""
import json
import os
import sys
import time

import torch
from faster_qwen3_tts import FasterQwen3TTS

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "voice_config.json"), encoding="utf-8"))
SEQ = int(sys.argv[1]) if len(sys.argv) > 1 else 2048
MIB = 2 ** 20


def mem(tag):
    print(f"{tag:28s} allocated {torch.cuda.memory_allocated() / MIB:6.0f} MiB, reserved "
          f"{torch.cuda.memory_reserved() / MIB:6.0f}, peak {torch.cuda.max_memory_allocated() / MIB:6.0f}", flush=True)


model = FasterQwen3TTS.from_pretrained(CFG["model"], max_seq_len=SEQ)
mem(f"loaded (max_seq_len {SEQ})")
w = sum(p.numel() * p.element_size() for p in model.model.model.parameters())
print(f"weights of the TTS model      {w / MIB:6.0f} MiB, dtype {next(model.model.model.parameters()).dtype}")
for text in ["Ну и что ты на меня так смотришь? Это обычный эксперимент.",
             "Если подумать как следует, то в этой задаче нет ничего сложного, просто нужно внимательно прочитать условие "
             "и не торопиться с выводами, как ты обычно делаешь."]:
    t = time.time()
    wavs, sr = model.generate_custom_voice(text=text, speaker=CFG["speaker"], language=CFG["language"],
                                           temperature=CFG["temperature"], top_k=CFG["top_k"])
    torch.cuda.synchronize()
    dur = len(wavs[0]) / sr
    print(f"generated {dur:4.1f} s of speech in {time.time() - t:4.1f} s")
    mem("after generation")
