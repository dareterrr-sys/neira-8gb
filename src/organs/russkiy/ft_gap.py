"""EGE tasks 9-12, the meaning choices the dictionaries leave open («зап..вать (водой)»: запивать / запевать) - the
task-13 recipe: (1) every gap word of the bank is asked of the organ (БУКВА); words with two possible letters are the
ambiguous ones; (2) both spellings, in every form (pymorphy lexeme), are looked up in our correct texts - the spelling
found is the label, the sentence is the meaning; (3) a BERT classifier picks the letter for «… зап..вать …».
The organ then asks the net instead of the brain (92.6%). Out: models/gap912. Usage: python ft_gap.py [epochs];
python ft_gap.py --eval  (organ + net on half B of tasks 9-12)
"""
import json
import os
import random
import re
import subprocess
import sys
import time

import pymorphy3
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "RUPunct/RUPunct_big"
OUT = os.path.join(HERE, "models", "gap912")
LETTERS = list("аеёиоуыэюяъьздст") + ["∅"]
L2I = {c: i for i, c in enumerate(LETTERS)}
M = pymorphy3.MorphAnalyzer()
EXE = os.path.join(HERE, "russkiy.exe")
random.seed(0)
torch.manual_seed(0)


def organ(lines):
    out = subprocess.run([EXE], input="\n".join(lines) + "\n", capture_output=True, text=True, encoding="utf-8").stdout
    return [l.rsplit(" = ", 1)[-1] for l in out.splitlines()]


def bank912():
    bank = json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8"))
    return sorted([x for x in bank if 9 <= x["task"] <= 12], key=lambda x: int(x["id"]))


def gap_words(q):
    body = re.split(r"\s*(Ответ дай|В ответ)", q[q.find("1)"):])[0]
    return set(w.lower() for w in re.findall(r"[а-яёА-ЯЁ-]*\.\.[а-яёА-ЯЁ-]*", body.replace("…", "..").replace("_", "..")))


def ambiguous_pairs():
    words = set()
    for x in bank912():
        words |= gap_words(x["q"])
    # fragments like «..», «т..», «..бить» from the parse are noise: at least 4 letters, no gap at the very start
    words = sorted(w for w in words if w.count("..") == 1 and len(w.replace("..", "").replace("-", "")) >= 4
                   and not w.startswith(".."))
    res = organ([f'БУКВА("{w}")' for w in words])
    pairs = {}
    for w, r in zip(words, res):
        m = re.search(r"А ([^;]+); Б ([^;)]+)", r)
        if r.startswith("не знаю") and m:
            a = {c.strip() for c in m.group(1).split(",")}
            b = {c.strip() for c in m.group(2).split(",")}
            let = sorted(c for c in a & b if c in L2I and c != "∅")
            if len(let) >= 2:
                pairs[w] = let
    return pairs


