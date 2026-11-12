"""Seconds since the last user input (GetLastInputInfo). Our own SendInput also resets it, so
check it BEFORE starting a live test, not during."""
import ctypes
from ctypes import wintypes

from .win import kernel32, user32

LIVE_MIN_IDLE = 300.0


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


kernel32.GetTickCount.restype = wintypes.DWORD


def idle_seconds() -> float:
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise OSError("GetLastInputInfo failed")
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def idle_enough(min_seconds: float = LIVE_MIN_IDLE) -> bool:
    return idle_seconds() >= min_seconds
