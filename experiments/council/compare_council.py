"""Which EGE Russian task numbers need the full council? (the author, 28.10: «оптимизируй, где тратим время зря»)
For the numbers the council answers now (2, 3, 6, 8, 22-26), N tasks of each from the explanations dataset (half B),
two ways: ONE call of the brain with short thinking (750 tokens, as task 1) vs the full council. Right answers and
seconds of each. Resumable: rows go to runs/compare_council.jsonl.
Usage (Open-LLM-VTuber venv, brain on :8080): ORGANS=words,units,russkiy python compare_council.py [n=8]"""
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "russkiy"))
import eval_brain  # noqa: E402
import task1  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
TASKS = [2, 3, 6, 8, 22, 23, 24, 25, 26]
ORDERED = {8, 22, 26}   # matching tasks: the order of the digits is the answer
OUT = os.path.join(HERE, "runs", "compare_council.jsonl")
SYS1 = ("Ты эксперт ЕГЭ по русскому языку. Реши задание: внимательно прочитай текст и условие, проверь каждый вариант. "
        "Последней строкой напиши: ОТВЕТ: <только ответ в той форме, которую требует задание — цифры без пробелов "
        "или слово>.")


def norm(s):
    return re.sub(r"[^0-9а-яa-z]", "", (s or "").lower().replace("ё", "е"))


def right(task, got, key):
    g = norm(got)
    for k in key.split("|"):
        k = norm(k)
        if not k or not g:
            continue
        if k.isdigit() and g.isdigit():
            if (g == k) if task in ORDERED else (sorted(g) == sorted(k)):
                return True
        elif g == k:
            return True
    return False


def tail(task, key):
    if all(norm(k).isdigit() for k in key.split("|")):
        return " Ответ дай одной строкой: цифры."
    return " Ответ дай одним словом (или словами), как требует задание."


def one_call(q):
    a = task1._think(SYS1, q)
    m = re.findall(r"ОТВЕТ:\s*(.+)", a)
    return m[-1].strip() if m else ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    task1.THINK = 750
    rows = [json.loads(l) for l in open(os.path.join(os.path.dirname(HERE), "russkiy", "data", "razbor.jsonl"),
                                        encoding="utf-8")]
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["id"] for l in open(OUT, encoding="utf-8")}
    system = eval_brain.neira_system()
    rng = random.Random(28)
    for t in TASKS:
        pool = [r for r in rows if r["task"] == t and r["half"] == "B" and len(r["q"]) > 40]
        for r in rng.sample(pool, min(N, len(pool))):
            if r["id"] in done:
                continue
            q = r["q"] + tail(t, r["ans"])
            t0 = time.time()
            a1 = one_call(q)
            s1 = time.time() - t0
            t0 = time.time()
            a, _ = eval_brain.answer_council(q, system)
            a2 = eval_brain.extract(q, a)
            s2 = time.time() - t0
            row = {"id": r["id"], "task": t, "key": r["ans"], "one": a1, "one_ok": right(t, a1, r["ans"]), "one_s": round(s1, 1),
                   "council": a2, "council_ok": right(t, a2, r["ans"]), "council_s": round(s2, 1)}
            open(OUT, "a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{t:2} {r['id']:>6} ключ {r['ans'][:14]:14} | один {a1[:14]:14} {'OK ' if row['one_ok'] else 'BAD'} {s1:5.0f} с"
                  f" | совет {a2[:14]:14} {'OK ' if row['council_ok'] else 'BAD'} {s2:5.0f} с", flush=True)
    report()


def report():
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    print("\nномер | один вызов: верно, с/задание | совет: верно, с/задание")
    for t in TASKS:
        rs = [r for r in rows if r["task"] == t]
        if rs:
            n = len(rs)
            print(f"{t:4} | {sum(r['one_ok'] for r in rs)}/{n}, {sum(r['one_s'] for r in rs) / n:.0f} с | "
                  f"{sum(r['council_ok'] for r in rs)}/{n}, {sum(r['council_s'] for r in rs) / n:.0f} с")


if __name__ == "__main__":
    report() if "--report" in sys.argv else main()
