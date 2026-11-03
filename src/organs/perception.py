"""Neira's perception: code that reads structured parts of a message before any model sees it (the author's idea:
fix perception before reasoning; information is Neira's material world).

numbers_to_digits(): Russian number words -> digits, in any case form: "две тысячи сотый год" -> "2100-й год",
"из трёх лампочек" -> "из 3 лампочек", "два с половиной" -> "2.5". Council v2.2 read "две тысячи сотый" as 2000
and answered that the year is a leap year. A lone "один/одна" (often a pronoun: "один мальчик сказал") and a lone
ordinal ("каким ты стал - вторым?") are left as they are; ordinals are converted only inside a compound number.
"""
import re

# every case form of every number word -> its value; kind: u units (0-9), t teens/tens, h hundreds, k thousand-like
_W = {}


def _add(value, kind, *forms):
    for f in forms:
        _W[f] = (value, kind)


_add(0, "u", "ноль", "нуль", "нуля", "нулю", "нолём", "нулём", "нолем", "нулем", "ноле", "нуле")
_add(1, "u", "один", "одного", "одному", "одним", "одном", "одна", "одной", "одну", "одною", "одно")
_add(2, "u", "два", "две", "двух", "двум", "двумя")
_add(3, "u", "три", "трёх", "трех", "трём", "трем", "тремя")
_add(4, "u", "четыре", "четырёх", "четырех", "четырём", "четырем", "четырьмя")
for v, stem in [(5, "пят"), (6, "шест"), (7, "сем"), (8, "восем"), (9, "девят"), (10, "десят")]:
    _add(v, "u" if v < 10 else "t", stem + "ь", stem + "и" if v != 8 else "восьми", stem + "ью")
_add(8, "u", "восьмью")
for v, stem in [(11, "одиннадцат"), (12, "двенадцат"), (13, "тринадцат"), (14, "четырнадцат"), (15, "пятнадцат"),
                (16, "шестнадцат"), (17, "семнадцат"), (18, "восемнадцат"), (19, "девятнадцат"), (20, "двадцат"),
                (30, "тридцат")]:
    _add(v, "t", stem + "ь", stem + "и", stem + "ью")
_add(40, "t", "сорок", "сорока")
for v, nom, obl, ins in [(50, "пятьдесят", "пятидесяти", "пятьюдесятью"), (60, "шестьдесят", "шестидесяти", "шестьюдесятью"),
                         (70, "семьдесят", "семидесяти", "семьюдесятью"), (80, "восемьдесят", "восьмидесяти", "восемьюдесятью")]:
    _add(v, "t", nom, obl, ins)
_add(90, "t", "девяносто", "девяноста")
_add(100, "h", "сто", "ста")
_add(200, "h", "двести", "двухсот", "двумстам", "двумястами", "двухстах")
_add(300, "h", "триста", "трёхсот", "трехсот", "трёмстам", "тремстам", "тремястами", "трёхстах", "трехстах")
_add(400, "h", "четыреста", "четырёхсот", "четырехсот", "четырёмстам", "четыремстам", "четырьмястами", "четырёхстах",
     "четырехстах")
for v, stem in [(500, "пят"), (600, "шест"), (700, "сем"), (800, "восем"), (900, "девят")]:
    obl = "восьми" if v == 800 else stem + "и"
    _add(v, "h", stem + "ьсот", obl + "сот", obl + "стам", stem + "ьюстами", obl + "стах")
for v, stem in [(1000, "тысяч"), (10 ** 6, "миллион"), (10 ** 9, "миллиард")]:
    ends = ["а", "и", "у", "ей", "ею", "", "ам", "ами", "ах", "е"] if v == 1000 else \
        ["", "а", "у", "ом", "е", "ы", "ов", "ам", "ами", "ах"]
    _add(v, "k", *[stem + e for e in ends])

# ordinals (only as the last word of a compound number): stem -> value
_ORD = {"нулев": 0, "перв": 1, "втор": 2, "трет": 3, "четвёрт": 4, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7,
        "восьм": 8, "девят": 9, "десят": 10, "одиннадцат": 11, "двенадцат": 12, "тринадцат": 13,
        "четырнадцат": 14, "пятнадцат": 15, "шестнадцат": 16, "семнадцат": 17, "восемнадцат": 18,
        "девятнадцат": 19, "двадцат": 20, "тридцат": 30, "сороков": 40, "пятидесят": 50, "шестидесят": 60,
        "семидесят": 70, "восьмидесят": 80, "девяност": 90, "сот": 100, "двухсот": 200, "трёхсот": 300,
        "трехсот": 300, "четырёхсот": 400, "четырехсот": 400, "пятисот": 500, "шестисот": 600, "семисот": 700,
        "восьмисот": 800, "девятисот": 900}   # no "тысячный": after a cardinal it is a fraction ("пять тысячных")
