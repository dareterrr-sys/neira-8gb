"""Reading speed of a long prompt (~2.9k tokens of Neira's config text, cold: no prompt cache) and writing speed.
Usage: python long_read.py <port>"""
import json
import sys
import urllib.request

port = sys.argv[1]
base = open(r"D:\AI\Open-LLM-VTuber\conf.yaml", encoding="utf-8").read()[:9000]
for i in range(2):
    body = {"prompt": base + f"\n#{i}", "n_predict": 60, "temperature": 0, "cache_prompt": False}
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"http://127.0.0.1:{port}/completion", json.dumps(body).encode(), {"Content-Type": "application/json"}),
        timeout=900).read())
    t = r["timings"]
    print(f"   read {t['prompt_n']} tok at {t['prompt_per_second']:.0f} tok/s ({t['prompt_ms'] / 1000:.1f} s), "
          f"write {t['predicted_per_second']:.1f} tok/s", flush=True)
