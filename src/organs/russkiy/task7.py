"""EGE task 7 (a wrongly formed word: «с ПОВИДЛОЙ» -> повидлом) from ready parts: OpenCorpora (pymorphy3) + Hunspell
say whether a form exists at all; for every highlighted word all the forms of its lemma are scored in its phrase by
ruRoberta (mlm_choice.pll). The error is the word whose best other form beats it by the largest margin (a form that
does not exist gets a bonus); the answer is that best form. No training - the whole bank is the test.
Usage: python task7.py [--eval]
"""
import json
import os
import re
import sys

os.environ.setdefault("RUSSKIY_MLM", r"D:\AI\models\ruRoberta-large")
import pymorphy3  # noqa: E402

import mlm_choice as M  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MORPH = pymorphy3.MorphAnalyzer()
_hun = None


def hun_ok(w):
    global _hun
    if _hun is None:
        try:
            import subprocess
            exe = os.path.join(HERE, "russkiy.exe")
            _hun = lambda x: "Hunspell: да" in subprocess.run([exe], input=f'ЕСТЬ("{x}")\n', capture_output=True,  # noqa
                                                              text=True, encoding="utf-8").stdout
        except Exception:
            _hun = lambda x: True  # noqa: E731
    return _hun(w)


def phrases(q):
    body = q.split("правильно.", 1)[-1] if "правильно." in q else q
    body = re.split(r"\s*(Ответ дай|В ответ)", body)[0]
    lines = [l.strip() for l in body.split("\n") if re.search(r"[А-ЯЁ]{3,}", l)]
    if len(lines) >= 4:
        return lines
    # one line: cut before every capitalised word except the first, keep lowercase words that follow it
    words = body.split()
    out, cur = [], []
    for w in words:
        if re.fullmatch(r"[А-ЯЁ-]{2,}[.,]?", w) and any(re.fullmatch(r"[А-ЯЁ-]{2,}[.,]?", c) for c in cur):
            out.append(" ".join(cur))
            cur = [c for c in cur if not re.fullmatch(r"[А-ЯЁ-]{2,}[.,]?", c)][-1:] if False else []
        cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out


def candidates(w):
    forms = set()
    for p in MORPH.parse(w)[:4]:
        for f in p.lexeme:
            forms.add(f.word)
        if p.tag.POS in ("ADJF", "ADJS", "COMP", "ADVB"):
            n = p.normal_form
            for q in MORPH.parse(n)[:2]:
                for f in q.lexeme:
                    forms.add(f.word)
    forms.discard(w)
    return sorted(f for f in forms if abs(len(f) - len(w)) <= 4)[:60]


def solve(q):
    best = None
    for ph in phrases(q):
        m = re.search(r"[А-ЯЁ]{2,}(?:-[А-ЯЁ]+)?", ph)
        if not m:
            continue
        w = m.group(0).lower()
        text = ph[:m.start()].lower() + w + ph[m.end():].lower()
        a = m.start()
        base = M.pll(text, a, a + len(w))
        exists = MORPH.word_is_known(w) and hun_ok(w)
        top, top_s = None, None
        for c in candidates(w):
            s = M.pll(text[:a] + c + text[a + len(w):], a, a + len(c))
            if top_s is None or s > top_s:
                top, top_s = c, s
        if top is None:
            continue
        margin = top_s - base + (0 if exists else 6.0)
        if best is None or margin > best[0]:
            best = (margin, top, w)
    return best


def evaluate():
    bank = [x for x in json.load(open(os.path.join(HERE, "data", "bank_5_8_21.json"), encoding="utf-8"))
            if x["task"] == 7]
    ok = 0
    rows = []
    for x in bank:
        r = solve(x["q"])
        ans = [a.strip().lower().replace("ё", "е") for a in x["ans"].split("|")]
        got = r[1].replace("ё", "е") if r else ""
        good = got in ans
        ok += good
        rows.append({"id": x["id"], "ans": x["ans"], "got": got, "margin": r[0] if r else None, "wrong_word": r[2] if r else None, "ok": good})
    json.dump(rows, open(os.path.join(HERE, "data", "task7_eval.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"задание 7: {ok}/{len(bank)}")
    for th in (2, 4, 6, 8, 10):
        sel = [r for r in rows if r["margin"] is not None and r["margin"] > th]
        print(f"  отрыв > {th}: {sum(r['ok'] for r in sel)}/{len(sel)} (охват {len(sel) / len(rows):.0%})")


if __name__ == "__main__":
    evaluate()
