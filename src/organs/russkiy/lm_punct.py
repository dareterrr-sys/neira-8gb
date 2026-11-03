"""Punctuation by the brain as a scorer, not a writer (tasks 17-20: commas at numbered places). At every place (k) the
brain (raw completion, no chat) sees the passage up to that place - earlier places already decided - and we read the
probability of a comma against the probability of the next word. A comma if log P(",") - log P(next word) > HI, none
if < LO, otherwise «не знаю» for the whole task. The brain must run on 8080.
Out: data/lm_punct_<task>.json with per-place scores, so thresholds can be chosen afterwards without the brain.
Usage: python lm_punct.py 17 [limit]
"""
import json
import math
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "http://127.0.0.1:8080"
TASK = int(sys.argv[1]) if len(sys.argv) > 1 else 17
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9


def post(path, body):
    req = urllib.request.Request(API + path, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


def first_token(text):
    return post("/tokenize", {"content": text})["tokens"][0]


def next_logprobs(prompt):
    r = post("/completion", {"prompt": prompt, "n_predict": 1, "n_probs": 100, "temperature": 0,
                             "cache_prompt": True, "post_sampling_probs": False})
    top = r["completion_probabilities"][0]["top_logprobs"]
    return {t["id"]: t["logprob"] for t in top}, min(t["logprob"] for t in top)


def passage(q):
    """The text after the instruction, with (1), (2) ... kept."""
    m = re.search(r"запят\w*\s*\(-?\w*\)\s*\.\s*", q)
    p = q[m.end():] if m else q
    p = re.split(r"\s*В ответ (выпишите|запишите)", p)[0]
    return re.sub(r"\s+", " ", p).strip()


COMMA = None


def score_places(p):
    """-> [(k, delta)] in order; delta = logP(",") - logP(next word), decisions so far taken by the sign."""
    global COMMA
    if COMMA is None:
        COMMA = first_token(",")
    parts = re.split(r"\s*\((\d)\)\s*", p)   # text, k, text, k, ...
    out, prefix = [], parts[0]
    for i in range(1, len(parts), 2):
        k, rest = int(parts[i]), parts[i + 1]
        nxt = rest.split(" ")[0] if rest else ""
        if not nxt or not re.match(r"[а-яёА-ЯЁ«\"]", nxt):
            out.append((k, None))
            prefix += " " + rest
            continue
        lp, floor = next_logprobs(prefix)
        word_tok = first_token(" " + nxt)
        d = lp.get(COMMA, floor - 1) - lp.get(word_tok, floor - 1)
        out.append((k, d))
        prefix += ("," if d > 0 else "") + " " + rest
    return out


def main():
    bank = [x for x in json.load(open(os.path.join(HERE, "data", "bank_16_21.json"), encoding="utf-8"))
            if x["task"] == TASK][:LIMIT]
    rows, t0 = [], time.time()
    for i, x in enumerate(bank):
        sc = score_places(passage(x["q"]))
        rows.append({"id": x["id"], "ans": x["ans"], "scores": sc})
        if (i + 1) % 20 == 0:
            print(f"{i + 1}/{len(bank)} {time.time() - t0:.0f} с", flush=True)
    json.dump(rows, open(os.path.join(HERE, "data", f"lm_punct_{TASK}.json"), "w", encoding="utf-8"), indent=0)
    print(f"готово {len(rows)} за {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
