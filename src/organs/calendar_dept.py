"""Neira's calendar department (plan step 3, perception): days of the week, dates, clock time, time zones, centuries
and leap years are computed by code, not guessed by the model. 4 of the 6 confident errors of council v2.1-v2.2 were
of this kind ("через 100 дней" -> Monday, 2100 -> leap, Novosibirsk +5 hours).

As with the calculator, the model only translates the question into one call of a tiny language; two independent
routes write the call, and a note goes on only if both calls give the same result. A riddle gets НЕТ.
"""
import datetime
import re
import zoneinfo

CALENDAR = (
    "Ты помощник-календарь. Если в вопросе нужно посчитать что-то с датами, днями недели, временем на часах, "
    "часовыми поясами, веками или високосными годами, переведи вопрос в ОДИН вызов из списка; иначе ответь НЕТ.\n"
    "ДЕНЬ(день недели, N) — какой день недели будет через N дней (раньше — минус N);\n"
    "ДАТА(ДД.ММ.ГГГГ, N) — какая дата будет через N дней;\n"
    "ДЕНЬ_ДАТЫ(ДД.ММ.ГГГГ) — на какой день недели приходится дата;\n"
    "ДНЕЙ_МЕЖДУ(ДД.ММ.ГГГГ, ДД.ММ.ГГГГ) — сколько дней между датами;\n"
    "ВРЕМЯ(ЧЧ:ММ, +ЧЧ:ММ) — что покажут часы, если прибавить (или с минусом отнять) промежуток;\n"
    "ПОЯС(ЧЧ:ММ, город, город) — сколько времени во втором городе, когда в первом указанное время;\n"
    "ВИСОКОСНЫЙ(год);\n"
    "ВЕК(год) — к какому веку относится год.\n"
    "Полдень — 12:00, полночь — 00:00. Если вопрос — загадка с подвохом или такой расчёт не нужен, ответь НЕТ.\n"
    "Примеры: «Сегодня вторник, какой день будет через 20 дней?» → ДЕНЬ(вторник, 20). «Поезд ушёл в 23:10 и ехал "
    "3 часа 5 минут, когда он прибыл?» → ВРЕМЯ(23:10, +03:05). «Когда в Лондоне полдень, сколько в Токио?» → "
    "ПОЯС(12:00, Лондон, Токио).")
CALENDAR_2 = (
    "Ты внимательный помощник по календарю. Сначала одной строкой напиши, что дано и что спрашивают. Затем на "
    "последней строке запиши ОДИН вызов из списка или слово НЕТ, если это загадка или расчёт с датами не нужен: "
    "ДЕНЬ(день недели, сдвиг в днях); ДАТА(ДД.ММ.ГГГГ, сдвиг в днях); ДЕНЬ_ДАТЫ(ДД.ММ.ГГГГ); "
    "ДНЕЙ_МЕЖДУ(ДД.ММ.ГГГГ, ДД.ММ.ГГГГ); ВРЕМЯ(ЧЧ:ММ, +ЧЧ:ММ или -ЧЧ:ММ); ПОЯС(ЧЧ:ММ, город откуда, город куда); "
    "ВИСОКОСНЫЙ(год); ВЕК(год). Полдень — 12:00, полночь — 00:00.")
CALENDAR_ROUTES = ((CALENDAR, 40), (CALENDAR_2, 160))

_ASK = re.compile(
    r"понедельник|вторник|\bсред[аыуе]\b|четверг|пятниц|суббот|воскресень|день недели|дн\w+ недели|високос|\bвек"
    r"|\bгод[ау]?\b|через \d+ (?:дн|ден|недел|час|мин|сут|месяц|лет|год)|во сколько|котор\w+ (?:сейчас )?час"
    r"|\d{1,2}:\d{2}|пояс|сколько времени|полд|полноч|январ|феврал|\bмарт|апрел|\bма[йя]\b|июн|июл|август"
    r"|сентябр|октябр|ноябр|декабр|\d{1,2}\.\d{1,2}\.\d{2,4}", re.I)


def asks_calendar(text):
    return bool(_ASK.search(text or ""))


_DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_DAY_STEMS = ["понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресен"]
_CITIES = {
    "москва": "Europe/Moscow", "санкт-петербург": "Europe/Moscow", "петербург": "Europe/Moscow",
    "казань": "Europe/Moscow", "нижний новгород": "Europe/Moscow", "сочи": "Europe/Moscow",
    "калининград": "Europe/Kaliningrad", "самара": "Europe/Samara", "волгоград": "Europe/Volgograd",
    "саратов": "Europe/Saratov", "ульяновск": "Europe/Ulyanovsk", "астрахань": "Europe/Astrakhan",
    "екатеринбург": "Asia/Yekaterinburg", "челябинск": "Asia/Yekaterinburg", "пермь": "Asia/Yekaterinburg",
    "уфа": "Asia/Yekaterinburg", "тюмень": "Asia/Yekaterinburg", "омск": "Asia/Omsk",
    "новосибирск": "Asia/Novosibirsk", "томск": "Asia/Tomsk", "барнаул": "Asia/Barnaul",
    "кемерово": "Asia/Novokuznetsk", "новокузнецк": "Asia/Novokuznetsk", "красноярск": "Asia/Krasnoyarsk",
    "иркутск": "Asia/Irkutsk", "улан-удэ": "Asia/Irkutsk", "чита": "Asia/Chita", "якутск": "Asia/Yakutsk",
    "владивосток": "Asia/Vladivostok", "хабаровск": "Asia/Vladivostok", "магадан": "Asia/Magadan",
    "южно-сахалинск": "Asia/Sakhalin", "петропавловск-камчатский": "Asia/Kamchatka",
    "минск": "Europe/Minsk", "киев": "Europe/Kyiv", "алматы": "Asia/Almaty", "астана": "Asia/Almaty",
    "ташкент": "Asia/Tashkent", "тбилиси": "Asia/Tbilisi", "ереван": "Asia/Yerevan", "баку": "Asia/Baku",
    "лондон": "Europe/London", "париж": "Europe/Paris", "берлин": "Europe/Berlin", "рим": "Europe/Rome",
    "мадрид": "Europe/Madrid", "стамбул": "Europe/Istanbul", "нью-йорк": "America/New_York",
    "вашингтон": "America/New_York", "чикаго": "America/Chicago", "лос-анджелес": "America/Los_Angeles",
    "токио": "Asia/Tokyo", "пекин": "Asia/Shanghai", "шанхай": "Asia/Shanghai", "сеул": "Asia/Seoul",
    "дели": "Asia/Kolkata", "дубай": "Asia/Dubai", "сидней": "Australia/Sydney", "бангкок": "Asia/Bangkok",
    "гонконг": "Asia/Hong_Kong", "сингапур": "Asia/Singapore", "каир": "Africa/Cairo"}
