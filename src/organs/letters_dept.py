"""Neira's letters department: counting letters, vowels, syllables, the n-th letter, reversals, the next letter of the
alphabet. The model sees tokens (pieces of words), not letters: on work3 it said 3 «о» in «обороноспособность»
(right: 7) and 9 vowels in «электрификация» (right: 7), and once even claimed a calculator had counted them.

As with the calculator and the calendar, the model only translates the question into one call of a tiny language;
two independent routes write the call, the C++ program bukvy.exe (D:\\AI\\neira-tools\\bukvy) runs it, and a note goes on
only if both calls give the same result. A riddle gets НЕТ.
"""
import os
import re
import subprocess

BUKVY = os.environ.get("NEIRA_BUKVY", r"D:\AI\neira-tools\bukvy\bukvy.exe")

LETTERS = (
    "Ты помощник по буквам. Если в вопросе нужно посчитать буквы, гласные, согласные или слоги в слове, найти букву "
    "на какой-то позиции, прочитать слово задом наперёд, заменить букву или найти соседнюю букву алфавита, переведи "
    "вопрос в ОДИН вызов из списка; иначе ответь НЕТ.\n"
    "ДЛИНА(слово) — сколько букв; СКОЛЬКО(слово, буква) — сколько раз встречается буква; ГЛАСНЫЕ(слово); "
    "СОГЛАСНЫЕ(слово); СЛОГИ(слово); БУКВА(слово, n) — n-я буква, n < 0 — считая с конца (-1 — последняя); "
    "НАОБОРОТ(слово); ПАЛИНДРОМ(слово); ЗАМЕНИТЬ(слово, n, буква) — заменить n-ю букву; НОМЕР(буква) — номер в "
    "алфавите; СЛЕДУЮЩАЯ(буква); ПРЕДЫДУЩАЯ(буква).\n"
    "Примеры: «Сколько букв "
    "«р» в слове «барабанщик»?» → СКОЛЬКО(барабанщик, р). «Какая вторая буква с конца в слове «окно»?» → БУКВА(окно, -2). "
    "«Какая буква идёт после «ж»?» → СЛЕДУЮЩАЯ(ж).")
LETTERS_2 = (
    "Ты внимательный помощник по буквам и словам. Сначала одной строкой напиши, какое слово и что про его буквы "
    "спрашивают. Затем на последней строке запиши ОДИН вызов или слово НЕТ, если это загадка или про буквы не "
    "спрашивают: ДЛИНА(слово); СКОЛЬКО(слово, буква); ГЛАСНЫЕ(слово); СОГЛАСНЫЕ(слово); СЛОГИ(слово); "
    "БУКВА(слово, номер или минус номер с конца); НАОБОРОТ(слово); ПАЛИНДРОМ(слово); ЗАМЕНИТЬ(слово, номер, буква); "
    "НОМЕР(буква); СЛЕДУЮЩАЯ(буква); ПРЕДЫДУЩАЯ(буква).")
LETTERS_ROUTES = ((LETTERS, 40), (LETTERS_2, 160))

_ASK = re.compile(r"букв|гласн|согласн|слог|задом наперёд|задом наперед|наоборот|палиндром|алфавит", re.I)
_CALL = re.compile(r"(ДЛИНА|СКОЛЬКО|ГЛАСНЫЕ|СОГЛАСНЫЕ|СЛОГИ|БУКВА|НАОБОРОТ|ПАЛИНДРОМ|ЗАМЕНИТЬ|НОМЕР|СЛЕДУЮЩАЯ"
                   r"|ПРЕДЫДУЩАЯ)\s*\(([^()]*)\)")


def asks_letters(text):
    return bool(_ASK.search(text or ""))


def run_calls(calls):
    """['СКОЛЬКО(молоко, о)', ...] -> ['3', ...] (None where the program reports an error), one bukvy.exe run."""
    out = subprocess.run([BUKVY], input=("\n".join(calls) + "\n").encode("utf-8"), capture_output=True, timeout=10)
    lines = out.stdout.decode("utf-8", errors="replace").splitlines()
    results = []
    for line in lines:
        answer = line.rsplit(" = ", 1)[-1].strip()
        results.append(None if answer.startswith("ошибка") else answer)
    return results


def letters_note(*replies):
    """Calls from independent routes -> a checked note if they all run and agree, else ""."""
    calls = []
    for r in replies:
        found = _CALL.findall(r or "")
        if not found:   # НЕТ, or no call at all
            return ""
        calls.append(f"{found[-1][0]}({found[-1][1]})")
    try:
        results = run_calls(calls)
    except (OSError, subprocess.SubprocessError):
        return ""
    if len(results) != len(calls) or None in results or len(set(results)) != 1:
        return ""
    return (f"Справка буквенного счётчика ({len(calls)} способа сошлись, посчитано кодом по буквам): {calls[0]} = "
            f"{results[0]}. Подсчёт проверен, не пересчитывай буквы в уме; но проверь, правильно ли выбрано слово и вопрос.")
