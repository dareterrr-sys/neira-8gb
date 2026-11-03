"""Fine-tune RUPunct on EGE punctuation (tasks 17-20, half A of each task's bank - the same split as net_eval.py, so
half B stays untouched). Every task gives a fully labelled passage: the punctuation already in the text plus the
answer (comma at the listed places, nothing at the others). Labels follow RUPunct's scheme (LOWER_/UPPER_ + mark).
Out: models/rupunct_ege. Usage: python ft_punct.py [epochs=3]
"""
import json
import os
import random
import re
import sys
import time

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "RUPunct/RUPunct_big"
EPOCHS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
# CLASSICS=N: add N sentences of classic prose (data/classics.jsonl) and repeat the EGE half A EGE_REPEAT times
CLASSICS = int(os.environ.get("CLASSICS", "0"))
EGE_REPEAT = int(os.environ.get("EGE_REPEAT", "1"))
# NORM=N: N sentences of FIPI reading texts (data/norm_texts.jsonl, modern punctuation norms)
NORM = int(os.environ.get("NORM", "0"))
OUT = os.path.join(HERE, "models", os.environ.get("OUT_NAME") or ("rupunct_ege_cls" if CLASSICS else "rupunct_ege"))
DEV = "cuda" if torch.cuda.is_available() else "cpu"
BS = 16 if DEV == "cuda" else 8
torch.manual_seed(0)
random.seed(0)

tok = AutoTokenizer.from_pretrained(BASE, strip_accents=False, add_prefix_space=True)
net = AutoModelForTokenClassification.from_pretrained(BASE).to(DEV)
L = net.config.label2id
MARK = {",": "COMMA", ".": "PERIOD", "—": "TIRE", "–": "TIRE", "-": "TIRE", ":": "DVOETOCHIE", "?": "QUESTION",
        "!": "VOSKL", ";": "PERIODCOMMA", "…": "MNOGOTOCHIE"}
WORD = re.compile(r"[а-яёА-ЯЁa-zA-Z0-9]+(?:-[а-яёА-ЯЁa-zA-Z0-9]+)*")
TOKEN = re.compile(r"\((\d)\)|[а-яёА-ЯЁa-zA-Z0-9]+(?:-[а-яёА-ЯЁa-zA-Z0-9]+)*|\.\.\.|[,.—–:;?!…]|\s-\s")


def passage(q):
    m = re.search(r"запят\w*\s*\(-?\w*\)\s*\.\s*", q)
    p = q[m.end():] if m else q
    p = re.split(r"\s*В ответ (выпишите|запишите)", p)[0]
    return re.sub(r"\s+", " ", p).strip()


def labelled(q, ans, text=None):
    """-> (lower-case words, label ids) for a passage with (k) places resolved by the answer (or a plain sentence)."""
    commas = set(ans.split("|")[0]) if ans else set()
    words, marks, case = [], [], []
    for m in TOKEN.finditer(text if text is not None else passage(q)):
        t = m.group(0)
        if m.group(1):                       # a place (k)
            if m.group(1) in commas and words:
                marks[-1] = "COMMA"
            continue
        t = t.strip()
        if t == "...":
            t = "…"
        if t in MARK:
            if words and marks[-1] == "O":
                marks[-1] = MARK[t]
            continue
        words.append(t.lower())
        marks.append("O")
        case.append("UPPER_TOTAL" if len(t) > 1 and t.isupper() else "UPPER" if t[0].isupper() else "LOWER")
    labels = [L.get(f"{c}_{mk}", L[f"{c}_O"]) for c, mk in zip(case, marks)]
    return words, labels


def split_A():
    bank = json.load(open(os.path.join(HERE, "data", "bank_16_21.json"), encoding="utf-8"))
    out = []
    for t in (17, 18, 19, 20):
        rows = sorted([x for x in bank if x["task"] == t], key=lambda x: int(x["id"]))
        out += rows[0::2]                    # half A, exactly as net_eval.py
    return out


def encode(words, labels):
    enc = tok(words, is_split_into_words=True, truncation=True, max_length=256)
    lab, prev = [], None
    for w in enc.word_ids():
        lab.append(-100 if w is None or w == prev else labels[w])
        prev = w
    enc["labels"] = lab
    return enc


def main():
    data = [encode(*labelled(x["q"], x["ans"])) for x in split_A()] * EGE_REPEAT
    if CLASSICS:
        cls = [json.loads(l)["s"] for l in open(os.path.join(HERE, "data", "classics.jsonl"), encoding="utf-8")]
        data += [encode(*labelled(None, None, text=s.replace("«", "").replace("»", ""))) for s in cls[:CLASSICS]]
    if int(os.environ.get("AUG", "0")):   # rule-made sentences (aug_punct.py) for tasks 16 and 18
        ag = [json.loads(l)["s"] for l in open(os.path.join(HERE, "data", "aug.jsonl"), encoding="utf-8")]
        data += [encode(*labelled(None, None, text=s)) for s in ag[:int(os.environ["AUG"])]]
    if NORM:
        nt = [json.loads(l)["s"] for l in open(os.path.join(HERE, "data", "norm_texts.jsonl"), encoding="utf-8")]
        data += [encode(*labelled(None, None, text=s.replace("«", "").replace("»", ""))) for s in nt[:NORM]]
    print(f"примеров {len(data)}, эпох {EPOCHS}, {DEV}", flush=True)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, weight_decay=0.01)
    steps = EPOCHS * ((len(data) + BS - 1) // BS)
    scaler = torch.amp.GradScaler(enabled=DEV == "cuda")
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / steps))
    net.train()
    t0, step = time.time(), 0
    for ep in range(EPOCHS):
        random.shuffle(data)
        total = 0.0
        for i in range(0, len(data), BS):
            chunk = data[i:i + BS]
            # tok.pad cannot pad labels: pad the inputs without them, then the labels by hand
            batch = tok.pad([{k: v for k, v in d.items() if k != "labels"} for d in chunk], return_tensors="pt")
            n = batch["input_ids"].shape[1]
            batch["labels"] = torch.tensor([d["labels"] + [-100] * (n - len(d["labels"])) for d in chunk])
            batch = {k: v.to(DEV) for k, v in batch.items()}
            with torch.autocast(DEV, dtype=torch.float16, enabled=DEV == "cuda"):
                loss = net(**batch).loss
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            opt.zero_grad()
            total += loss.item()
            step += 1
        print(f"эпоха {ep + 1}: потеря {total / ((len(data) + BS - 1) // BS):.4f}, {time.time() - t0:.0f} с", flush=True)
    os.makedirs(OUT, exist_ok=True)
    net.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print("сохранено", OUT)


if __name__ == "__main__":
    main()
