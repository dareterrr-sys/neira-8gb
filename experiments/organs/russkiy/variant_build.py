"""A whole sdamgia training variant (print page with answers) -> council question set.
Usage: python variant_build.py data/sdamgia/var57739967.html ../council/ege_var15_questions.json"""
import json
import re
import sys

import bank_build

ORDERED = {8, 22}   # matching tasks: the order of digits is the answer


def digits_pattern(alts, task):
    a = alts[0]
    if task in ORDERED:
        return "^" + r"\D*".join(a)
    allowed = "".join(sorted(set(a)))
    look = "".join(f"(?=.*{c})" for c in sorted(set(a)))
    return f"^(?!.*[^{allowed}\\s,;.и])" + look


src = open(sys.argv[1], encoding="utf-8").read()
items = []
for n, b in enumerate(re.split(r'class="prob_maindiv"', src)[1:], 1):
    ans = re.search(r'<div class="answer"[^>]*>(.*?)<div', b, re.S)
    if not ans:
        continue
    key = re.sub(r"^\s*Ответ:\s*", "", bank_build.text(ans.group(1))).strip()
    # the condition: the plain pbody (not the solution); the text for 1-3 / 22-26 sits in probtext before it
    body = b.split('class="solution"')[0].split('class="answer"')[0]
    parts = []
    for m in re.finditer(r'<div[^>]*class="(?:pbody|probtext)"[^>]*>', body):
        rest = body[m.end():]
        depth, end = 1, len(rest)
        for d in re.finditer(r"<div\b|</div>", rest):   # balanced: the matching tasks keep columns in nested divs
            depth += 1 if d.group(0) == "<div" else -1
            if depth == 0:
                end = d.start()
                break
        t = bank_build.text(rest[:end])
        if "html(resp)" in t or "Сообщить об ошибке" in t or t.startswith("Пояснение") or len(t) < 5 or t in parts:
            continue
        parts.append(t)
    q = "\n".join(parts)
    alts = [x.strip() for x in key.split("|") if x.strip()]
    if all(re.fullmatch(r"\d+", x) for x in alts):
        pat = digits_pattern(alts, n)
        tail = " Ответ дай одной строкой: цифры."
    else:
        pat = "|".join(re.escape(x.lower().replace("ё", "е")) for x in alts)
        tail = " Ответ дай одним словом (или словами), как требует задание."
    items.append({"id": f"v15_{n:02d}", "cat": f"русский {n}", "q": q + tail, "ans": pat, "key": key})
json.dump(items, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for it in items:
    print(it["id"], it["key"], "|", len(it["q"]), "|", it["q"][:150].replace("\n", " "))
