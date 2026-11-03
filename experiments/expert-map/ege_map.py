"""Expert map on EGE Russian tasks (the explanations dataset, data/razbor.jsonl): how often each expert of each of the
40 MoE layers is picked while the brain reads a task with its explanation. For the hot experts kept in VRAM (the
mixed CPU/GPU split, 28.10). map_broad dropped layer 39 (sorted(r)[:-1]); here all 40 are kept, the MTP head is not run.
Out: ege_map.npz {"tasks": int64 [40, 256], "per_task_<n>": ...}. Usage: python ege_map.py [per_task=10]"""
import collections
import json
import os
import random
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from route_tap import RouteTap  # noqa: E402

MODEL = r"D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
PER_TASK = int(sys.argv[1]) if len(sys.argv) > 1 else 10
N_LAYER, N_EXPERT = 40, 256


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [json.loads(l) for l in open(r"D:\AI\neira-tools\russkiy\data\razbor.jsonl", encoding="utf-8")]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["task"]].append(r)
    rng = random.Random(28)
    sample = []
    for t in sorted(by):
        sample += rng.sample(by[t], min(PER_TASK, len(by[t])))
    tap = RouteTap(MODEL, n_ctx=4096)
    total = np.zeros((N_LAYER, N_EXPERT), np.int64)
    per = collections.defaultdict(lambda: np.zeros((N_LAYER, N_EXPERT), np.int64))
    t0 = time.time()
    for i, r in enumerate(sample):
        text = (r["q"] + "\nРазбор: " + r["explanation"] + "\nОтвет: " + r["ans"])[-6000:]
        try:
            route = tap.route(text)
        except RuntimeError as e:
            print("skip", i, e, flush=True)
            continue
        for layer, picks in route.items():
            if layer < N_LAYER:
                np.add.at(total[layer], picks.ravel(), 1)
                np.add.at(per[r["task"]][layer], picks.ravel(), 1)
        if i % 20 == 0:
            print(f"{i}/{len(sample)}, {time.time() - t0:.0f} s", flush=True)
    np.savez(os.path.join(HERE, "ege_map.npz"), tasks=total, **{f"task_{t}": m for t, m in per.items()})
    print("done", len(sample), f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
