"""Gate on the council's MGSM errors with cross-fitting: 5 folds over the MGSM problems; the probe trains on the fact
probe + the brain's MGSM answers of the other folds and is scored on the council's answers of this fold (no problem
is both learned and tested). Both readings: before the answer (hidden_council.npz) and after it (hidden_after.npz).
Usage: python gate_crossfit.py
"""
import os
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import gate_eval

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    qs = gate_eval.questions()
    for npz in ("hidden_council.npz", "hidden_after.npz"):
        d = np.load(os.path.join(HERE, npz))
        X, y, sets, layers = d["X"].astype(np.float32), d["y"].astype(int), d["set"], d["layers"]
        test_all = np.where(sets == "council_mgsm")[0]
        problems = np.unique(qs[test_all])
        line = [f"{npz:20}"]
        for j, l in enumerate(layers):
            p = np.zeros(len(y))
            for k, (_, te) in enumerate(KFold(5, shuffle=True, random_state=0).split(problems)):
                held = np.isin(qs, problems[te])
                tr = (sets == "train_facts") | ((sets == "train_mgsm") & ~held)
                test = (sets == "council_mgsm") & held
                clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.01, max_iter=3000)).fit(X[tr, j], y[tr])
                p[test] = clf.predict_proba(X[test, j])[:, 1]
            line.append(f"L{l} {roc_auc_score(y[test_all], p[test_all]):.3f}")
        print(" | ".join(line), flush=True)


if __name__ == "__main__":
    main()
