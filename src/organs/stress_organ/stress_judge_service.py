"""Stress judge for Neira's live voice (author, 04.11.2026: «Да, делай судьёй»; register item 10).

The voice server asks it about a take: was the stress right in the words that have a NORM (FIPI 2026, or the
«года» class by OpenCorpora morphology - stress_text.py)? Only the О/А vowel contrast decides (stress_organ.py,
O_ONLY). A take with a wrong stress is retaken by the voice server, like a take with wrong words.
CPU only, no VRAM. Text half: stress_text.py --serve in the russkiy venv (one process, kept alive).

  GET  /health -> ok (after the phoneme model is loaded)
  POST /words  {"text"}                     -> {"words": [{"w", "expected_form", "why"}]}  words with a norm
  POST /judge  {"text", "sr", "pcm16"(b64)} -> {"checked": n, "bad": k, "words": [{"w", "verdict", "heard_form",
                                                "expected_form", "q_margin"}], "ms": ...}
Sentences with Latin letters or digits are not judged (their sounds cannot be aligned): checked = 0.
Usage (fastqwen venv): python -I stress_judge_service.py [port=8094]
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("STRESS_THREADS", "4")   # the brain's CPU experts and the voice judges share the CPU
import numpy as np  # noqa: E402

import stress_organ as so  # noqa: E402  (sets TMP / HF_HOME to D:)

LOCK = threading.Lock()
SKIP_RE = re.compile(r"[A-Za-z0-9]")


class TextWorker:
    def __init__(self):
        self.p = subprocess.Popen([so.RUSSKIY_PY, os.path.join(HERE, "stress_text.py"), "--serve"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        ready = self.p.stdout.readline()
        if "ready" not in ready:
            raise RuntimeError("stress_text worker: " + ready)

    def analyse(self, text):
        self.p.stdin.write(json.dumps([text], ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        out = json.loads(self.p.stdout.readline())
        if isinstance(out, dict):
            raise RuntimeError(out.get("error"))
        return out[0]


WORKER = None


def normed(info):
    return [w for w in info["words"] if w["check"] and w["expected"] is not None]


def words(text):
    if SKIP_RE.search(text):
        return []
    with LOCK:
        info = WORKER.analyse(text)
    return [{"w": w["w"], "expected_form": so.stressed(w["w"], w["expected"]), "why": w["why"]} for w in normed(info)]


def judge(text, sr, pcm16):
    t = time.time()
    if SKIP_RE.search(text):
        return {"checked": 0, "bad": 0, "words": [], "skipped": "latin/digits", "ms": 0}
    with LOCK:
        info = WORKER.analyse(text)
        if not normed(info):
            return {"checked": 0, "bad": 0, "words": [], "ms": round((time.time() - t) * 1000)}
        a = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if sr != 16000:
            import librosa
            a = librosa.resample(a, orig_sr=sr, target_sr=16000)
        res = so.check_audio(a.astype(np.float32), info, use_vosk=False, only_norm=True)
    out = [{"w": r["word"], "verdict": r["verdict"], "heard_form": r.get("heard_form"),
            "expected_form": r.get("expected_form"), "q_margin": r.get("q_margin")} for r in res]
    return {"checked": len(out), "bad": sum(r["verdict"] == "неверно" for r in out), "words": out,
            "ms": round((time.time() - t) * 1000)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
            if self.path.endswith("/words"):
                self._send(200, {"words": words(req.get("text", ""))})
            elif self.path.endswith("/judge"):
                self._send(200, judge(req.get("text", ""), int(req.get("sr", 24000)), base64.b64decode(req["pcm16"])))
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:   # the voice server then keeps the take as it is
            self._send(500, {"error": repr(e)})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8094
    t = time.time()
    WORKER = TextWorker()
    so.phone_model()
    so.emissions(np.zeros(16000, dtype=np.float32))   # warm-up: the first real take does not pay for it
    print(f"stress judge ready in {time.time() - t:.0f}s on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
