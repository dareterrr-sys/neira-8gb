"""Neira's council v4.0 (29.10: no red critic, no step judge, no mouth; v3.0 is the user's design): specialists from her own brain, a deep thinker for disputes, checkers.

Fast round: three role specialists answer without thinking (a few seconds each). All three agree -> high confidence,
Neira answers at once. They disagree -> Neira says a human pause line and one specialist thinks the question through
(Qwen3.6 thinking, seeing the three answers); its answer is the conclusion. A numeric conclusion is then plugged into
blind tests from three checkers with different methods; a failed test lowers confidence and Neira says she is not
sure (v1-v2.3 had three voting controllers instead; see the research journal for why they went).
Used by eval_brain.py (mode "council"); the live wiring into Open-LLM-VTuber comes after the measurement.
"""
import collections
import json
import re
import time
import urllib.request

import os
import sys
from concurrent.futures import ThreadPoolExecutor


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # D:\AI\neira-tools
import perception  # noqa: E402


FORMAT = ("Ответь строго в двух строках:\nОТВЕТ: <только итог без пояснений: если ответ — количество или величина, "
          "то число цифрами; если день недели, имя, название, да/нет или утверждение — словами>\n"
          "ПОЧЕМУ: <одно короткое обоснование>")
SPECIALISTS = {
    "логик": "Ты логик. Реши задачу шаг за шагом в уме, проверь каждый шаг и ловушки в формулировке. " + FORMAT,
    "проверяющий": ("Ты проверяющий факты. Сначала проверь, верны ли утверждения, на которых построен вопрос; если "
                    "посылка ложна, твой ответ — её опровержение. Отвечай только тем, в чём уверен. " + FORMAT),
    "адвокат": ("Ты адвокат дьявола. Ищи подвох, двусмысленность и типичную ошибку, которую сделал бы торопливый "
                "человек, затем дай правильный ответ. " + FORMAT),
}
SAME = ("Даны вопрос и несколько кратких ответов. Совпадают ли все ответы по смыслу (одно и то же итоговое утверждение "
        "или число)? Ответь одним словом: ДА или НЕТ.")
DEEP = ("Ты внимательный решатель. Тебе дан вопрос и ответы трёх специалистов, которые разошлись. Разберись сам, "
        "кто прав или нет ли правильного ответа, которого никто не дал. " + FORMAT)
PAUSE = "Хмм... дай минутку, тут надо подумать."
# 04.11, the author's design (24.10: «проблема не в калькуляторе, а в том, что выражение не правильно составлено, как
# калькулятор может ошибаться?»): on a counting task the council checks the EXPRESSION each specialist builds from the
# condition, the code computes it, and the calculator's result is the answer. Reasons first, expression last: with the
# answer line first all three blurted «15» for 24 - 24/3 + 7 and computed 23 only in their reasons (field test C1,
# 3 of 3; v4.0 also stopped calling the calculator in council turns, commit f4117a2). COUNCIL_EXPR=0 - v4.0 as before.
EXPR = os.environ.get("COUNCIL_EXPR", "0") != "0"
FORMAT_EXPR = ("Ответь строго в двух строках:\nПОЧЕМУ: <коротко, по шагам: что дано и что с ним делают по условию>\n"
               "ВЫРАЖЕНИЕ: <одно арифметическое выражение по условию: только числа, + - * / и скобки, без единиц и "
               "без знака =; если ответ не получить счётом — НЕТ>")
SPECIALISTS_EXPR = {n: r.replace(FORMAT, FORMAT_EXPR) for n, r in SPECIALISTS.items()}
DEEP_EXPR = ("Ты внимательный решатель. Тебе дан вопрос и выражения, которые три специалиста составили по его условию; "
             "код их посчитал, и результаты разошлись. Проверь, какое выражение правильно понимает условие, или составь "
             "своё. " + FORMAT_EXPR)
