"""Plan step 12, the step judge (the author's design, 24.10: "judges decide by a check, not an opinion"): two solvers
write the solution independently as explicit steps - ДАНО (numbers of the condition with names), НАЙТИ, ШАГ lines
"name = expression", УРАВНЕНИЕ lines for unknowns, ОТВЕТ - and code computes every step (sympy: arithmetic, percents,
ceil/floor, equations). The model never counts in its head (diagnosis: 20/16 = 4, 4.95 -> 6 bags, a sign, a system).
Two computed answers agree -> the answer; disagree -> a third solver, the majority; no majority -> None (the council
falls back to the deep thinker). The judge is code: no extra model, nothing extra in VRAM.
"""
import re

import sympy

import units

SOLVER = (
    "Реши задачу по шагам в строгом формате. В уме ничего не считай: только записывай выражения, их посчитает "
    "калькулятор.\n"
    "ДАНО: по одной строке на каждое число из условия: имя = число [единица]  # что это (проценты пиши как 30%; "
    "неизвестные в ДАНО не пиши)\n"
    "НАЙТИ: что спрашивают [единица ответа]\n"
    "Единицы — одним словом: час, минута, рубль, страница, занятие, пакет; составные через /: занятие/день, км/час, "
    "страница/письмо; у долей, процентов и «во сколько раз» пиши [1]. Единицы проверит код: часы с занятиями не "
    "складываются, а занятия*час/занятие дают часы.\n"
    "ШАГ: имя = выражение из чисел и уже введённых имён  # что это\n"
    "(сколько нужно шагов; знаки + - * / ** и скобки, функции ceil, floor, sqrt, abs, max, min; дроби пиши через /)\n"
    "Если величину удобнее найти из уравнения: УРАВНЕНИЕ: левая часть = правая часть  (неизвестное — новое имя)\n"
    "ОТВЕТ: имя величины, которую спрашивают\n"
    "Имена — латиницей, коротко (a, b, cats, x). Каждый пункт на своей строке, без лишних слов. "
    "Если это не задача на счёт, ответь одним словом: НЕСЧЁТ.")
SOLVER_2 = SOLVER.replace("Реши задачу по шагам", "Сначала внимательно перечитай условие и вопрос. Затем реши задачу "
                          "по шагам, другим путём, чем решил бы торопливый человек,")
