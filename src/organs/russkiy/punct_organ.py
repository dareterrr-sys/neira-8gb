"""Punctuation organ for EGE tasks 16-20: RUPunct (MIT, BERT token classification) fine-tuned on half A of the bank
of real tasks + 6000 sentences of classic prose (ft_punct.py, model models/p_ege_cls6k). At each place (k) the net
gives the log-odds of a comma after the word before it; the organ answers only when every place is decisive, else
None (the brain answers). Thresholds were chosen on one quarter of the bank the net never saw and checked on another:
tasks 17-20 (one wording for all four, so shared thresholds) 188/197 = 95.4% at 70% coverage; task 16 31/32.
The model loads on first use (~0.7 GB RAM, CPU is enough: ~50 ms a task).
"""
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("RUSSKIY_PUNCT_MODEL", os.path.join(HERE, "models", "p_ege_cls6k"))
HI_PLACES, LO_PLACES = 0.0, 0.0        # tasks 17-20: always answer (raw 94% on 17/19/20, 72% on 18 - the brain is lower; 28.10)
HI_16, LO_16 = 0.0, 0.0                # task 16: always answer (raw ~75%)
WORD = re.compile(r"[а-яёА-ЯЁa-zA-Z0-9]+(?:-[а-яёА-ЯЁa-zA-Z0-9]+)*")
_net = None


def _load():
    global _net
    if _net is None:
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL, strip_accents=False, add_prefix_space=True)
        net = AutoModelForTokenClassification.from_pretrained(MODEL).eval()
        comma = [int(i) for i, l in net.config.id2label.items() if l.endswith("_COMMA")]
        _net = (torch, tok, net, comma)
    return _net


def comma_logodds(words):
    torch, tok, net, comma = _load()
    enc = tok(words, is_split_into_words=True, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        probs = net(**enc).logits[0].softmax(-1)
    out, seen = [None] * len(words), set()
    for pos, w in enumerate(enc.word_ids()):
        if w is None or w in seen:
            continue
        seen.add(w)
        p = min(max(float(probs[pos, comma].sum()), 1e-6), 1 - 1e-6)
        out[w] = math.log(p / (1 - p))
    return out


def passage(q):
    m = re.search(r"запят\w*\s*\(-?\w*\)\s*\.\s*", q)
    p = q[m.end():] if m else q
    p = re.split(r"\s*(В ответ (выпишите|запишите)|Ответ дай)", p)[0]
    return re.sub(r"\s+", " ", p).strip()


def places_answer(q):
    """Tasks 17-20: digits of the places with a comma, or None."""
    words, after = [], {}
    for piece in re.split(r"(\(\d\))", passage(q)):
        m = re.fullmatch(r"\((\d)\)", piece)
        if m:
            after[int(m.group(1))] = len(words) - 1
        else:
            words += [w.lower() for w in WORD.findall(piece)]
    if len(after) < 2 or not words:
        return None
    lo = comma_logodds(words)
    got = ""
    for k, i in sorted(after.items()):
        d = lo[i] if 0 <= i < len(lo) else None
        if d is None or LO_PLACES <= d <= HI_PLACES:
            return None
        if d > HI_PLACES:
            got += str(k)
    return got or None   # «no comma anywhere» is not an EGE answer: leave it to the brain


def one_comma_answer(q):
    """Task 16: numbers of the sentences that need exactly one comma, or None."""
    body = q[q.find("1)"):]
    body = re.split(r"\s*(Ответ дай|В ответ)", body)[0]
    sents = [s.strip() for s in re.split(r"\s*\d\)\s*", body) if s.strip()][:5]
    if len(sents) < 4:
        return None
    got = ""
    for i, s in enumerate(sents, 1):
        lo = [v for v in comma_logodds([w.lower() for w in WORD.findall(s)])[:-1] if v is not None]
        if any(LO_16 <= v <= HI_16 for v in lo):
            return None
        if sum(v > HI_16 for v in lo) == 1:
            got += str(i)
    return got or None
