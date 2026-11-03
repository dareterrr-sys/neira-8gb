"""Task 17 by the syntax parser (Natasha) and two rules: a gerund phrase is set off by commas; a participle phrase is
set off when it stands after the word it describes. The passage is parsed without the (k) marks; a comma goes at a
place that is an edge of such a phrase (and not the edge of the sentence). Measured per task on the whole bank.
Usage: python syntax_punct.py [--show]
"""
import json
import os
import re
import sys

from natasha import Doc, NewsEmbedding, NewsMorphTagger, NewsSyntaxParser, Segmenter

HERE = os.path.dirname(os.path.abspath(__file__))
emb = NewsEmbedding()
SEG, MORPH, SYN = Segmenter(), NewsMorphTagger(emb), NewsSyntaxParser(emb)


def passage(q):
    m = re.search(r"запят\w*\s*\(-?\w*\)\s*\.\s*", q)
    p = q[m.end():] if m else q
    p = re.split(r"\s*В ответ (выпишите|запишите)", p)[0]
    return re.sub(r"\s+", " ", p).strip()


def predict(p):
    """-> set of places (str) with a comma."""
    parts = re.split(r"\s*\((\d)\)\s*", p)
    text, marks = parts[0], []          # marks: (k, char offset where the gap is)
    for i in range(1, len(parts), 2):
        marks.append((parts[i], len(text)))
        text += " " + parts[i + 1]
    doc = Doc(text)
    doc.segment(SEG)
    doc.tag_morph(MORPH)
    doc.parse_syntax(SYN)
    toks = doc.tokens
    idx = {t.id: i for i, t in enumerate(toks)}
    kids = {}
    for t in toks:
        kids.setdefault(t.head_id, []).append(t.id)

    def span(tid):
        # the parser can return a cycle (27.10: a run without this check grew to 24 GB) - visit each token once
        out, stack, seen = [], [tid], set()
        while stack:
            x = stack.pop()
            if x in seen or x not in idx:
                continue
            seen.add(x)
            out.append(idx[x])
            stack += kids.get(x, [])
        return min(out), max(out)

    edges = set()   # char offsets where a comma is needed
    for t in toks:
        form = t.feats.get("VerbForm") if t.feats else None
        if form == "Conv" and t.rel in ("advcl", "conj", "acl", "parataxis"):
            a, b = span(t.id)
        elif form == "Part" and t.rel == "acl" and t.head_id in idx and idx[t.head_id] < idx[t.id]:
            a, b = span(t.id)
            a = min(a, idx[t.id])
        else:
            continue
        while b > a and toks[b].pos == "PUNCT":
            b -= 1
        edges.add(toks[a].start)          # before the phrase
        edges.add(toks[b].stop)           # after the phrase
    got = set()
    for k, off in marks:
        # the gap at off: a comma if a phrase starts right after it or ends right before it
        nxt = next((t.start for t in toks if t.start >= off), None)
        prv = max((t.stop for t in toks if t.stop <= off), default=None)
        last = toks[-1].stop
        if (nxt in edges and nxt != toks[0].start) or (prv in edges and prv not in (last,)):
            got.add(k)
    return got


def main():
    bank = [x for x in json.load(open(os.path.join(HERE, "data", "bank_16_21.json"), encoding="utf-8"))
            if x["task"] == 17]
    ok = 0
    for x in bank:
        got = predict(passage(x["q"]))
        want = set(x["ans"].split("|")[0])
        ok += got == want
        if "--show" in sys.argv and got != want:
            print(f"ждали {''.join(sorted(want))} дал {''.join(sorted(got))} | {passage(x['q'])[:200]}")
    print(f"задание 17: {ok}/{len(bank)} = {ok / len(bank):.1%} (без права молчать)")


if __name__ == "__main__":
    main()
