"""The russkiy organ alone on the bank of real EGE tasks (bank_build.py): how many it answers (coverage) and how many of
its answers are right (precision - the goal is 98-100%). Answers are digit sets: «125» = «1, 2, 5» = «521».
Out: data/eval_<tasks>.json and a short table. Usage: python eval_bank.py [tasks=4,9,10,11,12] [--wrong]
"""
import collections
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "russkiy.exe")
TASKS = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 and sys.argv[1][0].isdigit() else [4, 9, 10, 11, 12]
SHOW = "--wrong" in sys.argv


def digits(s):
    return "".join(sorted(set(re.sub(r"\D", "", s))))


def main():
    path = os.environ.get("BANK", os.path.join(HERE, "data", "bank.json"))
    bank = [x for x in json.load(open(path, encoding="utf-8")) if x["task"] in TASKS]
    calls = []
    for x in bank:
        q = re.sub(r"\s+", " ", x["q"]).replace('"', "«")
        calls.append(f'ЗАДАНИЕ({x["task"]}, "{q}")')
    t = time.time()
    out = subprocess.run([EXE], input="\n".join(calls) + "\n", capture_output=True, text=True, encoding="utf-8")
    dt = time.time() - t
    lines = out.stdout.splitlines()
    assert len(lines) == len(calls), (len(lines), len(calls), out.stderr[:500])
    stat = collections.defaultdict(collections.Counter)
    rows = []
    for x, line in zip(bank, lines):
        got = line.rsplit(" = ", 1)[1]
        single = "один источник" in got
        if got.startswith("не знаю") or got.startswith("ошибка"):
            verdict = "молчит"
        else:
            verdict = "верно" if digits(got.split(" (")[0]) == digits(x["ans"]) else "НЕВЕРНО"
        stat[x["task"]][verdict] += 1
        stat[x["task"]]["один источник"] += single
        rows.append({"id": x["id"], "task": x["task"], "ans": x["ans"], "got": got, "verdict": verdict, "q": x["q"]})
        if SHOW and verdict != "верно":
            print(f'{x["task"]} {x["id"]} {verdict}: ждали {x["ans"]}, орган {got}\n   {x["q"][:300]}')
    json.dump(rows, open(os.path.join(HERE, "data", f"eval_{'_'.join(map(str, TASKS))}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{'задание':>8} {'всего':>6} {'ответил':>8} {'верно':>6} {'точность':>9} {'охват':>6}  (один источник)")
    tot = collections.Counter()
    for t in TASKS:
        s = stat[t]
        n, ok, bad = sum(s[k] for k in ("верно", "НЕВЕРНО", "молчит")), s["верно"], s["НЕВЕРНО"]
        tot.update({"n": n, "ok": ok, "bad": bad})
        prec = ok / (ok + bad) if ok + bad else 0
        print(f"{t:>8} {n:>6} {ok + bad:>8} {ok:>6} {prec:>8.1%} {(ok + bad) / n:>6.0%}  ({s['один источник']})")
    n, ok, bad = tot["n"], tot["ok"], tot["bad"]
    print(f"{'итого':>8} {n:>6} {ok + bad:>8} {ok:>6} {ok / max(1, ok + bad):>8.1%} {(ok + bad) / max(1, n):>6.0%}"
          f"   время {dt:.2f} с на {n} заданий")


if __name__ == "__main__":
    main()
