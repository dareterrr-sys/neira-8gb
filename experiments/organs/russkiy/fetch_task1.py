"""Past EGE tasks 1 with their texts: the catalog pages carry only the question, the text and the gap <...> are on
/problem?id=N. In: data/bank_1.json (bank_build.py 1). Out: data/bank_1_full.json [{id, q, ans}]."""
import json
import re

import bank_build


def blocks(page):
    """The condition: text (probtext) + question (pbody), not the rule popup and not the explanation."""
    parts = []
    for m in re.finditer(r'<div[^>]*class="(?:pbody|probtext)"[^>]*>', page):
        rest = page[m.end():]
        depth, end = 1, len(rest)
        for d in re.finditer(r"<div\b|</div>", rest):
            depth += 1 if d.group(0) == "<div" else -1
            if depth == 0:
                end = d.start()
                break
        t = bank_build.text(rest[:end])
        if "html(resp)" in t or "Сообщить об ошибке" in t or t.startswith("Пояснение") or len(t) < 5 or t in parts:
            continue
        parts.append(t)
    return "\n".join(parts)


def main():
    out = []
    for x in json.load(open("data/bank_1.json", encoding="utf-8")):
        page = bank_build.get(f"/problem?id={x['id']}", f"problem_{x['id']}.html")
        page = page.split('class="solution"')[0]
        q = blocks(page)
        if "<...>" in q:
            out.append({"id": x["id"], "q": q, "ans": x["ans"]})
    json.dump(out, open("data/bank_1_full.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(out), "заданий с текстом и пропуском")


if __name__ == "__main__":
    main()