_NAME = re.compile(r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*")
_FUNCS = {"ceil": sympy.ceiling, "floor": sympy.floor, "sqrt": sympy.sqrt, "abs": sympy.Abs, "max": sympy.Max,
          "min": sympy.Min, "round": lambda v: sympy.Integer(round(v))}


def _expr(text, env, keep_unknown=True):
    """One side of a line -> sympy. Names are mapped to safe symbols (Cyrillic names work). An unknown name is an
    unknown of an equation when keep_unknown; otherwise it is a unit ("240 км", "100 yards", "2 л / 10 фут") and is
    dropped - the first measurement lost 6 of 11 problems to units."""
    text = text.split("#")[0].strip().rstrip(".;")
    text = text.replace("×", "*").replace("·", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    text = text.replace("$", "").replace("₽", "")
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", text)
    text = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", text)          # 25 000 -> 25000
    local = dict(_FUNCS)
    names = {}

    def name(m):
        n = m.group(0)
        if n in _FUNCS:
            return n
        if n in env or keep_unknown and not re.search(r"[А-Яа-яЁё]", n):
            names.setdefault(n, f"v{len(names)}")
            local[names[n]] = env.get(n, sympy.Symbol(n))
            return names[n]
        return " "                                              # a unit
    text = _NAME.sub(name, text)
    text = re.sub(r"(?<=[\d)])\s+(?=[\d(v])", "*", text.strip())     # "4 (" after a dropped unit -> 4*(
    text = re.sub(r"[\s*/+\-]+$", "", text).strip()
    text = re.sub(r"^[\s*/+]+", "", text)
    text = re.sub(r"/\s*(?=[)]|$)", "", text)
    if not text:
        raise ValueError("пусто")
    return sympy.sympify(text, locals=local, rational=True)


def compute(solution):
    """-> (value as sympy number, None) or (None, why it failed)."""
    if not solution or "НЕСЧЁТ" in solution.upper():
        return None, "не счёт"
    env, eqs, answer = {}, [], None
    for raw in solution.splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        kind, body = "", line
        while True:   # "ШАГ: УРАВНЕНИЕ: ..." - the innermost label counts
            m = re.match(r"^(ДАНО|ШАГ|ОТВЕТ|УРАВНЕНИЕ|НАЙТИ)\s*\d*\s*[:.)]?\s*(.*)$", body, re.I)
            if not m:
                break
            kind, body = m.group(1).upper(), m.group(2)
        if kind == "НАЙТИ":
            continue
        if kind == "ОТВЕТ":
            answer = body.split("#")[0].strip().rstrip(".")
            answer = answer.split("=")[0].strip() or answer
            continue
        body = body.split("#")[0]
        if "=" not in body:
            continue
        left, right = body.split("=", 1)
        left = left.strip()
        right = units.bracket(right)[0]                          # "3 [занятие/день]": the unit is units.py's
        if re.fullmatch(r"\s*\??\s*", right) or "?" in right:   # "x = ?" declares an unknown, nothing to compute
            continue
        try:
            if kind == "УРАВНЕНИЕ" or not _NAME.fullmatch(left):
                eqs.append(sympy.Eq(_expr(left, env), _expr(right, env)))
            else:
                v = _expr(right, env, keep_unknown=bool(eqs) or kind != "ДАНО")
                if v.free_symbols and eqs:
                    v = v.subs(_solve(eqs))
                env[left] = v
        except Exception as e:   # noqa: BLE001 - a line the code cannot read
            return None, f"не читается: {line[:60]} ({type(e).__name__})"
    if answer is None:
        return None, "нет ОТВЕТ"
    try:
        v = _expr(answer, env)
        if v.free_symbols and eqs:
            v = v.subs(_solve(eqs))
        v = sympy.nsimplify(v)
        if v.free_symbols:
            return None, "ответ не вычислен"
        return v, None
    except Exception as e:   # noqa: BLE001
        return None, f"ответ не читается ({type(e).__name__})"


def satisfies(solution, value):
    """Substitution check (the author's step 5: "the dispute is settled by a check - put the answer into the
    condition"): the solution's УРАВНЕНИЕ lines are the problem's conditions; does the answer = value fit them (with
    the other unknowns free)? -> True / False, or None if the conditions cannot be read."""
    env, eqs, answer = {}, [], None
    for raw in (solution or "").splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        kind, body = "", line
        while True:
            m = re.match(r"^(ДАНО|ШАГ|ОТВЕТ|УРАВНЕНИЕ|НАЙТИ)\s*\d*\s*[:.)]?\s*(.*)$", body, re.I)
            if not m:
                break
            kind, body = m.group(1).upper(), m.group(2)
        if kind == "НАЙТИ":
            continue
        if kind == "ОТВЕТ":
            answer = body.split("#")[0].strip().rstrip(".").split("=")[0].strip()
            continue
        body = body.split("#")[0]
        if "=" not in body:
            continue
        left, right = body.split("=", 1)
        right = units.bracket(right)[0]
        if "?" in right:
            continue
        try:
            if kind == "УРАВНЕНИЕ" or not _NAME.fullmatch(left.strip()):
                eqs.append(sympy.Eq(_expr(left, env), _expr(right, env)))
            else:
                env[left.strip()] = _expr(right, env, keep_unknown=kind != "ДАНО")
        except Exception:   # noqa: BLE001
            return None
    if not eqs or answer is None:
        return None
    try:
        system = eqs + [sympy.Eq(_expr(answer, env), sympy.nsimplify(str(value).replace(",", ".")))]
        syms = sorted(set().union(*[e.free_symbols for e in system if hasattr(e, "free_symbols")]), key=str)
        system = [e for e in system if e is not True]
        if any(e is False for e in system):
            return False
        if not syms:
            return all(abs(float(e.lhs - e.rhs)) < 1e-6 for e in system)
        sols = sympy.solve(system, syms, dict=True)
        return any(all(v.is_real for v in s.values()) for s in sols)
    except Exception:   # noqa: BLE001
        return None


SOLVER_EQ = (
    "Запиши условия задачи уравнениями, но НЕ решай их: их решит калькулятор.\n"
    "ДАНО: по одной строке на каждое число из условия: имя = число  # что это (проценты пиши как 30%)\n"
    "Искомую величину (ровно то, что спрашивают в вопросе) обозначь x; другие неизвестные — y, z.\n"
    "УРАВНЕНИЕ: левая часть = правая часть  — по одному уравнению на каждое условие задачи, из имён ДАНО и x, y, z\n"
    "ОТВЕТ: x\n"
    "Каждый пункт на своей строке, без лишних слов. Если это не задача на счёт, ответь одним словом: НЕСЧЁТ.")


def check(task, conclusion, chat, temperature=0.7):
    """Judge v2 (25.10, the author: different methods for the solvers + the substitution check): solver A counts
    forward by steps, solver B only writes the conditions as equations; the council's conclusion is put into B's
    equations. Fits -> confirmed. Does not fit and a solver has another number -> object with it.
    -> (object?, proposed answer or None, info)."""
    info = {"values": []}
    texts = [chat([{"role": "system", "content": s}, {"role": "user", "content": task}], temperature, 800)[0]
             for s in (SOLVER, SOLVER_EQ)]
    info["solutions"] = texts
    vals = []
    for t in texts:
        v, why = compute(t)
        if v is not None and check_units(t)[0] is False:
            v, why = None, "единицы"
        vals.append(v)
        info["values"].append(fmt(v) if v is not None else f"— {why}")
    try:
        c = sympy.nsimplify(str(conclusion).replace(",", ".").replace(" ", ""))
        c = c if c.is_number else None
    except Exception:   # noqa: BLE001
        c = None
    if c is None:
        info["verdict"] = "вывод не число"
        return False, None, info
    fits = satisfies(texts[1], c)
    info["fits"] = fits
    other = [v for v in vals if v is not None and abs(float(v - c)) > 1e-6]
    if fits is True:
        info["verdict"] = "подстановка сошлась"
        return False, None, info
    if fits is False and other:
        info["verdict"] = "подстановка не сошлась"
        return True, fmt(vals[1] if vals[1] is not None and vals[1] in other else other[0]), info
    if fits is None and len(other) == 2 and abs(float(other[0] - other[1])) < 1e-6:
        info["verdict"] = "оба решателя против"
        return True, fmt(other[0]), info
    info["verdict"] = "нет оснований"
    return False, None, info


def check_units(solution):
    """-> (True, '') the units agree; (False, why) a step adds different units or the answer is not in the asked unit;
    (None, why) cannot check (a number without a unit, equations, no НАЙТИ unit). Plan step 12: a check of the
    expression itself, by code - the model's translation of the problem is what goes wrong, not the arithmetic."""
    env, want, answer = {}, None, None
    for raw in (solution or "").splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        kind, body = "", line
        while True:
            m = re.match(r"^(ДАНО|ШАГ|ОТВЕТ|УРАВНЕНИЕ|НАЙТИ)\s*\d*\s*[:.)]?\s*(.*)$", body, re.I)
            if not m:
                break
            kind, body = m.group(1).upper(), m.group(2)
        body = body.split("#")[0]
        if kind == "УРАВНЕНИЕ":
            return None, "уравнения"
        if kind == "НАЙТИ":
            _, u = units.bracket(body)
            want = units.unit(u) if u is not None else None
            continue
        if kind == "ОТВЕТ":
            answer = body.strip().rstrip(".").split("=")[0].strip()
            continue
        if "=" not in body:
            continue
        left, right = body.split("=", 1)
        left = left.strip()
        if "?" in right or not _NAME.fullmatch(left):
            continue
        right, u = units.bracket(right)
        try:
            v = _expr(right, env, keep_unknown=False)
        except Exception:   # noqa: BLE001
            return None, f"не читается: {left}"
        if kind == "ДАНО":
            if u is None:
                return None, f"нет единицы у {left}"
            v = v * units.unit(u)
        try:
            num, unit_ = units.split(v)
        except Exception:   # noqa: BLE001 - a value sympy cannot even expand («00:00..23:59»)
            return None, f"не читается: {left}"
        if num is None:
            return False, f"шаг {left}: сложены разные единицы ({units.show(sympy.expand(v))[:60]})"
        env[left] = v
    if want is None or answer is None:
        return None, "нет единицы ответа"
    try:
        num, got = units.split(_expr(answer, env, keep_unknown=False))
    except Exception:   # noqa: BLE001
        return None, "ответ не читается"
    if num is None:
        return False, "ответ смешивает единицы"
    if got != want and got != 1 and want != 1:   # attempt 2: «без единиц» is the model not labelling, not a mistake
        return False, f"ответ в [{units.show(got)}], а спрашивают [{units.show(want)}]"
    return True, ""


def _solve(eqs):
    """The unknowns of the УРАВНЕНИЕ lines: a positive real solution if there are several."""
    sols = sympy.solve(eqs, dict=True)
    if not sols:
        raise ValueError("уравнения не решаются")
    for s in sols:
        if all(val.is_real and val > 0 for val in s.values()):
            return s
    return sols[0]


def fmt(v):
    v = sympy.nsimplify(v)
    if v.is_Integer:
        return str(int(v))
    f = float(v)
    return f"{f:.6f}".rstrip("0").rstrip(".") if abs(f - round(f, 6)) < 1e-9 else f"{f:.4f}"


def judge(task, chat, temperature=0.7):
    """-> (answer string or None, info). chat(messages, temperature, max_tokens) -> (text, usage)."""
    info = {"solutions": [], "values": []}

    def solve(system):
        text = chat([{"role": "system", "content": system}, {"role": "user", "content": task}], temperature, 800)[0]
        v, why = compute(text)
        ok_units, why_units = check_units(text)
        info.setdefault("units", []).append(why_units or ("сошлись" if ok_units else ""))
        if v is not None and ok_units is False:   # a wrongly composed solution does not count
            v, why = None, "единицы: " + why_units
        info["solutions"].append(text)
        info["values"].append(fmt(v) if v is not None else f"— {why}")
        return v

    vals = [solve(SOLVER), solve(SOLVER_2)]
    if all(v is None for v in vals) and "не счёт" in info["values"][0]:
        info["verdict"] = "не счёт"
        return None, info
    if vals[0] is not None and vals[1] is not None and abs(float(vals[0] - vals[1])) < 1e-9:
        info["verdict"] = "2 из 2"
        return fmt(vals[0]), info
    vals.append(solve(SOLVER))
    ok = [v for v in vals if v is not None]
    for v in ok:
        if sum(abs(float(v - w)) < 1e-9 for w in ok) >= 2:
            info["verdict"] = "2 из 3"
            return fmt(v), info
    info["verdict"] = "разошлись"
    return None, info
