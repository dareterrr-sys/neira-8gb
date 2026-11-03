"""Fresh sealed EGE Russian exam from FIPI (31.10): demo versions 2025, 2026 and the 2027 project (fipi.ru, with
answers) + the open variant of the real 2026 exam (no answers on fipi.ru - its key is added separately, see
OPEN_KEY). Demo versions give 2-3 examples for some numbers («ИЛИ»); every example is its own item, exact repeats
across years are dropped. Keys were copied by hand from the answer tables (pages 23-24 of each demo).
Out: fipi_questions.json [{id, task, q, ans, key, src}] (the same format as ege_exam / compare_council grading).
Usage: python fipi_build.py"""
import json
import os
import re

SRC = r"D:\AI\datasets\ege_fresh\txt"
HERE = os.path.dirname(os.path.abspath(__file__))
# per task: a list (one key per example, «Пример 1/2/3»); alternatives inside a key are split by «|»
KEYS = {
    "demo2025": {1: ["эти|такие|те"], 2: ["345"], 3: ["245"], 4: ["145"], 5: ["праздничный"],
                 6: ["очень", "одержать|усилие|усилия"], 7: ["повидлом"], 8: ["43827"], 9: ["25"], 10: ["134"],
                 11: ["123"], 12: ["245"], 13: ["134", "35"], 14: ["14", "135", "35"], 15: ["14", "34"], 16: ["125"],
                 17: ["134"], 18: ["1245"], 19: ["23"], 20: ["1345"], 21: ["13", "235", "259"], 22: ["75924"],
                 23: ["15", "234"], 24: ["134", "25"], 25: ["вконцеконцов|можетбыть|оставиливпокое|насвоёмместе"],
                 26: ["35"]},
    "demo2026": {1: ["сам|весь"], 2: ["45"], 3: ["345"], 4: ["125"], 5: ["гарантированного"],
                 6: ["очень", "одержать|усилие|усилия"], 7: ["запечатлеть"], 8: ["43827"], 9: ["234"], 10: ["234"],
                 11: ["135"], 12: ["134"], 13: ["134", "35"], 14: ["14", "135", "35"], 15: ["14", "34"], 16: ["1235"],
                 17: ["2"], 18: ["12567"], 19: ["12"], 20: ["1345"], 21: ["13", "235", "259"], 22: ["75924"],
                 23: ["125", "34"], 24: ["34", "125"], 25: ["всвоюочередь"], 26: ["21"]},
    "demo2027": {1: ["такие|эти|те"], 2: ["235"], 3: ["1234"], 4: ["1245"], 5: ["безответственное"],
                 6: ["очень", "одержать|усилие|усилия"], 7: ["туфель"], 8: ["73148"], 9: ["45"], 10: ["124"],
                 11: ["34"], 12: ["345"], 13: ["134", "35"], 14: ["14", "135", "35"], 15: ["14", "34"], 16: ["13"],
                 17: ["123"], 18: ["1234"], 19: ["12345"], 20: ["124"], 21: ["13", "235", "259"], 22: ["64138"],
                 23: ["24", "135"], 24: ["245", "13"], 25: ["суесловие"], 26: ["8"]},
}
JUNK = re.compile(r"^(©.*|Демонстрационный вариант.*|Открытый вариант.*|ПРОЕКТ.*|РУССКИЙ ЯЗЫК, 11 класс.*|"
                  r"РУССКИЙ ЯЗЫК\s*\d+\s*/\s*\d+.*|&%end_page&%|\d+\s*/\s*\d+|Ответ: _+\.?|Ответ:)\s*$")


def tasks(raw):
    """-> {number: (passage or '', [example texts])} for 1-26."""
    lines = [l.rstrip() for l in raw.splitlines()]
    body = "\n".join(l for l in lines if not JUNK.match(l.strip()))
    body = body[body.find("Прочитайте текст и выполните задания 1"):]
    # task starts: «N Текст» at a line start, numbers in order (options are «1)», with a bracket)
    starts, n, pos = [], 1, 0
    while n <= 27:
        m = re.compile(rf"^{n} (?=[А-ЯЁA-Z(«])", re.M).search(body, pos)
        if not m:
            break
        starts.append((n, m.start(), m.end()))
        pos, n = m.end(), n + 1
    out = {}
    text1 = body[:starts[0][1]].replace("Прочитайте текст и выполните задания 1–3.", "").strip()
    for i, (k, s, e) in enumerate(starts):
        if k == 27:
            break
        end = starts[i + 1][1] if i + 1 < len(starts) else len(body)
        chunk = body[e:end].strip()
        if k == 21:   # the second text sits between task 21 and task 22
            cut = chunk.find("Прочитайте текст и выполните задания 22")
            if cut >= 0:
                out["text2"] = re.sub(r"^Прочитайте текст и выполните задания 22[^\n]*\n", "", chunk[cut:]).strip()
                chunk = chunk[:cut].strip()
        # the part 2 and the scoring section are not part of task 26
        chunk = re.split(r"\n(?:Часть 2|27 Напишите|Система оценивания)", chunk)[0]
        chunk = re.sub(r"Ответ:\s*_+\.?", "", chunk)
        # «ИЛИ» starts the next example: alone on its line or before the next wording
        examples = [x.strip() for x in re.split(r"\n\s*ИЛИ(?:\s*\n|\s+)", "\n" + chunk) if x.strip()]
        out[k] = examples
    out["text1"] = text1
    return out


def tail(key):
    return (" Ответ дай одной строкой: цифры." if all(re.fullmatch(r"\d+", a) for a in key.split("|"))
            else " Ответ дай одним словом (или словами), как требует задание.")


def main():
    items, seen = [], set()
    for name, keys in KEYS.items():
        t = tasks(open(os.path.join(SRC, name + "_raw.txt"), encoding="utf-8").read())
        for k in range(1, 27):
            exs = t.get(k, [])
            if len(exs) != len(keys[k]):
                print(f"!! {name} {k}: примеров {len(exs)}, ключей {len(keys[k])}")
            for j, (ex, key) in enumerate(zip(exs, keys[k]), 1):
                passage = t["text1"] if k <= 3 else (t.get("text2", "") if k >= 22 else "")
                q = (f"Прочитайте текст.\n{passage}\n\n" if passage else "") + f"Задание {k}. {ex}"
                sig = re.sub(r"\W", "", ex.lower())[:300]
                if sig in seen:
                    continue
                seen.add(sig)
                items.append({"id": f"{name}_{k:02d}" + (f"_{j}" if len(keys[k]) > 1 else ""), "task": k,
                              "q": q + tail(key), "ans": key, "key": key, "src": name})
    json.dump(items, open(os.path.join(HERE, "fipi_questions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(items), "заданий;", dict(sorted(Counter(i["task"] for i in items).items())))
    print(Counter(i["src"] for i in items))


if __name__ == "__main__":
    main()
