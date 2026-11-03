"""Warm Neira's brain up right after it starts. One long throwaway prompt makes llama-server pull the model's experts
from disk into RAM and get its GPU kernels going, so her first real answer doesn't pay for that
(measured with the voice loaded: a 3.7k-token first prompt takes ~23 s cold and ~5 s warm).
Started in the background by D:\\AI\\Neira-start.bat. Usage: python warm_brain.py [tokens=3000]
"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8080"
MODEL = r"D:\AI\gguf\qwen36\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"   # brain v40 (was the old Qwen3-VL file until 29.10)
TEXTS = [
    "Слушай, я тут подумала: может, сначала разберёмся с видеокартой, а потом уже будем ставить новую игру? "
    "Серьёзно, ты потратил всю ночь на то, чтобы настроить обои в редакторе кода? Ладно, признаю, это было умно.",
    "Свет солнца — это смесь волн разной длины. Короткие синие волны рассеиваются в атмосфере сильнее красных, "
    "поэтому днём небо голубое, а на закате красноватое. Сила трения почти не зависит от площади соприкосновения.",
    "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n"
    "for (int i = 0; i < n; i++) { sum += arr[i] * 2; } printf(\"%d\\n\", sum);",
    "The quick brown fox jumps over the lazy dog. Memory, reminders and notes are stored in a knowledge graph; "
    "entities, relations and observations can be searched and opened by name.",
    "Сегодня пятнадцатое октября, на улице семь градусов, вечером обещают дождь. 2 + 2 = 4, 17 * 3 = 51, "
    "а в таблице сорок два, хотя в отчёте почему-то тридцать семь. Майнкрафт, сапёр, шахматы, аниме, музыка.",
    "Не переживай так. Всё получится, просто выспись нормально. Знаешь, иногда мне кажется, что ты разговариваешь "
    "со мной чаще, чем с людьми. Хмф. Глупости, мне вообще ничего не угрожает. Ха-ха, ты опять проиграл?",
]


def post(path, body, timeout=900):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    for _ in range(200):  # the brain may still be loading
        try:
            if urllib.request.urlopen(URL + "/health", timeout=2).status == 200:
                break
        except Exception:
            pass
        time.sleep(3)
    t0 = time.time()
    with open(MODEL, "rb") as f:  # the whole file into the OS cache: experts no prompt touched yet load fast too
        while f.read(64 << 20):
            pass
    print(f"model file read in {time.time() - t0:.0f} s", flush=True)
    block = "\n\n".join(TEXTS) + "\n\n"
    prompt = block * max(1, want // len(post("/tokenize", {"content": block})["tokens"]))
    t0 = time.time()
    r = post("/completion", {"prompt": prompt, "n_predict": 1, "cache_prompt": False})
    print(f"brain warmed up: {r['timings']['prompt_n']} tokens in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
