"""Task 21 through russkiy_dept._task21 at the thinking budget THINK_MAX_21 on the same 10 tasks of half B as
brain21.py (9000 tokens: 5/10, 1398 s). Usage: THINK_MAX_21=750 python t21_budget.py"""
import os
import sys
import time

import ft_21

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import russkiy_dept  # noqa: E402

ok, t0 = 0, time.time()
tasks = ft_21.bank_tasks("B")[:10]
for t in tasks:
    q = f"Знак: {t['mark']}.\n" + "\n".join(f"({k}) {s}" for k, s in sorted(t["sents"].items(), key=lambda z: int(z[0])))
    got = russkiy_dept._task21(q) or ""
    ok += set(got) == set(t["ans"])
    print(f"ждали {''.join(t['ans'])} дал {got}", flush=True)
print(f"задание 21, бюджет {os.environ.get('THINK_MAX_21')}: {ok}/{len(tasks)}, {time.time() - t0:.0f} с")
