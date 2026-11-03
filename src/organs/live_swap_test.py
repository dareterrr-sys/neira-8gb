"""Live check of the voice swap (28.10): one hard turn through Neira's own websocket, as her page sends it. Prints
each message type with its time; audio payloads are counted, not played. Usage: python live_swap_test.py [file]"""
import asyncio
import json
import sys
import time

import websockets

TASK = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else (
    "Задание 9 ЕГЭ по русскому. Укажите варианты ответов, в которых во всех словах одного ряда пропущена одна и та "
    "же буква. Запишите номера ответов. 1) з..ря, прил..гательное, г..ревать; 2) р..стовщик, выр..щенный, р..сток; "
    "3) обл..котиться, ст..листический, ап..теоз; 4) в..ршина, ск..чок, заг..рать; 5) пл..вчиха, р..внина, к..снуться. "
    "Объясни коротко.")


async def main():
    async with websockets.connect("ws://localhost:12393/client-ws", max_size=None) as ws:
        t0 = time.time()
        await ws.send(json.dumps({"type": "text-input", "text": TASK}))
        audio = 0
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=240)
            except asyncio.TimeoutError:
                print("no messages for 240 s")
                break
            m = json.loads(raw)
            ty = m.get("type")
            t = time.time() - t0
            if ty == "audio":
                audio += 1
                text = (m.get("display_text") or {}).get("text", "")
                print(f"{t:6.1f} s  audio #{audio} ({len(m.get('audio') or '') // 1000} kB b64): {text[:100]!r}", flush=True)
            elif ty in ("full-text", "control", "conversation-chain-end", "backend-synth-complete"):
                print(f"{t:6.1f} s  {ty} {str(m.get('text', ''))[:80]!r}", flush=True)
                if ty == "control" and m.get("text") == "conversation-chain-end":
                    break
            if ty == "backend-synth-complete":
                await ws.send(json.dumps({"type": "frontend-playback-complete"}))


asyncio.run(main())
