"""The council v4.0 inside live Neira (29.10, plan step 15): the agent's dispatcher sends a task here (council_router)
with the organs' notes; the council's conclusion comes back as one more note, which Neira's brain says in her own
words - she does not solve it again aloud. Runs while the voice is parked (the agent's voice swap)."""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import council  # noqa: E402
from council_router import needs_council  # noqa: E402,F401  (the agent asks this first)

API = os.environ.get("BRAIN_API", "http://127.0.0.1:8080/v1/chat/completions")


def chat(messages, temperature=0.7, max_tokens=600, **extra):
    body = {"model": "brain", "messages": messages, "temperature": temperature, "max_tokens": max_tokens, **extra}
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = json.loads(op.open(req, timeout=600).read())
    return r["choices"][0]["message"].get("content") or "", r.get("usage", {})


def solve(text, notes):
    """-> (note for Neira or "", info)."""
    _, info = council.answer(text, "", chat, list(notes))
    concl, conf = info.get("conclusion", ""), info.get("confidence", "")
    why = ""
    for name in ("deep",):
        if info.get(name) and info[name][0] == concl:
            why = info[name][1]
    if not why:
        why = next((w for a, w in (info.get("specialists") or {}).values() if a == concl and w), "")
    if not concl:
        return ("(Ты обдумала задачу, но к выводу не пришла. Честно скажи, что не уверена, и коротко объясни, что "
                "сбивает.)"), info
    note = f"(Ты решила эту задачу: ответ — {concl}." + (f" Почему: {why}." if why else "")
    if conf == "низкая":
        note += " Ты в этом не до конца уверена — скажи это прямо."
    note += " Назови этот ответ и объясни коротко, в двух-трёх предложениях; не решай заново и не рассуждай вслух.)"
    return note, info
