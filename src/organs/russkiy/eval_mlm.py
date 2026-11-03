"""ruRoberta-large (mlm_choice.py) on the meaning choices of EGE tasks 13, 14, 15: every item's spellings are scored in
the whole sentence; the margins are saved so the threshold is chosen on half A and checked on half B (like
rule_stats.py). Item truth: 13 - item in the answer <=> written the asked way; 15 - marker in the answer <=> НН (or Н);
14 - all compounds of a row in the answer are written the asked way.
Out: data/mlm_<task>.json. Usage: python eval_mlm.py 13 14 15
"""
import json
import os
import re
import sys
import time

os.environ.setdefault("RUSSKIY_MLM", r"D:\AI\models\ruRoberta-large")
import mlm_choice as M  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def items(q):
    body = q[q.find("1)"):]
    body = re.split(r"\s*(Ответ дай|В ответ)", body)[0]
    parts = re.split(r"(?:^|\s)(\d)\)\s*", " " + body)
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


COMP = re.compile(r"(?:\(([А-ЯЁ-]+)\)\s?|([А-ЯЁ]+(?:-[А-ЯЁ]+)*))(?:\(([А-ЯЁ-]+)\)\s?|([А-ЯЁ]+))+")


def compounds(s):
    """«ДАВНЫМ(ДАВНО)», «(ПО)ЗИМНЕМУ», «(НЕ)ОБОЗЛЁН» -> (start, end, parts)."""
    out = []
    for m in re.finditer(r"(?:\(?[А-ЯЁ]+(?:-[А-ЯЁ]+)*\)?\s?){2,4}", s):
        txt = m.group(0).rstrip()
        if "(" not in txt:
            continue
        parts = [p for p in re.findall(r"\(?([А-ЯЁ-]+)\)?", txt)]
        if len(parts) >= 2:
            out.append((m.start(), m.start() + len(txt), parts))
    return out


def variants(parts, kinds):
    low = [p.lower() for p in parts]
    out = {}
    if "S" in kinds:
        out["S"] = "".join(low)
    if "R" in kinds:
        out["R"] = " ".join(low)
    if "D" in kinds and len(low) == 2:
        out["D"] = "-".join(low)
    return out


def score_compound(s, start, end, parts, kinds):
    vs = variants(parts, kinds)
    texts, spans, keys = [], [], []
    for k, v in vs.items():
        t = s[:start] + v + s[end:]
        texts.append(t)
        spans.append((start, start + len(v)))
        keys.append(k)
    scores = [M.pll(t, a, b) for t, (a, b) in zip(texts, spans)]
    return dict(zip(keys, scores))


def task13(x):
    head = x["q"][:x["q"].find("1)")]
    want_together = "СЛИТНО" in head
    ans = set(x["ans"].split("|")[0])
    rows = []
    for n, s in items(x["q"]).items():
        cs = compounds(s)
        if len(cs) != 1:
            rows.append({"n": n, "skip": True})
            continue
        a, b, parts = cs[0]
        sc = score_compound(s, a, b, parts, "SR")
        truth_together = (str(n) in ans) == want_together
        rows.append({"n": n, "S": sc["S"], "R": sc["R"], "truth": "S" if truth_together else "R"})
    return rows


def task14(x):
    head = x["q"][:x["q"].find("1)")]
    want = "D" if "ДЕФИС" in head else "R" if "РАЗДЕЛЬНО" in head else "S"
    ans = set(x["ans"].split("|")[0])
    rows = []
    for n, s in items(x["q"]).items():
        comps = []
        for a, b, parts in compounds(s):
            comps.append(score_compound(s, a, b, parts, "SRD"))
        rows.append({"n": n, "comps": comps, "want": want, "row_ok": str(n) in ans})
    return rows


def task15(x):
    q = x["q"]
    head = q[:q.find("(1)")]
    want_nn = "НН" in head[head.find("пишется"):]
    ans = set(x["ans"].split("|")[0])
    text = q[q.find("(1)") - 200 if q.find("(1)") > 200 else 0:]
    text = text[text.find(" ") + 1:] if not text.startswith(q[:5]) else text
    rows = []
    for k in range(1, 10):
        mk = f"({k})"
        if mk not in text:
            break
        base = re.sub(r"\((?!%d\))\d\)" % k, "н", text)    # other places: one н (only the local window matters)
        i = base.find(mk)
        t1 = base[:i] + "н" + base[i + 3:]
        t2 = base[:i] + "нн" + base[i + 3:]
        s1, s2 = M.pll(t1, i, i + 1), M.pll(t2, i, i + 2)
        truth_nn = (str(k) in ans) == want_nn
        rows.append({"k": k, "N": s1, "NN": s2, "truth": "NN" if truth_nn else "N"})
    return rows


def main():
    bank = json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8"))
    for t in [int(a) for a in sys.argv[1:]]:
        fn = {13: task13, 14: task14, 15: task15}[t]
        out, t0 = [], time.time()
        for x in sorted([x for x in bank if x["task"] == t], key=lambda x: int(x["id"])):
            out.append({"id": x["id"], "rows": fn(x)})
        json.dump(out, open(os.path.join(HERE, "data", f"mlm_{t}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print(f"задание {t}: {len(out)} за {time.time() - t0:.0f} с", flush=True)


if __name__ == "__main__":
    main()
