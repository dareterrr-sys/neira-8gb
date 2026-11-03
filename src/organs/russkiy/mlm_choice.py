"""Meaning choices by a ready masked language model (ai-forever/ruRoberta-large) instead of the brain's chat (92.6%):
which spelling of a phrase or sentence is more probable - «запивать водой» / «запевать водой», «недаром» / «не даром».
Pseudo-log-likelihood of the tokens around the place that differs (each masked in turn, one batch), compared between
the variants; the answer is the best variant if it wins by MARGIN, else None.
"""
import os

MODEL = os.environ.get("RUSSKIY_MLM", "ai-forever/ruRoberta-large")
MARGIN = float(os.environ.get("RUSSKIY_MLM_MARGIN", "2.0"))
_m = None


def _load():
    global _m
    if _m is None:
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL)
        net = AutoModelForMaskedLM.from_pretrained(MODEL).eval()
        dev = "cuda" if torch.cuda.is_available() and os.environ.get("RUSSKIY_MLM_GPU") == "1" else "cpu"
        _m = (torch, tok, net.to(dev), dev)
    return _m


def pll(text, start, end, pad=2):
    """Sum of log P(token | rest) over the tokens covering text[start:end] and `pad` tokens on each side."""
    torch, tok, net, dev = _load()
    enc = tok(text, return_offsets_mapping=True, return_tensors="pt")
    ids = enc["input_ids"][0]
    offs = enc["offset_mapping"][0].tolist()
    span = [i for i, (a, b) in enumerate(offs) if b > a and a < end and b > start]
    if not span:
        return 0.0
    lo, hi = max(1, span[0] - pad), min(len(ids) - 2, span[-1] + pad)
    pos = list(range(lo, hi + 1))
    batch = ids.repeat(len(pos), 1)
    for r, p in enumerate(pos):
        batch[r, p] = tok.mask_token_id
    with torch.no_grad():
        logits = net(input_ids=batch.to(dev)).logits.float().log_softmax(-1).cpu()
    return float(sum(logits[r, p, ids[p]] for r, p in enumerate(pos)))


def choose(variants, spans):
    """variants: full texts; spans: (start, end) of the differing part in each. -> (index or None, scores)."""
    scores = [pll(t, a, b) for t, (a, b) in zip(variants, spans)]
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    if len(order) > 1 and scores[order[0]] - scores[order[1]] < MARGIN:
        return None, scores
    return order[0], scores
