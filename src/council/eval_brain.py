"""Hard-question test of Neira's brain: each question in its own conversation, the way Neira answers now (persona +
the Live2D prompt + the dispatcher's clock and calculator notes), then a strict persona-free request extracts the final
answer and it is checked against the expected pattern (hard_questions.json).
Usage (Open-LLM-VTuber venv, brain on :8080): python eval_brain.py <out.json> [mode=neira] [repeats=1]
"""
import json
import os
import re
import sys
import time
import urllib.request

os.environ.setdefault("NEIRA_MEMORY", "0")      # the test must not write to or read from Neira's memory
OLV = r"D:\AI\Open-LLM-VTuber"
sys.path[:0] = [os.path.join(OLV, "src"), OLV]
import yaml  # noqa: E402
from open_llm_vtuber.agent.agents import basic_memory_agent as agent  # noqa: E402
from prompts import prompt_loader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.environ.get("BRAIN_API", "http://127.0.0.1:8080/v1/chat/completions")
EXTRACT = ("Тебе дан вопрос и чей-то ответ на него. Выпиши итоговый ответ из этого текста максимально коротко: одним числом "
           "цифрами (без единиц измерения) или одним-тремя словами. Если в ответе отвергается ложная посылка вопроса или "
           "говорится «не знаю», перескажи это в трёх-пяти словах. Ничего не добавляй от себя.")


def chat(messages, temperature=0.7, max_tokens=600, **extra):
    body = {"model": "brain", "messages": messages, "temperature": temperature, "max_tokens": max_tokens, **extra}
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    for attempt in range(3):   # v2.3's first run died on one reset connection after 14 questions
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=900).read())
            break
        except (ConnectionError, urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise
            print(f"  (brain request failed: {e}; retrying)", flush=True)
            time.sleep(10)
    return r["choices"][0]["message"].get("content") or "", r.get("usage", {})


def neira_system():
    conf = yaml.safe_load(open(os.path.join(OLV, "conf.yaml"), encoding="utf-8"))
    live = prompt_loader.load_util("live2d_expression_prompt").replace(
        "[<insert_emomap_keys>]", "[neutral], [joy], [anger], [sadness], [surprise], [smirk], [disgust]")
    return conf["character_config"]["persona_prompt"] + live


def dispatcher_notes(text):
    """The same notes BasicMemoryAgent._dispatch adds (clock, calculator, calendar, letters; memory is off in tests)."""
    notes = []
    if agent.asks_time(text):
        notes.append("Справка часов: " + agent._now_ru() + ".")
    # 29.10: COUNCIL_CALC=0 - no calculator note before the council (live Neira skips it on council turns: 10-14 s,
    # and on «24 яблока, треть съели» it said 15); 1 - as before
    if agent.needs_calculator(text) and os.environ.get("COUNCIL_CALC", "1") != "0":
        exprs = [chat([{"role": "system", "content": p}, {"role": "user", "content": text}], temperature=0, max_tokens=m)[0]
                 for p, m in agent.MATH_ROUTES]
        note = agent.math_note(*exprs)
        if note:
            notes.append(note)
    if agent.CALENDAR and agent.CALENDAR.asks_calendar(text):
        calls = [chat([{"role": "system", "content": p}, {"role": "user", "content": text}], temperature=0, max_tokens=m)[0]
                 for p, m in agent.CALENDAR.CALENDAR_ROUTES]
        note = agent.CALENDAR.calendar_note(*calls)
        if note:
            notes.append(note)
    # organs under test (25.10): words (slova.exe) and units (edinicy.exe); ORGANS=words,units turns them on
    organs = os.environ.get("ORGANS", "")
    if "words" in organs or "units" in organs:
        sys.path.insert(0, os.path.dirname(HERE))
        import edinicy_dept
        import slova_dept
        for flag, dept, asks, routes, note_fn in (
                ("words", slova_dept, slova_dept.asks_words, slova_dept.SLOVA_ROUTES, slova_dept.words_note),
                ("units", edinicy_dept, edinicy_dept.asks_units, edinicy_dept.EDINICY_ROUTES, edinicy_dept.units_note)):
            if flag in organs and asks(text):
                calls = [chat([{"role": "system", "content": p}, {"role": "user", "content": text}], temperature=0,
                              max_tokens=m)[0] for p, m in routes]
                note = note_fn(*calls)
                if note:
                    notes.append(note)
    if agent.LETTERS and agent.LETTERS.asks_letters(text):
        calls = [chat([{"role": "system", "content": p}, {"role": "user", "content": text}], temperature=0, max_tokens=m)[0]
                 for p, m in agent.LETTERS.LETTERS_ROUTES]
        note = agent.LETTERS.letters_note(*calls)
        if note:
            notes.append(note)
    return notes


def answer_neira(q, system):
    q = agent.perceive(q)   # as the live dispatcher does (NEIRA_PERCEPTION=0: off)
    notes = dispatcher_notes(q)
    user = q + ("\n\n(" + " ".join(notes) + ")" if notes else "")
    text, usage = chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    return text, notes


def answer_one(q, system):
    """28.10: one call with short thinking (750 tokens, then «time is up»), with the organs' notes - is the council
    worth its 3x time on other questions too? (on EGE Russian it was not: 62% vs 49%)."""
    first = russian_first(q)
    if first:
        return first
    q = agent.perceive(q)
    notes = dispatcher_notes(q)
    user = q + ("\n\n(" + " ".join(notes) + ")" if notes else "")
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "russkiy"))
    import task1
    task1.THINK = int(os.environ.get("ONE_THINK", "750"))
    a = task1._think(system + "\nЕсли нужно, кратко подумай. Последней строкой: ОТВЕТ: <итог>.", user)
    return a, {"notes": notes}


