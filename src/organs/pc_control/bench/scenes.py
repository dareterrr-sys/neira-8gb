r"""Make the snapshot set (10 scenes) + UIA ground truth.
  python -m bench.scenes --current NAME   capture what is on screen now (no input is sent; safe any time)
  python -m bench.scenes --auto           open the 10 scenes itself (sends input!): only when idle >= 300 s and no game
Output: bench\data\scenes\NN_name.png (full resolution) and NN_name.json (screen size, windows, elements, targets)."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import uiautomation as auto

from pc_control import idle
from pc_control.actions import Controller
from pc_control.capture import grab
from pc_control.safety import Safety
from . import uia_dump

DATA = Path(__file__).resolve().parent / "data"
SCENES = DATA / "scenes"
GAMES = ("wow.exe", "wow-64.exe", "wowclassic.exe", "wowt.exe")


def game_running() -> bool:
    out = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    return any(g in out for g in GAMES)


def capture(name, idx=0, root=None):
    SCENES.mkdir(parents=True, exist_ok=True)
    shot = grab(long_side=0, fmt="png")          # full resolution, no downscale
    fg = root or uia_dump.foreground_window()
    elems = uia_dump.dump(fg)
    if len(elems) < 5:                            # start menu etc.: fall back to the whole desktop
        elems = uia_dump.dump(auto.GetRootControl(), max_elems=600, max_depth=8)
    stem = f"{idx:02d}_{name}"
    shot.image.save(SCENES / f"{stem}.png")
    meta = {"name": name, "screen": [shot.frame.width, shot.frame.height], "windows": uia_dump.top_windows(),
            "foreground": getattr(fg, "Name", ""), "elements": elems, "targets": uia_dump.pick_targets(elems, 3)}
    (SCENES / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{stem}: {len(elems)} elements, {len(meta['targets'])} targets, foreground={meta['foreground']!r}")
    return meta


def _close_window_of(ctrl):
    try:
        ctrl.GetWindowPattern().Close()
    except Exception:
        pass


def auto_scenes():
    assert idle.idle_seconds() >= idle.LIVE_MIN_IDLE, "user is active"
    assert not game_running(), "a game is running"
    s = Safety(indicator=True, log_path=DATA / "scenes_actions.jsonl")
    s.enable()
    c = Controller(s, grab().frame)
    procs = []
    note = DATA / "tmp" / "заметка.txt"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("Список покупок\nмолоко, хлеб, яблоки\nВстреча в четверг в 15:30\n", encoding="utf-8")

    def settle(sec=2.5):
        time.sleep(sec)

    try:
        c.hotkey("win", "d"); settle(1.5); capture("desktop", 1)
        procs.append(subprocess.Popen(["explorer.exe", r"D:\AI"])); settle(3); capture("explorer", 2); _close_window_of(auto.GetForegroundControl())
        p = subprocess.Popen(["notepad.exe", str(note)]); procs.append(p); settle(2); capture("notepad_text", 3)
        # Save dialog: make a change, then Ctrl+S on an untitled document -> Notepad shows "Save as"
        subprocess.run(["taskkill", "/PID", str(p.pid), "/F"], capture_output=True)
        p = subprocess.Popen(["notepad.exe"]); procs.append(p); settle(2)
        c.type("проверка Нейры"); c.hotkey("ctrl", "s"); settle(2); capture("save_dialog", 4)
        c.hotkey("esc"); settle(0.5)
        subprocess.run(["taskkill", "/PID", str(p.pid), "/F"], capture_output=True)
        subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:"], shell=False); settle(4); capture("windows_settings", 5); _close_window_of(auto.GetForegroundControl())
        subprocess.Popen(["cmd", "/c", "start", "", "chrome", "--new-window", "https://ru.wikipedia.org"]); settle(6)
        capture("chrome_site", 6)
        subprocess.Popen(["cmd", "/c", "start", "", "chrome", "--new-window", "https://www.youtube.com"]); settle(7)
        capture("youtube", 7)
        for _ in range(2):                         # close the two Chrome windows we opened (not the user's: they were not there)
            _close_window_of(auto.GetForegroundControl()); settle(1)
        q = auto.WindowControl(searchDepth=1, SubName="Нейра")
        if q.Exists(0, 0):
            q.SetActive(); settle(1); capture("neira_qt", 8, q)
        else:
            print("neira_qt: the Neira window is not open - scene skipped")
        c.hotkey("win"); settle(1.5); capture("start_menu", 9); c.hotkey("esc"); settle(0.5)
        err = subprocess.Popen(["powershell", "-NoProfile", "-Command",
                                "Add-Type -AssemblyName PresentationFramework;"
                                "[void][System.Windows.MessageBox]::Show('Не удалось открыть файл отчёт.docx. Файл повреждён или занят другим процессом.','Ошибка','OK','Error')"])
        procs.append(err); settle(3); capture("error_dialog", 10)
        subprocess.run(["taskkill", "/PID", str(err.pid), "/T", "/F"], capture_output=True)
    finally:
        s.close()
        for p in procs:
            if p.poll() is None and p.args and "explorer" not in str(p.args[0]).lower():
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--current")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--index", type=int, default=0)
    a = ap.parse_args()
    if a.auto:
        auto_scenes()
    elif a.current:
        capture(a.current, a.index)
    else:
        sys.exit(ap.format_help())
