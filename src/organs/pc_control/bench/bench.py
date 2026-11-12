r"""Measure the vision brain against a running llama-server (:8080).
  python -m bench.bench --tag offload0 [--sizes 1024,1280,1600] [--no-coords]
Writes bench\data\results\<tag>\{speed,describe,coords}.json (raw) and prints a summary.
Speed: text-only and image requests (llama-server `timings`), free VRAM before/after, voice port alive.
Describe: reply to "what is on the screen" + recall of facts (window titles / element names from UI Automation).
Coords: the model returns a click point for a named UIA element, in 0-1000 and in image pixels; hit = inside the UIA box."""
import argparse
import base64
import io
import json
import re
import subprocess
import time
from pathlib import Path

import requests
from PIL import Image

DATA = Path(__file__).resolve().parent / "data"
URL = "http://127.0.0.1:8080/v1/chat/completions"
S = requests.Session()
S.trust_env = False


def vram_free():
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free,memory.used", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    f, u = r.stdout.strip().split(",")
    return {"free_mib": int(f), "used_mib": int(u)}


def port_listening(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    return f"127.0.0.1:{port} " in out or f"0.0.0.0:{port} " in out


def b64(img, fmt="JPEG"):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, fmt, quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def resized(path, side):
    im = Image.open(path)
    k = side / max(im.size)
    return im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS) if k < 1 else im


def ask(text, image=None, max_tokens=300):
    content = [{"type": "text", "text": text}]
    if image is not None:
        content.insert(0, {"type": "image_url", "image_url": {"url": b64(image)}})
    t0 = time.time()
    r = S.post(URL, json={"model": "brain", "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens,
                          "temperature": 0.0, "cache_prompt": False}, timeout=600)
    dt = time.time() - t0
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"] or "", j.get("timings", {}), dt, j.get("usage", {})


def norm(s):
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


def recall(reply, facts):
    r = norm(reply)
    hit = [f for f in facts if norm(f) and norm(f) in r]
    return len(hit), len(facts), hit


