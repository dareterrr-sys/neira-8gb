"""EGE task 5 (paronyms) by the FIPI «Список паронимов – 2026» (doc.fipi.ru navigator, ru-2-leksika-i-frazeologija.pdf;
the task takes its words only from this list). The brain finds which highlighted word is wrong and what it should mean;
the list gives the replacement - a word of the same paronym group, in the same form (pymorphy3 inflects it); among
several candidates the brain chooses by meaning.
  build: python paronyms.py --build  (data/fipi_lex_2026.txt -> data/paronyms.json)"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "paronyms.json")
_MORPH = None


def build():
    t = open(os.path.join(HERE, "data", "fipi_lex_2026.txt"), encoding="utf-8").read()
    t = t[t.find("«Списку паронимов"):]
    t = t[:t.find("Обратите внимание!")]
    groups = []
    for line in t.splitlines():
        ws = [w.strip().lower() for w in re.split(r"\s+[–—-]\s+", line.strip()) if w.strip()]
        if len(ws) >= 2 and all(re.fullmatch(r"[а-яё]+(-[а-яё]+)?(\s\([^)]*\))?", w) for w in ws):
            groups.append([re.sub(r"\s\(.*", "", w) for w in ws])
    json.dump(groups, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(groups), "групп,", sum(map(len, groups)), "слов")


def morph():
    global _MORPH
    if _MORPH is None:
        import pymorphy3
        _MORPH = pymorphy3.MorphAnalyzer()
    return _MORPH


def lemma(w):
    return morph().parse(w.lower())[0].normal_form.replace("ё", "е")


def candidates(word):
    """The highlighted word (any form) -> its paronyms put into the same form."""
    groups = json.load(open(OUT, encoding="utf-8"))
    w = word.lower().replace("ё", "е")
    lems = {p.normal_form.replace("ё", "е") for p in morph().parse(w)} | {w}
    if w.endswith(("чно", "ски", "ично")):   # adverb: гармонично -> гармоничный / гармонически -> гармонический
        adj = re.sub(r"чно$", "чный", re.sub(r"ски$", "ский", w))
        return [re.sub(r"чный$", "чно", re.sub(r"ский$", "ски", x)) for x in candidates(adj)] if adj != w else []
    out = []
    for g in groups:
        g2 = [x.replace("ё", "е") for x in g]
        if lems & set(g2):
            ps = [p for p in morph().parse(w) if p.normal_form.replace("ё", "е") in g2]
            src = next((p for p in ps if p.tag.case in (None, "nomn")), ps[0] if ps else None)
            for x in g2:
                if x in lems:
                    continue
                form = x
                if src is not None:
                    verb = {"VERB", "INFN"}
                    tgt = next((p for p in morph().parse(x) if p.tag.POS == src.tag.POS or
                                (src.tag.POS in verb and p.tag.POS in verb)), None)
                    gr = {g for g in (src.tag.case, src.tag.number, src.tag.gender, src.tag.tense, src.tag.person,
                                      src.tag.mood) if g}
                    if src.tag.POS == "ADJS":
                        gr = {g for g in (src.tag.number, src.tag.gender) if g}
                    if tgt is not None:
                        f = tgt.inflect(gr) if gr else None
                        if src.tag.POS == "ADJS" and tgt.tag.POS != "ADJS":
                            f = None
                        form = f.word if f else x
                out.append(form)
    return list(dict.fromkeys(out))


def _lev(a, b, cap=2):
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


_FORMS = None


def near(word, limit=8):
    """Not in the FIPI list (older exams: обоняние -> обаяние): dictionary words in the same grammatical form, same
    first letter, at most 2 edits away, another lemma."""
    global _FORMS
    if _FORMS is None:
        _FORMS = [l.strip() for l in open(os.path.join(HERE, "data", "opencorpora.txt"), encoding="utf-8")]
    w = word.lower().replace("ё", "е")
    src = morph().parse(w)[0]
    lem = src.normal_form.replace("ё", "е")
    out = []
    for f in _FORMS:
        if f[:1] != w[:1] or abs(len(f) - len(w)) > 2 or f == w or "-" in f:
            continue
        if _lev(w, f) > 2:
            continue
        ok = [p for p in morph().parse(f) if p.tag.POS == src.tag.POS and p.normal_form.replace("ё", "е") != lem
              and (not src.tag.case or p.tag.case == src.tag.case)]
        if not ok:
            continue
        out.append(f)
    return out[:limit * 4]


def highlighted(q):
    """The CAPITALISED words of a task 5 and their sentences."""
    body = q.split("Запишите подобранное слово", 1)[-1]
    out = []
    for s in re.split(r"\n+", body):
        for m in re.finditer(r"\b[А-ЯЁ]{3,}(?:-[А-ЯЁ]+)?\b", s):
            out.append((m.group(0), s.strip()))
    return out


ASK_WRONG = ("Задание ЕГЭ 5 (паронимы). В одном предложении выделенное ЗАГЛАВНЫМИ буквами слово употреблено неверно: "
             "его значение не подходит к сочетанию. Какое это слово? Ответь только этим словом.")
ASK_PICK = "Ответь только одним словом из предложенных, без пояснений."


def _word(a):
    a = (a or "").strip().split("\n")[-1]
    m = re.findall(r"[А-Яа-яЁё-]+", a)
    return m[-1].lower().replace("ё", "е") if m else ""


def answer(q, chat):
    """Task 5 -> the corrected word, or None. chat(messages, temperature, max_tokens) -> (text, usage)."""
    hl = highlighted(q)
    if len(hl) < 3:
        return None
    # every highlighted word against its paronyms, by meaning (as the 9-12 choice: 92.6%); the wrong one is the
    # word the brain replaces
    flips = []
    for word, sent in hl:
        cands = candidates(word)
        if not cands:
            continue
        opts = [word.lower()] + cands
        a = chat([{"role": "system", "content": ASK_PICK},
                  {"role": "user", "content": f"Предложение: «{sent}». Какое слово уместно на месте {word}: "
                                              + ", ".join(opts) + "?"}], temperature=0, max_tokens=20)[0]
        p = _word(a)
        if p in cands:
            flips.append(p)
    if len(flips) == 1:
        return flips[0]
    if flips:
        return None
    # nothing flipped: the error may be a word outside the FIPI list (older exams) - ask which word is wrong
    sents = "\n".join(s for s in dict.fromkeys(s for _, s in hl))
    w = _word(chat([{"role": "system", "content": ASK_WRONG}, {"role": "user", "content": sents}], temperature=0,
                   max_tokens=20)[0])
    hit = [(x, s) for x, s in hl if x.lower().replace("ё", "е") == w and not candidates(x)]
    if len(hit) != 1:
        return None
    word, sent = hit[0]
    cands = near(word)
    if not cands:
        return None
    a = chat([{"role": "system", "content": ASK_PICK},
              {"role": "user", "content": f"В предложении «{sent}» слово {word} употреблено неверно. Каким словом "
                                          f"его заменить: " + ", ".join(cands) + "?"}], temperature=0, max_tokens=20)[0]
    p = _word(a)
    return p if p in cands else None


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    for w in sys.argv[1:]:
        if not w.startswith("--"):
            print(w, "->", candidates(w))
