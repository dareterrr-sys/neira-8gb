"""Контраст текстовых токенов Theme.qml на фонах (WCAG, порог 4.5:1). Запуск: python -I contrast.py"""
import re, sys, pathlib

src = pathlib.Path(__file__).resolve().parent.parent.joinpath("qml", "Theme.qml").read_text(encoding="utf-8")
tok = dict(re.findall(r'property color (\w+):\s*"(#[0-9A-Fa-f]{6})"', src))

def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

bad = 0
for fg in ("text", "text2", "text3", "text4", "accent", "lav", "gold", "ok", "warn", "bad"):
    for bg in ("bg", "rail", "panel", "raised", "field"):
        r = ratio(tok[fg], tok[bg])
        flag = "" if r >= 4.5 else "  <-- НИЖЕ 4.5"
        bad += r < 4.5
        print(f"{fg:6} на {bg:6} {r:5.2f}{flag}")
for bg in ("accent", "accentHi", "lav", "gold"):
    r = ratio(tok["accentText"], tok[bg])
    bad += r < 4.5
    print(f"accentText на {bg}: {r:.2f}")
print("НАРУШЕНИЙ:", bad)
sys.exit(1 if bad else 0)
