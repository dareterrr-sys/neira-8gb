"""Task 15: the dictionary organ decides where it can (100% on the bank), the nn15 net only the places it leaves open.
Half B, task level, with a confidence margin for the net chosen on B1 and checked on B2. Usage: python combo15.py"""
import json
import os
import re
import subprocess

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import ft_nn

HERE = os.path.dirname(os.path.abspath(__file__))
tok = AutoTokenizer.from_pretrained(os.path.join(HERE, "models", "nn15"))
net = AutoModelForSequenceClassification.from_pretrained(os.path.join(HERE, "models", "nn15")).eval()
recs = []
for x, want_nn, ans, items in ft_nn.bank_items("B"):
    q = re.sub(r"\s+", " ", x["q"]).replace('"', "«")
    out = subprocess.run([os.path.join(HERE, "russkiy.exe")], input=f'РАЗБОР(15, "{q}")\n', capture_output=True,
                         text=True, encoding="utf-8").stdout
    org = {int(k): int(v) for k, v, _ in re.findall(r"(\d+):(-?\d+):(\S+?);", out)}
    its = []
    for k, s in items.items():
        truth = (str(k) in ans) == want_nn
        if org.get(k, -1) in (0, 1):
            its.append((1.0 if org[k] == 1 else 0.0, truth, "словарь"))
        else:
            with torch.no_grad():
                p = float(net(**tok(s, truncation=True, max_length=160, return_tensors="pt")).logits.softmax(-1)[0, 1])
            its.append((p, truth, "сеть"))
    recs.append(its)


def level(rs, c):
    ok = bad = 0
    for its in rs:
        if any(src == "сеть" and abs(p - 0.5) < c for p, _, src in its):
            continue
        r = all((p > 0.5) == t for p, t, _ in its)
        ok += r
        bad += not r
    return ok, bad


B1, B2 = recs[0::2], recs[1::2]
o, b = level(recs, 0)
print(f"словарь + сеть, без порога: {o}/{o + b} (всего {len(recs)})")
best = None
for c in [i / 100 for i in range(0, 50)]:
    o1, b1 = level(B1, c)
    if o1 + b1 and b1 / (o1 + b1) <= 0.02 and (best is None or o1 > best[0]):
        best = (o1, b1, c)
if best:
    o2, b2 = level(B2, best[2])
    print(f"порог {best[2]}: B1 {best[0]}/{best[0] + best[1]}; B2 {o2}/{o2 + b2} = {o2 / max(1, o2 + b2):.1%}, "
          f"охват {(o2 + b2) / len(B2):.0%}")
else:
    print("нет порога с 98%")
