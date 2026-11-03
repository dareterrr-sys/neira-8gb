"""Neira's Russian department (the author, 27.10: «чтобы ЕГЭ по русскому норм прошло», «огромный словарный запас»,
«органы на C++»): EGE Russian tasks that a dictionary decides - stress (task 4), the missing letter (9-12), Н/НН (15) -
are solved by the C++ organ russkiy.exe (D:\\AI\\neira-tools\\russkiy) over OpenCorpora, Hunspell, RUAccent and the
FIPI orthoepic list. The organ answers only when its routes agree; on the bank of 1122 real tasks it gave 499/499 right
answers. Where a word has two real spellings and the meaning decides («зап..вать (водой)»: запивать / запевать), the
brain chooses between the two whole words - it is bad at letters but good at meaning - by two differently worded
questions; only an agreeing choice goes back to the organ («зап[и]вать»).

When the organ is sure, its answer IS the answer (like the calculator): the brain only says it.
"""
import os
import re
import subprocess

RUSSKIY = os.environ.get("NEIRA_RUSSKIY", r"D:\AI\neira-tools\russkiy\russkiy.exe")

# the FIPI wordings (they never change: «Осмыслите суть задания (оно имеет всегда одинаковую формулировку!)»)
_TASKS = (
    (4, re.compile(r"верно выделена буква, обозначающая ударный гласный", re.I)),
    (15, re.compile(r"на месте которой\(?-?ых\)? пишется (одна буква )?НН?\b|пишется одна буква Н\b|пишется НН\b")),
    (9, re.compile(r"(во всех словах|в обоих словах|во всех) одного ряда пропущена одна и та же буква", re.I)),
    (16, re.compile(r"нужно поставить ОДНУ запятую")),
    (17, re.compile(r"на месте которой\(?-?ых\)?\s*должна\(?-?ы\)?\s*стоять запят", re.I)),
    (13, re.compile(r"НЕ( \(НИ\))? с выделенным словом пишется (СЛИТНО|РАЗДЕЛЬНО)")),
    (7, re.compile(r"выделенных ниже слов допущена (грамматическая )?ошибка", re.I)),
    (5, re.compile(r"подобрав к выделенному слову пароним", re.I)),
    (1, re.compile(r"Самостоятельно подберите .{0,80}на месте пропуска", re.S)),
    (14, re.compile(r"все выделенные слова пишутся (СЛИТНО|РАЗДЕЛЬНО|ЧЕРЕЗ ДЕФИС)")),
    (21, re.compile(r"Найдите предложения, в которых (тире|запят|двоеточие).{0,90}?правилом пунктуации", re.S)),
)


def asks_russian(text):
    """EGE task number (4, 9-12, 15) by its standard wording, else 0. 9-12 share the wording: 9 stands for all."""
    text = text or ""
    for n, rx in _TASKS:
        if rx.search(text.replace("⁠", "")) and (n in (1, 5, 7) or re.search(r"\b1\)|\(1\)", text)):   # no numbers
            return n
    return 0


def organ(calls):
    """['ЗАДАНИЕ(4, "...")', ...] -> answers (one russkiy.exe run)."""
    out = subprocess.run([RUSSKIY], input=("\n".join(calls) + "\n").encode("utf-8"), capture_output=True, timeout=60)
    return [line.rsplit(" = ", 1)[-1].strip() for line in out.stdout.decode("utf-8", errors="replace").splitlines()]


def _call(n, text):
    one = re.sub(r"\s+", " ", text).replace('"', "«")
    return f'ЗАДАНИЕ({n}, "{one}")'


# «ряд 2: зап..вать: А е,и; Б е,и» -> word with the gap and the letters both dictionaries allow
_AMBIG = re.compile(r"ряд \d+: (\S*\.\.\S*): А ([^;]+); Б ([^;)]+)")

_HARD = re.compile(r"^(супер|сверх|суб|контр|пан|меж|двух|трех|трёх|четырех|четырёх|ад|дез|диз|кон|транс|пост|экс)"
                   r"\.\.[еюя]", re.I)   # not ё (супер..ёлка) and not native prefixes (пред..юльский) - bank 28.10