# plan step 8в.7: independent calls (the three specialists, the three checkers) go to the server together, so it reads
# the weights once per batch; needs llama-server --parallel N. 1 = one after another, as before.
PARALLEL = int(os.environ.get("COUNCIL_PARALLEL", "1"))
# v3.7: the deep thinker's reasoning budget in tokens (it was 6000; see deep_think) and the raw completion endpoint
DEEP_BUDGET = int(os.environ.get("COUNCIL_DEEP_BUDGET", "750"))
COMPLETION = os.environ.get("BRAIN_COMPLETION", "http://127.0.0.1:8080/completion")
# v3.8 (plan step 11, way 2, attempt 2): the «не знаю» control vector (vec_abstain.gguf, «не знаю» minus a made-up year)
# only on erudition questions. On the whole brain it kept work3 (78/80) but broke ЕГЭ solutions and her speech; it is
# about remembering, not about solving (the author's point). Needs the llama-neira server: per-request "cvec" factor,
# off by default, so the grader and everything else stay unsteered. 0 = never.
CVEC = float(os.environ.get("COUNCIL_CVEC", "1"))
ERUDITION = ("Определи тип вопроса. ДА — если для ответа нужно вспомнить факт о мире: дату, имя, место, число из "
             "справочника, событие, кто что сделал или открыл. НЕТ — если ответ получают расчётом, логикой или из "
             "условия задачи, а также если это просьба или болтовня. Ответь одним словом: ДА или НЕТ.")


# v3.8: a refusal is kept whatever its words: the council concludes «неизвестно», Neira says «не знаю, кто это» -
# before, kept() saw two different answers and made her say it again (17 of 30 people questions, 5 without the vector)
REFUSAL = re.compile(r"не знаю|не существ|нет такого|нет такой|нет данных|не могу|не уверен|неизвестн|невозможно|"
                     r"отсутству|вымышл|выдуман|не найд|нет сведений|нет информации|не удалось|затрудняюсь", re.I)


# v3.9: the doubt sensor (plan step 11, the author's point: an unfamiliar topic must lower the confidence). A linear
# probe on layer 16 at the question's last token under a neutral instruction, read by the llama-neira server
# ("probe": true). On the vector's leftover lies about people AUC 0.986; on other facts (films, books, towns,
# buildings, events) 0.955. Below PROBE_THR an erudition conclusion is said with low confidence. 0.5 is the probe's
# own boundary; 0.2, chosen on the training data, caught only 30 of 71 wrong answers on the other facts.
HEDGE = re.compile(r"не уверен|не до конца|кажется|возможно|вероятно|если не ошибаюсь|не помню точно|точно не помню|"
                   r"могу ошибаться|не ручаюсь", re.I)
PROBE_THR = float(os.environ.get("COUNCIL_PROBE_THR", "0.5"))


def probe(q):
    """-> the sensor's P(the brain knows the answer), None if the server has no sensor."""
    prompt = (f"<|im_start|>system\nОтветь на вопрос.<|im_end|>\n<|im_start|>user\n{q}<|im_end|>\n"
              "<|im_start|>assistant\n<think>\n\n</think>\n\n")
    body = {"prompt": prompt, "n_predict": 1, "temperature": 0, "probe": True}
    req = urllib.request.Request(COMPLETION, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read()).get("neira_probe")


def erudition(q, chat):
    verdict, _ = chat([{"role": "system", "content": ERUDITION}, {"role": "user", "content": q}], 0, 3)
    return verdict.strip().upper().startswith("ДА")


def _map(fn, items):
    items = list(items)
    if PARALLEL <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(min(PARALLEL, len(items))) as pool:
        return list(pool.map(fn, items))


