import pytest

from pc_control import safety
from pc_control.safety import (ConfirmationDenied, ControlDisabled, Forbidden, Safety, forbidden_text_reason,
                               hotkey_status, label_is_irreversible, luhn_ok)


def test_luhn():
    assert luhn_ok("4111 1111 1111 1111")
    assert not luhn_ok("4111 1111 1111 1112")
    assert not luhn_ok("12345")


@pytest.mark.parametrize("text", [
    "4111 1111 1111 1111", "карта 4111-1111-1111-1111 срок 12/30", "5500000000000004",
    "cvv 123", "CVC: 4567", "пин-код 1234", "пароль: hunter2", "password=abc123", "Password is qwerty",
])
def test_secret_text_is_forbidden(text):
    assert forbidden_text_reason(text)


@pytest.mark.parametrize("text", [
    "проверка Нейры", "привет, как дела?", "номер заказа 1234567890123", "версия 3.10.22", "пароли надо хранить в менеджере",
    "pin the tab", "2026-11-10 12:30",
])
def test_ordinary_text_is_allowed(text):
    assert forbidden_text_reason(text) is None


def test_hotkeys():
    assert hotkey_status(["ctrl", "s"]) == "ok"
    assert hotkey_status(["Alt", "F4"]) == "irreversible"
    assert hotkey_status(["ctrl", "shift", "delete"]) == "irreversible"
    assert hotkey_status(["win", "l"]) == "banned"
    assert hotkey_status(["pause"]) == "banned"


def test_labels():
    for t in ("Удалить", "Отправить", "Купить сейчас", "Оплатить", "Delete", "Send", "Pay now", "Не сохранять"):
        assert label_is_irreversible(t), t
    for t in ("Открыть", "Отмена", "Назад", None, ""):
        assert not label_is_irreversible(t), t


def test_blocked_card_is_never_typed_and_not_logged(rig, tmp_path):
    s, c = rig
    s.enable()
    with pytest.raises(Forbidden):
        c.type("4111 1111 1111 1111")
    assert c.sent == []
    log = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert "4111" not in log and "<hidden>" in log


def test_password_field_blocks_typing(rig):
    s, c = rig
    s.focus_check = lambda: True
    s.enable()
    with pytest.raises(Forbidden):
        c.type("абвгд")
    assert c.sent == []
    c.hotkey("ctrl", "a")            # only typing is blocked
    assert c.sent


def test_irreversible_needs_confirm_default_denies(rig):
    s, c = rig
    s.enable()
    with pytest.raises(ConfirmationDenied):
        c.click(10, 10, label="Удалить всё")
    with pytest.raises(ConfirmationDenied):
        c.hotkey("alt", "f4")
    assert c.sent == []


def test_irreversible_runs_when_confirmed(rig):
    s, c = rig
    asked = []
    s.confirm = lambda a, r: asked.append((a["type"], r)) or True
    s.enable()
    c.click(10, 10, label="Отправить")
    assert asked and c.sent


def test_pause_during_confirm_cancels(rig):
    s, c = rig

    def confirm(a, r):
        s.disable("Pause")
        return True
    s.confirm = confirm
    s.enable()
    with pytest.raises(Exception):
        c.click(10, 10, label="Оплатить")
    assert c.sent == []


def test_banned_hotkey(rig):
    s, c = rig
    s.enable()
    with pytest.raises(Forbidden):
        c.hotkey("win", "l")


def test_disable_is_instant_and_notifies(rig):
    s, c = rig
    events = []
    s.on_change.append(lambda st, r: events.append((st, r)))
    s.enable()
    s.disable("кнопка")
    assert not s.enabled and events == [(True, "enable"), (False, "кнопка")]
    with pytest.raises(ControlDisabled):
        c.click(1, 1)


def test_enable_refused_without_stop_hotkey(tmp_path, monkeypatch):
    s = Safety(log_path=tmp_path / "l.jsonl", indicator=False, require_hotkey=True)
    monkeypatch.setattr(s, "start_hotkey", lambda: None)       # registration failed
    with pytest.raises(ControlDisabled):
        s.enable()
    assert not s.enabled


def test_confirm_exception_means_deny(rig):
    s, c = rig

    def boom(a, r):
        raise RuntimeError("dialog crashed")
    s.confirm = boom
    s.enable()
    with pytest.raises(ConfirmationDenied):
        c.click(1, 1, label="Купить")


def test_default_confirm_denies():
    assert safety.deny_confirm({}, "x") is False
