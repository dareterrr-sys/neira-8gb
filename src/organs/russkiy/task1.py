"""EGE task 1: «Самостоятельно подберите <вид слова>, которое должно стоять на месте пропуска». The word comes from a
small closed class; the class is read from the question, its members (pronouns - in all their forms, OpenCorpora via
pymorphy3) are given to the brain, which chooses by meaning, as in the 9-12 and 5 choices. An answer outside the
list is not taken. Open classes (наречие, числительное) - the brain alone."""
import re

LISTS = {
    "притяжательн": ["мой", "твой", "свой", "наш", "ваш", "его", "её", "их"],
    "определительн": ["весь", "сам", "самый", "всякий", "каждый", "любой", "иной", "другой"],
    "указательн": ["этот", "тот", "такой", "таков", "столько", "сей", "этакий"],
    "личн": ["я", "ты", "он", "она", "оно", "мы", "вы", "они"],
    "отрицательн": ["никто", "ничто", "никакой", "ничей", "нисколько", "некого", "нечего"],
    "неопределённ": ["некто", "нечто", "некий", "несколько", "кто-то", "что-то", "какой-то", "какой-нибудь",
                     "кое-кто", "кое-что", "кое-какой", "чей-то"],
    "относительн": ["который", "какой", "чей", "что", "кто", "сколько", "каков"],
    "союзное": ["который", "какой", "чей", "что", "кто", "сколько", "где", "куда", "откуда", "когда", "почему",
                "зачем", "как"],
    "противительн": ["но", "а", "однако", "зато", "да", "же", "тогда как", "а то"],
    "разделительн": ["или", "либо", "то ли", "не то", "то"],
    "соединительн": ["и", "да", "также", "тоже", "ни"],
    "сочинительн": ["и", "а", "но", "однако", "зато", "или", "либо", "да", "также", "тоже"],
    "подчинительн": ["что", "чтобы", "потому что", "так как", "поскольку", "если", "когда", "хотя", "как",
                     "будто", "словно", "как будто", "пока", "раз", "ибо", "так что", "несмотря на то что",
                     "для того чтобы", "в то время как", "прежде чем", "после того как"],
    "уступительн": ["хотя", "хоть", "несмотря на то что", "пусть", "пускай", "невзирая на то что"],
    "уточняющ": ["именно", "как раз", "точно", "ровно", "прямо", "почти", "как раз именно"],
    "ограничительн": ["только", "лишь", "лишь только", "исключительно", "единственно", "хотя бы", "хоть",
                      "даже", "именно"],
    "выделительн": ["только", "лишь", "лишь только", "исключительно", "единственно", "даже", "именно", "хотя бы"],
    "усилительн": ["даже", "же", "ведь", "ни", "и", "уж", "всё-таки", "всё же", "даже и"],
    "отрицательную частиц": ["не", "ни"],
    "производный": ["благодаря", "вследствие", "в течение", "в продолжение", "несмотря на", "невзирая на",
                    "ввиду", "в связи с", "среди", "посреди", "вроде", "наподобие", "в отличие от",
                    "в результате", "по мере", "в целях", "в силу", "в качестве", "в ходе", "в случае",
                    "в зависимости от", "по причине", "по сравнению с", "с помощью", "при помощи", "в виде",
                    "вместо", "вокруг", "вдоль", "внутри", "вне", "мимо", "около", "согласно", "вопреки",
                    "насчёт", "вслед за", "наряду с", "в области", "в сфере", "за счёт", "в адрес",
                    "в отношении", "по отношению к", "в рамках", "в течении", "в продолжении", "в заключение",
                    "посредством", "на протяжении", "в соответствии с", "наряду с", "из-за", "кроме", "помимо",
                    "после", "путём", "по поводу", "в продолжение"],
    "предлог": ["благодаря", "вследствие", "ввиду", "из-за", "по причине", "в силу", "кроме", "помимо", "после",
                "до", "перед", "через", "среди", "вместо", "несмотря на", "в течение", "на протяжении", "вроде",
                "в связи с", "в отличие от", "в соответствии с", "наряду с", "посредством", "с помощью",
                "при помощи", "за счёт", "вопреки", "согласно", "навстречу", "вслед", "около", "вокруг"],
    "союз": ["и", "а", "но", "однако", "зато", "или", "либо", "что", "чтобы", "потому что", "так как", "поскольку",
             "если", "когда", "хотя", "как", "будто", "словно", "ибо", "так что", "тоже", "также", "раз"],
    "вводн": ["однако", "например", "во-первых", "во-вторых", "конечно", "наоборот", "напротив",
              "следовательно", "таким образом", "значит", "кроме того", "к сожалению", "к счастью", "впрочем",
              "итак", "наконец", "по-видимому", "вероятно", "безусловно", "разумеется", "очевидно", "кстати",
              "в частности", "в первую очередь", "прежде всего", "стало быть", "в общем", "в итоге",
              "в результате", "одним словом", "иными словами", "другими словами", "словом", "к примеру",
              "так", "возможно", "может быть", "действительно", "несомненно", "по мнению", "по словам",
              "с одной стороны", "с другой стороны", "в свою очередь"],
}
PRONOUNS = ("притяжательн", "определительн", "указательн", "личн", "отрицательн", "неопределённ", "относительн",
            "союзное")