_ORD_END = r"(ый|ой|ий|ая|ое|ые|ого|ому|ым|ом|ую|ей|ых|ыми|ье|ья|ьи|ьего|ьему|ьим|ьем|ью|ьей|ьих)"
_ORD_RE = re.compile("(" + "|".join(sorted(_ORD, key=len, reverse=True)) + ")" + _ORD_END + "$")
_HALF = {"полтора": 1.5, "полторы": 1.5, "полутора": 1.5}

_TOKEN = re.compile(r"[А-Яа-яЁё]+|\S")


def _ordinal(word):
    m = _ORD_RE.match(word)
    if not m:
        return None
    end = m.group(2)
    # "трет" takes the soft endings (третий, третьего); the others the hard ones
    if (m.group(1) == "трет") != end.startswith("ь") and not (m.group(1) == "трет" and end in ("ий", "ья", "ье", "ьи")):
        return None
    return _ORD[m.group(1)], end


def _value(words):
    """Values of a run of cardinal words -> the number they spell, or None if they are not one number
    ("три четыре" is two numbers; a unit after a unit breaks the run)."""
    total, group, last = 0, 0, None
    for v, kind in words:
        if kind == "k":
            total += (group or 1) * v
            group, last = 0, "k"
            continue
        order = {"h": 3, "t": 2, "u": 1}[kind]
        if last in ("h", "t", "u") and {"h": 3, "t": 2, "u": 1}[last] <= order:
            return None
        if kind == "t" and v < 20 and last == "t":
            return None
        group += v
        last = kind if not (kind == "t" and v < 20) else "u"   # a teen ends its group like a unit
    return total + group


_SUFFIX = {"ый": "й", "ой": "й", "ий": "й", "ого": "го", "его": "го", "ьего": "го", "ому": "му", "ему": "му",
           "ьему": "му", "ым": "м", "им": "м", "ьим": "м", "ом": "м", "ем": "м", "ьем": "м", "ая": "я", "ья": "я",
           "ую": "ю", "ью": "ю", "ое": "е", "ье": "е", "ые": "е", "ьи": "е", "ых": "х", "их": "х", "ьих": "х",
           "ыми": "ми", "ей": "й", "ьей": "й"}


def _kind(v):
    return "u" if v < 10 else "t" if v < 100 else "h" if v < 1000 else "k"


def _groups(run):
    """Split a run of cardinal words into numbers, longest first: "три четыре пять" -> 3, 4, 5."""
    out, a = [], 0
    while a < len(run):
        b = len(run)
        while b > a + 1 and _value(run[a:b]) is None:
            b -= 1
        out.append((a, b, _value(run[a:b])))
        a = b
    return out


def numbers_to_digits(text):
    spans = [(m.start(), m.end(), m.group(0).lower()) for m in _TOKEN.finditer(text)]
    out, pos, i = [], 0, 0

    def joined(j):   # token j follows token j-1 with only spaces between
        return text[spans[j - 1][1]:spans[j][0]].strip() == ""

    while i < len(spans):
        s, e, w = spans[i]
        if w in _HALF:
            out.append(text[pos:s] + "1.5")
            pos, i = e, i + 1
            continue
        if w not in _W:
            i += 1
            continue
        j = i
        while j < len(spans) and spans[j][2] in _W and (j == i or joined(j)):
            j += 1
        run = [_W[spans[k][2]] for k in range(i, j)]
        groups = _groups(run)
        for g, (a, b, value) in enumerate(groups):
            first, last = i + a, i + b - 1
            end_pos = spans[last][1]
            text_num = str(value)
            if g == len(groups) - 1:
                ordinal = _ordinal(spans[j][2]) if j < len(spans) and joined(j) else None
                if ordinal and _value(run[a:b] + [(ordinal[0], _kind(ordinal[0]))]) is not None:
                    full = _value(run[a:b] + [(ordinal[0], _kind(ordinal[0]))])
                    text_num = f"{full}-{_SUFFIX.get(ordinal[1], ordinal[1])}"
                    end_pos = spans[j][1]
                    j += 1
                else:
                    half = re.match(r"\s+с\s+половиной\b", text[end_pos:], re.I)
                    if half:
                        text_num, end_pos = f"{value}.5", end_pos + half.end()
                        while j < len(spans) and spans[j][0] < end_pos:
                            j += 1
            if b - a == 1 and value == 1 and text_num == "1":
                continue   # a lone "один/одна": often a pronoun ("один мальчик"), leave it
            gap = text[pos:spans[first][0]]
            # "девятью девять", "пятью пять": a number in the instrumental right before another is the
            # multiplication table (council v3.1 read "9 9" as 99)
            if g > 0 and gap.strip() == "" and spans[i + groups[g - 1][1] - 1][2].endswith(("ью", "мя")):
                gap = " × "
            out.append(gap + text_num)
            pos = end_pos
        i = j
    out.append(text[pos:])
    return _tidy("".join(out))


