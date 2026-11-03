"""Neira's calculator: a tiny MCP server (stdio) with one tool, calculate(expression).

The brain sends arithmetic here instead of counting "in its head" (both brains got 3 - 2 + 5 - 1 wrong in a blind test).
Only arithmetic is evaluated, by walking the parsed expression tree: no eval/exec, no names except the math functions
and constants below. Numbers stay exact fractions until a function (sqrt, sin, ...) needs a float.
Run (Open-LLM-VTuber venv): python calc_server.py   - Open-LLM-VTuber starts it from mcp_servers.json.
"""
import ast
import math
import os
import re
import subprocess
from fractions import Fraction

from mcp.server.fastmcp import FastMCP

MAX_POW = 10_000          # exponent limit: 2**10000 is fine, 10**10**10 is not
MAX_DIGITS = 4_000        # an exact result longer than this is refused
FUNCS = {
    "sqrt": math.sqrt, "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x), "exp": math.exp,
    "ln": math.log, "log": math.log, "log10": math.log10, "log2": math.log2,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh, "degrees": math.degrees, "radians": math.radians,
    "abs": abs, "floor": math.floor, "ceil": math.ceil, "round": round,
}
INT_FUNCS = {"factorial": math.factorial, "gcd": math.gcd, "lcm": math.lcm}
CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _num(x):
    return Fraction(x) if isinstance(x, (int, Fraction)) else x


def _check(x):
    if isinstance(x, Fraction) and (len(str(x.numerator)) > MAX_DIGITS or len(str(x.denominator)) > MAX_DIGITS):
        raise ValueError("слишком большое число")
    return x


