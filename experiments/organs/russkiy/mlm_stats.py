"""Margins for eval_mlm.py: an item is decided when the best spelling wins by more than MARGIN, else «не знаю».
Item level (13, 15) and row level (14); the margin is chosen on half A (best coverage with >=98% right) and checked on
half B. Usage: python mlm_stats.py 13 15 14
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def item_pairs(t, recs):
    """-> [(margin, right?)] per decided-able item."""
    out = []
    for r in recs:
        for it in r["rows"]:
            if it.get("skip"):
                continue
            if t == 13:
                a, b, truth = it["S"], it["R"], it["truth"]
                best = "S" if a > b else "R"
            elif t == 15:
                a, b, truth = it["NN"], it["N"], it["truth"]
                best = "NN" if a > b else "N"
            out.append((abs(a - b), best == truth))
    return out


def task_level(t, recs, m):
    """Whole task answered only when every item is decided: -> (right, wrong)."""
    ok = bad = 0
    for r in recs:
        items = [it for it in r["rows"] if not it.get("skip")]
        if t == 14:
            decided, good = True, True
            for row in r["rows"]:
                kinds = []
                for c in row["comps"]:
                    s = sorted(c.items(), key=lambda kv: -kv[1])
                    if len(s) > 1 and s[0][1] - s[1][1] < m:
                        kinds.append(None)
                    else:
                        kinds.append(s[0][0])
                if not kinds:
                    decided = False
                    break
                known_bad = any(k is not None and k != row["want"] for k in kinds)
                if known_bad:
                    good &= not row["row_ok"]
                elif None in kinds:
                    decided = False
                    break
                else:
                    good &= row["row_ok"]
            if not decided:
                continue
            ok += good
            bad += not good
            continue
        pairs = item_pairs(t, [{"rows": items}])
        if len(pairs) != len(items) or any(mg < m for mg, _ in pairs):
            continue
        right = all(g for _, g in pairs)
        ok += right
        bad += not right
    return ok, bad


for t in [int(a) for a in sys.argv[1:]]:
    recs = sorted(json.load(open(os.path.join(HERE, "data", f"mlm_{t}.json"), encoding="utf-8")), key=lambda r: int(r["id"]))
    A, B = recs[0::2], recs[1::2]
    if t != 14:
        pa = item_pairs(t, A)
        print(f"\n== {t}: пунктов A {len(pa)}, верно без порога {sum(g for _, g in pa) / len(pa):.1%}")
    best = None
    for m in [x / 4 for x in range(0, 61)]:
        ok, bad = task_level(t, A, m)
        if ok + bad and bad / (ok + bad) <= 0.02 and (best is None or ok > best[0]):
            best = (ok, bad, m)
    ok0, bad0 = task_level(t, recs, 0)
    print(f"   задания без порога: {ok0}/{ok0 + bad0}")
    if best:
        ok, bad, m = best
        okB, badB = task_level(t, B, m)
        print(f"   порог {m}: A {ok}/{ok + bad} (охват {(ok + bad) / len(A):.0%}); "
              f"B {okB}/{okB + badB} = {okB / max(1, okB + badB):.1%} (охват {(okB + badB) / len(B):.0%})")
    else:
        print("   на A нет порога с 98%")
