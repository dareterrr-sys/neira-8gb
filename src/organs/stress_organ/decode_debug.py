"""Debug: what phonemes the recogniser hears (greedy CTC) next to what the organ expects. fastqwen venv.
Usage: python decode_debug.py <wav> "<text>" out.txt"""
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import stress_organ as so  # noqa: E402

wav, text, out = sys.argv[1:4]
m, vocab = so.phone_model()
inv = {v: k for k, v in vocab.items()}
lp = so.emissions(so.load16(wav))
best = lp.argmax(-1).tolist()
seq, prev = [], None
for b in best:
    if b != prev and b != 0:
        seq.append(inv[b])
    prev = b
info = so.text_analysis([text])[0]
exp = []
for w in info["words"]:
    exp += so.word_phones(w["w"], w["stress"])[0] + ["|"]
missing = sorted({p for p in exp if p != "|" and p not in vocab})
open(out, "w", encoding="utf-8").write("heard:    " + " ".join(seq) + "\nexpected: " + " ".join(exp)
                                       + "\nnot in vocab: " + " ".join(missing) + "\n")
