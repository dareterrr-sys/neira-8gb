"""EGE Russian tasks go to ONE call of the brain with short thinking, not to the council (28.10): on 72 past tasks
(numbers 2, 3, 6, 8, 22-26, explanations dataset half B) one call was right more often than the council (see
runs/compare_council.jsonl) and took ~31 s instead of ~95 s. The task is recognised by FIPI wordings for Russian only."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "russkiy"))
sys.path.insert(0, os.path.dirname(HERE))
import task1  # noqa: E402

EGE_RU = re.compile(
    r"Укажите варианты ответов|Запишите номера (ответов|этих предложений)|Установите соответствие между|"
    r"Самостоятельно подберите|Какие из высказываний соответствуют|Какие из перечисленных утверждений|"
    r"Найдите предложени|Из предложений \d+\s*[–—-]\s*\d+|Отредактируйте предложение|"
    r"Исправьте лексическую ошибку|Выпишите (это слово|синоним|антоним|фразеологизм|слово)|"
    r"изобразительно-выразительн|Прочитайте текст и выполните задание|фрагмент рецензии", re.I)
SYS = ("Ты эксперт ЕГЭ по русскому языку. Реши задание: внимательно прочитай текст и условие, проверь каждый вариант. "
       "Последней строкой напиши: ОТВЕТ: <только ответ в той форме, которую требует задание — цифры без пробелов "
       "или слово>.")


def is_ege_ru(q):
    import russkiy_dept   # the organ's own FIPI wordings (7, 13-21, ...) count too
    return bool(EGE_RU.search(q or "")) or bool(russkiy_dept.asks_russian(q or ""))


# 31.10, Neira's textbook (the author: «учебник с правилами, как человек»): the task kind by its FIPI wording ->
# the chapter D:\AI\neira-tools\knowledge\russkiy\NN_*.md she reads before solving. 9-12 and 17-20 share wordings.
BOOK = os.path.join(os.path.dirname(HERE), "knowledge", "russkiy")
KINDS = [(8, r"соответствие между грамматическими ошибками"), (22, r"изобразительно-выразительн"),
         (21, r"одним и тем же правилом пунктуации"), (16, r"ОДНУ запятую"), (17, r"должна\(-ы\) стоять запят"),
         (15, r"пишется (НН|одна буква Н)"), (14, r"все выделенные слова пишутся"), (13, r"НЕ( \(НИ\))? с выделенным"),
         (9, r"пропущена одна и та же буква"), (4, r"ударный гласный"), (5, r"пароним"), (6, r"Отредактируйте предложение"),
         (7, r"допущена\s+грамматическая\s+ошибка"), (2, r"лексическое значение выделенного"), (3, r"характеристики (текста|фрагмента)"),
         (23, r"соответствуют содержанию"), (24, r"утверждений являются"), (26, r"связан\w*(\(-ы\))? с предыдущ"),
         (25, r"[Вв]ыпишите"), (1, r"Самостоятельно подберите")]


def kind(q):
    return next((n for n, rx in KINDS if re.search(rx, q or "")), 0)


def chapter(q):
    """The textbook chapter for this kind of task, or ''. Off until measured (live Neira loads this file):
    EGE_BOOK=1 turns it on."""
    n = kind(q)
    mode = os.environ.get("EGE_BOOK", "0")
    if not n or mode == "0" or not os.path.isdir(BOOK):
        return ""
    if mode == "roz":   # the original: Rozental's own points about the kinds named in the task (31.10, the author)
        sys.path.insert(0, os.path.dirname(BOOK))
        import rozental
        return rozental.sections_for(q, n)
    files = [f for f in os.listdir(BOOK) if f.startswith(f"{n:02d}_") and f.endswith(".md")]
    return open(os.path.join(BOOK, files[0]), encoding="utf-8").read() if files else ""


def _rows(q):
    body = re.split(r"Запишите номера ответов\.", q, maxsplit=1)[-1].split("Ответ дай")[0]
    return re.findall(r"(\d)\)\s*(.+?)(?=\s+\d\)\s|$)", body.strip(), re.S)


def organ_note(q):
    """31.10: the organ answers a task only when it knows every item; otherwise the brain got nothing. Now the brain
    gets what the dictionaries do know, item by item (stress for 4, the missing letter for 9-12), and decides the
    rest. Off until measured (live Neira loads this file): EGE_ORGAN_NOTE=1 turns it on."""
    n = kind(q)
    if n not in (4, 9) or os.environ.get("EGE_ORGAN_NOTE", "0") == "0":
        return ""
    import russkiy_dept
    rows = _rows(q)
    if not rows:
        return ""
    lines = []
    if n == 4:
        verdicts = russkiy_dept.organ([f'УДАРЕНИЕ("{re.sub(r"[(][^)]*[)]", "", w).strip()}")' for _, w in rows])
        for (k, w), v in zip(rows, verdicts):
            lines.append(f"пункт {k} {w.strip()}: " + ("словарь: ВЕРНО" if v.startswith("верно") else
                                                     "словарь: НЕВЕРНО" if v.startswith("неверно") else "словаря нет, реши сам"))
    else:
        for k, row in rows:
            words = [w.strip() for w in row.split(",") if ".." in w]
            got = russkiy_dept.organ([f'БУКВА("{re.sub(r"[(][^)]*[)]", "", w).strip()}")' for w in words])
            parts = [f"{w} → {g}" if not g.startswith("не знаю") else f"{w} → словарь не уверен, реши по смыслу"
                     for w, g in zip(words, got)]
            lines.append(f"ряд {k}: " + "; ".join(parts))
    return ("Справка словарей (где словарь назвал ответ, ему можно верить; остальное реши сам):\n" + "\n".join(lines))


# 31.10: the matching tasks (8: nine sentences x five error kinds; 22) ran out of the 750-token thinking every time
# and guessed the last letter (dev: 4 of 5 letters right in most misses). EGE_ONE_THINK_LONG - their budget
# (750 like the rest until measured: live Neira loads this file).
LONG = {8, 22}


def by_letters(ans):
    """«2Б8В1Д9Г7А» / «А-2, Б-8…» -> «72891»: digits in the order of the letters А-Д."""
    pairs = re.findall(r"([А-Д])\s*[-–:)]?\s*(\d)|(\d)\s*([А-Д])", ans or "")
    got = {}
    for l1, d1, d2, l2 in pairs:
        got[l1 or l2] = d1 or d2
    letters = "АБВГД"[:len(got)]
    return "".join(got[l] for l in letters) if len(got) >= 4 and all(l in got for l in letters) else ans


# 31.10 (the author): on Russian-language tasks she thought in English («Here's a thinking process:»), retold the
# whole task to herself and ran out of the 750 tokens on the second of nine sentences. Now her thinking is begun for
# her in Russian (she goes on in the language it starts in), and the budget grows in steps: 750, then her own thought
# goes on (the prompt is cached, nothing is read again) up to 2000, then «time is up». EGE_THINK_RU=1 turns it on.
COMPLETION = "http://127.0.0.1:8080/completion"
RU_START = "Рассуждаю по-русски и коротко, условие не переписываю. Иду по пунктам по порядку.\n"


def _complete(prompt, n):
    import json
    import urllib.request
    body = {"prompt": prompt, "n_predict": n, "temperature": 0, "cache_prompt": True}
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = json.loads(op.open(urllib.request.Request(COMPLETION, json.dumps(body).encode("utf-8"),
                                                  {"Content-Type": "application/json"}), timeout=1800).read())
    return r["content"], r["timings"]["predicted_n"]


def think_ru(system, user):
    """-> (text after the thinking, tokens of thinking, the step it ended in: 1, 2 or 0 = time ran out)."""
    steps = [int(x) for x in os.environ.get("EGE_BUDGETS", "750,2000").split(",")]
    head = (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n{RU_START}")
    thought, used = "", 0
    for i, total in enumerate(steps, 1):
        more, n = _complete(head + thought, total - used)
        thought, used = thought + more, used + n
        if "</think>" in thought:
            after = thought.split("</think>", 1)[1]
            if "ОТВЕТ" not in after:
                tail, _ = _complete(head + thought, 120)
                after += tail
            return after, used, i
    after, _ = _complete(head + thought + "\n\nВремя вышло, записываю ответ.\n</think>\n\nОТВЕТ:", 40)
    return "ОТВЕТ:" + after, used, 0


def _dict_note(q):
    """Опционально (EGE_DICT=1): толкования незнакомых слов задачи из локального словаря."""
    if os.environ.get("EGE_DICT", "0") != "1":
        return ""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "knowledge", "russkiy"))
        from dict_lookup import gloss, is_known
    except Exception:
        return ""
    seen, out = set(), []
    for w in re.findall(r"[А-Яа-яЁё]{4,}", q):
        wl = w.lower()
        if wl in seen or is_known(wl):
            continue
        g = gloss(wl)
        if g:
            seen.add(wl)
            out.append(f"{wl} — {g}")
        if len(out) >= 5:
            break
    return ("Справка словаря (для незнакомых слов):\n" + "\n".join(out)) if out else ""


def answer(q):
    """-> the answer line (digits or word) or ''."""
    if os.environ.get("EGE_THINK_RU", "0") == "1":
        n = kind(q)
        book = chapter(q)
        system = SYS + ("\n\nРаздел учебника, который ты держишь перед глазами:\n" + book if book else "")
        note = organ_note(q) + _dict_note(q)
        a, used, step = think_ru(system, q + ("\n\n" + note if note else ""))
        m = re.findall(r"ОТВЕТ:\s*(.+)", a)
        ans = m[-1].strip() if m else ""
        return by_letters(ans) if n in LONG else ans
    n = kind(q)
    task1.THINK = int(os.environ.get("EGE_ONE_THINK_LONG", "750") if n in LONG else os.environ.get("EGE_ONE_THINK", "750"))
    book = chapter(q)
    system = SYS + ("\n\nГлава учебника, которую ты держишь перед глазами:\n" + book if book else "")
    note = organ_note(q) + _dict_note(q)
    a = task1._think(system, q + ("\n\n" + note if note else ""))
    m = re.findall(r"ОТВЕТ:\s*(.+)", a)
    ans = m[-1].strip() if m else ""
    return by_letters(ans) if n in LONG else ans
