"""Thresholds for punct_net.py scores: a task is answered only if every place (every word for task 16) is decisive -
log-odds > HI comma, < LO none. Chosen on half A (best coverage with >=98% right), checked on half B.
Usage: python net_eval.py RUPunct_big 16 17 18 19 20
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHORT = sys.argv[1]


def truth(ans):
    return set(ans.split("|")[0])


def decide(r, hi, lo):
    """-> predicted set of digits, or None (not sure)."""
    if "sent" in r:      # task 16: sentences with exactly one comma
        got = set()
        for i, vals in r["sent"]:
            if any(lo <= v <= hi for v in vals):
                return None
            if sum(v > hi for v in vals) == 1:
                got.add(str(i))
        return got
    got = set()
    for k, d in r["scores"]:
        if d is None:
            return None
        if d > hi:
            got.add(str(k))
        elif d >= lo:
            return None
    return got


def run(rows, hi, lo):
    ok = bad = 0
    for r in rows:
        g = decide(r, hi, lo)
        if g is None:
            continue
        ok += g == truth(r["ans"])
        bad += g != truth(r["ans"])
    return ok, bad


for t in [a for a in sys.argv[2:] if not a.startswith("--")]:
    rows = sorted(json.load(open(os.path.join(HERE, "data", f"net_{SHORT}_{t}.json"), encoding="utf-8")),
                  key=lambda r: int(r["id"]))
    A, B = rows[0::2], rows[1::2]
    if "--Bonly" in sys.argv:   # a net trained on half A: thresholds on one half of B, the check on the other
        rows = B
        A, B = B[0::2], B[1::2]
    s0 = run(rows, 0, 0)
    best = None
    for hi in [x / 2 for x in range(-4, 25)]:
        for lo in [-x / 2 for x in range(0, 25)]:
            if lo > hi:
                continue
            ok, bad = run(A, hi, lo)
            if ok + bad and bad / (ok + bad) <= 0.02 and (best is None or ok > best[0]):
                best = (ok, bad, hi, lo)
    line = f"{SHORT} {t}: всего {len(rows)}, без порогов {s0[0]}/{len(rows)} = {s0[0] / len(rows):.0%}"
    if best:
        ok, bad, hi, lo = best
        okB, badB = run(B, hi, lo)
        line += (f" | пороги HI {hi} LO {lo}: A {ok}/{ok + bad} (охват {(ok + bad) / len(A):.0%}), "
                 f"B {okB}/{okB + badB} = {okB / max(1, okB + badB):.1%} (охват {(okB + badB) / len(B):.0%})")
    else:
        line += " | на A нет порогов с 98%"
    print(line)