CHOOSE_1 = ("Выбери слово, которое подходит по смыслу. Ответь только этим словом, без пояснений.")
CHOOSE_2 = ("Ты редактор. Какое из слов уместно в этом сочетании? Напиши одно слово — то, которое подходит, "
            "и ничего больше.")


def _choice(chat, word, letters, context):
    """The brain picks the meaningful word among the spellings; two wordings must agree. -> letter or None."""
    options = [word.replace("..", c) for c in letters]
    q1 = f"Сочетание: «{context}». Варианты: " + ", ".join(f"«{o}»" for o in options) + "."
    q2 = f"«{context}» — здесь пропущена буква. Подходит: " + " или ".join(options) + "?"
    picks = []
    for system, q in ((CHOOSE_1, q1), (CHOOSE_2, q2)):
        a = chat([{"role": "system", "content": system}, {"role": "user", "content": q}], temperature=0,
                 max_tokens=20)[0]
        a = re.sub(r"[^а-яё]", "", (a or "").lower().split()[0] if a and a.split() else "")
        hit = [c for c, o in zip(letters, options) if a == o.lower()]
        picks.append(hit[0] if len(hit) == 1 else None)
    if picks[0] and picks[0] == picks[1]:
        return picks[0]
    # the two disagree (скр..пите (листы), 28.10): whole phrases with the hint, the majority of three decides
    phrases = [re.sub(r"[()]", "", context.replace("…", c)).strip() for c in letters]
    a = chat([{"role": "system", "content": "Ответь только одним сочетанием из предложенных, без пояснений."},
              {"role": "user", "content": "Какое сочетание правильно по смыслу: " +
               " или ".join(f"«{p}»" for p in phrases) + "?"}], temperature=0, max_tokens=30)[0] or ""
    hit = [c for c, o in zip(letters, options) if o.lower() in a.lower()]
    picks.append(hit[0] if len(hit) == 1 else None)
    best = [c for c in letters if picks.count(c) >= 2]
    return best[0] if best else None


_PUNCT = None


def _punct():
    """punct_organ.py loaded once (its net stays in memory between tasks)."""
    global _PUNCT
    if _PUNCT is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("punct_organ", os.path.join(os.path.dirname(RUSSKIY),
                                                                                   "punct_organ.py"))
        _PUNCT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PUNCT)
    return _PUNCT


_MODS = {}


def _module(name):
    """A module from the russkiy folder, loaded once (its nets stay in memory)."""
    if name not in _MODS:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, os.path.join(os.path.dirname(RUSSKIY), name + ".py"))
        _MODS[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_MODS[name])
    return _MODS[name]


