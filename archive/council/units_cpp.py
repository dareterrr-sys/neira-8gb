# -*- coding: utf-8 -*-
"""Гибрид: C++-версия строковых функций units.py + sympy-версия символьных.

Зачем: stem() и bracket() работают с чистыми строками — они перенесены на C++
(units.dll, сборка w64devkit). unit() берёт из C++ канонический вид монома, но
возвращает sympy-объект (контракт с steps.py, где unit() умножается на числа и
передаётся в split()/show()). split() и show() работают с sympy-объектами и
остаются на Python.

Использование: в steps.py заменить `import units` на `import units_cpp as units`.
Если units.dll отсутствует — прозрачный откат на исходный units.py целиком.

Проверено (25.10.2026): stem()/unit()/bracket() дают те же результаты, что и
Python, на 30+ тестах; judge() на фейковом чате отвечает верно.
"""
import ctypes
import os

import sympy

_HERE = os.path.dirname(os.path.abspath(__file__))
_DLL = os.path.join(_HERE, "cpp", "units.dll")

_lib = None
try:
    if os.path.exists(_DLL):
        _lib = ctypes.CDLL(_DLL)
        _lib.units_stem.restype = ctypes.c_char_p
        _lib.units_unit.restype = ctypes.c_char_p
        _lib.units_bracket.restype = ctypes.c_char_p
except Exception:
    _lib = None


def _c(fn, text):
    raw = fn(text.encode("utf-8"))
    return raw.decode("utf-8") if raw is not None else ""


# Символьные функции обязательно из Python (работают с sympy-объектами)
from units import split, show  # noqa: E402,F401

if _lib is None:
    from units import stem, unit, bracket  # noqa: E402,F401
else:
    def stem(word):
        return _c(_lib.units_stem, word)

    def unit(text):
        """'занятие/день' -> sympy monomial U_занят / U_ден (как в units.py)."""
        mono = _c(_lib.units_unit, text)
        if mono in ("", "1"):
            return sympy.Integer(1)
        expr = sympy.Integer(1)
        for tok in mono.split():
            name = tok.replace("U_", "")
            if "^" in name:
                base, power = name.split("^", 1)
                expr *= sympy.Symbol("U_" + base) ** int(power)
            else:
                expr *= sympy.Symbol("U_" + name)
        return expr

    def bracket(text):
        raw = _c(_lib.units_bracket, text)
        if "|" in raw:
            body, u = raw.split("|", 1)
            return body, (u if u else None)
        return raw, None
