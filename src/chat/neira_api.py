# -*- coding: utf-8 -*-
"""
Полнийра_api.py — однострочный запрос к мозгу Нейры напрямую через API.
Обход чат-клиента: без обрывов, автопродолжения и персоны (по умолчанию).

Использование:
  python neira_api.py "промпт"
  echo "промпт" | python neira_api.py
  python neira_api.py --temp 0 --max-tokens 8000 "промпт"

Промпт можно передать аргументом или через stdin (файл/конвейер).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = "brain"

SYSTEM = (
    "Ты — инженер-исполнитель. Пишешь только код: без вступлений, без эмоций, "
    "без пояснений, без дублирования задания. Отвечаешь ровно тем, что просили."
)


def ask(prompt, temperature=0.2, max_tokens=8192):
    if isinstance(prompt, str):
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ]
    else:
        messages = prompt
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}"
            print(f"    [neira_api] попытка {attempt+1}/3 — {last_err}", flush=True)
            time.sleep(20)
    raise RuntimeError(f"Мозг не ответил: {last_err}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--temp", type=float, default=0.2)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("prompt", nargs="*")
    a = p.parse_args()

    if a.prompt:
        prompt = " ".join(a.prompt)
    else:
        prompt = sys.stdin.read()

    if not prompt.strip():
        sys.stderr.write("Пустой промпт.\n")
        sys.exit(2)

    out = ask(prompt, temperature=a.temp, max_tokens=a.max_tokens)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
