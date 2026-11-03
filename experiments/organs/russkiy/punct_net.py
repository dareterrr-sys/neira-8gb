"""Punctuation by a trained network (RUPunct and kin: BERT token classification - punctuation after every word).
Tasks 17-20: the passage without punctuation and in lower case goes to the net; at each place (k) we read P(comma after
the word before it). Task 16: five sentences, «one comma» = exactly one word with a comma. Scores are saved as the
log-odds of a comma, so lm_punct_eval.py chooses thresholds on half A and checks half B.
Out: data/net_<model>_<task>.json. Usage: python punct_net.py RUPunct/RUPunct_big 16 17 18 19 20
"""
import json
import math
import os
import re
import sys
import time

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = sys.argv[1]
TASKS = [int(x) for x in sys.argv[2:]] or [17]
DEV = "cuda" if torch.cuda.is_available() and os.environ.get("CPU") != "1" else "cpu"
tok = AutoTokenizer.from_pretrained(NAME, strip_accents=False, add_prefix_space=True)
net = AutoModelForTokenClassification.from_pretrained(NAME).to(DEV).eval()
labels = net.config.id2label
COMMA = [int(i) for i, l in labels.items() if l.endswith("_COMMA")]
WORD = re.compile(r"[а-яёА-ЯЁa-zA-Z0-9]+(?:-[а-яёА-ЯЁa-zA-Z0-9]+)*")


def comma_logodds(words):
    """-> log-odds of a comma after each word."""
    enc = tok(words, is_split_into_words=True, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        probs = net(**{k: v.to(DEV) for k, v in enc.items()}).logits[0].softmax(-1).cpu()
    out, seen = [None] * len(words), set()
    for pos, w in enumerate(enc.word_ids()):
        if w is None or w in seen:
            continue
        seen.add(w)
        p = float(probs[pos, COMMA].sum())
        p = min(max(p, 1e-6), 1 - 1e-6)
        out[w] = math.log(p / (1 - p))
    return out


def passage(q):
    m = re.search(r"запят\w*\s*\(-?\w*\)\s*\.\s*", q)
    p = q[m.end():] if m else q
    p = re.split(r"\s*В ответ (выпишите|запишите)", p)[0]
    return re.sub(r"\s+", " ", p).strip()


def places(p):
    """Words of the passage (lower case, no punctuation) and which word each (k) follows."""
    words, after = [], {}
    for piece in re.split(r"(\(\d\))", p):
        m = re.fullmatch(r"\((\d)\)", piece)
        if m:
            after[int(m.group(1))] = len(words) - 1
        else:
            words += [w.lower() for w in WORD.findall(piece)]
    return words, after


def sentences16(q):
    body = q[q.find("1)"):]
    return [s.strip() for s in re.split(r"\s*\d\)\s*", body) if s.strip()]


def main():
    bank = json.load(open(os.path.join(HERE, "data", "bank_16_21.json"), encoding="utf-8"))
    short = NAME.split("/")[-1]
    for t in TASKS:
        rows, t0 = [], time.time()
        for x in [x for x in bank if x["task"] == t]:
            if t == 16:
                sc = []
                for i, s in enumerate(sentences16(x["q"])[:5], 1):
                    words = [w.lower() for w in WORD.findall(s)]
                    lo = comma_logodds(words)[:-1]  # after the last word - the end of the sentence
                    sc.append((i, [round(v, 3) for v in lo if v is not None]))
                rows.append({"id": x["id"], "ans": x["ans"], "sent": sc})
            else:
                words, after = places(passage(x["q"]))
                lo = comma_logodds(words)
                sc = [(k, None if i < 0 or i >= len(lo) or lo[i] is None else round(lo[i], 3))
                      for k, i in sorted(after.items())]
                rows.append({"id": x["id"], "ans": x["ans"], "scores": sc})
        json.dump(rows, open(os.path.join(HERE, "data", f"net_{short}_{t}.json"), "w", encoding="utf-8"))
        print(f"{short} задание {t}: {len(rows)} за {time.time() - t0:.0f} с на {DEV}", flush=True)


if __name__ == "__main__":
    main()
