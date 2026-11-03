"""Texts edited to modern norms for the punctuation net: the reading texts of EGE tasks 1-3 and 22-26 on
rus-ege.sdamgia.ru (FIPI texts: punctuation by the current rules, unlike the classics' authorial punctuation).
Sentences come numbered «(1)…(N)»; the numbers are dropped. Uses bank_build.py's polite cached fetch (3 s).
Out: data/norm_texts.jsonl {"text_id", "s"}. Usage: python fetch_texts.py [max_texts=400] [max_pages=320]
"""
import hashlib
import json
import os
import re
import sys

import bank_build as b

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_TEXTS = int(sys.argv[1]) if len(sys.argv) > 1 else 400
MAX_PAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 320


def texts(page):
    for m in re.finditer(r'<div[^>]*class="probtext"[^>]*>(.*?)</div>', page, re.S):
        t = b.text(m.group(1))
        if len(t) > 500 and "(1)" in t:
            yield t


def main():
    cats = b.categories()
    seen, rows, pages = set(), [], 0
    order = [c for t in (23, 24, 25, 26, 1, 2, 3) for c in cats.get(t, [])]   # task 22 pages carry no probtext
    for cid in order:
        p, loaded = 1, 0
        while pages < MAX_PAGES and len(seen) < MAX_TEXTS:
            page = None
            for attempt in range(3):          # the site sometimes answers 502
                try:
                    page = b.get(f"/test?filter=all&category_id={cid}", f"cat{cid}_p{p}.html",
                                 None if p == 1 else {"ajax": 1, "skip": loaded})
                    break
                except Exception as e:
                    print("  повтор:", e, flush=True)
                    import time
                    time.sleep(10)
            if page is None:
                break
            pages += 1
            got = b.problems(page)
            loaded += len(got)
            for t in texts(page):
                key = hashlib.md5(re.sub(r"\W", "", t[:300]).encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                for s in re.split(r"\(\d+\)", t):
                    s = re.sub(r"\s+", " ", s).strip()
                    if 4 <= len(s.split()) <= 60 and re.match(r"^[«—–\-\"]?\s*[А-ЯЁ]", s):
                        rows.append({"text_id": key[:8], "s": s})
            if not got:
                break
            p += 1
        print(f"категория {cid}: текстов {len(seen)}, предложений {len(rows)}, страниц {pages}", flush=True)
        if pages >= MAX_PAGES or len(seen) >= MAX_TEXTS:
            break
    with open(os.path.join(HERE, "data", "norm_texts.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("всего: текстов", len(seen), "предложений", len(rows))


if __name__ == "__main__":
    main()
