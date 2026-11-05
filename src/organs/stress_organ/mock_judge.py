"""Mock stress judge for one code-path test of the voice server's retake loop: /words always names one word, /judge
says «неверно» on odd calls and «верно» on even ones. fastqwen venv. Usage: python -I mock_judge.py 8095"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

N = [0]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.path.endswith("/words"):
            self._send({"words": [{"w": "года", "expected_form": "гОда", "why": "mock"}]})
        else:
            N[0] += 1
            bad = N[0] % 2
            self._send({"checked": 1, "bad": bad, "words": [{"w": "года", "verdict": "неверно" if bad else "верно",
                                                               "heard_form": "годА" if bad else "гОда",
                                                               "expected_form": "гОда", "q_margin": 9.9}]})


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
