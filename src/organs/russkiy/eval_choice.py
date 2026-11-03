"""Tasks 9-12 where the organ alone is silent: how often the brain's meaning choice (two wordings, must agree) lets the
organ answer, and how often that answer is right. The brain must run on 8080. Out: data/eval_choice.json.
Usage (russkiy/.venv): python eval_choice.py [limit]
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "council"))
import russkiy_dept as d  # noqa: E402
import urllib.request  # noqa: E402

API = "http://127.0.0.1:8080/v1/chat/completions"


def chat(messages, temperature=0, max_tokens=20):
    body = {"model": "brain", "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return r["choices"][0]["message"]["content"], r.get("usage", {})


def digits(s):
    return "".join(sorted(set(re.sub(r"\D", "", s or ""))))


bank = [x for x in json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8")) if 9 <= x["task"] <= 12]
silent = [x for x in bank if d.asks_russian(x["q"]) and d.russian_answer(x["q"])[0] is None]
limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(silent)
rows, t0 = [], time.time()
for i, x in enumerate(silent[:limit]):
    ans, trace = d.russian_answer(x["q"], chat)
    ok = None if ans is None else digits(ans) == digits(x["ans"].split("|")[0])
    rows.append({"id": x["id"], "task": x["task"], "ans": x["ans"], "got": ans, "ok": ok, "trace": trace})
    if (i + 1) % 25 == 0:
        a = [r for r in rows if r["ok"] is not None]
        print(f"{i + 1}/{limit}: ответил {len(a)}, верно {sum(r['ok'] for r in a)}, {time.time() - t0:.0f} с", flush=True)
json.dump(rows, open(os.path.join(HERE, "data", "eval_choice.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
a = [r for r in rows if r["ok"] is not None]
print(f"итого: молчавших {len(rows)}, с выбором мозга ответил {len(a)}, верно {sum(r['ok'] for r in a)}, "
      f"{time.time() - t0:.0f} с")
