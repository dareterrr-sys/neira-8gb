"""EGE Russian exam by task number (the author, 31.10: «сделай, чтобы она ЕГЭ на 95+% решала»): N fresh tasks of each
number 1-26 from the explanations dataset, the live route (organ by code -> one call with short thinking), per number:
right answers, seconds, and where the answer came from. Two sets, never mixed:
  dev  - half A (tuning allowed: look at single answers, change prompts and budgets);
  test - half B without the 72 tasks of compare_council and variant №15 (sealed: only the per-number totals are looked
         at, run once per finished version).
Resumable: rows go to runs/ege_exam_<set>_<tag>.jsonl.
Usage (Open-LLM-VTuber venv, brain on :8080): ORGANS=words,units,russkiy python ege_exam.py <dev|test> <tag> [n=8]
       python ege_exam.py <dev|test> <tag> --report"""
import json
import os
import random
import re
import sys
import time

os.environ.setdefault("ORGANS", "words,units,russkiy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "russkiy"))
_argv, sys.argv = sys.argv, sys.argv[:1]   # compare_council reads its own argv on import
import compare_council  # noqa: E402  (grading: digits in any order, matching tasks in order)
sys.argv = _argv
import eval_brain  # noqa: E402
import ege_one  # noqa: E402

SET, TAG = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 8
# a set may also be a question file (31.10: the sealed exam written for this test, D:\AI\datasets\ege_sealed)
FILE = SET if SET.endswith(".json") else None
if FILE:
    SET = "sealed_" + os.path.splitext(os.path.basename(FILE))[0]
OUT = os.path.join(HERE, "runs", f"ege_exam_{SET}_{TAG}.jsonl")
# EGE_TASKS=8,22 - only these numbers (tuning one chapter at a time on dev)
TASKS = [int(x) for x in os.environ["EGE_TASKS"].split(",")] if os.environ.get("EGE_TASKS") else list(range(1, 27))


def pick():
    if FILE:   # the items carry their own answer tail
        return [dict(r, tail="") for r in json.load(open(FILE, encoding="utf-8")) if r["task"] in TASKS]
    rows = [json.loads(l) for l in open(os.path.join(os.path.dirname(HERE), "russkiy", "data", "razbor.jsonl"),
                                        encoding="utf-8")]
    used = {json.loads(l)["id"] for l in open(os.path.join(HERE, "runs", "compare_council.jsonl"), encoding="utf-8")}
    half = "A" if SET == "dev" else "B"
    rng = random.Random(31)
    out = []
    for t in TASKS:
        pool = sorted((r for r in rows if r["task"] == t and r["half"] == half and r["id"] not in used
                       and len(r["q"]) > 40), key=lambda r: r["id"])
        out += rng.sample(pool, min(N, len(pool)))
    return out


def solve(q):
    """The live route. -> (answer, route)."""
    first = eval_brain.russian_first(q)
    if first:
        return re.sub(r"^Итог:\s*|\.$", "", first[0]), "organ"   # «1, 2, 5»: grading drops the commas
    # 14 of 208 tasks are not recognised by the FIPI wordings (live Neira would send them to the council or to chat):
    # they are solved the same way and marked, so the router and the solving are counted apart
    return ege_one.answer(q), "one" if ege_one.is_ege_ru(q) else "unrec"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["id"] for l in open(OUT, encoding="utf-8")}
    for r in pick():
        if r["id"] in done:
            continue
        t = r["task"]
        q = r["q"] + r.get("tail", compare_council.tail(t, r["ans"]))
        t0 = time.time()
        a, route = solve(q)
        s = time.time() - t0
        ok = compare_council.right(t, a, r["ans"])
        row = {"id": r["id"], "task": t, "key": r["ans"], "got": a, "ok": ok, "route": route, "s": round(s, 1)}
        open(OUT, "a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
        if SET == "dev":   # the test set is sealed: no single answers on screen
            print(f"{t:2} {r['id']:>6} ключ {r['ans'][:16]:16} | {a[:16]:16} {'OK ' if ok else 'BAD'} {route:5} {s:5.0f} с",
                  flush=True)
        else:
            print(f"{t:2} {'.' if ok else 'x'}", flush=True)
    report()


def report():
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    print(f"\n{SET} {TAG}: номер | верно | с/задание | код")
    for t in TASKS:
        rs = [r for r in rows if r["task"] == t]
        if rs:
            print(f"{t:4} | {sum(r['ok'] for r in rs)}/{len(rs)} | {sum(r['s'] for r in rs) / len(rs):4.0f} | "
                  f"{sum(r['route'] == 'organ' for r in rs)}")
    n, ok = len(rows), sum(r["ok"] for r in rows)
    print(f"ИТОГО {ok}/{n} = {100 * ok / max(n, 1):.1f}%, {sum(r['s'] for r in rows) / 60:.0f} мин; "
          f"не узнаны роутером {sum(r['route'] == 'unrec' for r in rows)} (верно из них "
          f"{sum(r['ok'] for r in rows if r['route'] == 'unrec')})")


if __name__ == "__main__":
    report() if "--report" in sys.argv else main()