def _ev(node):
    if isinstance(node, ast.Expression):
        return _ev(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Fraction(node.value) if isinstance(node.value, int) else Fraction(str(node.value))
    if isinstance(node, ast.Name) and node.id in CONSTS:
        return CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _ev(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp):
        a, b = _ev(node.left), _ev(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return _check(a + b)
        if isinstance(op, ast.Sub):
            return _check(a - b)
        if isinstance(op, ast.Mult):
            return _check(a * b)
        if isinstance(op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if b == 0:
                raise ZeroDivisionError("деление на ноль")
            if isinstance(op, ast.Div):
                return _check(a / b)
            return _check(a // b if isinstance(op, ast.FloorDiv) else a % b)
        if isinstance(op, ast.Pow):
            if isinstance(b, Fraction) and b.denominator == 1 and isinstance(a, Fraction):
                if abs(b) > MAX_POW:
                    raise ValueError("слишком большая степень")
                return _check(a ** int(b))
            return _real(float(a) ** float(b))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        args = [_ev(x) for x in node.args]
        name = node.func.id
        if name in INT_FUNCS:
            if any(not (isinstance(x, Fraction) and x.denominator == 1) for x in args):
                raise ValueError(f"{name} принимает только целые числа")
            ints = [int(x) for x in args]
            if name == "factorial" and (len(ints) != 1 or not 0 <= ints[0] <= 1000):
                raise ValueError("факториал считаю для чисел от 0 до 1000")
            return _check(Fraction(INT_FUNCS[name](*ints)))
        if name in FUNCS:
            if name == "round" and len(args) == 2:
                return Fraction(round(args[0], int(args[1])))
            if name in ("abs", "floor", "ceil", "round") and all(isinstance(x, Fraction) for x in args):
                r = FUNCS[name](*args)
                return Fraction(r)
            return _real(FUNCS[name](*[float(x) for x in args]))
    raise ValueError("непонятная часть выражения: " + ast.dump(node)[:60])


def _real(x):
    """A root of a negative number etc. gives a complex number in Python; for Neira it is an error (the author's C
    calculator says "math error" there - a cross-check of the two calculators found this, 2026-10-20)."""
    if isinstance(x, complex):
        raise ValueError("результат не вещественное число")
    return x


def _show(x) -> str:
    if isinstance(x, Fraction):
        if x.denominator == 1:
            return str(x.numerator)
        dec = f"{float(x):.10g}"
        return f"{dec} (точно {x.numerator}/{x.denominator})" if x.denominator < 10_000 else dec
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            raise ValueError("результат не число")
        return f"{x:.10g}"
    return str(x)


C_CALC = os.environ.get("NEIRA_CALC_EXE", r"D:\AI\neira-tools\calc_c\calc.exe")
C_ERRORS = {"syntax error": "Ошибка: непонятное выражение", "division by zero": "Ошибка: деление на ноль",
            "math error": "Ошибка: результат не вещественное число или слишком большой"}


def python_calc(text: str) -> str:
    try:
        return _show(_ev(ast.parse(text, mode="eval")))
    except ZeroDivisionError:
        return "Ошибка: деление на ноль"
    except (ValueError, TypeError, OverflowError, SyntaxError) as e:
        return f"Ошибка: {e}"


C_DLL = os.environ.get("NEIRA_CALC_DLL", r"D:\AI\neira-tools\calc_c\calc.dll")
_c_lib = None


def _load_c_lib():
    """calc.dll in this process (2.8 us per expression; the calc.exe process start took 3.9 ms)."""
    global _c_lib
    if _c_lib is None and os.path.exists(C_DLL):
        import ctypes
        lib = ctypes.CDLL(C_DLL)
        lib.calc_eval.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_double)]
        lib.calc_eval.restype = ctypes.c_int
        _c_lib = lib
    return _c_lib


def c_calc(text: str):
    """The author's C calculator (calc_c/calc.c) for plain arithmetic; None when it is missing or not applicable."""
    if not re.fullmatch(r"[0-9.\s+\-*/()]+", text):
        return None
    lib = _load_c_lib()
    if lib is not None:
        import ctypes
        result = ctypes.c_double()
        status = lib.calc_eval(text.encode("ascii"), ctypes.byref(result))
        if status:
            return C_ERRORS[{1: "syntax error", 2: "division by zero"}.get(status, "math error")]
        return f"{result.value:.12g}"
    if not os.path.exists(C_CALC):
        return None
    try:                              # fallback: the program itself
        out = subprocess.run([C_CALC], input=text, capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return C_ERRORS.get(out, out)


def calculate_text(expression: str) -> str:
    text = expression.strip().replace("×", "*").replace("·", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)          # 2,5 -> 2.5 (Russian decimals)
    if len(text) > 500:
        return "Ошибка: выражение слишком длинное"
    py = python_calc(text)
    c = c_calc(text)
    if c is None:                     # functions (sqrt, sin...) or no C calculator: Python alone
        return py
    # two independent calculators must agree, like Neira's specialists
    if py.startswith("Ошибка") or c.startswith("Ошибка"):
        return py if py.startswith("Ошибка") else c
    try:
        agree = math.isclose(float(py.split(" ")[0]), float(c), rel_tol=1e-9, abs_tol=1e-9)
    except ValueError:
        agree = False
    return py if agree else f"Ошибка: два калькулятора разошлись (Python {py}, C {c})"


mcp = FastMCP("calculator")


@mcp.tool()
def calculate(expression: str) -> str:
    """Точно вычисляет математическое выражение. Используй для ЛЮБОГО счёта, даже простого, вместо счёта в уме.
    Пиши выражение цифрами и знаками: + - * / ** (степень) // (целая часть) % (остаток), скобки;
    функции sqrt, cbrt, exp, ln, log10, log2, sin, cos, tan (радианы), degrees, radians, abs, floor, ceil, round,
    factorial, gcd, lcm; константы pi, e. Пример: (3 - 2 + 5) - 1  или  60 * 1 / (90 - 60).
    Возвращает число (дроби точно, например 0.3333333333 (точно 1/3)) или текст ошибки."""
    return calculate_text(expression)


if __name__ == "__main__":
    mcp.run()
