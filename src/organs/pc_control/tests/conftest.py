import pytest

from pc_control import win
from pc_control.actions import Controller
from pc_control.capture import Frame
from pc_control.safety import Safety


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """Safety + Controller with a fake SendInput: the real cursor/keyboard are never touched."""
    monkeypatch.setattr(win, "virtual_desktop", lambda: (0, 0, 2560, 1440))
    sent = []
    s = Safety(confirm=lambda a, r: False, log_path=tmp_path / "log.jsonl", indicator=False,
               require_hotkey=False, focus_check=lambda: False)
    c = Controller(s, Frame(0, 0, 2560, 1440, 1280, 720), step_delay=0, key_delay=0)
    c.sender = lambda inputs: sent.extend(list(inputs)) or len(list(inputs))
    c.sent = sent
    return s, c
