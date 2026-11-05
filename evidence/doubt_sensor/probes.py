"""Plan step 11: three doubt sensors on the residual stream before the answer (author's choice: linear, a small
network, KAN). Out-of-fold AUC (5-fold, stratified, 3 repeats) per layer and per set; plus transfer (train on one set,
test on the other). The baseline to beat is the model's token probability of its own answer (lp_min), which is read
AFTER the answer - the sensors read the stream BEFORE it.
Usage: python probes.py
"""
import os
import sys

import numpy as np
import torch
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))


class KAN(torch.nn.Module):
    """A small Kolmogorov-Arnold network (FastKAN style: each edge is a learned function of one variable, written as
    a sum of Gaussian bumps on a fixed grid), 2 layers: d -> h -> 1."""

    def __init__(self, d, h=8, grid=8):
        super().__init__()
        self.register_buffer("centers", torch.linspace(-2, 2, grid))
        self.w1 = torch.nn.Parameter(torch.randn(d * grid, h) * 0.05)
        self.w2 = torch.nn.Parameter(torch.randn(h * grid, 1) * 0.05)
        self.ln = torch.nn.LayerNorm(h)

    def basis(self, x):
        return torch.exp(-((x.unsqueeze(-1) - self.centers) ** 2) / 0.5).flatten(1)

    def forward(self, x):
        h = self.ln(self.basis(x) @ self.w1)
        return (self.basis(h) @ self.w2).squeeze(-1)


def kan_fit_predict(Xtr, ytr, Xte, seed):
    torch.manual_seed(seed)
    pre = make_pipeline(StandardScaler(), PCA(n_components=min(32, len(Xtr) - 1), random_state=seed), StandardScaler())
    a = torch.tensor(pre.fit_transform(Xtr), dtype=torch.float32).clamp(-3, 3)
    b = torch.tensor(pre.transform(Xte), dtype=torch.float32).clamp(-3, 3)
    t = torch.tensor(ytr, dtype=torch.float32)
    m = KAN(a.shape[1])
    opt = torch.optim.Adam(m.parameters(), lr=0.01, weight_decay=1e-2)
    for _ in range(300):
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(m(a), t)
        loss.backward()
        opt.step()
    with torch.no_grad():
        return torch.sigmoid(m(b)).numpy()


def models(seed):
    return {
        "linear": lambda Xtr, ytr, Xte: make_pipeline(StandardScaler(), LogisticRegression(C=0.01, max_iter=2000))
        .fit(Xtr, ytr).predict_proba(Xte)[:, 1],
        "network": lambda Xtr, ytr, Xte: make_pipeline(StandardScaler(), PCA(n_components=min(64, len(Xtr) - 1), random_state=seed),
                                                       MLPClassifier((32,), alpha=1.0, max_iter=2000, random_state=seed))
        .fit(Xtr, ytr).predict_proba(Xte)[:, 1],
        "KAN": lambda Xtr, ytr, Xte: kan_fit_predict(Xtr, ytr, Xte, seed)}


def cv_auc(X, y, name, repeats=3):
    aucs = []
    for rep in range(repeats):
        oof = np.zeros(len(y))
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=rep).split(X, y):
            oof[te] = models(rep)[name](X[tr], y[tr], X[te])
        aucs.append(roc_auc_score(y, oof))
    return float(np.mean(aucs))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    d = np.load(os.path.join(HERE, "hidden_probe.npz"))
    X, y, sets, layers = d["X"].astype(np.float32), d["y"].astype(int), d["set"], d["layers"]
    for s in ("facts", "mgsm"):
        m = sets == s
        print(f"\n{s}: {m.sum()} questions, {y[m].sum()} right; baseline (token probability of the answer, read "
              f"after it) AUC {roc_auc_score(y[m], d['lp_min'][m]):.3f}")
        print("layer   linear  network     KAN")
        for j, l in enumerate(layers):
            row = [cv_auc(X[m, j], y[m], name) for name in ("linear", "network", "KAN")]
            print(f"{l:5}   " + "   ".join(f"{a:.3f}" for a in row), flush=True)
    print("\ntransfer (linear, train on one set, test on the other):")
    for j, l in enumerate(layers):
        out = []
        for a, b in (("facts", "mgsm"), ("mgsm", "facts")):
            ma, mb = sets == a, sets == b
            p = models(0)["linear"](X[ma, j], y[ma], X[mb, j])
            out.append(f"{a}->{b} {roc_auc_score(y[mb], p):.3f}")
        print(f"  layer {l:2}: " + ", ".join(out), flush=True)


if __name__ == "__main__":
    main()
