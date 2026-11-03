"""Calibrate gramota.py on correct prose the net never saw (classics.jsonl past the first 6000 used by p_ege_cls6k,
puha.jsonl): clean sentences must stay unchanged; a dropped comma must come back; a stray comma must go.
Thresholds are picked on half 1 (criterion: fixed > broken, then most fixed) and reported on half 2."""
import json
import random
import re
import time

import gramota
import punct_organ

random.seed(1)
cls = [json.loads(l)["s"] for l in open("data/classics.jsonl", encoding="utf-8")][18000:]
puha = [json.loads(l).get("s") or json.loads(l).get("text", "") for l in open("data/puha.jsonl", encoding="utf-8")]
sents = [s for s in cls[:1500] + puha[:1500] if 5 <= len(s.split()) <= 40 and "\n" not in s]
random.shuffle(sents)
sents = sents[:1600]

# cache log-odds per sentence once; thresholds are applied offline
rows = []
t0 = time.time()
for s in sents:
    spans = [(m.start(), m.end()) for m in gramota.WORD.finditer(s)]
    if len(spans) < 3:
        continue
    gaps = [s[spans[i][1]:spans[i + 1][0]] for i in range(len(spans) - 1)]
    words = [s[a:b].lower() for a, b in spans]
    lo = punct_organ.comma_logodds(words)[:-1]
    rows.append((gaps, lo))
print(f"{len(rows)} предложений, {time.time() - t0:.0f} с ({(time.time() - t0) / len(rows) * 1000:.0f} мс на предложение)")


def score(part, add, drop):
    """-> (clean sentences changed, dropped commas restored, stray commas removed, wrong edits in damaged)"""
    false, fixed, broken = 0, 0, 0
    for gaps, lo in part:
        # clean: any edit is a false alarm
        e = sum(bool((re.fullmatch(r" +", g) and d is not None and d > add) or
                (re.fullmatch(r", ?", g) and d is not None and d < drop)) for g, d in zip(gaps, lo))
        false += e > 0
        commas = [i for i, g in enumerate(gaps) if re.fullmatch(r", ?", g)]
        spaces = [i for i, g in enumerate(gaps) if re.fullmatch(r" +", g)]
        if commas:   # damage 1: a comma dropped (the net saw the gap as space - the log-odds do not depend on it)
            i = random.Random(len(gaps)).choice(commas)
            fixed += bool(lo[i] is not None and lo[i] > add)
        if spaces:   # damage 2: a stray comma put into a space gap
            i = random.Random(len(gaps) + 7).choice(spaces)
            fixed += bool(lo[i] is not None and lo[i] < drop)
    return false, fixed


half = len(rows) // 2
best = None
for add in (2, 3, 4, 5, 6, 7, 8):
    for drop in (-2, -3, -4, -5, -6, -8):
        f, x = score(rows[:half], add, drop)
        if x > f and (best is None or x - f > best[0]):
            best = (x - f, add, drop)
        print(f"add {add} drop {drop}: ложных правок {f}, исправлено {x}")
_, add, drop = best
f, x = score(rows[half:], add, drop)
print(f"ВЫБРАНО add {add} drop {drop}; на второй половине ({len(rows) - half}): ложных правок {f}, исправлено {x}")
