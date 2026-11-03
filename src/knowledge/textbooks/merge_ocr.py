"""Two readings of a scanned book voted word by word (31.10, the author: «учебник должен быть идеальным»): the first
OCR (fast model) and the second (tessdata_best). Where they agree, the word stays as it is - so Rozental's
deliberately wrong examples («агитнуть», «согласно приказа») are never «corrected». Where they differ, the reading
the dictionary (pymorphy3) knows wins; a tie goes to the accurate model. Every decision is logged for review.
Usage (Open-LLM-VTuber venv: pymorphy3): python merge_ocr.py <first pages dir> <second pages dir> <out.txt> <log.tsv>"""
import difflib
import os
import re
import sys

import pymorphy3

MORPH = pymorphy3.MorphAnalyzer()
TOKEN = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+|\s+|[^\sА-Яа-яЁёA-Za-z0-9]")


def known(w):
    if re.fullmatch(r"\d*[06]\d*", w) and len(w) <= 3:   # «06» for «ов», «6» for «б»: digits OCR made of letters
        return False
    if not re.fullmatch(r"[А-Яа-яЁё]+", w):
        return not re.search(r"[А-Яа-яЁё]", w) or False   # punctuation and numbers: neutral
    return MORPH.word_is_known(w.lower())


def score(tokens):
    words = [t for t in tokens if re.fullmatch(r"[А-Яа-яЁё]{2,}", t) or re.fullmatch(r"\d*[06]\d*", t) and len(t) <= 3]
    mixed = sum(bool(re.search(r"[А-Яа-яЁё]", t) and re.search(r"[A-Za-z0-9]", t)) for t in tokens)
    return sum(known(w) for w in words) - len(words) - 2 * mixed   # 0 = all known; lower = more unknown words


def merge(a, b, log, page):
    ta, tb = TOKEN.findall(a), TOKEN.findall(b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            out += ta[i1:i2]
            continue
        sa, sb = ta[i1:i2], tb[j1:j2]
        if "".join(sa).strip() == "" and "".join(sb).strip() == "":
            out += sa   # whitespace only: keep the first reading's line breaks
            continue
        pick = sb if score(sb) >= score(sa) else sa
        out += pick
        log.write(f"{page}\t{''.join(sa).strip()!r}\t{''.join(sb).strip()!r}\t{'B' if pick is sb else 'A'}\n")
    return "".join(out)


def main():
    first, second, out_path, log_path = sys.argv[1:5]
    pages = sorted(f for f in os.listdir(first) if f.endswith(".txt"))
    with open(log_path, "w", encoding="utf-8") as log, open(out_path, "w", encoding="utf-8") as out:
        for f in pages:
            a = open(os.path.join(first, f), encoding="utf-8").read()
            pb = os.path.join(second, f)
            b = open(pb, encoding="utf-8").read() if os.path.exists(pb) else a
            b = re.sub(r"(?<=\s)--(?=\s)", "—", b)   # the accurate model writes the dash as «--»
            out.write(f"=== стр. {int(f[:4])} ===\n" + merge(a, b, log, int(f[:4])) + "\n")
    print("страниц", len(pages))


if __name__ == "__main__":
    main()