def corpus_items(pairs):
    sents = []
    for name in ("norm_texts.jsonl", "classics.jsonl", "dostoevsky.jsonl", "puha.jsonl"):
        p = os.path.join(HERE, "data", name)
        if os.path.exists(p):
            sents += [json.loads(l)["s"] for l in open(p, encoding="utf-8")]
    # form -> (gap word form with "..", letter)
    forms = {}
    for w, lets in pairs.items():
        g = w.find("..")
        for c in lets:
            filled = w[:g] + c + w[g + 2:]
            for p in M.parse(filled)[:2]:
                if not p.is_known:
                    continue
                for f in p.lexeme:
                    fw = f.word
                    if fw[:g] == filled[:g] and len(fw) > g and fw[g] == c:
                        forms.setdefault(fw, (fw[:g] + ".." + fw[g + 1:], c))
    items = []
    word_re = re.compile(r"[а-яё]+", re.I)
    for s in sents:
        for m in word_re.finditer(s):
            lw = m.group(0).lower()
            if lw in forms:
                gapf, c = forms[lw]
                items.append((s[:m.start()] + gapf + s[m.end():], L2I[c]))
    random.shuffle(items)
    return items


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pairs = ambiguous_pairs()
    json.dump(pairs, open(os.path.join(HERE, "data", "gap_pairs.json"), "w", encoding="utf-8"), ensure_ascii=False)
    data = corpus_items(pairs)[:60000]
    from collections import Counter
    print(f"спорных слов {len(pairs)}, примеров {len(data)}, буквы {Counter(LETTERS[l] for _, l in data).most_common(6)}, {dev}",
          flush=True)
    tok = AutoTokenizer.from_pretrained(BASE)
    net = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=len(LETTERS),
                                                             ignore_mismatched_sizes=True).to(dev)
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
            if (i // bs) % 300 == 0:
                print(f"  шаг {i // bs}, {time.time() - t0:.0f} с", flush=True)
        print(f"эпоха {ep + 1}: потеря {tot / ((len(data) + bs - 1) // bs):.4f}, {time.time() - t0:.0f} с", flush=True)
    os.makedirs(OUT, exist_ok=True)
    net.save_pretrained(OUT)
    tok.save_pretrained(OUT)


_net = None


def choose(context, word, letters, margin=0.0):
    """-> the letter the net prefers among `letters` for «word» in `context`, or None if below the margin."""
    global _net
    if _net is None:
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _net = (AutoTokenizer.from_pretrained(OUT), AutoModelForSequenceClassification.from_pretrained(OUT).to(dev).eval(), dev)
    tok, net, dev = _net
    with torch.no_grad():
        p = net(**tok(context, truncation=True, max_length=96, return_tensors="pt").to(dev)).logits.softmax(-1)[0]
    sc = sorted(((float(p[L2I[c]]), c) for c in letters if c in L2I), reverse=True)
    if not sc or (len(sc) > 1 and sc[0][0] - sc[1][0] < margin):
        return None
    return sc[0][1]


def solve(q, margin):
    """Organ first; each ambiguous word -> the net picks the letter, written back as «зап[и]вать», up to 8 rounds."""
    work = q
    for _ in range(8):
        one = re.sub(r"\s+", " ", work).replace('"', "«")
        got = organ([f'ЗАДАНИЕ(9, "{one}")'])[0]
        m = re.match(r"^(\d+)", got)
        if m and not got.startswith("не знаю"):
            return m.group(1)
        a = re.search(r"ряд \d+: (\S*\.\.\S*): А ([^;]+); Б ([^;)]+)", got)
        if not a:
            return None
        word = a.group(1)
        lets = sorted({c.strip() for c in a.group(2).split(",")} & {c.strip() for c in a.group(3).split(",")} - {"∅"})
        if len(lets) < 2:
            return None
        cm = re.search(r"(\([^)]*\)\s*)?" + re.escape(word) + r"(\s*\([^)]*\))?", work)
        ctx = cm.group(0) if cm else word
        c = choose(ctx, word, lets, margin)
        if not c:
            return None
        work = work.replace(word, word.replace("..", f"[{c}]"), 1)
    return None


def evaluate():
    rows = bank912()
    B = rows[1::2]
    silent_before = [x for x in B if not re.match(r"^\d", organ([f'ЗАДАНИЕ(9, "{re.sub(chr(10), " ", x["q"]).replace(chr(34), "«")}")'])[0])]
    print(f"половина B: {len(B)} заданий, орган сам молчит в {len(silent_before)}")
    for margin in (0.0, 0.2, 0.5):
        ok = bad = 0
        for x in silent_before:
            a = solve(x["q"], margin)
            if a is None:
                continue
            right = set(a) == set(x["ans"].split("|")[0])
            ok += right
            bad += not right
        print(f"  отрыв {margin}: сеть помогла ответить на {ok + bad}, верно {ok} ({ok / max(1, ok + bad):.1%})")


if __name__ == "__main__":
    evaluate() if "--eval" in sys.argv else main()
