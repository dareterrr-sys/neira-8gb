"""Neira's literacy filter (the author, 28.10: «сделай чтобы она грамотно писала и говорила»): every sentence she says
passes through it before the subtitles and the voice.
  1) spacing: «Привет.Ты» -> «Привет. Ты», «Хотя...может» -> «Хотя... может», no space before , . ! ?
  2) commas: the fine-tuned RUPunct net (punct_organ, models/p_ege_cls6k) adds a comma it is sure of and removes one it
     is sure is wrong. Only gaps that are plain spaces or a plain comma are touched; tags [smirk] {смех}, dashes,
     quotes and brackets are left alone. Thresholds ADD / DROP come from gramota_eval.py on held-out correct prose.
GRAMOTA=0 turns it off.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import punct_organ  # noqa: E402

ADD = float(os.environ.get("GRAMOTA_ADD", "6.0"))    # comma log-odds above it: add
DROP = float(os.environ.get("GRAMOTA_DROP", "-8.0"))  # comma log-odds below it: remove
WORD = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+(?:-[А-Яа-яЁёA-Za-z0-9]+)*")
TAG = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>")


def spacing(t):
    t = re.sub(r"(?<=[А-Яа-яЁё])(\.\.\.|…)(?=[А-Яа-яЁё])", r"\1 ", t)
    t = re.sub(r"(?<=[А-Яа-яЁё)»])([.!?])(?=[А-ЯЁ])", r"\1 ", t)
    t = re.sub(r"(?<=[А-Яа-яЁё)»])([,;:])(?=[А-Яа-яЁё«(])", r"\1 ", t)
    t = re.sub(r"(?<=[А-Яа-яЁё]) +([,.!?;:])", r"\1", t)
    return t


def commas(t):
    """One sentence -> the same sentence with sure comma fixes."""
    spans = [(m.start(), m.end()) for m in WORD.finditer(t)]
    if len(spans) < 3:
        return t
    tags = [(m.start(), m.end()) for m in TAG.finditer(t)]
    spans = [s for s in spans if not any(a <= s[0] < b for a, b in tags)]
    if len(spans) < 3:
        return t
    lo = punct_organ.comma_logodds([t[a:b].lower() for a, b in spans])
    out, last = [], 0
    for i in range(len(spans) - 1):
        gap_a, gap_b = spans[i][1], spans[i + 1][0]
        gap, d = t[gap_a:gap_b], lo[i]
        new = gap
        if d is not None and re.fullmatch(r" +", gap) and d > ADD:
            new = ", "
        elif d is not None and re.fullmatch(r", ?", gap) and d < DROP:
            new = " "
        out.append(t[last:gap_a] + new)
        last = gap_b
    out.append(t[last:])
    return "".join(out)


CODE = re.compile(r"#include|[;{}]\s*$|\w\(.*\)\s*[;{]")


def fix(text):
    if not text or os.environ.get("GRAMOTA", "1") == "0":
        return text
    if "```" in text:   # code: only the prose before it
        head, sep, rest = text.partition("```")
        return fix(head) + sep + rest
    if CODE.search(text):
        return text
    text = spacing(text)
    parts = re.split(r"(?<=[.!?…])(\s+)", text)
    return "".join(p if not p.strip() else commas(p) for p in parts)


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        print(fix(line.rstrip("\n")))
