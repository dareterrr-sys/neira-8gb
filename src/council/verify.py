"""Checkers instead of voting controllers (the author's idea, council v3): a checker does not pick an answer, it plugs
it into the conditions, the way a person checks a solution. The checker writes the conditions as a test of an unknown
x WITHOUT seeing any answer (so the test cannot lean towards one), then code - not the model - puts each candidate
into the test. In v2.2 the voting controllers turned 4 right answers into wrong ones and fixed 1.
"""
import ast
import math
import re

CHECK = ("Тебе дана задача. Запиши её условия как проверку для неизвестного ответа x: одно выражение на Python, которое "
         "истинно, если x — правильный ответ, и ложно иначе. Используй == для равенств и and между условиями, "
         "только числа, x, + - * / // % ** и скобки. Ничего не решай и не пиши ответ, только условия. Пример: «У Маши "
         "яблок вдвое больше, чем у Пети, а вместе у них 12. Сколько у Пети?» → x + 2 * x == 12. Если ответ задачи — "
         "не число или его нельзя проверить подстановкой (нужен факт, день недели, да/нет), ответь словом НЕТ.")

# Three checkers, each with its own method, blind to each other and to every answer (the author's idea: make them
# think differently; assigning methods up front keeps one checker's misreading from leaking into the others)
ESTIMATE = ("Тебе дана задача. Не решай её. Запиши границы здравого смысла для правильного ответа x: одно выражение на "
            "Python из сравнений, соединённых and, например x > 0 and x <= 15 and x == int(x). Пиши только то, что "
            "точно следует из условия (целое ли число, больше или меньше каких чисел из условия). Только числа, x, "
            "+ - * / и функции int, abs. Если ответ задачи — не число, ответь словом НЕТ.")
RESTATE = ("Тебе дана задача. Сначала перескажи её одним простым предложением своими словами, не решая. Затем запиши "
           "её условия как проверку для неизвестного ответа x: одно выражение на Python, истинное, только если x — "
           "правильный ответ (== для равенств, and между условиями, только числа, x, + - * / // % ** и скобки).\n"
           "Формат строго:\nПЕРЕСКАЗ: <предложение>\nПРОВЕРКА: <выражение>\n"
           "Если ответ задачи — не число, вместо выражения напиши НЕТ.")
METHODS = {"алгебраист": CHECK, "прикидчик": ESTIMATE, "пересказчик": RESTATE}
_FUNCS = {"int": lambda v: float(int(v)), "abs": abs, "round": lambda v, n=0: round(v, int(n))}

_OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b if abs(b) <= 64 else math.inf}


def _close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


_CMP = {ast.Eq: _close, ast.NotEq: lambda a, b: not _close(a, b), ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b}


def _ev(node, x):
    if isinstance(node, ast.Expression):
        return _ev(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id == "x":
        return x
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
        v = _ev(node.operand, x)
        return -v if isinstance(node.op, ast.USub) else (not v if isinstance(node.op, ast.Not) else v)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
            and not node.keywords and 1 <= len(node.args) <= 2):
        return _FUNCS[node.func.id](*[_ev(a, x) for a in node.args])
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.left, x), _ev(node.right, x))
    if isinstance(node, ast.BoolOp):
        vals = [bool(_ev(v, x)) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare) and all(type(o) in _CMP for o in node.ops):
        left = _ev(node.left, x)
        for op, comp in zip(node.ops, node.comparators):
            right = _ev(comp, x)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    raise ValueError(f"not allowed: {ast.dump(node)[:60]}")


def parse_check(text):
    """The checker's reply -> a test expression with x and a comparison, or None (НЕТ, prose, unsafe)."""
    t = (text or "").strip().strip("`").replace("×", "*").replace("−", "-").replace("^", "**")
    m = re.search(r"ПРОВЕРКА:\s*(.+)", t)   # the restater writes its retelling first
    if m:
        t = m.group(1).strip().strip("`")
    elif "ПЕРЕСКАЗ:" in t:
        return None
    t = re.sub(r"^(python|проверка:?)\s*", "", t, flags=re.I).splitlines()[0].strip() if t else ""
    if not t or t.upper().startswith("НЕТ") or "x" not in t:
        return None
    try:
        tree = ast.parse(t, mode="eval")
        if not any(isinstance(n, ast.Compare) for n in ast.walk(tree)):
            return None
        _ev(tree, 1.0)   # rejects anything outside the whitelist
        return t
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError):
        return t if _safe(t) else None


def _safe(t):
    try:
        tree = ast.parse(t, mode="eval")
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        names = {n.func.id for n in calls if isinstance(n.func, ast.Name)}
        return (all(isinstance(n, (ast.Expression, ast.Constant, ast.Name, ast.UnaryOp, ast.BinOp, ast.BoolOp,
                                   ast.Compare, ast.Call, ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.Load))
                    for n in ast.walk(tree))
                and all(isinstance(c.func, ast.Name) and not c.keywords for c in calls) and names <= set(_FUNCS)
                and all(n.id == "x" or n.id in _FUNCS for n in ast.walk(tree) if isinstance(n, ast.Name)))
    except SyntaxError:
        return False


def _has_x(node):
    return any(isinstance(n, ast.Name) and n.id == "x" for n in ast.walk(node))


def is_answer(check):
    """True for a 'test' that is really an answer: x on one side, no x on the other ("x == 100", "24 / 3 - 24 + 7 ==
    x"). In the checker measurement every real wrong answer that slipped through came from such a line or from one
    misread condition: the checker solved the problem instead of writing its conditions, and repeated the mistake."""
    try:
        body = ast.parse(check, mode="eval").body
    except SyntaxError:
        return False
    parts = body.values if isinstance(body, ast.BoolOp) and isinstance(body.op, ast.And) else [body]
    for p in parts:
        if isinstance(p, ast.Compare) and len(p.ops) == 1 and isinstance(p.ops[0], ast.Eq):
            sides = [p.left, p.comparators[0]]
            if any(isinstance(s, ast.Name) and s.id == "x" for s in sides) and sum(_has_x(s) for s in sides) == 1:
                return True
    return False


def holds(check, value):
    """True / False if the candidate value meets the test; None if the test cannot run on it."""
    try:
        return bool(_ev(ast.parse(check, mode="eval"), float(value)))
    except (ValueError, ZeroDivisionError, OverflowError, TypeError, SyntaxError):
        return None


def write_method_checks(q, chat, mapper=map):
    """One test per method (алгебраист, прикидчик, пересказчик) -> {method: (test or None, raw reply)}.
    mapper: map, or a parallel map that sends the three to the server as one batch (plan step 8в.7)."""
    def one(item):
        name, prompt = item
        return chat([{"role": "system", "content": prompt}, {"role": "user", "content": q}], 0.7,
                    200 if name == "пересказчик" else 80)[0]
    raws = list(mapper(one, METHODS.items()))
    return {name: (parse_check(raw), raw) for name, raw in zip(METHODS, raws)}


def write_checks(q, chat, n=3):
    """n independent checkers write the test; -> list of parsed tests (None where a checker declined)."""
    return [parse_check(chat([{"role": "system", "content": CHECK}, {"role": "user", "content": q}], 0.7, 80)[0])
            for _ in range(n)]


def verdict(checks, value):
    """How the checkers judge one candidate: 'да' (most runnable tests hold), 'нет' (most fail), None (can't tell)."""
    res = [holds(c, value) for c in checks if c]
    res = [r for r in res if r is not None]
    if len(res) < 2:
        return None
    yes = sum(res)
    return "да" if yes * 2 > len(res) else ("нет" if yes * 2 < len(res) else None)
