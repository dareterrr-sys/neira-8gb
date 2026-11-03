# -*- coding: utf-8 -*-
"""Нейра пишет my_sprintf: цикл «генерация → тест → фидбек» через API.
"""
import os
import re
import subprocess
import sys
import tempfile
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neira_api import ask

MIN_ENV = {
    "PATH": r"D:\Programs\w64devkit\bin;C:\Windows\System32;C:\Windows",
    "SystemRoot": r"C:\Windows",
    "TEMP": os.environ.get("TEMP", tempfile.gettempdir()),
    "TMP": os.environ.get("TMP", tempfile.gettempdir()),
    "TMPDIR": tempfile.gettempdir(),
}

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = r"D:\AI\neira-tools\saved"
HARNESS = os.path.join(SAVED, "sprintf_harness.c")
IMPL = os.path.join(SAVED, "sprintf_neira_impl.c")
FULL = os.path.join(SAVED, "sprintf_neira_full.c")
GCC = r"D:\Programs\w64devkit\bin\gcc.exe"

TASK = (
    "Напиши на C функцию int my_sprintf(char *buffer, const char *format, ...) — "
    "полный аналог sprintf (C99/C11). Поддержка всех спецификаторов: "
    "d i u o x X e E f F g G c s p n %; флагов - + пробел # 0; ширины (число и *); "
    "точности (число, *, пустая); модификаторов длины hh h l ll j z t L. "
    "Генерация всех цифр — ТОЛЬКО целочисленной арифметикой (BigInt/массивы). "
    "ЗАПРЕЩЕНО вызывать любые printf/snprintf/vsnprintf для генерации результата. "
    "Округление вещественных — по точному двоичному значению: при попадании ровно "
    "на середину округляй к чётной цифре, иначе в большую сторону. "
    "Знаки: -0.0 выводится с минусом; inf/-inf/nan как в C. "
    "Возвращаемое значение — число записанных символов без NUL. "
    "Буфер всегда завершай NUL. Не используй плавающую арифметику для генерации цифр. "
    "Не используй ограничители кода (тройные обратные кавычки ```) — верни ТОЛЬКО "
    "чистый код функции my_sprintf (без main, без тестов, без пояснений)."
)

def extract_code(text):
    fences = text.count("```")
    if fences >= 2:
        first = text.find("```")
        last = text.rfind("```")
        inner = text[first:last]
        # убрать флаги языка после открывающих ``` (```c и т.п.)
        nl = inner.find("\n")
        if nl != -1 and inner.count("\n", 0, nl) == 0:
            head = inner[:nl].strip()
            if head.startswith("```"):
                inner = inner[nl + 1:]
        # обрезать хвост после закрывающих
        tail = inner.rfind("```")
        if tail != -1:
            inner = inner[:tail]
        return inner.strip()
    return text.strip()

def prepare_impl(impl):
    """Оставить только саму реализацию: без тестов, main допускается (см. сборку)."""
    for marker in ("// ---------- тесты", "/* ---------- тесты"):
        idx = impl.find(marker)
        if idx != -1:
            impl = impl[:idx]
    first_incl = impl.find("#include")
    if first_incl > 300:
        impl = impl[first_incl:]
    return impl.strip()

def split_code_from_harness(harness, impl):
    marker = "/* ---------- тесты ---------- */"
    idx = harness.index(marker)
    head = harness[:idx]
    cut = head.index("/* РЕАЛИЗАЦИЯ (вставь сюда): */")
    tail = harness[idx:]
    # если в реализации нет main — дописываем обёртку, зовущую harness_main
    if "int main(" not in impl:
        tail += "\nint main(void) { return harness_main(); }\n"
    return head[:cut] + impl + "\n\n" + tail

CHECK_CODE = r"D:\AI\neira-tools\check_code.exe"

def compile_run(final):
    import json as _json
    try:
        comp = subprocess.run(
            [CHECK_CODE, final, "--timeout", "120000"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=MIN_ENV, cwd=HERE, timeout=300)
    except OSError as e:
        return 127, f"check_code OSError: {e!r}", None
    try:
        data = _json.loads(comp.stdout)
    except Exception:
        data = {}
    if not data.get("ok"):
        errs = data.get("errors") or []
        if isinstance(errs, list):
            errs = "\n".join(errs[-15:])
        tail = (data.get("stdout") or "")[-1200:] + (data.get("stderr") or "")[-1200:]
        log = (str(errs)[:2500] + "\n--- stdout/stderr ---\n" + tail)[-4500:]
        return 1, log, None
    out = data.get("stdout") or ""
    return 0, out[-3000:], None

def main():
    with open(HARNESS, "r", encoding="utf-8") as f:
        harness = f.read()

    messages = [{"role": "system", "content": (
        "Ты — инженер-исполнитель. Пишешь только код: без вступлений, без эмоций, "
        "без пояснений, без дублирования задания. Отвечаешь ровно тем, что просили."
    )}, {"role": "user", "content": TASK}]

    last = ""
    for rnd in range(1, 8):
        print(f"--- раунд {rnd}: запрос к мозгу...", flush=True)
        out = ask(messages, temperature=0.2, max_tokens=6000)
        impl = prepare_impl(extract_code(out))
        if len(impl) < 300:
            print("  ответ слишком короткий, повторяю", flush=True)
            messages = messages[:2] + [
                {"role": "user", "content": (
                    "Твой ответ слишком короткий. Верни ПОЛНУЮ функцию my_sprintf "
                    "кодом: только my_sprintf и её static-вспомогательные функции, "
                    "без main, без тестов, без пояснений."
                )}
            ]
            continue
        last = impl
        with open(IMPL, "w", encoding="utf-8") as f:
            f.write(impl)
        final = split_code_from_harness(harness, impl)
        with open(FULL, "w", encoding="utf-8") as f:
            f.write(final)
        rc, log, exe = compile_run(final)
        print(f"  компиляция/запуск rc={rc}", flush=True)
        print("  " + log.replace("\n", "\n  ")[:1600], flush=True)
        if rc == 0 and log.strip().startswith("OK"):
            print("УСПЕХ: Нейра написала код, тесты прошли.", flush=True)
            return 0
        # контекст минимален: только ТЗ + последняя версия + фидбек
        messages = [
            {"role": "system", "content": messages[0]["content"]},
            {"role": "user", "content": TASK},
            {"role": "assistant", "content": impl[-5000:]},
            {"role": "user", "content": (
                f"Результат проверки твоего кода (компиляция + тесты):\n{log}\n"
                "Исправь ошибки. Верни ТОЛЬКО полную исправленную функцию "
                "my_sprintf и её static-вспомогательные функции. БЕЗ main, БЕЗ "
                "тестов, БЕЗ пояснений."
            )},
        ]
    print("НЕ УСПЕЛИ за 7 раундов.", flush=True)
    return 1

if __name__ == "__main__":
    sys.exit(main())