def facts_of(meta):
    f = [w["name"] for w in meta["windows"][:6]]
    f += [e["name"] for e in meta["elements"] if e["type"] in ("TabItemControl", "MenuItemControl", "ButtonControl")
          and 3 <= len(e["name"]) <= 25][:12]
    seen, out = set(), []
    for x in f:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def parse_point(reply):
    m = re.search(r'"x"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"y"\s*:\s*(-?\d+(?:\.\d+)?)', reply) or \
        re.search(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", reply)
    return (float(m.group(1)), float(m.group(2))) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--sizes", default="1280,1024,1600")
    ap.add_argument("--no-coords", action="store_true")
    ap.add_argument("--describe-size", type=int, default=1280)
    a = ap.parse_args()
    out = DATA / "results" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    scenes = sorted((DATA / "scenes").glob("*.png"))
    assert scenes, "no scenes: run python -m bench.scenes first"
    sizes = [int(x) for x in a.sizes.split(",")]
    voice = lambda: port_listening(8090)

    # ---- speed ----
    speed = {"vram_before": vram_free(), "voice_before": voice(), "text": [], "image": []}
    ask("Ответь одним словом: привет.", max_tokens=8)                                  # warm-up
    for i in range(3):
        txt, tm, dt, us = ask("Расскажи коротко, зачем людям нужен сон.", max_tokens=200)
        speed["text"].append({"wall_s": dt, "tok_s": tm.get("predicted_per_second"), "n": tm.get("predicted_n"),
                              "prompt_ms": tm.get("prompt_ms")})
    for size in sizes:
        img = resized(scenes[0], size)
        for rep in range(2):                      # 1st run encodes, nothing is cached (cache_prompt False)
            txt, tm, dt, us = ask("Что на экране? Ответь одной фразой.", img, max_tokens=60)
            speed["image"].append({"size": size, "img_px": list(img.size), "wall_s": dt, "prompt_n": tm.get("prompt_n"),
                                   "prompt_ms": tm.get("prompt_ms"), "tok_s": tm.get("predicted_per_second"),
                                   "prompt_tokens": us.get("prompt_tokens")})
    speed["vram_after"] = vram_free(); speed["voice_after"] = voice()
    (out / "speed.json").write_text(json.dumps(speed, ensure_ascii=False, indent=1), encoding="utf-8")
    print("speed:", json.dumps(speed, ensure_ascii=False)[:1500])

    # ---- select by number from a text list of UIA elements (no image) ----
    sel = []
    for p in scenes:
        meta = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
        elems = meta["elements"][:300]
        lines = [f'{i + 1}. [{e["type"].replace("Control", "")}] {e["name"]}' for i, e in enumerate(elems)]
        for t in meta["targets"]:
            idx = next((i + 1 for i, e in enumerate(elems) if e["rect"] == t["rect"] and e["name"] == t["name"]), None)
            if idx is None:
                continue
            nl = chr(10)
            q = ("Список видимых элементов окна:" + nl + nl.join(lines) + nl + nl
                 + f'Нужно нажать на элемент «{t["name"]}». Ответь только номером элемента из списка.')
            reply, tm, dt, us = ask(q, None, max_tokens=12)
            m = re.search(r"\d+", reply)
            got = int(m.group(0)) if m else None
            sel.append({"scene": p.stem, "target": t["name"], "want": idx, "got": got, "hit": got == idx, "wall_s": dt,
                        "prompt_tokens": us.get("prompt_tokens"), "n_elems": len(elems), "reply": reply})
            (out / "select.json").write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "select.json").write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    if sel:
        print(f"select by number (text only): {sum(x['hit'] for x in sel)}/{len(sel)} hits, "
              f"mean {sum(x['wall_s'] for x in sel) / len(sel):.1f} s")

    # ---- describe ----
    desc = []
    for p in scenes:
        meta = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
        facts = facts_of(meta)
        reply, tm, dt, _ = ask("Опиши подробно, что открыто на экране: какие окна, программы и какой видимый текст.",
                               resized(p, a.describe_size), max_tokens=400)
        n, tot, hit = recall(reply, facts)
        desc.append({"scene": p.stem, "reply": reply, "facts": facts, "hit": hit, "recall": n / tot if tot else None,
                     "wall_s": dt})
        print(f"describe {p.stem}: recall {n}/{tot}")
        (out / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- coords ----
    if not a.no_coords:
        rows = []
        for size in sizes:
            for p in scenes:
                meta = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
                sw, sh = meta["screen"]
                img = resized(p, size)
                for t in meta["targets"]:
                    l, tp, r, b = t["rect"]
                    row = {"size": size, "scene": p.stem, "target": t["name"], "type": t["type"], "rect": t["rect"]}
                    for mode in ("norm", "px"):
                        if mode == "norm":
                            q = (f'На скриншоте найди элемент «{t["name"]}». Верни точку для клика по его центру в координатах '
                                 'от 0 до 1000 по каждой оси (0,0 — левый верхний угол). Только JSON: {"x": ..., "y": ...}')
                        else:
                            q = (f'Скриншот {img.width}x{img.height} пикселей. Найди элемент «{t["name"]}». Верни точку для клика '
                                 'по его центру в пикселях скриншота. Только JSON: {"x": ..., "y": ...}')
                        reply, _, dt, _ = ask(q, img, max_tokens=40)
                        pt = parse_point(reply)
                        if pt is None:
                            row[mode] = {"reply": reply, "hit": False, "parsed": False}
                            continue
                        x = pt[0] / 1000 * sw if mode == "norm" else pt[0] * sw / img.width
                        y = pt[1] / 1000 * sh if mode == "norm" else pt[1] * sh / img.height
                        cx, cy = (l + r) / 2, (tp + b) / 2
                        row[mode] = {"reply": reply, "parsed": True, "x": x, "y": y, "hit": l <= x <= r and tp <= y <= b,
                                     "err_px": ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5}
                    rows.append(row)
                    (out / "coords.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"coords size {size}: done"); (out / "coords.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "coords.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        for size in sizes:
            for mode in ("norm", "px"):
                rs = [r[mode] for r in rows if r["size"] == size]
                print(f"coords {size} {mode}: {sum(x['hit'] for x in rs)}/{len(rs)} hits")


if __name__ == "__main__":
    main()