def answer_think(q, system):
    """The same, but the brain thinks first (Qwen3.6 hybrid thinking, switched on per request)."""
    q = agent.perceive(q)
    notes = dispatcher_notes(q)
    user = q + ("\n\n(" + " ".join(notes) + ")" if notes else "")
    body = {"model": "brain", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7, "max_tokens": int(os.environ.get("THINK_MAX", "6000")),
            "chat_template_kwargs": {"enable_thinking": True}}
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    m = r["choices"][0]["message"]
    return m.get("content") or "", {"notes": notes, "think_chars": len(m.get("reasoning_content") or ""),
                                    "tokens": r.get("usage", {}).get("completion_tokens"),
                                    "finish": r["choices"][0].get("finish_reason")}


def russian_first(q):
    """ORGANS=...,russkiy (27.10): an EGE Russian task the organ is sure of is answered by code, like the calculator -
    the organ's answer IS the answer, said the way the council's mouth says a number. None - the brain answers."""
    if "russkiy" not in os.environ.get("ORGANS", ""):
        return None
    sys.path.insert(0, os.path.dirname(HERE))
    import russkiy_dept
    # meaning choices by the brain: 75/81 = 92.6% on the bank - above the brain solving the whole task, on since
    # 28.10 (RUSSKIY_CHOICE=0 - off)
    ans, trace = russkiy_dept.russian_answer(q, chat if os.environ.get("RUSSKIY_CHOICE", "1") != "0" else None)
    if not ans:
        return None
    return "Итог: " + (", ".join(ans) if ans.isdigit() else ans) + ".", {"russkiy": trace}   # 7: a word, not digits


def answer_council(q, system):
    first = russian_first(q)
    if first:
        return first
    sys.path.insert(0, HERE)
    import ege_one
    if os.environ.get("EGE_ONE", "1") != "0" and ege_one.is_ege_ru(q):
        # 28.10: an EGE Russian task the organ left goes to one call with short thinking, not to the council
        # (72 past tasks: one call 62% vs council 49%, ~31 s vs ~95 s). EGE_ONE=0 - the council as before
        ans = ege_one.answer(q)
        return ("Итог: " + ans + "." if ans else "Не знаю."), {"ege_one": ans}
    q = agent.perceive(q)
    sys.path.insert(0, HERE)
    import council
    return council.answer(q, system, chat, dispatcher_notes(q), int(os.environ.get("THINK_MAX", "6000")))


def extract(q, a):
    return chat([{"role": "system", "content": EXTRACT}, {"role": "user", "content": f"Вопрос: {q}\nОтвет: {a}"}],
                temperature=0, max_tokens=40)[0].strip()


