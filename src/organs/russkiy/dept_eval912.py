"""Tasks 9-12 through russkiy_dept.russian_answer (organ + dictionary agreement + Ъ rule + brain choice) on the
whole sdamgia bank. Usage: python dept_eval912.py <path to russkiy_dept.py> [label]"""
import importlib.util
import json
import sys
import time

spec = importlib.util.spec_from_file_location("dept", sys.argv[1])
dept = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dept)
dept.RUSSKIY = r"D:\AI\neira-tools\russkiy\russkiy.exe"
bank = [x for x in json.load(open("data/bank_4_12.json", encoding="utf-8")) if x["task"] in (9, 10, 11, 12)]
ok = bad = 0
t0 = time.time()
for x in bank:
    got, trace = dept.russian_answer(x["q"])
    if not got:
        continue
    keys = ["".join(sorted(k.strip())) for k in x["ans"].split("|")]
    good = "".join(sorted(got)) in keys
    ok += good
    bad += not good
    if not good:
        print("BAD", x["id"], got, x["ans"], trace[:200], flush=True)
print(f"{sys.argv[2] if len(sys.argv) > 2 else ''}: 9-12 верно {ok}, неверно {bad}, не знаю {len(bank) - ok - bad} "
      f"из {len(bank)}, {time.time() - t0:.0f} с")
