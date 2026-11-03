"""Classic Russian prose for the punctuation net (the author's idea, 27.10: «обучи на книгах классических русских
писателей»): public-domain texts from az.lib.ru (Мошков), modern orthography only (texts with ѣ/і are skipped).
Sentences of 5-45 words, cut by razdel. One request every 2 s; pages cached in data/classics_cache.
Out: data/classics.jsonl {"author", "s"}. Usage: python fetch_classics.py [sentences_per_author=4000]
"""
import html
import json
import os
import random
import re
import sys
import time
import urllib.request

from razdel import sentenize

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "classics_cache")
PER = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
AUTHORS = {"Достоевский": "d/dostoewskij_f_m"} if os.environ.get("ONLY") == "dost" else {"Чехов": "c/chehow_a_p", "Тургенев": "t/turgenew_i_s", "Толстой": "t/tolstoj_lew_nikolaewich",
           "Пушкин": "p/pushkin_a_s", "Гоголь": "g/gogolx_n_w", "Куприн": "k/kuprin_a_i"}
os.makedirs(CACHE, exist_ok=True)
random.seed(0)


def get(url):
    f = os.path.join(CACHE, re.sub(r"[^a-z0-9_.]", "_", url.split("az.lib.ru/")[-1]))
    if os.path.exists(f):
        return open(f, encoding="utf-8").read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; one request per 2 s)"})
    t = urllib.request.urlopen(req, timeout=60).read().decode("cp1251", errors="replace")
    open(f, "w", encoding="utf-8").write(t)
    time.sleep(2)
    return t


def sentences(page):
    body = page.split("<dd>", 1)[-1]
    body = re.sub(r"<[^>]+>", "\n", body)
    body = html.unescape(body).replace("\xa0", " ")
    out = []
    for para in body.split("\n"):
        para = para.strip()
        if len(para) < 40 or re.search(r"[a-zA-Z]{3}|\d{3}|\[|\]|©|http", para):
            continue
        for s in sentenize(para):
            t = s.text.strip()
            n = len(t.split())
            if 5 <= n <= 45 and re.match(r"^[«—–\-\"]?\s*[А-ЯЁ]", t) and t[-1] in ".!?…»":
                out.append(t)
    return out


def main():
    rows = []
    for name, path in AUTHORS.items():
        index = get(f"http://az.lib.ru/{path}/")
        links = sorted(set(re.findall(r"text_[0-9a-z_]+\.shtml", index)))
        random.shuffle(links)
        got = []
        for ln in links:
            if len(got) >= PER:
                break
            try:
                page = get(f"http://az.lib.ru/{path}/{ln}")
            except Exception as e:
                print("  пропуск", ln, e, flush=True)
                continue
            if "ѣ" in page or re.search(r"[а-я]і[а-я]", page):
                continue                     # pre-1918 spelling
            got += sentences(page)
        got = got[:PER]
        rows += [{"author": name, "s": s} for s in got]
        print(f"{name}: {len(got)} предложений", flush=True)
    random.shuffle(rows)
    out_name = "dostoevsky.jsonl" if os.environ.get("ONLY") == "dost" else "classics.jsonl"
    with open(os.path.join(HERE, "data", out_name), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("всего", len(rows))


if __name__ == "__main__":
    main()
