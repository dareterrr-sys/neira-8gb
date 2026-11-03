"""EGE task 21 by the brain thinking (enable_thinking): for every sentence name the rule of its mark, then the
sentences with the same rule. N tasks of half B. Usage: python brain21.py [n=10]"""
import json
import re
import sys
import time
import urllib.request

import ft_21

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
SYS = ("Ты эксперт ЕГЭ по русскому языку, задание 21 (пунктуационный анализ). Для КАЖДОГО предложения кратко назови "
       "правило, по которому в нём стоит указанный знак (например: тире между подлежащим и сказуемым; тире в "
       "бессоюзном сложном предложении; тире при обобщающем слове; тире при приложении; запятая при однородных; "
       "запятая при обособленном обстоятельстве; запятая в сложном предложении; запятая при вводном слове...). "
       "Затем найди предложения с ОДНИМ И ТЕМ ЖЕ правилом. Последней строкой: ОТВЕТ: номера через запятую.")


def chat(task):
    q = f"Знак: {task['mark']}.\n" + "\n".join(f"({k}) {s}" for k, s in sorted(task["sents"].items(), key=lambda z: int(z[0])))
    body = {"model": "brain", "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}],
            "temperature": 0.3, "max_tokens": 6000, "chat_template_kwargs": {"enable_thinking": True}}
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(op.open(req, timeout=1800).read())["choices"][0]["message"]["content"]


ok, t0 = 0, time.time()
tasks = ft_21.bank_tasks("B")[:N]
for t in tasks:
    a = chat(t)
    m = re.findall(r"ОТВЕТ:\s*([\d,\s]+)", a)
    got = set(re.findall(r"\d", m[-1])) if m else set()
    ok += got == set(t["ans"])
    print(f"ждали {''.join(t['ans'])} дал {''.join(sorted(got))}", flush=True)
print(f"мозг с размышлением, задание 21: {ok}/{len(tasks)}, {time.time() - t0:.0f} с")
