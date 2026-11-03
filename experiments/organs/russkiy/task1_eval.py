"""Task 1 on past tasks with texts (data/bank_1_full.json): the closed-list choice vs the brain alone (same short
prompt without the list). Usage: python task1_eval.py"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import russkiy_dept  # noqa: E402
import task1  # noqa: E402

bank = json.load(open("data/bank_1_full.json", encoding="utf-8"))
res = {"список": [0, 0], "мозг": [0, 0]}
t0 = time.time()
for x in bank:
    keys = [k.strip().lower().replace("ё", "е").replace(" ", "") for k in x["ans"].split("|")]
    got = task1.answer(x["q"], russkiy_dept._brain_chat)
    if got:
        res["список"][0 if got in keys else 1] += 1
    saved = task1.options
    task1.options = lambda k: None
    alone = task1.answer(x["q"], russkiy_dept._brain_chat)
    task1.options = saved
    if alone:
        res["мозг"][0 if alone in keys else 1] += 1
    print(f"{x['id']} ждали {keys} | список {got} | мозг {alone}", flush=True)
for k, (ok, bad) in res.items():
    print(f"{k}: верно {ok}, неверно {bad}, не знаю {len(bank) - ok - bad} из {len(bank)}")
print(f"{time.time() - t0:.0f} с")
