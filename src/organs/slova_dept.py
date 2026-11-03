"""Neira's words department (pair to the letters department): counting words and sentences, finding a substring and
how many times it occurs, the n-th word, the longest / shortest word, words in alphabetical or reverse order, the most
frequent word, anagrams. The model sees tokens, not words and letters, so these are guesses in its head and exact in
code (the author's request, 24.10: "что-нибудь, что разгрузило бы мозг, с чем код справляется быстрее и надёжнее").

As with the letters department: the model only writes one call of a tiny language, two independent routes write it,
the C++ program slova.exe (D:\\AI\\neira-tools\\slova) runs both, and a note goes on only if they agree.
Not wired into the council or live Neira yet: that needs a measurement first (one change - one measurement).
"""
import os
import re
import subprocess

SLOVA = os.environ.get("NEIRA_SLOVA", r"D:\AI\neira-tools\slova\slova.exe")

_LIST = ('СЛОВА("текст") — сколько слов; ПРЕДЛОЖЕНИЯ("текст"); СИМВОЛЫ("текст") — символов с пробелами; '
         'БУКВЫ("текст") — букв во всём тексте; ВХОЖДЕНИЯ("текст", "подстрока") — сколько раз встречается; '
         'ПОЗИЦИЯ("текст", "подстрока") — с какого символа начинается; СЛОВО("текст", n) — n-е слово, n < 0 — с конца; '
         'ДЛИННОЕ("текст"); КОРОТКОЕ("текст"); АЛФАВИТ("текст") — слова по алфавиту; ЧАСТОЕ("текст") — самое '
         'частое слово; НАЧИНАЮТСЯ("текст", "буквы"); ОКАНЧИВАЮТСЯ("текст", "буквы") — сколько слов; '
         'ПОРЯДОК("текст") — слова задом наперёд; АНАГРАММА("слово1", "слово2"); ОДИНАКОВЫ("текст1", "текст2")')
SLOVA_1 = ("Ты помощник по словам и текстам. Если в вопросе нужно посчитать слова или предложения, найти подстроку, "
           "выписать слово по номеру, расставить слова по алфавиту или проверить анаграмму, переведи вопрос в ОДИН вызов "
           "из списка, текст бери в кавычки дословно; иначе ответь НЕТ.\n" + _LIST)
SLOVA_2 = ("Ты внимательный помощник по текстам. Сначала одной строкой напиши, какой текст и что про него спрашивают. "
           "Затем на последней строке запиши ОДИН вызов (текст дословно в кавычках) или слово НЕТ, если это загадка "
           "или про слова текста не спрашивают:\n" + _LIST)
SLOVA_ROUTES = ((SLOVA_1, 200), (SLOVA_2, 300))

_ASK = re.compile(r"сколько (раз|слов|предложени|символ)|слов[оа]? (по счёту|номер)|по алфавиту|в алфавитном|"
                  r"анаграмм|подстрок|встречается|самое (длинное|короткое|частое)|обратном порядке|"
                  r"начинаются (с|на)|оканчиваются на|(первое|второе|третье|последнее|предпоследнее) слово", re.I)
_CALL = re.compile(r"(СЛОВА|ПРЕДЛОЖЕНИЯ|СИМВОЛЫ|БУКВЫ|ВХОЖДЕНИЯ|ПОЗИЦИЯ|СЛОВО|ДЛИННОЕ|КОРОТКОЕ|АЛФАВИТ|ЧАСТОЕ"
                   r"|НАЧИНАЮТСЯ|ОКАНЧИВАЮТСЯ|ПОРЯДОК|АНАГРАММА|ОДИНАКОВЫ)\s*\((.*)\)")


_QUOTED = re.compile(r"«[^»]{2,}»|\"[^\"]{2,}\"")
_ABOUT = re.compile(r"слов|букв|символ|анаграм|по счёту|по счету|с конца|по алфавиту|встречается|оканчива|начина|"
                    r"предложени|подстрок|составить", re.I)


def asks_words(text):
    """A quoted text and a question about its words, letters or symbols (or one of the explicit phrasings)."""
    text = text or ""
    return bool(_ASK.search(text)) or bool(_QUOTED.search(text) and _ABOUT.search(text))


def run_calls(calls):
    """['СЛОВА("мама мыла раму")', ...] -> ['3', ...] (None where the program reports an error), one slova.exe run."""
    out = subprocess.run([SLOVA], input=("\n".join(calls) + "\n").encode("utf-8"), capture_output=True, timeout=10)
    results = []
    for line in out.stdout.decode("utf-8", errors="replace").splitlines():
        answer = line.rsplit(" = ", 1)[-1].strip()
        results.append(None if answer.startswith("ошибка") else answer)
    return results


def words_note(*replies):
    """Calls from independent routes -> a checked note if they all run and agree, else ""."""
    calls = []
    for r in replies:
        lines = [m for m in (_CALL.search(line) for line in (r or "").splitlines()) if m]
        if not lines:   # НЕТ, or no call at all
            return ""
        calls.append(f"{lines[-1].group(1)}({lines[-1].group(2)})")
    try:
        results = run_calls(calls)
    except (OSError, subprocess.SubprocessError):
        return ""
    if len(results) != len(calls) or None in results or len(set(results)) != 1:
        return ""
    return (f"Справка текстового счётчика ({len(calls)} способа сошлись, посчитано кодом): {calls[0]} = {results[0]}. "
            f"Подсчёт проверен, не пересчитывай в уме; но проверь, тот ли текст и тот ли вопрос.")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(run_calls(['СЛОВА("Мама мыла раму")', 'АНАГРАММА("апельсин", "спаниель")', 'СЛОВО("один два", 5)']))
    print(words_note('СЛОВА("Мама мыла раму")', 'Спрашивают число слов.\nСЛОВА("Мама мыла раму")'))
    print(asks_words("Сколько слов в предложении «Мама мыла раму»?"), asks_words("Сколько будет 2+2?"))
