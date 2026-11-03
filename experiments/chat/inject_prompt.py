# -*- coding: utf-8 -*-
"""Запускает C++ клиент и программно вставляет промпт (UTF-8) + Enter."""
import subprocess
import sys
import os

PROMPT = r"D:\AI\neira-tools\saved\sprintf_prompt.txt"
BAT = r"D:\AI\Neira-chat-cpp-inner.bat"
OUT = r"%USERPROFILE%\AppData\Local\Temp\opencode\neira_inject_out.txt"

def main():
    with open(PROMPT, "r", encoding="utf-8") as f:
        prompt = f.read()

    # добавляем завершающий Enter (пустая строка = отправка)
    data = prompt.encode("utf-8") + b"\n"

    proc = subprocess.Popen(
        ["cmd", "/c", BAT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    proc.stdin.write(data)
    proc.stdin.flush()
    proc.stdin.close()

    out, _ = proc.communicate(timeout=1800)
    with open(OUT, "wb") as f:
        f.write(out)

    text = out.decode("utf-8", errors="replace")
    print("exit =", proc.returncode)
    print("bytes =", len(out))
    print("---- первые 2500 ----")
    print(text[:2500])
    print("---- последние 1500 ----")
    print(text[-1500:])

if __name__ == "__main__":
    sys.exit(main())
