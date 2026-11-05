"""Short live check of the stress judge inside the working voice (R4: minutes). The voice server must run with a config
copy WITHOUT save_dir (voice_config_test.json). Saves the takes the voice chose to runs/judge_live/. fastqwen venv."""
import json
import os
import time
import urllib.request

OUT = r"D:\AI\neira-tools\stress_organ\runs\judge_live"
os.makedirs(OUT, exist_ok=True)
GODA = "С августа две тысячи двадцать первого по сентябрь две тысячи двадцать третьего года."
TEXTS = [GODA] * 5 + ["Она позвонит тебе завтра утром.", "Мне нужно позвонить маме.", "Звонит мама, возьми трубку."]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for i, t in enumerate(TEXTS):
    t0 = time.time()
    body = {"model": "neira", "voice": "refvoice", "input": t, "response_format": "wav"}
    req = urllib.request.Request("http://127.0.0.1:8090/v1/audio/speech", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    data = op.open(req, timeout=300).read()
    open(os.path.join(OUT, f"{i:02d}.wav"), "wb").write(data)
    print(i, f"{time.time() - t0:.1f}s", t[:40], flush=True)
    time.sleep(2.5)   # each one starts a new answer, like Neira's first sentence
