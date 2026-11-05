"""Plan step 11, way 1 (the gate): does the stream before the answer, read under one neutral instruction, tell the
council's own wrong answers from right ones? A linear probe (logistic, C=0.01, standardized) per layer is trained on
the brain's short answers (fact probe + MGSM probe) and scored by AUC on each council set (MGSM v3.6, work3 v3.7,
ЕГЭ v3.7, the held-out people v3.7). A question that is in both training and a test set (MGSM: the same problems;
people: the 50 known ones) is left out of training for that test set.
Usage: python gate_eval.py   (needs hidden_council.npz from extract_hidden2.py)
"""
import json
import os
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
COUNCIL = r"D:\AI\neira-tools\council"
TESTS = {"council_mgsm": "council_v36_mgsm.json", "council_work3": "council_v37letters_work3.json",
         "council_ege": "council_v37_ege.json", "council_people": "council_v37_people.json"}


def questions():
    """The question texts in extract_hidden2's order."""
    load = lambda f: json.load(open(os.path.join(COUNCIL, f), encoding="utf-8"))   # noqa: E731
    qs = [r["q"] for r in load("fact_probe_answers.json") if r["label"] in ("right", "wrong")]
    qs += [r["q"] for r in load("mgsm_probe_answers.json")]
    for f in TESTS.values():
        qs += [r["q"] for r in load(f)]
    return np.array(qs)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    d = np.load(os.path.join(HERE, os.environ.get("GATE_NPZ", "hidden_council.npz")))
    X, y, sets, layers = d["X"].astype(np.float32), d["y"].astype(int), d["set"], d["layers"]
    qs = questions()
    assert len(qs) == len(y)
    train = np.isin(sets, ["train_facts", "train_mgsm"])
    print(f"train {train.sum()} (wrong {(1 - y[train]).sum()})")
    out = {}
    for name in TESTS:
        test = sets == name
        if test.sum() == 0:
            continue
        tr = train & ~np.isin(qs, qs[test])
        line = [f"{name:15} n={test.sum():3} wrong={(1 - y[test]).sum():3} train={tr.sum()}"]
        out[name] = {}
        for j, l in enumerate(layers):
            clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.01, max_iter=3000))
            clf.fit(X[tr, j], y[tr])
            p = clf.predict_proba(X[test, j])[:, 1]
            auc = roc_auc_score(y[test], p) if 0 < y[test].sum() < test.sum() else float("nan")
            out[name][int(l)] = round(auc, 3)
            line.append(f"L{l} {auc:.3f}")
        print(" | ".join(line), flush=True)
    json.dump(out, open(os.path.join(HERE, "gate_eval.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