_UNITS = {"ноль": 0, "один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
          "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
          "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
          "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
          "семьдесят": 70, "восемьдесят": 80, "девяносто": 90, "сто": 100, "двести": 200, "триста": 300,
          "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900}


# ordinals count as numbers too: v2.1 took "вторым" and "2" for different answers and "corrected" a right reply
_ORDINALS = {"перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7, "восьм": 8, "девят": 9,
             "десят": 10}


def ordinal_of(word):
    for stem, n in _ORDINALS.items():
        if word.startswith(stem) and re.fullmatch(stem + r"(ый|ой|ий|ая|ое|ые|ым|ом|ого|ому|ую|ей|ыми|ых|ом|ье|ья|ьи|ьим|ьего)", word):
            return n
    return None


def number_of(text):
    """The first number in an answer, from digits ("1000", "7,5") or Russian words ("тысяча двести")."""
    t = (text or "").lower().replace("ё", "е")
    m = re.search(r"-?\d+(?:[.,]\d+)?", t.replace(" ", "") if re.fullmatch(r"[\d ]+", t.strip()) else t)
    if m:
        return float(m.group(0).replace(",", "."))
    total, cur, seen = 0, 0, False
    for w in re.findall(r"[а-я]+", t):
        if w in _UNITS:
            cur += _UNITS[w]
            seen = True
        elif w.startswith("тысяч"):
            total += (cur or 1) * 1000
            cur, seen = 0, True
        elif seen:
            break
    return total + cur if seen else None


def key_of(answer):
    """What makes two answers the same: an answer that starts with a number is that number ("тысяча" = "1000",
    "восемь дней 8" = "8"); otherwise its first two words ("Суббота" = "суббота, 6")."""
    t = (answer or "").strip().lower().replace("ё", "е")
    first = re.match(r"\s*(-?\d+(?:[.,]\d+)?|[а-я]+)", t)
    if first and ordinal_of(first.group(1)) is not None:
        return f"#{ordinal_of(first.group(1))}"
    if first and (re.fullmatch(r"-?\d+(?:[.,]\d+)?", first.group(1)) or first.group(1) in _UNITS
                  or first.group(1).startswith("тысяч")):
        n = number_of(t)
        if n is not None:
            return f"#{n:g}"
    words = re.findall(r"[а-яa-z]+", t)
    return " ".join(words[:2]) if words else t


RED = ("Ты красный критик. Три специалиста единогласно дали ответ на вопрос. Единогласие бывает и ошибочным: у всех "
       "трёх может быть одна и та же слепая зона. Предположи, что их ответ неверен, и честно поищи ошибку: подвох в "
       "формулировке, неверное чтение условия, логическую ошибку, ложную уверенность там, где ответ знать нельзя. "
       "Если после проверки ответ всё же верен, так и скажи — не придумывай возражений ради возражений.\n"
       "Ответь строго в трёх строках:\nВЕРДИКТ: ВЕРНО или ОШИБКА\nОТВЕТ: <твой правильный ответ: число цифрами, "
       "иначе словами; «не знаю», если ответ знать нельзя>\nПОЧЕМУ: <одно короткое обоснование>")


def _complete(prompt, n, cvec=0.0):
    body = {"prompt": prompt, "n_predict": n, "temperature": 0.6, "top_p": 0.95, "top_k": 20, "cache_prompt": True,
            "cvec": cvec}
    req = urllib.request.Request(COMPLETION, json.dumps(body).encode(), {"Content-Type": "application/json"})
    for attempt in range(3):   # the same unexplained connection resets as in eval_brain.chat
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=3600).read())
            return r["content"], r["timings"]["predicted_n"]
        except (ConnectionError, OSError):
            if attempt == 2:
                raise
            time.sleep(5)


