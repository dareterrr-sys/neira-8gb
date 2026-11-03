"""EGE task 21 (sentences whose comma / dash follows the same rule) as a pair task: a cross-encoder says whether two
sentences have the mark for the same reason. Labels come from the answers: pairs inside the answer - same; an answer
sentence with a non-answer one - different. Data: the bank (half A for training) + old variants from search.
Answer: the best pair, plus every other sentence that is «same» with both. Usage: python ft_21.py --fetch;
python ft_21.py [epochs]; python ft_21.py --eval
"""
import itertools
import json
import os
import random
import re
import sys
import time
import urllib.parse

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

import bank_build as b

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "RUPunct/RUPunct_big"
OUT = os.path.join(HERE, "models", "rule21")
random.seed(0)
torch.manual_seed(0)
TASK_RE = re.compile(r"Найдите (?:два |три )?предложени\w*, в котор\w+ (тире|запят\w*|двоеточие)[^\n]*?правил\w* "
                     r"пунктуации\.[^\n]*\n(.*?)Ответ:\s*([0-9|,\s]+)", re.S)


def split_sents(text):
    parts = re.split(r"\((\d{1,2})\)", text)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        s = re.sub(r"\s+", " ", parts[i + 1]).strip()
        s = s.split("Пояснение")[0].strip()
        if s:
            out[int(parts[i])] = s
    return out


def from_text(t):
    t = t.replace("⁠", "").replace(" ", " ")   # invisible joiners inside «запятая(-⁠ые)» on the site
    tasks = []
    for m in TASK_RE.finditer(t):
        mark, body, ans = m.group(1), m.group(2).split("Пояснение")[0], m.group(3)
        sents = split_sents(body)
        a = set(re.findall(r"\d", ans.split("|")[0]))   # «36» = sentences 3 and 6
        if len(sents) >= 4 and len(a) >= 2:
            tasks.append({"mark": mark, "sents": {str(k): v for k, v in sents.items()}, "ans": sorted(a)})
    return tasks


def fetch():
    out, seen = [], set()
    for qi, q in enumerate(["тире ставится в соответствии с одним и тем же правилом пунктуации",
                            "запятая ставится в соответствии с одним и тем же правилом пунктуации",
                            "запятые ставятся в соответствии с одним и тем же правилом",
                            "двоеточие ставится в соответствии с одним и тем же правилом"]):
        for p in range(1, 60):
            try:
                page = b.get("/search?search=" + urllib.parse.quote_plus(q) + f"&page={p}", f"search21_{qi}_p{p}.html")
            except Exception as e:
                print("  ошибка", e, flush=True)
                break
            got = [t for t in from_text(b.text(page)) if json.dumps(t["sents"], ensure_ascii=False)[:200] not in seen]
            if not got and p > 1:
                break
            for t in got:
                seen.add(json.dumps(t["sents"], ensure_ascii=False)[:200])
            out += got
        print(f"запрос {qi}: заданий {len(out)}", flush=True)
    json.dump(out, open(os.path.join(HERE, "data", "old21.json"), "w", encoding="utf-8"), ensure_ascii=False)


def bank_tasks(half):
    bank = sorted([x for x in json.load(open(os.path.join(HERE, "data", "bank_5_8_21.json"), encoding="utf-8"))
                   if x["task"] == 21], key=lambda x: int(x["id"]))
    rows = bank[0::2] if half == "A" else bank[1::2]
    out = []
    for x in rows:
        q = x["q"]
        mark = "тире" if "тире" in q[:120] else "двоеточие" if "двоеточие" in q[:120] else "запятая"
        sents = split_sents(q[q.find("(1)"):])
        a = sorted(set(re.findall(r"\d", x["ans"].split("|")[0])))
        if len(sents) >= 4:
            out.append({"mark": mark, "sents": {str(k): v for k, v in sents.items()}, "ans": a, "id": x["id"]})
    return out


def pair_text(mark, s1, s2):
    return f"[{mark}] {s1}", f"[{mark}] {s2}"


def pairs(task):
    a = set(task["ans"])
    out = []
    for i, j in itertools.permutations(task["sents"], 2):
        if i in a and j in a:
            out.append((pair_text(task["mark"], task["sents"][i], task["sents"][j]), 1))
        elif (i in a) != (j in a):
            out.append((pair_text(task["mark"], task["sents"][i], task["sents"][j]), 0))
    return out


def train(epochs):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    old = json.load(open(os.path.join(HERE, "data", "old21.json"), encoding="utf-8"))
    test_keys = {json.dumps(t["sents"], ensure_ascii=False)[:120] for t in bank_tasks("B")}
    old = [t for t in old if json.dumps(t["sents"], ensure_ascii=False)[:120] not in test_keys]
    data = [p for t in old + bank_tasks("A") for p in pairs(t)]
    pos = [d for d in data if d[1] == 1]
    data = data + pos * 3          # «same» pairs are rare
    random.shuffle(data)
    print(f"заданий {len(old)} старых + банк A; пар {len(data)}, одинаковых {sum(l for _, l in data)}, {dev}", flush=True)
    tok = AutoTokenizer.from_pretrained(BASE)
    net = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=2, ignore_mismatched_sizes=True).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, weight_decay=0.01)
    bs, steps = 16, epochs * ((len(data) + 15) // 16)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / steps))
    scaler = torch.amp.GradScaler(enabled=dev == "cuda")
    net.train()
    t0 = time.time()
    for ep in range(epochs):
        random.shuffle(data)
        for i in range(0, len(data), bs):
            ch = data[i:i + bs]
            enc = tok([p[0] for p, _ in ch], [p[1] for p, _ in ch], truncation=True, max_length=192, padding=True,
                      return_tensors="pt").to(dev)
            with torch.autocast(dev, dtype=torch.float16, enabled=dev == "cuda"):
                loss = net(**enc, labels=torch.tensor([l for _, l in ch], device=dev)).loss
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            opt.zero_grad()
            if (i // bs) % 300 == 0:
                print(f"  эпоха {ep + 1} шаг {i // bs}, {time.time() - t0:.0f} с", flush=True)
    os.makedirs(OUT, exist_ok=True)
    net.save_pretrained(OUT)
    tok.save_pretrained(OUT)


_m = None


def answer_task(task):
    global _m
    if _m is None:
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _m = (AutoTokenizer.from_pretrained(OUT), AutoModelForSequenceClassification.from_pretrained(OUT).to(dev).eval(), dev)
    tok, net, dev = _m
    ks = list(task["sents"])
    prob = {}
    for i, j in itertools.combinations(ks, 2):
        a, c = pair_text(task["mark"], task["sents"][i], task["sents"][j])
        with torch.no_grad():
            enc = tok([a, c], [c, a], truncation=True, max_length=192, padding=True, return_tensors="pt").to(dev)
            p = net(**enc).logits.softmax(-1)[:, 1].mean()
        prob[(i, j)] = prob[(j, i)] = float(p)
    i, j = max(((x, y) for x, y in itertools.combinations(ks, 2)), key=lambda z: prob[z])
    group = {i, j}
    for k in ks:
        if k not in group and prob[(k, i)] > 0.5 and prob[(k, j)] > 0.5:
            group.add(k)
    return "".join(sorted(group, key=int)), prob[(i, j)]


def evaluate():
    ok = n = 0
    for t in bank_tasks("B"):
        got, conf = answer_task(t)
        n += 1
        ok += set(got) == set(t["ans"])
    print(f"задание 21, половина B: {ok}/{n}")


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    elif "--eval" in sys.argv:
        evaluate()
    else:
        train(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
