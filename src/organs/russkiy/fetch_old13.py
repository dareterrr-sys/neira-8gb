"""Old-format EGE task 13 (before 2024: «Определите предложение, в котором НЕ со словом пишется СЛИТНО/РАЗДЕЛЬНО.
Раскройте скобки и выпишите это слово») from rus-ege.sdamgia.ru search - the author's idea, 27.10: «возьми
прошлогодние варианты». Exactly one of the five sentences is written the asked way, the answer names it, so all five
are labelled. Items are stored in the new form «(НЕ)WORD» like today's task. Polite cached fetch (bank_build.get).
Out: data/old13.jsonl {"s", "together"}. Usage: python fetch_old13.py [max_pages=40]
"""
import json
import os
import re
import sys
import urllib.parse

import bank_build as b

HERE = os.path.dirname(os.path.abspath(__file__))
MAXP = int(sys.argv[1]) if len(sys.argv) > 1 else 40
QUERIES = {"S": "пишется СЛИТНО Раскройте скобки", "R": "пишется РАЗДЕЛЬНО Раскройте скобки",
           "S2": "НЕ со словом пишется СЛИТНО", "R2": "НЕ со словом пишется РАЗДЕЛЬНО",
           "S3": "НЕ пишется слитно выпишите слово", "S4": "(НЕ) слитно"}


def parse(page):
    t = b.text(page)
    out = []
    for m in re.finditer(r"Определите предложение, в котором НЕ со словом пишется (СЛИТНО|РАЗДЕЛЬНО)\.[^\n]*\n(.*?)"
                         r"Ответ:\s*([^\n]+)", t, re.S):
        want, body, ans = m.group(1), m.group(2), m.group(3)
        body = body.split("Пояснение")[0]
        from razdel import sentenize   # sentences come one per line or all in one line
        lines = [s.text.strip() for s in sentenize(re.sub(r"\s+", " ", body)) if re.search(r"\((не|НЕ|Не)\)", s.text)]
        ans = ans.lower().replace("ё", "е")
        answers = set(re.findall(r"[а-я-]+", ans))
        if len(lines) < 4:
            continue
        for l in lines:
            mm = re.search(r"\((не|НЕ|Не)\)\s?([а-яёА-ЯЁ-]+)", l)
            if not mm:
                continue
            w = mm.group(2).lower()
            merged, sep = ("не" + w).replace("ё", "е"), ("не " + w).replace("ё", "е")
            hit = merged in answers or sep in ans
            together = hit if want == "СЛИТНО" else not hit
            s = l[:mm.start()] + "(НЕ)" + mm.group(2).upper() + l[mm.end():]
            out.append({"s": s, "together": int(together)})
    return out


def main():
    rows, seen = [], set()
    for key, q in QUERIES.items():
        for p in range(1, MAXP + 1):
            url = "/search?search=" + urllib.parse.quote_plus(q) + f"&page={p}"
            try:
                page = b.get(url, f"search13_{key}_p{p}.html")
            except Exception as e:
                print("  ошибка", e, flush=True)
                break
            got = [r for r in parse(page) if r["s"] not in seen]
            if not got:
                break
            for r in got:
                seen.add(r["s"])
            rows += got
        print(f"{key}: всего пунктов {len(rows)}", flush=True)
    with open(os.path.join(HERE, "data", "old13.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("пунктов", len(rows), "слитно", sum(r["together"] for r in rows))


if __name__ == "__main__":
    main()
