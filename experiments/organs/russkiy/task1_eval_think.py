"""Task 1, list choice with short thinking (TASK1_THINK tokens) on data/bank_1_full.json."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import russkiy_dept  # noqa: E402
import task1  # noqa: E402

bank = json.load(open("data/bank_1_full.json", encoding="utf-8"))
ok = bad = 0
t0 = time.time()
for x in bank:
    keys = [k.strip().lower().replace("ё", "е").replace(" ", "") for k in x["ans"].split("|")]
    got = task1.answer(x["q"], russkiy_dept._brain_chat)
    if got:
        ok += got in keys
        bad += got not in keys
    print(f"{x['id']} ждали {keys} | думал {got}", flush=True)
print(f"список + размышление {task1.THINK}: верно {ok}, неверно {bad}, не знаю {len(bank) - ok - bad} из {len(bank)}, "
      f"{time.time() - t0:.0f} с")
