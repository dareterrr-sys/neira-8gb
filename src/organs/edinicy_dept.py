"""Neira's units department: any quantity to SI and between units (km/h -> m/s, feet -> cm, °F -> °C, gallons,
pounds, horsepower...). Converting units is translating the problem into numbers, where the model slips like in
counting; the C program edinicy.exe (D:\\AI\\neira-tools\\edinicy) is exact (the author's request, 25.10).
As with the letters and words departments: two independent routes write one call, a note goes on only if both run
and agree.
"""
import os
import re
import subprocess

EDINICY = os.environ.get("NEIRA_EDINICY", r"D:\AI\neira-tools\edinicy\edinicy.exe")

_LIST = ("СИ(число единица) — перевести в систему СИ, например СИ(72 км/ч); ПЕРЕВЕСТИ(число единица, единица) — "
         "из одной единицы в другую, например ПЕРЕВЕСТИ(100 °F, °C), ПЕРЕВЕСТИ(6 футов, см). Единицы: мм см м км дюйм "
         "фут ярд миля, г кг т фунт унция пуд, с мин ч сутки неделя год, мл л галлон, га сотка акр, Н Дж кал ккал Вт "
         "л.с. Па атм бар мм рт. ст., °C °F К, узел; составные через / и *: км/ч, м/с2, кВт*ч")
EDINICY_1 = ("Ты помощник по единицам измерения. Если в вопросе нужно перевести величину из одних единиц в другие, "
             "переведи вопрос в ОДИН вызов; иначе ответь НЕТ.\n" + _LIST)
EDINICY_2 = ("Ты внимательный помощник по единицам. Сначала одной строкой напиши, какую величину и во что просят "
             "перевести. Затем на последней строке запиши ОДИН вызов или слово НЕТ, если перевода единиц нет:\n" + _LIST)
EDINICY_ROUTES = ((EDINICY_1, 60), (EDINICY_2, 160))

_ASK = re.compile(r"(перевед|переведи|перевести|выразите|выразить|сколько .{0,40}?\b(в|во)\b .{0,20}?(метр|километр|"
                  r"сантиметр|миллиметр|литр|грамм|килограмм|тонн|секунд|минут|час|сутк|фунт|фут|дюйм|миль|галлон|"
                  r"градус|джоул|ватт|паскал|атмосфер|м/с|км/ч)|в градус|по фаренгейт|по цельси|в систем\w* си)", re.I)
_CALL = re.compile(r"(СИ|ПЕРЕВЕСТИ)\s*\((.*)\)")


_UNIT = re.compile(r"(километр|сантиметр|миллиметр|метр|дюйм|фут|ярд|мил[ьяи]|верст|литр|галлон|килограмм|грамм|"
                   r"тонн|фунт|унци|пуд|секунд|минут|час|сут|кельвин|цельси|фаренгейт|гектар|сот(?:ка|ки|ок)|"
                   r"килоджоул|джоул|килокалори|калори|киловатт|ватт|лошадин|килопаскал|паскал|атмосфер|мм рт|узл|"
                   r"ньютон|кгс|км/ч|м/с|°[CСF])", re.I)


def asks_units(text):
    """A short question naming two different units (a long word problem is left to the calculator), or one of the
    explicit phrasings («переведи…», «в градусах Фаренгейта»)."""
    text = text or ""
    if _ASK.search(text):
        return True
    stems = {m.group(1).lower()[:5] for m in _UNIT.finditer(text)}
    return len(text) < 160 and len(stems) >= 2


def run_calls(calls):
    out = subprocess.run([EDINICY], input=("\n".join(calls) + "\n").encode("utf-8"), capture_output=True, timeout=10)
    results = []
    for line in out.stdout.decode("utf-8", errors="replace").splitlines():
        answer = line.rsplit(" = ", 1)[-1].strip()
        results.append(None if answer.startswith("ошибка") else answer)
    return results


def units_note(*replies):
    calls = []
    for r in replies:
        found = [m for m in (_CALL.search(line) for line in (r or "").splitlines()) if m]
        if not found:
            return ""
        calls.append(f"{found[-1].group(1)}({found[-1].group(2)})")
    try:
        results = run_calls(calls)
    except (OSError, subprocess.SubprocessError):
        return ""
    if len(results) != len(calls) or None in results:
        return ""
    values = {r.split(" ")[0] for r in results}
    if len(values) != 1:
        return ""
    return (f"Справка переводчика единиц ({len(calls)} способа сошлись, посчитано кодом): {calls[0]} = {results[0]}. "
            f"Перевод проверен, не пересчитывай в уме; но проверь, ту ли величину и в те ли единицы переводят.")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(run_calls(["СИ(72 км/ч)", "ПЕРЕВЕСТИ(100 °F, °C)"]))
    print(units_note("ПЕРЕВЕСТИ(6 футов, см)", "Переводят рост.\nПЕРЕВЕСТИ(6 футов, см)"))
    print(asks_units("Сколько будет 72 км/ч в м/с?"), asks_units("Переведи 100 градусов по Фаренгейту в Цельсий"))
