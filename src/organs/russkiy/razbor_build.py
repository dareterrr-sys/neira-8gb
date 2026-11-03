"""Dataset for teaching the brain (the author, 28.10: «собирай датасет из разборов»): every EGE Russian task 1-26 of
«Решу ЕГЭ» with the human-written explanation («Пояснение») and the answer. Tasks on a text (1-3, 22-26) take the text
from /problem?id=N (the catalog shows only the question). Pages are cached in data/sdamgia/.
Out: data/razbor.jsonl {id, task, q, explanation, ans, half} - half B (every second id) is kept for testing;
the tasks of variant №15 (data/sdamgia/var57739967.html) are left out.
Usage: python razbor_build.py [tasks=1,...,26]"""
import json
import os
import re
import sys

import bank_build
from fetch_task1 import blocks

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(range(1, 27))
TEXT_TASKS = {1, 2, 3, 22, 23, 24, 25, 26}


def balanced(page, start):
    depth, end = 1, len(page) - start
    for d in re.finditer(r"<div\b|</div>", page[start:]):
        depth += 1 if d.group(0) == "<div" else -1
        if depth == 0:
            end = d.start()
            break
    return page[start:start + end]


def solution(chunk):
    m = re.search(r'<div[^>]*class="solution"[^>]*>', chunk)
    if not m:
        return ""
    t = bank_build.text(balanced(chunk, m.end()))
    t = re.sub(r"^\s*(Пояснение|Решение)\s*\.?\s*", "", t)
    return re.split(r"\n\s*Ответ:", t)[0].strip()


def parse(page):
    out = []
    for b in re.split(r'id="problem_', page)[1:]:
        pid = re.match(r"(\d+)", b).group(1)
        ans = re.search(r'<div class="answer"[^>]*>(.*?)</div>', b, re.S)
        exp = solution(b)
        if not ans or len(exp) < 20:
            continue
        q = blocks(b.split('class="solution"')[0])
        out.append({"id": pid, "q": q, "explanation": exp,
                    "ans": re.sub(r"^\s*Ответ:\s*", "", bank_build.text(ans.group(1))).strip()})
    return out


def main():
    variant = set(re.findall(r'id="problem_(\d+)', open(os.path.join(HERE, "data", "sdamgia", "var57739967.html"),
                                                        encoding="utf-8").read()))
    cats = bank_build.categories()
    seen, n = set(variant), 0
    with open(os.path.join(HERE, "data", "razbor.jsonl"), "w", encoding="utf-8") as f:
        for t in TASKS:
            n0 = n
            for cid in cats.get(t, []):
                p, loaded = 1, 0
                while True:
                    page = bank_build.get(f"/test?filter=all&category_id={cid}", f"cat{cid}_p{p}.html",
                                          None if p == 1 else {"ajax": 1, "skip": loaded})
                    got = parse(page)
                    loaded += len(re.findall(r'id="problem_', page))
                    for x in got:
                        if x["id"] in seen:
                            continue
                        seen.add(x["id"])
                        if t in TEXT_TASKS and "Прочитайте" not in x["q"] and not re.search(r"\(\d+\)\s*[А-ЯЁ]", x["q"]):
                            full = bank_build.get(f"/problem?id={x['id']}", f"problem_{x['id']}.html")
                            got2 = parse(full.replace('id="problem_', 'id="problem_', 1))
                            q2 = blocks(full.split('class="solution"')[0])
                            if len(q2) > len(x["q"]):
                                x["q"] = q2
                            if got2 and len(got2[0]["explanation"]) > len(x["explanation"]):
                                x["explanation"] = got2[0]["explanation"]
                        x["half"] = "B" if int(x["id"]) % 2 else "A"
                        f.write(json.dumps({"task": t, **x}, ensure_ascii=False) + "\n")
                        f.flush()
                        n += 1
                    if not got and loaded == 0 or p >= 60 or not re.search(r'id="problem_', page):
                        break
                    p += 1
            print(f"задание {t}: {n - n0}", flush=True)
    print("всего", n)


if __name__ == "__main__":
    main()