_MORPH = None


def kind(q):
    m = re.search(r"[Пп]одберите (.{0,80}?)(?:,|\s+котор)", q)
    return m.group(1).lower() if m else ""


def options(k):
    """The closed class for the kind of word asked; pronouns in all forms. None - an open class."""
    global _MORPH
    keys = [key for key in LISTS if key in k]
    if "отрицательн" in keys and "частиц" in k:
        keys = ["отрицательную частиц"]
    if "союзн" in k:
        keys = ["союзное"]
    if len(keys) > 1 and "предлог" in keys:   # «производный предлог»: the specific list + the general one
        keys = [x for x in keys if x != "союз"]
    if len(keys) > 1 and "союз" in keys:      # «противительный союз»: the specific list only
        keys = [x for x in keys if x != "союз"]
    if not keys:
        return None
    words = []
    for key in keys:
        words += LISTS[key]
    if any(key in PRONOUNS for key in keys):
        if _MORPH is None:
            import pymorphy3
            _MORPH = pymorphy3.MorphAnalyzer()
        forms = []
        for w in words:
            if " " in w or w in ("его", "её", "их"):
                forms.append(w)
                continue
            p = next((p for p in _MORPH.parse(w) if p.normal_form.replace("ё", "е") == w.replace("ё", "е")), None)
            forms += [f.word for f in p.lexeme] if p else [w]
        words = forms
    return list(dict.fromkeys(w.replace("ё", "е") for w in words))


def gap_context(q):
    """The sentence with <...> and the one before it."""
    text = q.split("Самостоятельно подберите")[0]
    sents = re.split(r"(?<=[.!?…])\s+", re.sub(r"\s+", " ", text))
    i = next((j for j, s in enumerate(sents) if "<...>" in s), None)
    if i is None:
        return None
    return " ".join(sents[max(0, i - 1):i + 2])


SYS = ("Ты эксперт ЕГЭ по русскому языку, задание 1. Подбери слово на место пропуска <...> по смыслу и грамматике "
       "предложения (учти связь с соседними предложениями; помни: если владелец — подлежащее того же предложения, "
       "притяжательное местоимение — «свой»). Ответь ТОЛЬКО этим словом (или сочетанием) в нужной форме, без "
       "пояснений.")


THINK = int(__import__("os").environ.get("TASK1_THINK", "750"))   # 0 - no thinking: 49/28 vs 750: 64/19 of 87


def _think(system, user):
    """Thinking up to THINK tokens; if it has not finished, it is told time is up and answers."""
    import json
    import urllib.request

    def post(body):
        req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return json.loads(op.open(req, timeout=600).read())["choices"][0]["message"]

    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    m = post({"model": "brain", "messages": msgs, "temperature": 0, "max_tokens": THINK,
              "chat_template_kwargs": {"enable_thinking": True}})
    a = m.get("content") or ""
    if "ОТВЕТ:" not in a:
        thought = ((m.get("reasoning_content") or "") + "\n" + a).strip()
        a = post({"model": "brain", "messages": msgs + [{"role": "assistant", "content": thought},
                  {"role": "user", "content": "Время вышло. Одной строкой: ОТВЕТ: слово."}],
                  "temperature": 0, "max_tokens": 30, "chat_template_kwargs": {"enable_thinking": False}})
        a = a.get("content") or ""
    return a


def answer(q, chat):
    ctx = gap_context(q)
    if not ctx:
        return None
    k = kind(q)
    opts = options(k)
    task = q[q.find("Самостоятельно подберите"):].split("Ответ дай")[0].strip()
    user = f"Фрагмент: {ctx}\n{task}"
    if opts:
        base = sorted({o for o in opts if " " in o or len(o) < 14})
        user += "\nВозможные слова (в любой форме): " + ", ".join(base[:120])
    if THINK:   # short thinking (750 tokens, as the council's deep thinker), then the word on the last line
        a = _think(SYS + " Последней строкой: ОТВЕТ: слово.", user)
        m = re.findall(r"ОТВЕТ:\s*(.+)", a)
        a = m[-1] if m else ""
    else:
        a = chat([{"role": "system", "content": SYS}, {"role": "user", "content": user}], temperature=0,
                 max_tokens=20)[0] or ""
    a = re.sub(r"[«»\"'.!?*]", "", a.strip().split("\n")[0]).strip().lower().replace("ё", "е")
    if not a:
        return None
    if opts and a.replace(" ", "") not in {o.replace(" ", "") for o in opts}:
        return None
    return a.replace(" ", "")   # the EGE answer form: no spaces («несмотряна»)
