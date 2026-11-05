"""The doubt sensor for llama-server (NEIRA_PROBE): the linear probe of layer 16 trained on the brain's short answers
(fact probe + MGSM probe, hidden_council.npz), with the standardization folded into the weights:
    P(knows) = sigmoid(w . h + b),  w = coef / scale,  b = intercept - sum(coef * mean / scale).
Out: probe16.json. Also prints the offline P for the first council_people questions (to check the server's reading).
Usage: python export_probe.py
"""
import json
import os
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
LAYER = 16


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    d = np.load(os.path.join(HERE, "hidden_council.npz"))
    j = list(d["layers"]).index(LAYER)
    X, y, sets = d["X"][:, j].astype(np.float64), d["y"].astype(int), d["set"]
    train = np.isin(sets, ["train_facts", "train_mgsm"])
    sc = StandardScaler().fit(X[train])
    lr = LogisticRegression(C=0.01, max_iter=5000).fit(sc.transform(X[train]), y[train])
    w = lr.coef_[0] / sc.scale_
    b = float(lr.intercept_[0] - np.sum(lr.coef_[0] * sc.mean_ / sc.scale_))
    json.dump({"layer": LAYER, "w": [float(x) for x in w], "b": b}, open(os.path.join(HERE, "probe16.json"), "w"))
    p = 1 / (1 + np.exp(-(X @ w + b)))
    test = np.where(sets == "council_people")[0][:8]
    print("offline P for", [str(i) for i in d["ids"][test]], [round(float(x), 4) for x in p[test]])


if __name__ == "__main__":
    main()