def deep_think(user, budget, cvec=0.0, system=DEEP, marker="ОТВЕТ"):
    """v3.7, budget forcing (s1, Muennighoff et al. 2025): the deep thinker reasons up to `budget` tokens; if it has not
    closed its reasoning by then, it is closed for it and it must answer. On 40 saved disputes: 6000 tokens 34/40 in
    57 s, 1500 35/40 in 44 s, 750 34/40 in 25 s, 300 29/40 in 11 s. -> (answer text, tokens written, cut short?)"""
    head = (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n")
    text, n = _complete(head, budget, cvec)
    if "</think>" in text:
        answer = text.split("</think>", 1)[1]
        if marker in answer:
            return answer, n, False
        more, m = _complete(head + text, 160, cvec)
        return answer + more, n + m, False
    answer, m = _complete(head + text + "\n\nВремя на размышления вышло, отвечаю.\n</think>\n\n", 160, cvec)
    return answer, n + m, True


def parse(text):
    m = re.search(r"ОТВЕТ:\s*(.+)", text or "")
    why = re.search(r"ПОЧЕМУ:\s*(.+)", text or "")
    return (m.group(1).strip() if m else (text or "").strip()[:80]), (why.group(1).strip() if why else "")


def norm(s):
    return re.sub(r"[\s.,!?«»\"']+", " ", s.lower().replace("ё", "е")).strip()


def computed(text):
    """A specialist's or the thinker's reply in FORMAT_EXPR -> (expression, the calculator's result) or None."""
    from calc_server import calculate_text
    m = re.search(r"ВЫРАЖЕНИЕ:\s*(.+)", text or "")
    e = m.group(1).strip().strip("`").strip() if m else ""
    # «НЕТ», a list of answers («2,4») or no arithmetic at all is not an expression (the same guard as math_note)
    if not e or "НЕТ" in e.upper() or "," in e or "=" in e or not re.search(r"\d", e):
        return None
    r = calculate_text(e)
    return None if r.startswith("Ошибка") else (e, r.split(" ")[0])


def answer_expr(task, chat, think_max, info):
    """The author's design (see EXPR): specialists write the expression, code computes it, the result is the answer.
    -> (conclusion, why, confidence), or None when this is not a counting task (fewer than two expressions)."""
    replies = _map(lambda role: chat([{"role": "system", "content": role}, {"role": "user", "content": task}], 0.7, 250)[0],
                   SPECIALISTS_EXPR.values())
    exprs = {n: computed(t) for n, t in zip(SPECIALISTS_EXPR, replies)}
    info["expr"] = {n: (list(x) if x else None) for n, x in exprs.items()}
    good = {n: x for n, x in exprs.items() if x}
    if len(good) < 2:
        return None
    info["specialists"] = {n: (r, f"{e} = {r}") for n, (e, r) in good.items()}
    results = {key_of(r) for _, r in good.values()}
    if len(good) == 3 and len(results) == 1:
        e, r = next(iter(good.values()))
        info["agree"] = True
        return r, f"{e} = {r}", "высокая"
    # the expressions disagree (or one specialist found no expression): the thinker checks them and writes its own
    info["agree"], info["pause"] = False, True
    listing = "\n".join(f"- {n}: {e} = {r}" for n, (e, r) in good.items())
    deep, info["deep_tokens"], info["deep_cut"] = deep_think(f"{task}\n\nВыражения специалистов:\n{listing}",
                                                             min(think_max, DEEP_BUDGET), 0.0, DEEP_EXPR, "ВЫРАЖЕНИЕ")
    x = computed(deep)
    if x:
        info["deep"] = (x[1], f"{x[0]} = {x[1]}")
        return x[1], f"{x[0]} = {x[1]}", "средняя"
    # the thinker wrote no usable expression: the specialists' majority by result, else no conclusion
    by_key = collections.Counter(key_of(r) for _, r in good.values())
    top_key, top_n = by_key.most_common(1)[0]
    if top_n >= 2:
        e, r = next((e, r) for e, r in good.values() if key_of(r) == top_key)
        return r, f"{e} = {r}", "низкая"
    return "", "", "низкая"


def answer(q, system, chat, notes, think_max=6000):
    """-> (Neira's in-character answer, info). chat(messages, temperature, max_tokens, **extra) -> (text, usage)."""
    facts = " ".join(notes)
    task = q + (f"\n\n(Справка: {facts})" if facts else "")
    info = {"notes": notes, "specialists": {}, "pause": False}
    # a counting task has at least two numbers (perception has already turned «двадцать четыре» into 24)
    if EXPR and len(re.findall(r"\d+(?:[.,]\d+)?", q)) >= 2:
        got = answer_expr(task, chat, think_max, info)
        if got:
            conclusion, why, confidence = got
            info.update(conclusion=conclusion, confidence=confidence, route="expr")
            if not conclusion:
                return "Не знаю: к выводу не пришла.", info
            text = f"Итог: {conclusion}. {why}"
            if confidence == "низкая":
                text += " Но я в этом не до конца уверена."
            return text, info
        info["specialists"] = {}
    # v3.8: an organ's note means the answer is computed, not remembered - no vector then
    info["cvec"] = CVEC if CVEC and not notes and erudition(q, chat) else 0.0
    if info["cvec"] and PROBE_THR > 0:
        info["probe"] = probe(q)
    if info["cvec"]:
        plain_chat = chat
        chat = lambda m, t=0.7, n=600, **e: plain_chat(m, t, n, cvec=info["cvec"], **e)   # noqa: E731

    # 1. fast round: three specialists, no thinking
    replies = _map(lambda role: chat([{"role": "system", "content": role}, {"role": "user", "content": task}], 0.7, 120)[0],
                   SPECIALISTS.values())
    for name, txt in zip(SPECIALISTS, replies):
        info["specialists"][name] = parse(txt)
    finals = [a for a, _ in info["specialists"].values()]
    agree = len({key_of(a) for a in finals}) == 1
    if not agree:
        listing = "\n".join(f"- {a}" for a in finals)
        verdict, _ = chat([{"role": "system", "content": SAME},
                           {"role": "user", "content": f"Вопрос: {q}\nОтветы:\n{listing}"}], 0, 5)
        agree = verdict.strip().upper().startswith("ДА")
    info["agree"] = agree

    if agree:
        # the majority's answer (v2 took the logician's, even a stray "0" when the others said "не брал Петербург");
        # a tie goes to the fact checker
        by_key = collections.Counter(key_of(a) for a in finals)
        top_n = by_key.most_common(1)[0][1]
        pick = "проверяющий" if top_n == 1 else next(n for n, (a, _) in info["specialists"].items()
                                                        if by_key[key_of(a)] == top_n)
        conclusion, why = info["specialists"][pick]
        confidence = "высокая"
        # v4.0 (29.10, the author): no red critic and no step judge. Over 530 questions of the last runs (MGSM 250,
        # hard 2x100, work3 80) the red critic sent 12 questions to the thinker and that helped 3 times, at one more
        # call on every agreed question; the step judge sent 21 and helped 0 (council_ablate.py)
    if not agree:
        # 2. low confidence: pause line, one deep thinker decides
        info["pause"] = True
        listing = "\n".join(f"- {n}: {a} ({w})" for n, (a, w) in info["specialists"].items())
        deep, info["deep_tokens"], info["deep_cut"] = deep_think(f"{task}\n\nОтветы специалистов:\n{listing}",
                                                                 min(think_max, DEEP_BUDGET), info["cvec"])
        info["deep"] = parse(deep)
        # v3.0: no voting controllers. In v2.1-v2.3 the fast controllers turned a right deep answer into a wrong one
        # 7 times and fixed 2 (first a bias to option "2", then, debiased, they followed a wrong calculator note).
        # The deep thinker decides the dispute.
        if info["deep"][0].strip():
            conclusion, why = info["deep"]
            confidence = "средняя"
        else:
            # v2.3: the thinker spent its whole budget thinking and returned nothing (w015); fall back to the
            # specialists' majority, or to no conclusion at all - never to an improvised answer
            by_key = collections.Counter(key_of(a) for a in finals)
            top_key, top_n = by_key.most_common(1)[0]
            conclusion = next(a for a in finals if key_of(a) == top_key) if top_n >= 2 else ""
            why, confidence = "", "низкая"

    # v3.6: no checkers (plan step 4's blind tests). Over 476 numeric conclusions (MGSM, work3, work2) they lowered
    # confidence on 12% of right answers and on 12.5% of wrong ones - no signal - at 10% of the council's time.
    # An honest doubt is the doubt sensor's job (plan step 11).
    # v3.9: the sensor doubts a remembered fact -> say it, but not as a certainty (a refusal needs no doubt)
    if info.get("probe") is not None and info["probe"] < PROBE_THR and conclusion and not REFUSAL.search(conclusion):
        confidence = "низкая"
        info["probe_doubt"] = True
    info.update(conclusion=conclusion, confidence=confidence)

    # v4.0: no separate "mouth" (Neira retelling the conclusion in a 600-token call, then a check that she kept it):
    # in live Neira the brain itself says the conclusion, given as an organ's note (basic_memory_agent)
    if not conclusion:
        text = "Не знаю: к выводу не пришла."
    else:
        text = f"Итог: {conclusion}." + (f" {why}" if why else "")
        if confidence == "низкая" and not HEDGE.search(text):
            text += " Но я в этом не до конца уверена."
    return text, info
