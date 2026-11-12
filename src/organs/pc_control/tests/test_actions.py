import pytest

from pc_control import win
from pc_control.actions import vk_of
from pc_control.safety import ControlDisabled, Stopped


def mouse(sent):
    return [i.mi for i in sent if i.type == win.INPUT_MOUSE]


def test_struct_size_matches_win64():
    import ctypes
    assert ctypes.sizeof(win.INPUT) == 40


def test_disabled_by_default_nothing_sent(rig):
    s, c = rig
    assert not s.enabled
    with pytest.raises(ControlDisabled):
        c.click(10, 10)
    with pytest.raises(ControlDisabled):
        c.type("привет")
    assert c.sent == []


def test_click_maps_shot_coordinates_to_absolute(rig):
    s, c = rig
    s.enable()
    c.click(640, 360)                              # centre of a 1280x720 snapshot of a 2560x1440 screen
    m = mouse(c.sent)
    assert m[0].dwFlags & win.MOUSEEVENTF_ABSOLUTE and m[0].dwFlags & win.MOUSEEVENTF_VIRTUALDESK
    assert abs(m[0].dx - round(1280 * 65535 / 2559)) <= 1
    assert abs(m[0].dy - round(720 * 65535 / 1439)) <= 1
    assert [x.dwFlags for x in m[1:]] == [win.MOUSEEVENTF_LEFTDOWN, win.MOUSEEVENTF_LEFTUP]


def test_norm_coordinates_and_double_right(rig):
    s, c = rig
    s.enable()
    c.double_click(1000, 1000, space="norm")
    m = mouse(c.sent)
    assert m[0].dx == 65535 and m[0].dy == 65535
    assert [x.dwFlags for x in m[1:]] == [2, 4, 2, 4]
    c.sent.clear()
    c.right_click(0, 0, space="norm")
    assert [x.dwFlags for x in mouse(c.sent)[1:]] == [win.MOUSEEVENTF_RIGHTDOWN, win.MOUSEEVENTF_RIGHTUP]


def test_drag_always_releases_the_button(rig):
    s, c = rig
    s.enable()
    c.drag(100, 100, 300, 300, steps=4)
    fl = [x.dwFlags for x in mouse(c.sent)]
    assert fl.count(win.MOUSEEVENTF_LEFTDOWN) == 1 and fl[-1] == win.MOUSEEVENTF_LEFTUP


def test_drag_interrupted_by_stop_still_releases(rig):
    s, c = rig
    s.enable()
    calls = {"n": 0}
    orig = c.sender

    def sender(inputs):
        calls["n"] += 1
        if calls["n"] == 4:
            s.disable("test")
        return orig(inputs)
    c.sender = sender
    with pytest.raises(ControlDisabled):
        c.drag(100, 100, 300, 300, steps=10)
    assert mouse(c.sent)[-1].dwFlags == win.MOUSEEVENTF_LEFTUP


def test_scroll_wheel_delta(rig):
    s, c = rig
    s.enable()
    c.scroll(-3)
    m = mouse(c.sent)[0]
    assert m.dwFlags == win.MOUSEEVENTF_WHEEL and m.mouseData == (-360) & 0xFFFFFFFF
    c.sent.clear()
    c.scroll(2, horizontal=True)
    assert mouse(c.sent)[0].dwFlags == win.MOUSEEVENTF_HWHEEL


def test_type_russian_uses_unicode_events(rig):
    s, c = rig
    s.enable()
    c.type("проверка Нейры")
    ks = [i.ki for i in c.sent]
    assert all(k.dwFlags & win.KEYEVENTF_UNICODE for k in ks)
    downs = [k.wScan for k in ks if not k.dwFlags & win.KEYEVENTF_KEYUP]
    assert "".join(map(chr, downs)) == "проверка Нейры"


def test_type_emoji_as_surrogate_pair_and_newline(rig):
    s, c = rig
    s.enable()
    c.type("a😀\n")
    ks = [i.ki for i in c.sent]
    downs = [k for k in ks if not k.dwFlags & win.KEYEVENTF_KEYUP]
    assert [k.wScan for k in downs[:1]] == [ord("a")]
    assert downs[1].wScan == 0xD83D and downs[2].wScan == 0xDE00
    assert downs[3].wVk == 0x0D


def test_hotkey_order_and_release(rig):
    s, c = rig
    s.enable()
    c.hotkey("ctrl", "s")
    ks = [(i.ki.wVk, bool(i.ki.dwFlags & win.KEYEVENTF_KEYUP)) for i in c.sent]
    assert ks == [(0x11, False), (0x53, False), (0x53, True), (0x11, True)]


def test_vk_names():
    assert vk_of("F5") == 0x74 and vk_of("a") == 0x41 and vk_of("7") == 0x37
    with pytest.raises(ValueError):
        vk_of("flurb")


def test_run_queue_cancelled_by_stop(rig):
    s, c = rig
    s.enable()
    plan = [{"do": "click", "x": 10, "y": 10}, {"do": "click", "x": 20, "y": 20}, {"do": "click", "x": 30, "y": 30}]
    done = []
    orig = c.click

    def click(*a, **k):
        orig(*a, **k)
        done.append(1)
        if len(done) == 1:
            s.disable("Pause")
    c.click = click
    with pytest.raises(Exception):
        c.run(plan)
    assert len(done) == 1


def test_run_rejects_unknown_method(rig):
    s, c = rig
    s.enable()
    with pytest.raises(ValueError):
        c.run([{"do": "_begin", "action": {}}])
    with pytest.raises(ValueError):
        c.run([{"do": "see"}])


def test_run_hotkey_args(rig):
    s, c = rig
    s.enable()
    assert c.run([{"do": "hotkey", "keys": ["ctrl", "a"]}]) == 1


def test_actions_are_logged(rig, tmp_path):
    s, c = rig
    s.enable()
    c.click(5, 5)
    text = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert '"event": "enable"' in text and '"type": "click"' in text
