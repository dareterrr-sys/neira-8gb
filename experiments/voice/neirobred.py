"""Нейробред (29.10, the author's find): Russian text with its encoding broken (UTF-8 bytes read as Windows-1251,
«Слушай» -> «РЎР»СѓС€Р°Р№») spoken by Neira's live voice server. No real words, so the model gives everything to
melody, pauses and delivery - her freest manner. Usage: python neirobred.py "текст" [out.wav]
(or a .txt file as the first argument). Output: D:\\AI\\voices\\neirobred\\<time>.wav"""
import json
import os
import sys
import time
import urllib.request

arg = sys.argv[1] if len(sys.argv) > 1 else "Слушай, я тут подумала, пока ты молчал. Это же безумие!"
text = open(arg, encoding="utf-8").read() if os.path.isfile(arg) else arg
broken = text.encode("utf-8").decode("cp1251", errors="replace")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(r"D:\AI\voices\neirobred", time.strftime("%Y%m%d_%H%M%S") + ".wav")
os.makedirs(os.path.dirname(out), exist_ok=True)
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # past a VPN's system proxy
req = urllib.request.Request("http://127.0.0.1:8090/v1/audio/speech",
                             json.dumps({"input": broken, "voice": "neira"}).encode("utf-8"),
                             {"Content-Type": "application/json"})
open(out, "wb").write(op.open(req, timeout=600).read())
print(out)
