"""The selective '+' marks the working voice gets (the same code as the stress service :8093, D:\\AI\\ruaccent\\
mark_stress.py, STRESS_MODE=selective), computed offline when the service is down. ruaccent venv.
Usage: python mark_texts.py in.json out.json   (a list of sentences)"""
import json
import os
import sys

os.environ["STRESS_MODE"] = "selective"
sys.path.insert(0, r"D:\AI\ruaccent")
from mark_stress import mark  # noqa: E402

src = json.load(open(sys.argv[1], encoding="utf-8"))
json.dump([mark(t) for t in src], open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
