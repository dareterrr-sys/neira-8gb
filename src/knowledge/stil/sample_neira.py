"""Neira's answers to everyday prompts (prompts_neira.json), the way she answers live (persona + the Live2D prompt,
no thinking), scored by the stylistic filter. Step 1 of the «живая речь» plan: how much officialese and assistant
cliché is in her now. Resumable: rows go to runs/<tag>.jsonl.
Usage (Open-LLM-VTuber venv, brain on :8080): python sample_neira.py <tag> [repeats=1]   |   ... <tag> --report"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "council")]
import stil  # noqa: E402

TAG = sys.argv[1]
REPEATS = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
OUT = os.path.join(HERE, "runs", f"{TAG}.jsonl")


def clean(a):
    """What she says aloud: no emotion tags [joy], mood marks {задумчиво}, sound tags."""
    return re.sub(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>", "", a).strip()


def main():
    import eval_brain
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    system = eval_brain.neira_system()
    prompts = json.load(open(os.path.join(HERE, "prompts_neira.json"), encoding="utf-8"))
    done = set()
    if os.path.exists(OUT):
        done = {(r["q"], r["rep"]) for r in map(json.loads, open(OUT, encoding="utf-8"))}
    for rep in range(REPEATS):
        for cat, qs in prompts.items():
            for q in qs:
                if (q, rep) in done:
                    continue
                t0 = time.time()
                a, _ = eval_brain.chat([{"role": "system", "content": system}, {"role": "user", "content": q}],
                                       temperature=0.7, max_tokens=600)
                c = stil.check(clean(a))
                row = {"cat": cat, "q": q, "rep": rep, "a": a, "score": c["score"], "words": c["words"],
                       "hits": c["hits"], "s": round(time.time() - t0, 1)}
                open(OUT, "a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"{c['score']:5.1f} {cat[:10]:10} {q[:40]:40} | {[h[1] for h in c['hits']][:4]}", flush=True)
    report()


def report():
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    words = sum(r["words"] for r in rows)
    hits = [h for r in rows for h in r["hits"]]
    print(f"\n{TAG}: {len(rows)} ответов, {words} слов, {len(hits)} мест = {100 * len(hits) / max(words, 1):.2f} на 100 слов "
          f"(классика 0.24); ответов хотя бы с одним местом: {sum(bool(r['hits']) for r in rows)}/{len(rows)}")
    print("по видам:", {stil.KINDS[k]: sum(h[0] == k for h in hits) for k in stil.KINDS})
    cats = {}
    for r in rows:
        cats.setdefault(r["cat"], []).append(r)
    for cat, rs in cats.items():
        w = sum(r["words"] for r in rs)
        print(f"  {cat:18} {100 * sum(len(r['hits']) for r in rs) / max(w, 1):5.2f} на 100 слов, {w / len(rs):4.0f} слов в ответе")
    from collections import Counter
    print("частые:", Counter(h[1].lower() for h in hits).most_common(20))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    report() if "--report" in sys.argv else main()