def _brain_chat(messages, temperature=0, max_tokens=20):
    """The local brain for meaning choices when the caller gives no chat (the live agent): 92.6% on the bank's
    ambiguous words - below the 98% goal but above the brain solving the whole task (28.10). RUSSKIY_CHOICE=0 - off."""
    import json
    import urllib.request
    body = {"model": "brain", "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = json.loads(opener.open(req, timeout=120).read())
    return r["choices"][0]["message"]["content"], r.get("usage", {})


_SYS21 = ("Ты эксперт ЕГЭ по русскому языку, задание 21 (пунктуационный анализ). Для КАЖДОГО предложения кратко назови "
          "правило, по которому в нём стоит указанный знак (тире между подлежащим и сказуемым; тире в бессоюзном "
          "сложном предложении; тире при обобщающем слове; тире при приложении; запятая при однородных; запятая при "
          "обособленном обстоятельстве; запятая в сложном предложении; запятая при вводном слове...). Затем найди "
          "предложения с ОДНИМ И ТЕМ ЖЕ правилом. Последней строкой: ОТВЕТ: номера через запятую.")


def _post(body):
    import json
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(op.open(req, timeout=1800).read())["choices"][0]["message"]


def _task21(text):
    """Thinking budget THINK_MAX_21 (else THINK_MAX, else 9000); when it runs out, the brain is told «time is up»
    and gives the answer from what it has thought so far (as the council does)."""
    budget = int(os.environ.get("THINK_MAX_21", "9000"))   # 750 tokens: 1/10 vs 9000: 5/10 (28.10) - not THINK_MAX
    msgs = [{"role": "system", "content": _SYS21}, {"role": "user", "content": text}]
    m = _post({"model": "brain", "messages": msgs, "temperature": 0.3, "max_tokens": budget,
               "chat_template_kwargs": {"enable_thinking": True}})
    a = m.get("content") or ""
    if "ОТВЕТ:" not in a:
        thought = (m.get("reasoning_content") or "") + "\n" + a
        a = _post({"model": "brain", "messages": msgs + [
            {"role": "assistant", "content": thought.strip()},
            {"role": "user", "content": "Время на размышления вышло. Последней строкой: ОТВЕТ: номера через запятую."}],
            "temperature": 0, "max_tokens": 200, "chat_template_kwargs": {"enable_thinking": False}}).get("content") or ""
    m = re.findall(r"ОТВЕТ:\s*([\d,\s]+)", a)
    got = "".join(sorted(set(re.findall(r"\d", m[-1])))) if m else ""
    return got or None


def russian_answer(text, chat=None, rounds=6):
    """-> (answer digits or None, trace). With chat (the brain), meaning choices are tried for ambiguous words."""
    n = asks_russian(text)
    if not n:
        return None, "не задание ЕГЭ"
    if chat is None and os.environ.get("RUSSKIY_CHOICE", "1") != "0":
        chat = _brain_chat
    if n in (16, 17):   # punctuation: the fine-tuned RUPunct net (russkiy/punct_organ.py); 17 stands for 17-20
        try:
            po = _punct()
            ans = po.one_comma_answer(text) if n == 16 else po.places_answer(text)
        except Exception as e:   # no torch in this Python, model missing...
            return None, f"пунктуация: {e}"
        return (ans, "пунктуация: сеть") if ans else (None, "пунктуация: сеть не уверена")
    if n == 21:   # the brain THINKING, rule by rule (5/10 on the untouched half; without thinking the council 0/2)
        try:
            return _task21(text), "21: мозг с размышлением"
        except Exception as e:
            return None, f"21: {e}"
    if n == 1:   # the gap word: closed FIPI class + short thinking (past tasks: 64 right / 19 wrong of 87)
        if "<...>" not in text:
            return None, "1: пропуска нет"
        try:
            ans = _module("task1").answer(text, chat or _brain_chat)
        except Exception as e:
            return None, f"1: {e}"
        return (ans, "1: список ФИПИ + размышление") if ans else (None, "1: не выбрал")
    if n == 5:   # paronyms: the brain finds the wrong word, the FIPI 2026 list (else OpenCorpora) gives the paronym
        try:
            ans = _module("paronyms").answer(text, chat or _brain_chat)
        except Exception as e:
            return None, f"5: {e}"
        return (ans, "5: список паронимов ФИПИ + мозг") if ans else (None, "5: пароним не найден")
    if n == 7:   # traps of past variants (russkiy/task7_table.py): 41/44 on the untouched half, coverage 32%
        try:
            ans = _module("task7_table").answer(text)
        except Exception as e:
            return None, f"7: {e}"
        return (ans, "7: таблица прошлых вариантов") if ans else (None, "7: ловушка не знакома")
    if n == 14:   # net sp14 (pairs from the bank looked up in correct texts): 23/45 vs brain ~23%
        try:
            ans = _module("nets13_15").task14(text)
        except Exception as e:
            return None, f"14: {e}"
        return (ans, "14: сеть") if ans else (None, "14: сеть не решила")
    if n == 13:   # the fine-tuned classifier (russkiy/nets13_15.py), 30/41 on the untouched half vs brain ~40%
        try:
            ans = _module("nets13_15").task13(text)
        except Exception as e:
            return None, f"13: {e}"
        return (ans, "13: сеть") if ans else (None, "13: сеть не решила")
    if n == 15:   # the dictionary first; places it leaves open - the nn15 net (123/138 together)
        got = organ([_call(15, text)])[0]
        m_ans = re.match(r"^(\d+)", got)
        if m_ans and not got.startswith("не знаю"):
            return m_ans.group(1), got
        try:
            one = re.sub(r"\s+", " ", text).replace('"', "«")
            marks = {int(k): int(v) for k, v, _ in re.findall(r"(\d+):(-?\d+):(\S+?);", organ([f'РАЗБОР(15, "{one}")'])[0])}
            ans = _module("nets13_15").task15(text, marks)
        except Exception as e:
            return None, f"15: {e}"
        return (ans, "15: словарь + сеть") if ans else (None, got)
    trace = []
    work = text
    for _ in range(rounds):
        got = organ([_call(n, work)])[0]
        trace.append(got)
        m_ans = re.match(r"^(\d+)", got)
        if m_ans and not got.startswith("не знаю"):
            return m_ans.group(1), " | ".join(trace)
        m = _AMBIG.search(got)
        if not (m and n == 9):
            break
        word = m.group(1)
        a = set(x.strip() for x in m.group(2).split(","))
        b = set(x.strip() for x in m.group(3).split(","))
        letters = sorted(c for c in a & b if c != "∅" and len(c) == 1)
        if (a & b) == set(letters) and len(letters) == 1 and letters[0] not in "еёо":
            # both dictionaries agree on one letter (с..змала: ы); not ∅ (по..кинутый) and not е/ё/о, where the
            # organ's own yo/ov rules know better (перчёный, мелочовка)
            trace.append(f"словари согласны: {word} -> {letters[0]}")
            work = work.replace(word, word.replace("..", f"[{letters[0]}]"), 1)
            continue
        if not letters and _HARD.match(word):   # супер..яркий: Ъ after a prefix on a consonant before е, ё, ю, я
            trace.append(f"правило Ъ: {word}")
            work = work.replace(word, word.replace("..", "[ъ]"), 1)
            continue
        if not chat or len(letters) != 2:
            break
        # context: the word with its hint in brackets, as written in the task
        cm = re.search(r"(\([^)]*\)\s*)?" + re.escape(word) + r"(\s*\([^)]*\))?", work)
        context = cm.group(0).replace(word, word.replace("..", "…")) if cm else word
        c = _choice(chat, word, letters, context)
        trace.append(f"мозг: {word} -> {c}")
        if not c:
            break
        work = work.replace(word, word.replace("..", f"[{c}]"), 1)
    return None, " | ".join(trace)


_ROW = re.compile(r"(?<!\d)(\d)\)\s*(.+?)(?=\s*(?<!\d)\d\)|\s*Ответ|$)", re.S)


def reason_9_12(text, answer=""):
    """Why, for tasks 9-12 (28.10): every gap word with the letter the organ puts in (its БУКВА command), row by row -
    so Neira explains the answer from the dictionaries instead of making the explanation up."""
    rows = [(k, re.findall(r"[А-Яа-яЁё]*\.\.[А-Яа-яЁё]*", body)) for k, body in _ROW.findall(text)]
    words = [w for _, ws in rows for w in ws]
    if not words:
        return ""
    got = organ([f'БУКВА("{w}")' for w in words])
    letter = dict(zip(words, got))
    out = []
    for k, ws in rows:
        known = {letter[w] for w in ws if len(letter.get(w, "")) == 1}
        same = k in answer and len(known) == 1   # an answer row: one letter for all, the open words get it too
        fill = lambda w: letter[w] if len(letter.get(w, "")) == 1 else (next(iter(known)) if same else "_")  # noqa: E731
        filled = [w.replace("..", fill(w).upper()) for w in ws]
        out.append(f"{k}) " + ", ".join(filled) + (" — везде одна буква" if k in answer else ""))
    return "; ".join(out)


def russian_note(answer, why=""):
    return (f"(Справка органа «русский» — проверено по словарям OpenCorpora, Hunspell, RUAccent и списку ФИПИ: "
            f"ответ {answer}." + (f" Буквы по рядам: {why}." if why else "") + " Назови этот ответ.)")
