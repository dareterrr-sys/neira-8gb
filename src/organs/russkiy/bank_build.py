"""Test bank for the russkiy organ: real EGE tasks with answers from rus-ege.sdamgia.ru («Решу ЕГЭ»), tasks 4, 9-21.
Only a yardstick - nothing from here goes into the organ's dictionaries or rules. Polite: one request every 3 s, pages
cached in data/sdamgia/ so a rerun downloads nothing.
Out: data/bank.json [{id, task, q, ans, src}]. Usage (russkiy/.venv): python bank_build.py [tasks=4,9,...,21]
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "sdamgia")
BASE = "https://rus-ege.sdamgia.ru"
TASKS = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 and sys.argv[1][0].isdigit() else [4] + list(range(9, 22))
os.makedirs(CACHE, exist_ok=True)


def get(path, name, post=None):
    f = os.path.join(CACHE, name)
    if os.path.exists(f):
        return open(f, encoding="utf-8").read()
    data = urllib.parse.urlencode(post).encode() if post else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"User-Agent": "Mozilla/5.0 (research; one request per 3 s)"})
    for attempt in range(5):   # the site answers 502 now and then (28.10)
        try:
            t = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(10 * (attempt + 1))
    open(f, "w", encoding="utf-8").write(t)
    time.sleep(float(os.environ.get("SDAMGIA_DELAY", "1")))
    return t


def text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    h = re.sub(r"<(\.\.\.|…)>", "&lt;...&gt;", h)   # the gap of tasks 1, 26 is written as a bare <...>, not a tag
    h = re.sub(r"<br\s*/?>|</p>|<p>", "\n", h)
    s = html.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\xad", "").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def categories():
    """task number -> its category ids (every section: FIPI, past exams, training...)."""
    cat = get("/prob_catalog", "catalog.html")
    out = {}
    for part in re.split(r'<span class="theory"', cat)[1:]:
        m = re.search(r">\s*(\d+)\s*</span>\s*\.\s*", part) or re.search(r"Т\s*(?:<[^>]+>\s*)*(\d+)", part)
        num = re.search(r"\|\s*(\d+)\s*\|", text(part[:600]).replace("\n", " | "))
        ids = re.findall(r"category_id=(\d+)", part)
        n = int(m.group(1)) if m else None
        if n and ids:
            out.setdefault(n, []).extend(i for i in ids if i not in out.get(n, []))
    return out


def problems(page):
    out = []
    for b in re.split(r'id="problem_', page)[1:]:
        pid = re.match(r"(\d+)", b).group(1)
        # the condition is the first plain pbody: not the rule popup (it carries the «Сообщить об ошибке» link) and
        # not the explanation («Пояснение»)
        q = None
        for m in re.finditer(r'<div[^>]*id="body\d+"[^>]*class="pbody"[^>]*>(.*?)</div>', b, re.S):
            if "Сообщить об ошибке" in m.group(1).replace("\xad", ""):
                continue
            t = text(m.group(1))
            if t.startswith("Пояснение") or len(t) < 20:
                continue
            q = t
            break
        ans = re.search(r'<div class="answer"[^>]*>(.*?)</div>', b, re.S)
        src = re.search(r"Источники?:\s*</span>(.*?)</div>", b, re.S)
        if not q or not ans:
            continue
        a = re.sub(r"^\s*Ответ:\s*", "", text(ans.group(1)))
        out.append({"id": pid, "q": q, "ans": a, "src": text(src.group(1))[:120] if src else ""})
    return out


if __name__ == "__main__":
    cats = categories()
    bank, seen = [], set()
    for t in TASKS:
        n0 = len(bank)
        for cid in cats.get(t, []):
            p, loaded = 1, 0   # the site loads the rest by POST {ajax: 1, skip: how many are shown}
            while True:
                url = f"/test?filter=all&category_id={cid}"
                page = get(url, f"cat{cid}_p{p}.html", None if p == 1 else {"ajax": 1, "skip": loaded})
                got = problems(page)
                loaded += len(got)
                for x in got:
                    if x["id"] not in seen:
                        seen.add(x["id"])
                        bank.append({"task": t, **x})
                if not got or p >= 60:
                    break
                p += 1
        print(f"задание {t}: {len(bank) - n0}", flush=True)
    json.dump(bank, open(os.path.join(HERE, "data", "bank.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("всего", len(bank))
