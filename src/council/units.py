"""Units for the step judge (plan step 12, the author: "make the expressions be composed correctly"). The model cannot
be made to translate a problem into arithmetic without mistakes, but a whole class of wrong expressions is visible to
code: the units do not match. g155 wrote (3+3+2+2)*16 - lessons per week times weeks gives lessons, the question asks
for hours. Each number carries a unit in brackets ("a = 3 [занятие/день]"), НАЙТИ names the unit of the answer
("НАЙТИ: часов за семестр [час]"); units are sympy symbols, so * and / combine them by themselves, and + of different
units, or an answer in other units than asked, is a mistake in the expression.
"""
import re

import sympy

_ABBR = {"ч": "час", "мин": "минут", "с": "секунд", "сек": "секунд", "руб": "рубл", "р": "рубл", "долл": "доллар",
         "шт": "штук", "кг": "кг", "г": "грамм", "км": "км", "м": "метр", "см": "см", "мм": "мм", "л": "литр",
         "мл": "мл", "$": "доллар", "₽": "рубл", "%": "процент", "фут": "фут", "ярд": "ярд"}
_END = re.compile(r"(ами|ями|ов|ев|ей|ах|ях|ам|ям|ой|ий|ия|ие|ья|ье|а|я|ы|и|у|ю|е|о|ь|й)$")


def stem(word):
    """«часов» -> час, «занятия» -> занят, «мин» -> минут: one symbol for every form of a unit."""
    w = word.lower().replace("ё", "е").strip(" .")
    if w in _ABBR:
        return _ABBR[w]
    s = _END.sub("", w)
    return _ABBR.get(s, s) if len(s) >= 2 else w


def unit(text):
    """'занятие/день' -> sympy monomial U_занят / U_ден; '' or '1' -> 1 (no unit)."""
    text = (text or "").strip().strip("[]").strip()
    if text in ("", "1", "-", "—"):
        return sympy.Integer(1)
    num, *den = re.split(r"\s*/\s*", text)
    u = sympy.Integer(1)
    for part, sign in [(num, 1)] + [(d, -1) for d in den]:
        for w in re.split(r"\s*[*·×]\s*|\s+", part.strip()):
            if w and w != "1":
                m = re.match(r"^(.+?)(\^|\*\*)?(\d)?$", w)
                base, power = m.group(1), int(m.group(3) or 1)
                u *= sympy.Symbol("U_" + stem(base)) ** (sign * power)
    return u


def bracket(text):
    """'3 [занятие/день]  # ...' -> ('3', 'занятие/день'); no brackets -> (text, None)."""
    m = re.search(r"\[([^\]]*)\]", text)
    if not m:
        return text, None
    return (text[:m.start()] + text[m.end():]).strip(), m.group(1)


def split(q):
    """A sympy quantity -> (number part, unit monomial) or (None, None) if it mixes units (a sum of different ones)."""
    # ceil(545 чашка / 110 чашка/пакет) has the unit of its argument: for the units, rounding is the identity
    q = q.replace(lambda e: isinstance(e, (sympy.ceiling, sympy.floor)), lambda e: e.args[0])
    q = sympy.expand(q)
    terms = sympy.Add.make_args(q)
    units = set()
    for t in terms:
        coeff, rest = t.as_independent(*[s for s in t.free_symbols if s.name.startswith("U_")])
        units.add(rest)
    # attempt 2 (25.10): a bare number added to a quantity is the model not labelling it («5 человек - 2»), not a
    # wrong expression - only two different real units in one sum count
    if len(units) > 1:
        units.discard(sympy.Integer(1))
    if len(units) != 1:
        return None, None
    u = units.pop()
    return sympy.simplify(q / u), u


def show(u):
    return str(u).replace("U_", "") if u != 1 else "без единиц"