# number words the digit pass leaves as words on purpose (a pronoun-like "один", collectives, digit names, a lone
# ordinal) - but in an answer they do name a number ("всего пятеро детей", "девятка", "на восьмой день")
_SAID_EXTRA = {"двое": 2, "трое": 3, "четверо": 4, "пятеро": 5, "шестеро": 6, "семеро": 7, "девятеро": 9,
               "десятеро": 10, "единиц": 1, "двойк": 2, "тройк": 3, "четверк": 4, "пятерк": 5, "шестерк": 6,
               "семерк": 7, "восьмерк": 8, "девятк": 9, "десятк": 10, "ноль": 0, "нол": 0, "нул": 0, "один": 1,
               "одн": 1, "половин": 0.5}
_TAG = re.compile(r"\[[^\]]*\]|\{[^}]*\}")


def numbers_said(text):
    """Every number an answer names, in any form: digits, words in any case, "пятеро", "девятка", "восьмой"."""
    plain = _TAG.sub(" ", text or "")
    nums = {float(n.replace(",", ".")) for n in re.findall(r"-?\d+(?:[.,]\d+)?", numbers_to_digits(plain))}
    for w in re.findall(r"[а-яё]+", plain.lower()):
        w = w.replace("ё", "е")
        nums.update(float(v) for stem, v in _SAID_EXTRA.items() if w.startswith(stem))
        o = _ordinal(w)
        if o:
            nums.add(float(o[0]))
    return nums


_DENOM = {"втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7, "восьм": 8, "девят": 9, "десят": 10,
          "сот": 100, "тысячн": 1000}
_DENOM_RE = "(" + "|".join(_DENOM) + r")(?:ых|ые|ыми|ым|ая|ой|ую|и|ей|ям|ями|ях)"


def _tidy(t):
    """Patterns the word-by-word pass leaves half-read (all seen in the question sets):
    "0 целых 8 десятых" -> "0.8"; "2 пятых", "2 трети" -> "2/5", "2/3"; "в 10 45" -> "в 10:45";
    "один, один, 2, 3" -> "1, 1, 2, 3"; "от одного до 100" -> "от 1 до 100"."""
    def decimal(m):
        whole, part, d = m.group(1), m.group(2), _DENOM[m.group(3)]
        digits = len(str(d)) - 1
        return f"{whole}.{int(part):0{digits}d}" if int(part) < d else m.group(0)
    t = re.sub(r"\b(\d+) цел(?:ых|ая|ой|ую) (\d+) (десят|сот|тысячн)\w*", decimal, t)
    t = re.sub(r"\b(\d+) " + _DENOM_RE + r"\b", lambda m: f"{m.group(1)}/{_DENOM[m.group(2)]}", t)
    t = re.sub(r"\b(в|с|до|к|после|около|начался в|началась в)\s+(\d{1,2}) (\d{2})\b",
               lambda m: f"{m.group(1)} {m.group(2)}:{m.group(3)}"
               if int(m.group(2)) <= 24 and 10 <= int(m.group(3)) <= 59 else m.group(0), t)
    t = re.sub(r"\bот одного до (\d)", r"от 1 до \1", t)
    t = re.sub(r"\b([Мм])етр (\d{2})\b(?! ?(?:метр|сантиметр|см))", r"1.\2 м", t)   # "ростом метр пятьдесят" -> 1.50 м
    t = re.sub(r"\b([Дд]важды|[Тт]рижды|[Чч]етырежды)\s+(\d)",
               lambda m: {"д": "2", "т": "3", "ч": "4"}[m.group(1)[0].lower()] + " × " + m.group(2), t)
    for _ in range(3):   # a lone "один" inside a list of numbers is a number, not a pronoun
        t = re.sub(r"(?<![А-Яа-яЁё])[Оо]дин(?=,\s*(?:\d|[Оо]дин\b))", "1", t)
        t = re.sub(r"(?<=\d,\s)один\b", "1", t)
    return t
