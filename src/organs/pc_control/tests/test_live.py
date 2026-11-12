"""Live tests: the real cursor and keyboard. Skipped unless the user has been idle for >= 300 s.
Idle is measured once at import (our own input resets GetLastInputInfo)."""
import ctypes
import subprocess
import time
from ctypes import wintypes

import pytest

from pc_control import idle, win
from pc_control.actions import Controller
from pc_control.capture import grab
from pc_control.safety import Safety

IDLE_AT_START = idle.idle_seconds()
live = pytest.mark.skipif(IDLE_AT_START < idle.LIVE_MIN_IDLE,
                          reason=f"skipped: user is active (idle {IDLE_AT_START:.0f} s < 300 s)")
user32 = win.user32


def _notepad_edit_text(pid):
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    for top in found:
        edit = user32.FindWindowExW(top, None, "Edit", None)
        if edit:
            buf = ctypes.create_unicode_buffer(256)
            user32.SendMessageW(edit, 0x000D, 256, buf)       # WM_GETTEXT
            return top, buf.value
    return (found[0] if found else None), None


def test_idle_is_measurable():
    assert 0 <= idle.idle_seconds() < 10 * 365 * 86400


@live
def test_cursor_square_and_back(tmp_path):
    s = Safety(log_path=tmp_path / "l.jsonl", indicator=True)
    s.enable()
    try:
        c = Controller(s, grab(long_side=1280).frame, step_delay=0.02)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x0, y0 = pt.x, pt.y
        for nx, ny in ((200, 200), (400, 200), (400, 400), (200, 400), (200, 200)):
            c.move(nx, ny, space="norm")
            time.sleep(0.15)
        win.set_dpi_aware()
        user32.GetCursorPos(ctypes.byref(pt))
        want = c.frame.norm_to_screen(200, 200)
        assert abs(pt.x - want[0]) <= 2 and abs(pt.y - want[1]) <= 2
        user32.SetCursorPos(x0, y0)
    finally:
        s.close()


@live
def test_notepad_types_russian(tmp_path):
    s = Safety(log_path=tmp_path / "l.jsonl", indicator=True)
    s.enable()
    proc = subprocess.Popen(["notepad.exe"])
    try:
        time.sleep(1.5)
        top, _ = _notepad_edit_text(proc.pid)
        assert top, "Notepad window not found"
        user32.SetForegroundWindow(top)
        time.sleep(0.4)
        c = Controller(s, grab().frame)
        c.type("проверка Нейры")
        time.sleep(0.4)
        _, text = _notepad_edit_text(proc.pid)
        assert text == "проверка Нейры"
    finally:
        s.close()
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


@live
def test_pause_key_stops_control(tmp_path):
    s = Safety(log_path=tmp_path / "l.jsonl", indicator=False)
    s.enable()
    try:
        assert s.hotkey_ok
        user32.keybd_event(0x13, 0, 0, 0)
        user32.keybd_event(0x13, 0, 2, 0)
        for _ in range(40):
            if not s.enabled:
                break
            time.sleep(0.05)
        assert not s.enabled and s.stop_reason == "stop key"
    finally:
        s.close()


@live
def test_indicator_is_click_through_and_hidden_from_capture():
    from pc_control.indicator import (GWL_EXSTYLE, Indicator, WS_EX_LAYERED, WS_EX_TRANSPARENT)
    ind = Indicator()
    ind.start()
    try:
        assert ind.error is None and ind.hwnd
        user32.GetWindowLongW.restype = ctypes.c_long
        ex = user32.GetWindowLongW(ind.hwnd, GWL_EXSTYLE)
        assert ex & WS_EX_TRANSPARENT and ex & WS_EX_LAYERED
        aff = wintypes.DWORD()
        assert user32.GetWindowDisplayAffinity(ind.hwnd, ctypes.byref(aff)) and aff.value == 0x11
    finally:
        ind.stop()
        time.sleep(0.3)
    assert not ind.alive()
