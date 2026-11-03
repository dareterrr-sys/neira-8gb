"""EGE task 7 by the traps of past variants (the author's idea, 27.10: «возьми прошлогодние варианты»): the same wrong
forms come back year after year (полотенец, носков, поезжай, шестьюстами). From half A of the bank: a table of
highlighted forms known wrong (with their correction = the answer) and known right (the other four). On half B:
a highlighted form known wrong -> its correction; else if the others are all known right -> the remaining one is wrong,
corrected by the forms of its lemma closest to the known answers' patterns (pymorphy). Usage: python task7_table.py
"""
import json
import os
import re

import pymorphy3

HERE = os.path.dirname(os.path.abspath(__file__))
MORPH = pymorphy3.MorphAnalyzer()


def norm(w):
    return w.lower().replace("ё", "е")


def items(q):
    body = q.split("правильно.", 1)[-1] if "правильно." in q else q
    body = re.split(r"\s*(Ответ дай|В ответ)", body)[0]
    return [norm(m.group(0)) for m in re.finditer(r"[А-ЯЁ]{2,}(?:-[А-ЯЁ]+)?", body)]


PREP_CASE = {"с": "ablt", "со": "ablt", "без": "gent", "из": "gent", "у": "gent", "до": "gent", "от": "gent",
             "о": "loct", "об": "loct", "в": "loct", "на": "loct", "к": "datv", "по": "datv"}


def fix_invalid(form, q):
    """A form that does not exist: one vowel changed («запечатлить» -> запечатлеть) or the lemma put into the case the
    preposition before it asks («с повидлой» -> повидлом)."""
    if MORPH.word_is_known(form):
        return None
    vow = "аеиоуыэюяё"
    hits = {form[:i] + v + form[i + 1:] for i, c in enumerate(form) if c in vow for v in vow if v != c}
    hits = [h for h in hits if MORPH.word_is_known(h)]
    if len(hits) == 1:
        return hits[0]
    m = re.search(r"(\w+)\s+" + re.escape(form.upper()), q.replace("ё", "е").replace("Ё", "Е"))
    case = PREP_CASE.get(m.group(1).lower()) if m else None
    if case:
        for p in MORPH.parse(form)[:3]:
            f = p.inflect({case})
            if f and MORPH.word_is_known(f.word) and f.word != form:
                return norm(f.word)
    return None


def context(q, form):
    """The lowercase word right after the highlighted form (the noun a numeral agrees with)."""
    m = re.search(re.escape(form.upper()) + r"\s+([а-яё]+)", q.replace("ё", "е").replace("Ё", "Е"))
    return m.group(1) if m else ""


CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")


def fix_numeral(form, nxt):
    """«пятиста» + «учениками» -> «пятьюстами»: the numeral takes the case of the noun after it."""
    p = [x for x in MORPH.parse(form) if x.tag.POS == "NUMR" or x.normal_form.endswith(("сот", "ста", "сти", "сто"))]
    lem = None
    for x in MORPH.parse(form):
        if x.tag.POS == "NUMR":
            lem = x
            break
    if lem is None:
        cand = [x for x in MORPH.parse(re.sub(r"(ста|стам|стами|стах|сот)$", "сот", form)) if x.tag.POS == "NUMR"]
        lem = cand[0] if cand else None
    if lem is None or not nxt:
        return None
    nc = [x.tag.case for x in MORPH.parse(nxt) if x.tag.POS in ("NOUN", "ADJF", "NPRO") and x.tag.case in CASES]
    if not nc:
        return None
    case = "gent" if "gent" in nc and len(set(nc)) > 1 and nc[0] == "gent" else nc[0]
    f = lem.inflect({case})
    return norm(f.word) if f else None


def lemmas(w):
    return {p.normal_form.replace("ё", "е") for p in MORPH.parse(w)[:3]}


def wrong_of(its, answers):
    """The highlighted form the answer corrects: same lemma, else the closest spelling."""
    a = answers[0]
    la = lemmas(a.split()[-1])
    hits = [w for w in its if lemmas(w.split()[-1]) & la]
    if len(hits) == 1:
        return hits[0]
    import difflib
    return max(its, key=lambda w: difflib.SequenceMatcher(None, w, a).ratio())


def main():
    bank = sorted([x for x in json.load(open(os.path.join(HERE, "data", "bank_5_8_21.json"), encoding="utf-8"))
                   if x["task"] == 7], key=lambda x: int(x["id"]))
    A, B = bank[0::2], bank[1::2]
    bad, good = {}, set()
    for x in A:
        its = items(x["q"])
        ans = [norm(a) for a in x["ans"].split("|")]
        if len(its) < 4:
            continue
        w = wrong_of(its, ans)
        bad[w] = ans[0]
        good |= {i for i in its if i != w}
    ok = wrong = silent = 0
    for x in B:
        its = items(x["q"])
        ans = [norm(a) for a in x["ans"].split("|")]
        known_bad = [i for i in its if i in bad and i not in good]
        unknown = [i for i in its if i not in good]
        invalid = [i for i in its if " " not in i and not MORPH.word_is_known(i)]
        target = known_bad[0] if len(known_bad) == 1 else (unknown[0] if len(unknown) == 1 else
                                                            (invalid[0] if len(invalid) == 1 else None))
        got = None
        if target:
            num = fix_numeral(target, context(x["q"], target))   # numerals: the case comes from the noun
            got = num or bad.get(target) or fix_invalid(target, x["q"])
        if got is None:
            silent += 1
            continue
        ok += got in ans
        wrong += got not in ans
    print(f"таблица из половины A: ошибочных форм {len(bad)}, верных {len(good)}")
    print(f"половина B ({len(B)}): верно {ok}, неверно {wrong}, молчит {silent}; "
          f"точность {ok / max(1, ok + wrong):.1%}, охват {(ok + wrong) / len(B):.0%}")


TABLE = os.path.join(HERE, "data", "task7_table.json")


def build_table():
    """Production table from the WHOLE bank (the evaluation above used half A only)."""
    bank = [x for x in json.load(open(os.path.join(HERE, "data", "bank_5_8_21.json"), encoding="utf-8")) if x["task"] == 7]
    bad, good = {}, set()
    for x in bank:
        its = items(x["q"])
        ans = [norm(a) for a in x["ans"].split("|")]
        if len(its) >= 4:
            w = wrong_of(its, ans)
            bad[w] = ans[0]
            good |= {i for i in its if i != w}
    json.dump({"bad": bad, "good": sorted(good - set(bad))}, open(TABLE, "w", encoding="utf-8"), ensure_ascii=False)
    print("таблица:", len(bad), "ошибочных,", len(good), "верных ->", TABLE)


_T = None


def answer(q):
    """Task 7 for the department: the corrected word, or None."""
    global _T
    if _T is None:
        _T = json.load(open(TABLE, encoding="utf-8"))
        _T["good"] = set(_T["good"])
    its = items(q)
    if len(its) < 4:
        return None
    known_bad = [i for i in its if i in _T["bad"] and i not in _T["good"]]
    unknown = [i for i in its if i not in _T["good"]]
    invalid = [i for i in its if " " not in i and not MORPH.word_is_known(i)]   # a form that does not exist at all
    target = known_bad[0] if len(known_bad) == 1 else (unknown[0] if len(unknown) == 1 else
                                                        (invalid[0] if len(invalid) == 1 else None))
    if not target:
        return None
    return fix_numeral(target, context(q, target)) or _T["bad"].get(target) or fix_invalid(target, q)


if __name__ == "__main__":
    import sys
    build_table() if "--build" in sys.argv else main()
