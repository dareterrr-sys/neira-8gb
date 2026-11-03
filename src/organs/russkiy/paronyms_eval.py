"""Task 5 by paronyms.answer on the sdamgia bank (half B, untouched). Usage: python paronyms_eval.py [n]"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paronyms  # noqa: E402
import russkiy_dept  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 140
bank = sorted([x for x in json.load(open("data/bank_5_8_21.json", encoding="utf-8")) if x["task"] == 5],
              key=lambda x: int(x["id"]))[1::2][:N]
ok = bad = 0
t0 = time.time()
for x in bank:
    got = paronyms.answer(x["q"], russkiy_dept._brain_chat)
    keys = [k.strip().lower().replace("ё", "е") for k in x["ans"].split("|")]
    if got is None:
        print("НЕ ЗНАЮ", keys)
        continue
    good = got in keys
    ok += good
    bad += not good
    print("OK " if good else "BAD", got, keys, flush=True)
print(f"задание 5: верно {ok}, неверно {bad}, не знаю {len(bank) - ok - bad} из {len(bank)}, {time.time() - t0:.0f} с")
