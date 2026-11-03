"""The hot expert pool for NEIRA_HOT_EXPERTS (the mixed CPU/GPU split, 28.10): per layer the K most used experts by
the expert maps, then one stand-in for the cold side (the next most used expert: it is often selected anyway).
Sources: map_broad.npz (chat, Neira's answers, tasks, wiki - layers 0-38) and ege_map.npz (EGE tasks with explanations,
all 40 layers) when it exists; each source is normalised per layer, so every source weighs the same.
Out: binary int32 n_layer, K, then n_layer*(K+1) ids. Usage: python make_pool.py K out.bin [sources=chat,neira,tasks,ege]"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
N_LAYER, N_EXPERT = 40, 256


def sources(names):
    out = []
    broad = np.load(os.path.join(HERE, "map_broad.npz"))
    for n in names:
        if n == "ege":
            p = os.path.join(HERE, "ege_map.npz")
            if os.path.exists(p):
                out.append(np.load(p)["tasks"].astype(float))
            continue
        m = np.zeros((N_LAYER, N_EXPERT))
        m[:broad["cat_" + n].shape[0]] = broad["cat_" + n]   # layers 0-38; layer 39 stays empty here
        out.append(m)
    return out


def main():
    k, path = int(sys.argv[1]), sys.argv[2]
    names = sys.argv[3].split(",") if len(sys.argv) > 3 else ["chat", "neira", "tasks", "ege"]
    score = np.zeros((N_LAYER, N_EXPERT))
    for m in sources(names):
        tot = m.sum(1, keepdims=True)
        score += np.divide(m, tot, out=np.zeros_like(m), where=tot > 0)
    pool = np.full((N_LAYER, k + 1), -1, np.int32)
    cover = []
    for l in range(N_LAYER):
        if score[l].sum() == 0:
            continue
        order = np.argsort(-score[l], kind="stable")
        pool[l] = order[:k + 1]
        cover.append(score[l][order[:k]].sum() / score[l].sum())
    with open(path, "wb") as f:
        np.array([N_LAYER, k], np.int32).tofile(f)
        pool.tofile(f)
    print(f"{path}: K={k}, layers with a pool {len(cover)}/40, mean share of picks covered {np.mean(cover) * 100:.0f}%, "
          f"~{k * N_LAYER * 1.90:.0f} MiB of VRAM")


if __name__ == "__main__":
    main()
