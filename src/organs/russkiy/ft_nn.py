"""EGE task 15 (Н or НН) - same recipe as ft_ne.py. Was: EGE task 13 (НЕ together or apart) by a fine-tuned classifier - the recipe that worked for punctuation: the answers
come for free from correctly written texts. Every «не X» and prefix «неX» in the FIPI texts and the classics becomes an
item «… (НЕ)X …» with its true spelling; plus the items of half A of the bank (×3). Prefix «не» is told from a root
(небо, неделя) by OpenCorpora: «неX» and X are both words of the same part of speech, or X does not exist alone
(ненавидеть). Encoder: RUPunct_big's BERT, a new 2-way head. Out: models/ne13.
Usage: python ft_ne.py [epochs=3]   then   python ft_ne.py --eval
"""
import json
import os
import random
import re
import sys
import time

import pymorphy3
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "RUPunct/RUPunct_big"
OUT = os.path.join(HERE, "models", os.environ.get("NE_OUT", "nn15"))
M = pymorphy3.MorphAnalyzer()
random.seed(0)
torch.manual_seed(0)
POS_FAMILY = {"ADJF": "A", "ADJS": "A", "COMP": "A", "PRTF": "P", "PRTS": "P", "NOUN": "N", "ADVB": "D", "VERB": "V",
              "INFN": "V", "GRND": "G", "PRED": "D"}


def fam(w):
    return {POS_FAMILY.get(p.tag.POS) for p in M.parse(w) if p.score > 0.05 and p.is_known} - {None}


def prefix_ne(word):
    """«неширокий» -> True (prefix не), «небо», «неделя» -> False."""
    w = word.lower()
    if len(w) < 5 or not w.startswith("не"):
        return False
    rest = w[2:]
    fw = fam(w)
    if not fw or not M.word_is_known(w):
        return False
    if not M.word_is_known(rest):
        return bool(fw & {"A", "D", "N", "V", "P"}) and len(rest) >= 4   # ненавидеть, невежда
    return bool(fw & fam(rest))


END = r"(ый|ий|ая|ое|ые|ого|ому|ым|ом|ой|ую|ых|ыми|ою|ее|о|а|ы)"
SLOT = re.compile(r"\b([а-яё]{2,}[аеёияо])(нн|н)" + END + r"\b")