def norm(s):
    s = s.lower().replace("ё", "е").strip()
    s = re.sub(r"[«»\"'`*_]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .!?")


def readings(final):
    """The short answer and its other spellings: a fraction as a decimal ("9/25" -> "0.36", "0,36"), a number said in
    words as digits ("шесть долларов" -> "6"). Step 12 diagnosis: 4 of 32 council "errors" were right answers the
    grader did not read (e009t 9/25, e026o 9/8, e026t 9/4, g079 «шесть долларов»)."""
    out = [norm(final)]
    m = re.match(r"^\s*(-?\d+)\s*/\s*(\d+)\s*$", final or "")
    if m and int(m.group(2)):
        v = f"{int(m.group(1)) / int(m.group(2)):.6f}".rstrip("0").rstrip(".")
        out += [v, v.replace(".", ",")]
    if not re.search(r"\d", final or ""):
        sys.path.insert(0, os.path.dirname(HERE))
        import perception
        nums = perception.numbers_said(final or "")
        if len(nums) == 1:   # one number named: «шесть долларов»; several - no single reading
            out.append(f"{next(iter(nums)):g}")
    return out


def correct(item, final, full):
    """Each "|" alternative on its own: one anchored at the start ("^12") must match the extracted final answer
    (in any of its readings); an unanchored one (a word: "не перел", "au") may also match the whole answer."""
    finals = readings(final)
    for alt in item["ans"].replace("ё", "е").split("|"):
        if any(re.search(alt, f) for f in finals) or (not alt.startswith("^") and re.search(alt, norm(full))):
            return True
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "neira"
    repeats = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    # QSET: hard_questions.json (the anchor set, default), work_questions.json, sealed_exam.json (final exam only)
    items = json.load(open(os.path.join(HERE, os.environ.get("QSET", "hard_questions.json")), encoding="utf-8"))
    if mode == "regrade":   # check saved answers again with the current patterns, no brain calls
        by_id = {it["id"]: it for it in items}
        rows = json.load(open(out, encoding="utf-8"))
        for r in rows:
            r["ans"] = by_id[r["id"]]["ans"]
            r["ok"] = correct(r, r["final"], r["answer"])
        report(rows, out, "regrade")
        return
    system = neira_system()
    answer = {"neira": answer_neira, "think": answer_think, "council": answer_council, "one": answer_one}[mode]
    rows = []
    for item in items:
        for k in range(repeats):
            t = time.time()
            a, info = answer(item["q"], system)
            final = extract(item["q"], a)
            ok = correct(item, final, a)
            rows.append({**item, "k": k, "answer": a, "final": final, "ok": ok, "info": info, "s": round(time.time() - t, 1)})
            print(f"{'OK ' if ok else 'BAD'} {item['id']} {rows[-1]['s']:5.1f}s | {final[:40]:40} | {a[:90]!r}", flush=True)
    report(rows, out, mode)


# the user's rule: an honest "I don't know" is fine, only a confident wrong answer is a real error
ABSTAIN = re.compile(r"не знаю|не уверен|не могу (точно |с уверенностью )?(сказать|знать|ответить)|затрудняюсь|"
                     r"нет (однозначного|единого|точного) ответа|понятия не имею|не берусь", re.I)


def report(rows, out, mode):
    for r in rows:
        r["abstain"] = (not r["ok"]) and bool(ABSTAIN.search(r.get("answer", "")))
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cats = {}
    for r in rows:
        cats.setdefault(r["cat"], []).append(r)
    ok = sum(r["ok"] for r in rows)
    honest = sum(r["abstain"] for r in rows)
    print("\nRESULT", mode, f"{ok}/{len(rows)} right, {honest} honest 'не знаю', {len(rows) - ok - honest} confidently wrong",
          "| wrong:", " ".join(r["id"] + ("?" if r["abstain"] else "") for r in rows if not r["ok"]))
    for c, v in cats.items():
        print(f"  {c:17} {sum(r['ok'] for r in v)}/{len(v)}" + (f"  (+{sum(r['abstain'] for r in v)} не знаю)" if any(r['abstain'] for r in v) else ""))


if __name__ == "__main__":
    main()
