"""EGE tasks 13-14 by the brain with the rule in front of it (the author, 27.10: «есть же правила русского языка, почему
нельзя просто загрузить их в модель и все исключения?»): the rule text from the bank's rule popup + 3 solved tasks
from half A with their step-by-step explanations (sdamgia «Пояснение») + the new task; the brain goes item by item,
names the rule and ends with «ОТВЕТ: digits». Measured on N tasks of half B. The brain must run on 8080.
Usage: python brain_rules.py 13 14 [n=30]
"""
import json
import os
import re
import sys
import time
import urllib.request

import bank_build as bb

HERE = os.path.dirname(os.path.abspath(__file__))
API = "http://127.0.0.1:8080/v1/chat/completions"
TASKS = [int(a) for a in sys.argv[1:] if len(a) <= 2]
N = int(sys.argv[-1]) if len(sys.argv[-1]) > 2 or sys.argv[-1] == "30" else 30


def pages(task):
    cats = bb.categories()[task]
    for cid in cats:
        for p in range(1, 40):
            f = os.path.join(bb.CACHE, f"cat{cid}_p{p}.html")
            if not os.path.exists(f):
                break
            yield open(f, encoding="utf-8").read()


def rule_and_explanations(task):
    rule, expl = "", {}
    for page in pages(task):
        for b in re.split(r'id="problem_', page)[1:]:
            pid = re.match(r"(\d+)", b).group(1)
            for m in re.finditer(r'<div[^>]*class="pbody"[^>]*>(.*?)</div>', b, re.S):
                t = bb.text(m.group(1))
                if not rule and "Сообщить" in m.group(1).replace("\xad", "") and len(t) > 800:
                    rule = t
                if t.startswith("Пояснение") and pid not in expl:
                    expl[pid] = re.sub(r"\s+", " ", t)
    rule = re.sub(r"\s+", " ", rule)
    return rule[:6000], expl


def chat(messages, max_tokens=1500):
    body = {"model": "brain", "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=900).read())["choices"][0]["message"]["content"]


def digits(s):
    return "".join(sorted(set(re.sub(r"\D", "", s or ""))))


def main():
    bank = json.load(open(os.path.join(HERE, "data", "bank.json"), encoding="utf-8"))
    for t in TASKS:
        rows = sorted([x for x in bank if x["task"] == t], key=lambda x: int(x["id"]))
        A, B = rows[0::2], rows[1::2]
        rule, expl = rule_and_explanations(t)
        shots = [x for x in A if x["id"] in expl][:3]
        sys_msg = ("Ты опытный экзаменатор ЕГЭ по русскому языку. Решай строго по правилу ниже. Для КАЖДОГО пункта "
                   "определи часть речи и условия (зависимые слова, противопоставление, значение), назови правило и "
                   "напиши, как пишется выделенное слово. Последней строкой напиши: ОТВЕТ: номера через запятую.\n\n"
                   "ПРАВИЛО:\n" + rule)
        msgs = [{"role": "system", "content": sys_msg}]
        for x in shots:
            msgs += [{"role": "user", "content": x["q"]},
                     {"role": "assistant", "content": expl[x["id"]].replace("Пояснение (см. также Правило ниже).", "")
                      + f"\nОТВЕТ: {', '.join(x['ans'].split('|')[0])}"}]
        ok, t0, log = 0, time.time(), []
        for x in B[:N]:
            a = chat(msgs + [{"role": "user", "content": x["q"]}])
            m = re.findall(r"ОТВЕТ:\s*([\d,\s]+)", a)
            got = digits(m[-1]) if m else ""
            right = got == digits(x["ans"].split("|")[0])
            ok += right
            log.append({"id": x["id"], "ans": x["ans"], "got": got, "ok": right, "text": a})
        json.dump(log, open(os.path.join(HERE, "data", f"brain_rules_{t}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"задание {t}: мозг с правилом и примерами {ok}/{len(log)}, {time.time() - t0:.0f} с "
              f"(правило {len(rule)} знаков, примеров {len(shots)})", flush=True)


if __name__ == "__main__":
    main()
