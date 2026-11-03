"""EGE tasks 13 and 15 by fine-tuned classifiers (ft_ne.py, ft_nn.py), the brain's fallback replaced where the nets
beat it on the untouched half of the bank: task 13 - net ne13_old (corpus + old-format traps): 30/41 tasks;
task 15 - the dictionary organ first (100%), the net nn15 for the places it leaves open: 123/138. Below the 98% goal,
above the brain (13: 37-50%, 15 open places: much lower). Models load on first use, CPU is enough.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
_nets = {}


def _net(name):
    if name not in _nets:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        path = os.path.join(HERE, "models", name)
        _nets[name] = (torch, AutoTokenizer.from_pretrained(path),
                       AutoModelForSequenceClassification.from_pretrained(path).eval())
    return _nets[name]


def _p(name, s):
    torch, tok, net = _net(name)
    with torch.no_grad():
        return float(net(**tok(s, truncation=True, max_length=160, return_tensors="pt")).logits.softmax(-1)[0, 1])


def _items(q):
    body = re.split(r"\s*(Ответ дай|В ответ)", q[q.find("1)"):])[0]
    parts = re.split(r"(?:^|\s)(\d)\)\s*", " " + body)
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def task13(q):
    head = q[:q.find("1)")]
    want_together = "СЛИТНО" in head
    if want_together == ("РАЗДЕЛЬНО" in head):
        return None
    got = ""
    for n, s in _items(q).items():
        if "(НЕ)" not in s and "(НИ)" not in s:
            return None
        if (_p("ne13_old", s) > 0.5) == want_together:
            got += str(n)
    return got or None


def task14(q):
    """Rows whose every highlighted word is written the asked way (net sp14, 23/45 on the untouched half)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ft_14", os.path.join(HERE, "ft_14.py"))
    f14 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f14)
    torch, tok, net = _net("sp14")
    head = q[:q.find("1)")]
    want = 1 if "ДЕФИС" in head else 2 if "РАЗДЕЛЬНО" in head else 0
    got = ""
    for n, s in _items(q).items():
        preds = f14.predict_row(tok, net, "cpu", s)
        if not preds:
            return None
        if all(lab == want for lab, _ in preds):
            got += str(n)
    return got or None


def task15(q, organ_marks):
    """organ_marks: {k: 0/1/-1} from the dictionary organ (РАЗБОР); -1 = the net decides."""
    i0 = q.find("(1)")
    head = q[:i0]
    want_nn = "НН" in head[head.find("пишется"):]
    st = head.rfind(".") + 1 if head.rfind(".") > 0 else 0
    text = re.split(r"\s*(Ответ дай|В ответ)", q[st:])[0]
    got = ""
    for k in range(1, 10):
        if f"({k})" not in text:
            break
        v = organ_marks.get(k, -1)
        if v not in (0, 1):
            s = re.sub(r"\((?!%d\))\d\)" % k, "н", text).replace(f"({k})", "(1)")
            v = int(_p("nn15", s) > 0.5)
        if (v == 1) == want_nn:
            got += str(k)
    return got or None
