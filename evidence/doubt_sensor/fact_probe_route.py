"""Plan step 11: does the map's confirmed "facts department" (cat:wiki, 40 experts, causally checked in dept_ablate)
tell knowing from confabulating? For every fact-probe answer the brain re-reads question + its own answer (prefill)
and we measure the share of picks that go to the department: on the person's name (Ferrando et al. 2024: "do I know
this entity" shows on the entity's own tokens) and on the answer. The tasks department is a control.
Usage: python fact_probe_route.py -> adds f_* fields to fact_probe_answers.json (copy fact_probe_route.json)
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from route_tap import RouteTap  # noqa: E402

COUNCIL = r"D:\AI\neira-tools\council"
MODEL = r"D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
SYSTEM = ("Ответь коротко: только год рождения четырьмя цифрами. Если ты не знаешь этого человека или такого человека "
          "нет, ответь «не знаю».")


def prompt(user, answer=""):
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n{answer}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    groups = json.load(open(os.path.join(HERE, "dept", "dept_ablate.json"), encoding="utf-8"))["groups"]
    depts = {name: {(l, x) for l, x in groups[key]} for name, key in
             (("facts", "cat:wiki"), ("tasks", "cat:tasks"), ("random", "random1"))}
    rows = json.load(open(os.path.join(COUNCIL, "fact_probe_answers.json"), encoding="utf-8"))
    tap = RouteTap(MODEL, n_ctx=1024)
    for r in rows:
        q, ans = r["q"], r["answer"]
        name = re.match(r"Назови год рождения: (.+?), ", q).group(1)
        head = prompt(q[: q.index(name)])
        _, n_head = tap.tokens(head)
        _, n_name = tap.tokens(prompt(q[: q.index(name) + len(name)]))
        _, n_q = tap.tokens(prompt(q))
        routes = tap.route(prompt(q, ans))
        layers = sorted(routes)[:-1]
        for dname, members in depts.items():
            def share(a, b):
                hit = tot = 0
                for l in layers:
                    picks = routes[l][a:b]
                    tot += picks.size
                    hit += sum(1 for row in picks for x in row if (l, int(x)) in members)
                return hit / tot if tot else 0.0
            r[f"f_{dname}_name"] = share(n_head, n_name)
            r[f"f_{dname}_answer"] = share(n_q, len(routes[layers[0]]))
        print(r["id"], r["label"], " ".join(f"{k[2:]}={r[k]:.4f}" for k in r if k.startswith("f_")), flush=True)
    json.dump(rows, open(os.path.join(COUNCIL, "fact_probe_route.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
