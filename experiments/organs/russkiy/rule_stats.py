"""Precision of every rule of tasks 13-15 at item level, on half A of the new tasks (half B stays untouched for the
final measurement). Item truth: task 13 - item n is in the answer <=> it is written the asked way; task 15 - marker k
in the answer <=> НН (or Н, as asked); task 14 - known only for rows in the answer (every word the asked way) and
rows with one highlighted word.
Usage: python rule_stats.py [A|B]   ->  per rule: right / answered, and the wrong examples
"""
import collections
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HALF = sys.argv[1] if len(sys.argv) > 1 else "A"
test = json.load(open(os.path.join(HERE, "data", "bank_13_15_test.json"), encoding="utf-8"))
half = [x for i, x in enumerate(sorted(test, key=lambda x: int(x["id"]))) if (i % 2 == 0) == (HALF == "A")]
json.dump(half, open(os.path.join(HERE, "data", f"bank_13_15_{HALF}.json"), "w", encoding="utf-8"), ensure_ascii=False)

def one_line(q):
    return re.sub(r"\s+", " ", q).replace('"', "«")


calls = [f'РАЗБОР({x["task"]}, "{one_line(x["q"])}")' for x in half]
out = subprocess.run([os.path.join(HERE, "russkiy.exe")], input="\n".join(calls) + "\n", capture_output=True,
                     text=True, encoding="utf-8", env={**os.environ, "RUSSKIY_OFF": ""}).stdout.splitlines()
stat = collections.defaultdict(lambda: [0, 0])
bad = collections.defaultdict(list)
for x, line in zip(half, out):
    res = line.rsplit(" = ", 1)[1]
    ans = set(re.sub(r"\D", "", x["ans"].split("|")[0]))
    head = x["q"][:x["q"].find("1)")] if x["task"] != 15 else x["q"][:x["q"].find("(1)")]
    for part in res.split("; "):
        if not part.strip():
            continue
        k, v, rule = part.split(":")
        if rule == "-" or v in ("-1", "?"):
            continue
        if x["task"] == 13:
            want_together = "СЛИТНО" in head
            truth_together = (k in ans) == want_together
            ok = (v == "1") == truth_together
        elif x["task"] == 15:
            want_nn = "НН" in head[head.find("пишется"):]
            truth_nn = (k in ans) == want_nn
            ok = (v == "1") == truth_nn
        else:
            want = "D" if "ДЕФИС" in head else "R" if "РАЗДЕЛЬНО" in head else "S"
            row_parts = [p for p in res.split("; ") if p.startswith(k + ":")]
            if k in ans:
                ok = v == want
            elif len(row_parts) == 1:
                ok = v != want
            else:
                continue
        stat[(x["task"], rule)][0] += ok
        stat[(x["task"], rule)][1] += 1
        if not ok:
            bad[(x["task"], rule)].append(f'{x["id"]} п.{k} -> {v}: ' + re.sub(r"\s+", " ", x["q"])[100:260])
for key in sorted(stat):
    r, n = stat[key]
    print(f"{key[0]} {key[1]:>5}: {r:>3}/{n:<3} {r / n:6.1%}")
if "--bad" in sys.argv:
    for key in sorted(bad):
        print("\n==", key)
        for b in bad[key][:6]:
            print("  ", b)
