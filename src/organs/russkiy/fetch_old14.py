"""Old-format EGE task 14 from rus-ege.sdamgia.ru search: «Определите предложение, в котором оба выделенных слова
пишутся СЛИТНО (РАЗДЕЛЬНО, ЧЕРЕЗ ДЕФИС)…». The explanation («Приведём верное написание») gives every sentence written
correctly, so every highlighted pair gets its label (S together, D hyphen, R apart) - not only the answer row.
Out: data/old14.jsonl {"s": sentence with one marked pair, "lab": "S"|"D"|"R"}. Usage: python fetch_old14.py [pages]
"""
import json
import os
import re
import sys
import urllib.parse

import bank_build as b

HERE = os.path.dirname(os.path.abspath(__file__))
MAXP = int(sys.argv[1]) if len(sys.argv) > 1 else 40
QUERIES = ["оба выделенных слова пишутся СЛИТНО", "оба выделенных слова пишутся РАЗДЕЛЬНО",
           "оба выделенных слова пишутся ЧЕРЕЗ ДЕФИС", "выделенные слова пишутся слитно выпишите"]
PAIR = re.compile(r"\(?([А-ЯЁ]+)\)?\s?\(?([А-ЯЁ]+)\)?")


def parse(page):
    t = b.text(page)
    out = []
    for m in re.finditer(r"Определите предложение, в котором оба выделенных слова пишутся[^\n]*\n(.*?)Пояснение(.*?)"
                         r"(Ответ:|Правило:)", t, re.S):
        cond, expl = m.group(1), m.group(2)
        from razdel import sentenize
        cs = [s.text for s in sentenize(re.sub(r"\s+", " ", cond)) if "(" in s.text and re.search(r"[А-ЯЁ]{2}", s.text)]
        es = [s.text for s in sentenize(re.sub(r"\s+", " ", expl.split("написание", 1)[-1]))]
        for c in cs:
            for pm in re.finditer(r"(?:\(([А-ЯЁ]+)\)\s?([А-ЯЁ]+)|([А-ЯЁ]+)\s?\(([А-ЯЁ]+)\))", c):
                a, bb = (pm.group(1), pm.group(2)) if pm.group(1) else (pm.group(3), pm.group(4))
                pat = re.compile(r"(?<![а-яё])" + a.lower() + r"(-| |)" + bb.lower() + r"(?![а-яё])", re.I)
                hits = {mm.group(1) for e in es for mm in pat.finditer(e)}
                if len(hits) != 1:
                    continue
                sep = hits.pop()
                lab = "D" if sep == "-" else "R" if sep == " " else "S"
                out.append({"s": c, "lab": lab, "pair": a + "|" + bb})
    return out


def main():
    rows, seen = [], set()
    for qi, q in enumerate(QUERIES):
        for p in range(1, MAXP + 1):
            url = "/search?search=" + urllib.parse.quote_plus(q) + f"&page={p}"
            try:
                page = b.get(url, f"search14_{qi}_p{p}.html")
            except Exception as e:
                print("  ошибка", e, flush=True)
                break
            got = [r for r in parse(page) if (r["s"], r["pair"]) not in seen]
            if not got and p > 1:
                break
            for r in got:
                seen.add((r["s"], r["pair"]))
            rows += got
        print(f"запрос {qi}: всего {len(rows)}", flush=True)
    with open(os.path.join(HERE, "data", "old14.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print("пар", len(rows), Counter(r["lab"] for r in rows))


if __name__ == "__main__":
    main()