def corpus_items(limit):
    sents = []
    extra = os.environ.get("NE_EXTRA", "").split(",") if os.environ.get("NE_EXTRA") else []
    for name in ["norm_texts.jsonl", "classics.jsonl", "dostoevsky.jsonl"] + extra:
        path = os.path.join(HERE, "data", name)
        if os.path.exists(path):
            sents += [json.loads(l)["s"] for l in open(path, encoding="utf-8")]
    items = []
    for s in sents:
        for m in SLOT.finditer(s):
            w = m.group(0)
            if not (fam(w) & {"A", "P", "D"}):
                continue
            items.append((s[:m.start()] + m.group(1) + "(1)" + m.group(3) + s[m.end():], int(m.group(2) == "нн")))
    random.shuffle(items)
    nn = [it for it in items if it[1] == 1]
    n1 = [it for it in items if it[1] == 0]
    k = min(len(nn), len(n1), limit // 2)
    return nn[:k] + n1[:k]


def bank_items(half):
    bank = json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8"))
    rows = sorted([x for x in bank if x["task"] == 15], key=lambda x: int(x["id"]))
    rows = rows[0::2] if half == "A" else rows[1::2]
    out = []
    for x in rows:
        q = x["q"]
        i0 = q.find("(1)")
        head = q[:i0]
        want_nn = "НН" in head[head.find("пишется"):]
        ans = set(x["ans"].split("|")[0])
        st = head.rfind(".") + 1 if head.rfind(".") > 0 else 0
        text = re.split(r"\s*(Ответ дай|В ответ)", q[st:])[0]
        items = {}
        for k in range(1, 10):
            if f"({k})" not in text:
                break
            t = re.sub(r"\((?!%d\))\d\)" % k, "н", text).replace(f"({k})", "(1)")
            items[k] = t
        out.append((x, want_nn, ans, items))
    return out


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(BASE)
    net = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=2, ignore_mismatched_sizes=True).to(dev)
    data = corpus_items(int(os.environ.get("NE_CORPUS", "20000")))
    for x, want_tog, ans, items in bank_items("A"):
        for n, s in items.items():
            data += [(s, int((str(n) in ans) == want_tog))] * 3
    old = os.path.join(HERE, "data", "old15_none.jsonl")   # old-format task 13 traps (fetch_old13.py), x3
    if os.path.exists(old) and os.environ.get("NE_OLD", "1") == "1":
        data += [(r["s"], r["together"]) for r in map(json.loads, open(old, encoding="utf-8"))] * 3
    random.shuffle(data)
    print(f"примеров {len(data)} (слитно {sum(l for _, l in data)}), {dev}", flush=True)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, weight_decay=0.01)
    bs, steps = 32, epochs * ((len(data) + 31) // 32)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / steps))
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    net.train()
    t0 = time.time()
    for ep in range(epochs):
        random.shuffle(data)
        tot = 0.0
        for i in range(0, len(data), bs):
            chunk = data[i:i + bs]
            enc = tok([s for s, _ in chunk], truncation=True, max_length=128, padding=True, return_tensors="pt").to(dev)
            with torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda"):
                loss = net(**enc, labels=torch.tensor([l for _, l in chunk], device=dev)).loss
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            opt.zero_grad()
            tot += loss.item()
        print(f"эпоха {ep + 1}: потеря {tot / ((len(data) + bs - 1) // bs):.4f}, {time.time() - t0:.0f} с", flush=True)
    os.makedirs(OUT, exist_ok=True)
    net.save_pretrained(OUT)
    tok.save_pretrained(OUT)


def evaluate():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(OUT)
    net = AutoModelForSequenceClassification.from_pretrained(OUT).to(dev).eval()
    recs = []
    for x, want_tog, ans, items in bank_items("B"):
        its = []
        for n, s in items.items():
            with torch.no_grad():
                p = net(**tok(s, truncation=True, max_length=128, return_tensors="pt").to(dev)).logits.softmax(-1)[0, 1]
            its.append((n, float(p), (str(n) in ans) == want_tog))
        if its:
            recs.append(its)
    item_ok = sum((p > 0.5) == t for its in recs for _, p, t in its)
    item_n = sum(len(its) for its in recs)
    print(f"половина B: пунктов {item_ok}/{item_n} = {item_ok / item_n:.1%}")
    B1, B2 = recs[0::2], recs[1::2]

    def task_level(rs, conf):
        ok = bad = 0
        for its in rs:
            if any(abs(p - 0.5) < conf for _, p, _ in its):
                continue
            right = all((p > 0.5) == t for _, p, t in its)
            ok += right
            bad += not right
        return ok, bad
    ok0, bad0 = task_level(recs, 0)
    print(f"задания без порога: {ok0}/{ok0 + bad0}")
    best = None
    for c in [x / 100 for x in range(0, 50)]:
        ok, bad = task_level(B1, c)
        if ok + bad and bad / (ok + bad) <= 0.02 and (best is None or ok > best[0]):
            best = (ok, bad, c)
    if best:
        ok, bad, c = best
        o2, b2 = task_level(B2, c)
        print(f"порог уверенности {c}: B1 {ok}/{ok + bad} (охват {(ok + bad) / len(B1):.0%}); "
              f"B2 {o2}/{o2 + b2} = {o2 / max(1, o2 + b2):.1%} (охват {(o2 + b2) / len(B2):.0%})")
    else:
        print("нет порога с 98% на B1")


if __name__ == "__main__":
    evaluate() if "--eval" in sys.argv else main()
