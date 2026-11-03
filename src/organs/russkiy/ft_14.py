"""EGE task 14 (together / hyphen / apart) - the task-13 recipe: the pairs highlighted anywhere in the bank («ТАК(ЖЕ)»,
«(В)СЛЕДСТВИЕ», «(ПО)ВИДИМОМУ») are looked up in all our correct texts in any spelling - the spelling found is the
label - plus the rows of half A whose every word is written the asked way. 3-way BERT classifier on the item
«… ТАК(ЖЕ) …» (RUPunct_big encoder, like ft_ne.py). Usage: python ft_14.py [epochs]; python ft_14.py --eval
"""
import json
import os
import random
import re
import sys
import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "RUPunct/RUPunct_big"
OUT = os.path.join(HERE, "models", "sp14")
LAB = {"S": 0, "D": 1, "R": 2}
random.seed(0)
torch.manual_seed(0)
COMP = re.compile(r"(?:\(?[А-ЯЁ]+\)?(?![а-яё])\s?){2}")   # 28.10: not the «Д» of «Дина»; ТАК(ЖЕ) ЗА(ТО) - two


def compounds(s):
    out = []
    for m in COMP.finditer(s):
        txt = m.group(0).rstrip()
        if "(" not in txt:
            continue
        parts = re.findall(r"\(?([А-ЯЁ]+)\)?", txt)
        if len(parts) == 2:
            out.append((m.start(), m.start() + len(txt), parts))
    return out


def bank_rows(half):
    bank = json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8"))
    rows = sorted([x for x in bank if x["task"] == 14], key=lambda x: int(x["id"]))
    rows = rows[0::2] if half == "A" else rows[1::2]
    out = []
    for x in rows:
        q = x["q"]
        head = q[:q.find("1)")]
        want = "D" if "ДЕФИС" in head else "R" if "РАЗДЕЛЬНО" in head else "S"
        ans = set(x["ans"].split("|")[0])
        body = re.split(r"\s*(Ответ дай|В ответ)", q[q.find("1)"):])[0]
        parts = re.split(r"(?:^|\s)(\d)\)\s*", " " + body)
        items = {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
        out.append((x, want, ans, items))
    return out


def vocab():
    pairs = set()
    bank = json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8"))
    for x in bank:
        if x["task"] == 14:
            for _, _, (a, b) in compounds(x["q"]):
                pairs.add((a.lower(), b.lower()))
    return pairs


def corpus_items(pairs):
    sents = []
    for name in ("norm_texts.jsonl", "classics.jsonl", "dostoevsky.jsonl", "puha.jsonl"):
        p = os.path.join(HERE, "data", name)
        if os.path.exists(p):
            sents += [json.loads(l)["s"] for l in open(p, encoding="utf-8")]
    items = []
    for a, b in pairs:
        pat = re.compile(r"(?<![а-яё])(" + a + r")(-| |)(" + b + r")(?![а-яё])", re.I)
        for s in sents:
            for m in pat.finditer(s):
                lab = "D" if m.group(2) == "-" else "R" if m.group(2) == " " else "S"
                marked = a.upper() + "(" + b.upper() + ")" if random.random() < 0.5 else "(" + a.upper() + ")" + b.upper()
                items.append((s[:m.start()] + marked + s[m.end():], LAB[lab]))
    return items


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 4
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pairs = vocab()
    data = corpus_items(pairs)
    for x, want, ans, items in bank_rows("A"):
        for n, s in items.items():
            if str(n) in ans:
                for a, b, _ in compounds(s):
                    data += [(s, LAB[want])] * 3   # every compound of an answer row is written the asked way
    old = os.path.join(HERE, "data", "old14.jsonl")   # old-format task 14, every pair labelled (fetch_old14.py), x3
    if os.path.exists(old):
        for r in map(json.loads, open(old, encoding="utf-8")):
            a, b = r["pair"].split("|")
            s, comps = r["s"], compounds(r["s"])
            for j, (x1, x2, parts) in sorted(enumerate(comps), key=lambda z: -z[1][0]):
                if parts != [a, b]:
                    s = s[:x1] + " ".join(parts).lower() + s[x2:]
            data += [(s, LAB[r["lab"]])] * 3
    random.shuffle(data)
    from collections import Counter
    print(f"пар {len(pairs)}, примеров {len(data)}, по классам {Counter(l for _, l in data)}, {dev}", flush=True)
    tok = AutoTokenizer.from_pretrained(BASE)
    net = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=3, ignore_mismatched_sizes=True).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, weight_decay=0.01)
    bs, steps = 16, epochs * ((len(data) + 15) // 16)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / steps))
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    net.train()
    t0 = time.time()
    for ep in range(epochs):
        random.shuffle(data)
        tot = 0.0
        for i in range(0, len(data), bs):
            ch = data[i:i + bs]
            enc = tok([s for s, _ in ch], truncation=True, max_length=96, padding=True, return_tensors="pt").to(dev)
            with torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda"):
                loss = net(**enc, labels=torch.tensor([l for _, l in ch], device=dev)).loss
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            opt.zero_grad()
            tot += loss.item()
            if (i // bs) % 100 == 0:
                print(f"  шаг {i // bs}, {time.time() - t0:.0f} с", flush=True)
        print(f"эпоха {ep + 1}: потеря {tot / ((len(data) + bs - 1) // bs):.4f}, {time.time() - t0:.0f} с", flush=True)
    os.makedirs(OUT, exist_ok=True)
    net.save_pretrained(OUT)
    tok.save_pretrained(OUT)


def predict_row(tok, net, dev, s):
    """-> list of (label, confidence) per compound of the row, the compound marked alone each time."""
    out = []
    comps = compounds(s)
    for i, (a, b, _) in enumerate(comps):
        # one marked compound per text, like in training: the others become plain lowercase words
        t = s
        for j, (a2, b2, parts) in sorted(enumerate(comps), key=lambda z: -z[1][0]):
            if j != i:
                t = t[:a2] + " ".join(parts).lower() + t[b2:]
        with torch.no_grad():
            pr = net(**tok(t, truncation=True, max_length=128, return_tensors="pt").to(dev)).logits.softmax(-1)[0]
        out.append((int(pr.argmax()), float(pr.max())))
    return out


def evaluate():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(OUT)
    net = AutoModelForSequenceClassification.from_pretrained(OUT).to(dev).eval()
    ok = bad = 0
    for x, want, ans, items in bank_rows("B"):
        got = ""
        for n, s in items.items():
            preds = predict_row(tok, net, dev, s)
            if preds and all(l == LAB[want] for l, _ in preds):
                got += str(n)
        right = set(got) == ans
        ok += right
        bad += not right
    print(f"задание 14, половина B: {ok}/{ok + bad}")


if __name__ == "__main__":
    evaluate() if "--eval" in sys.argv else main()