_CALL = re.compile(r"(ДЕНЬ_ДАТЫ|ДНЕЙ_МЕЖДУ|ДЕНЬ|ДАТА|ВРЕМЯ|ПОЯС|ВИСОКОСНЫЙ|ВЕК)\s*\(([^()]*)\)")
_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
          (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def _roman(n):
    out = ""
    for v, s in _ROMAN:
        while n >= v:
            out, n = out + s, n - v
    return out


def _day(word):
    w = word.strip().lower().replace("ё", "е")
    return next((i for i, s in enumerate(_DAY_STEMS) if w.startswith(s)), None)


def _date(s):
    d, m, y = (int(x) for x in re.findall(r"\d+", s)[:3])
    return datetime.date(y, m, d)


def _hm(s, signed=False):
    m = re.fullmatch(r"\s*([+-]?)(\d{1,3}):(\d{2})\s*", s)
    if not m:
        raise ValueError(f"время {s!r}")
    minutes = int(m.group(2)) * 60 + int(m.group(3))
    return -minutes if m.group(1) == "-" else minutes


def _city(name):
    n = name.strip().lower().replace("ё", "е").removeprefix("в ").strip()
    if n in _CITIES:
        return _CITIES[n]
    for city, tz in _CITIES.items():   # "москве", "новосибирске"
        if len(city) > 3 and n.startswith(city[:-1]) and len(n) - len(city) <= 2:
            return tz
    raise ValueError(f"город {name!r}")


def _fmt_hm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def run_call(call):
    """'ДЕНЬ(понедельник, 100)' -> (key to compare, Russian sentence). Raises ValueError on a call it cannot run."""
    m = _CALL.search(call or "")
    if not m:
        raise ValueError("нет вызова")
    name, args = m.group(1), [a.strip() for a in m.group(2).split(",")]
    if name == "ДЕНЬ":
        start, n = _day(args[0]), int(args[1].replace(" ", ""))
        if start is None:
            raise ValueError(f"день {args[0]!r}")
        res = _DAYS[(start + n) % 7]
        rest = abs(n) % 7
        return res, (f"{'через' if n >= 0 else 'за'} {abs(n)} дн. от дня «{_DAYS[start]}» — {res} "
                     f"({abs(n) // 7} полных недель и {rest} дн.)")
    if name == "ДАТА":
        d = _date(args[0]) + datetime.timedelta(days=int(args[1].replace(" ", "")))
        return d.isoformat(), f"{args[0]} {'+' if int(args[1]) >= 0 else ''}{args[1]} дн. = {d:%d.%m.%Y}, {_DAYS[d.weekday()]}"
    if name == "ДЕНЬ_ДАТЫ":
        d = _date(args[0])
        return _DAYS[d.weekday()], f"{d:%d.%m.%Y} — {_DAYS[d.weekday()]}"
    if name == "ДНЕЙ_МЕЖДУ":
        n = abs((_date(args[1]) - _date(args[0])).days)
        return str(n), f"между {args[0]} и {args[1]} — {n} дн."
    if name == "ВРЕМЯ":
        total = _hm(args[0]) + _hm(args[1], signed=True)
        days, mins = divmod(total, 24 * 60)
        tail = "" if days == 0 else ", следующие сутки" if days == 1 else ", предыдущие сутки" if days == -1 else f", сдвиг на {days} сут."
        return f"{_fmt_hm(mins)}{tail}", f"{args[0]} {args[1]} = {_fmt_hm(mins)}{tail}"
    if name == "ПОЯС":
        h = _hm(args[0])
        today = datetime.date.today()
        src = datetime.datetime(today.year, today.month, today.day, h // 60, h % 60, tzinfo=zoneinfo.ZoneInfo(_city(args[1])))
        dst = src.astimezone(zoneinfo.ZoneInfo(_city(args[2])))
        diff = (dst.utcoffset() - src.utcoffset()).total_seconds() / 3600
        day = "" if dst.date() == src.date() else (", следующий день" if dst.date() > src.date() else ", предыдущий день")
        return f"{dst:%H:%M}{day}", (f"когда в городе {args[1]} {args[0]}, в городе {args[2]} {dst:%H:%M}{day} "
                                     f"(разница {diff:+g} ч, на сегодняшнюю дату)")
    if name == "ВИСОКОСНЫЙ":
        y = int(re.findall(r"\d+", args[0])[0])
        leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
        why = ("делится на 400" if y % 400 == 0 else "делится на 100, но не на 400" if y % 100 == 0
               else "делится на 4" if y % 4 == 0 else "не делится на 4")
        return str(leap), f"{y} год {'високосный' if leap else 'не високосный'} ({why})"
    if name == "ВЕК":
        y = int(re.findall(r"\d+", args[0])[0])
        c = (y - 1) // 100 + 1
        return str(c), f"{y} год относится к {c}-му веку ({_roman(c)}); век начинается с года, оканчивающегося на 01"
    raise ValueError(name)


def calendar_note(*replies):
    """Calls from independent routes -> a checked note if they all run and agree, else "" (no note: the clock
    note on riddles taught us that a wrong note hurts more than none)."""
    results = []
    for r in replies:
        if not r or (r.strip().upper().startswith("НЕТ") and not _CALL.search(r)):
            return ""
        calls = _CALL.findall(r)
        if not calls:
            return ""
        last = f"{calls[-1][0]}({calls[-1][1]})"
        try:
            results.append(run_call(last))
        except (ValueError, IndexError, OverflowError, zoneinfo.ZoneInfoNotFoundError):
            return ""
    if not results or len({k for k, _ in results}) != 1:
        return ""
    return (f"Справка календаря ({len(results)} способа сошлись, посчитано кодом): {results[0][1]}. "
            "Расчёт проверен, не пересчитывай его в уме; но проверь, правильно ли он понимает условие.")
