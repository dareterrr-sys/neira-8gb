"""pc_control_organ: commands, action parsing, open whitelist, agent loop with a fake brain, confirmation card."""
import asyncio
import importlib.util
import threading
import time

import pytest

spec = importlib.util.spec_from_file_location("pc_control_organ", r"D:\AI\neira-tools\pc_control_organ.py")
organ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(organ)


def test_parse_command():
    p = organ.parse_command
    assert p("включи управление", False) == ("enable",)
    assert p("Нейра, включи управление компьютером", False) == ("enable",)
    assert p("выключи управление", True) == ("disable",)
    assert p("посмотри на экран", False) == ("look",)
    assert p("Что у меня на экране?", False) == ("look",)
    assert p("открой Блокнот и набери привет", True) == ("task", "открой Блокнот и набери привет")
    assert p("В окне Chrome открой сайт wikipedia.org", True)[0] == "task"
    assert p("открой Блокнот", False) is None           # tasks only while control is on
    assert p("расскажи анекдот", True) is None
    assert p("", True) is None


def test_parse_action():
    assert organ.parse_action('{"kind":"click","id":3}') == {"kind": "click", "id": 3}
    assert organ.parse_action('Хорошо:\n```json\n{"kind":"type","text":"a}b","id":2}\n```') == \
        {"kind": "type", "text": "a}b", "id": 2}
    assert organ.parse_action("не json") is None
    assert organ.parse_action('{"done": true, "say": "ok"}')["done"] is True


def test_check_open():
    c = organ.check_open
    assert c("notepad") == "notepad"
    assert c("Notepad.exe") == "notepad"
    assert c(r"explorer D:\AI") == r"explorer D:\AI"
    assert c("chrome https://ru.wikipedia.org") == "chrome https://ru.wikipedia.org"
    assert c("ms-settings:display") == "ms-settings:display"
    for bad in ("cmd /c del x", "powershell", "notepad & calc", r"explorer D:\a & del", "chrome file:///c:/x",
                "format c:", r"explorer ..\x", r"notepad C:\x.txt"):
        assert c(bad) is None, bad


def make_view(titles):
    state = {"i": 0}
    def view():
        i = min(state["i"], len(titles) - 1)
        state["i"] += 1
        elems = titles[i]
        text = "\n".join(f'{e["id"]}. кнопка "{e["name"]}"' for e in elems)
        return "Окно", elems, text, lambda: "data:image/jpeg;base64,AAAA"
    return view


E = lambda n, name: {"id": n, "name": name, "type": "ButtonControl", "rect": [0, 0, 10, 10]}
MANY = [E(i, f"b{i}") for i in range(1, 8)]


def run(replies, view=None, execute=None, **kw):
    it = iter(replies)
    seen = []
    def ask(msgs, img):
        seen.append((msgs, img))
        return next(it)
    done = []
    res = organ.agent_loop("задача", ask, view or make_view([MANY]), execute or (lambda a, e: "сделала"),
                           emit=lambda k, d: done.append((k, d)), sleep=lambda s: None, **kw)
    return res, done, seen


def test_loop_done_after_actions():
    (ok, text), done, seen = run(['{"kind":"click","id":2}', '{"kind":"key","keys":"ctrl+s"}',
                                  '{"done":true,"say":"Готово"}'])
    assert ok and text == "Готово"
    assert [k for k, _ in done] == ["click", "key"]
    assert seen[0][1] is None                        # 7 elements: no picture
    assert "Элементы окна" in seen[0][0][1]["content"] and "b2" in seen[0][0][1]["content"]
    assert "1) сделала" in seen[2][0][1]["content"]  # history reaches the next step


def test_loop_picture_only_when_few_elements():
    (ok, _), _, seen = run(['{"kind":"wait"}', '{"done":true}'], view=make_view([[E(1, "x")], MANY]))
    assert seen[0][1] and seen[0][1].startswith("data:image")
    assert seen[1][1] is None


def test_loop_step_limit_and_stuck():
    (ok, text), _, _ = run(['{"kind":"click","id":%d}' % (i % 7 + 1) for i in range(30)], max_steps=5)
    assert not ok and "5 шагов" in text
    (ok, text), _, _ = run(['{"kind":"click","id":1}'] * 5)
    assert not ok and "Зациклилась" in text


def test_loop_time_limit():
    t = [0.0]
    def now():
        t[0] += 200
        return t[0]
    (ok, text), _, _ = run(['{"kind":"wait"}'] * 5, now=now)
    assert not ok and "Не успела" in text


def test_loop_unparsed_reply_recovers_then_gives_up():
    (ok, text), _, _ = run(["бла", '{"done":true,"say":"ok"}'])
    assert ok and text == "ok"
    (ok, text), _, _ = run(["бла", "бла", "бла"])
    assert not ok and "разобрать" in text


@pytest.mark.parametrize("cls,frag", [("Stopped", "Остановлено"), ("ConfirmationDenied", "не разрешил"),
                                      ("Forbidden", "делать не буду")])
def test_loop_safety_errors_end_task(cls, frag):
    E_ = type(cls, (Exception,), {})
    def execute(a, e):
        raise E_("причина")
    (ok, text), done, _ = run(['{"kind":"click","id":1}'], execute=execute)
    assert not ok and frag in text and not done


def test_loop_bad_id_goes_back_to_brain():
    calls = []
    def execute(a, e):
        if a.get("id") == 99:
            raise ValueError("нет элемента №99")
        calls.append(a)
        return "ok"
    (ok, text), _, seen = run(['{"kind":"click","id":99}', '{"kind":"click","id":1}', '{"done":true}'], execute=execute)
    assert ok and calls and "не вышло" in seen[1][0][1]["content"]


def test_loop_ensure_active_stops():
    def ensure():
        raise type("Stopped", (Exception,), {})("pause")
    with pytest.raises(Exception):
        run(['{"done":true}'], ensure_active=ensure)


# ---- Organ (Windows objects, but nothing is enabled: no input, no indicator) ----

@pytest.fixture
def org(tmp_path):
    o = organ.Organ(ask=lambda m, i=None: "", log_path=tmp_path / "a.jsonl")
    yield o
    o.safety.close()


def test_confirm_card_answer_and_timeout(org, monkeypatch):
    sent = []
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    async def send(m):
        sent.append(m)
    org.bind(send, loop)
    org.safety._enabled.set()

    def answer():
        while not sent:
            time.sleep(0.02)
        time.sleep(0.05)
        org.handle_confirm(sent[0]["id"], True)
    threading.Thread(target=answer).start()
    assert org._confirm({"type": "hotkey", "keys": ["alt", "f4"]}, "irreversible hotkey") is True
    assert sent[0]["type"] == "pc-control-confirm-request" and "alt+f4" in sent[0]["action"]

    monkeypatch.setattr(organ, "CONFIRM_TIMEOUT", 0.3)
    assert org._confirm({"type": "hotkey", "keys": ["alt", "f4"]}, "x") is False      # timeout = refusal
    org.safety._enabled.clear()
    loop.call_soon_threadsafe(loop.stop)


def test_pause_during_confirm_refuses(org):
    org.safety._enabled.set()
    threading.Timer(0.2, lambda: org.safety.disable("stop key")).start()
    assert org._confirm({"type": "hotkey", "keys": ["alt", "f4"]}, "x") is False


def test_enable_refused_when_game_runs(org, monkeypatch):
    monkeypatch.setattr(organ, "running_games", lambda: ["wow.exe"])
    sent = []
    async def send(m):
        sent.append(m)
    org.bind(send, None)
    assert asyncio.run(org.handle_enable()) is False
    assert sent[-1]["enabled"] is False and "wow.exe" in sent[-1]["reason"]
    assert not org.safety.enabled


def test_execute_rejects_unlisted_open_and_unknown(org):
    with pytest.raises(ValueError):
        org._execute({"kind": "open", "text": "cmd /c calc"}, [])
    with pytest.raises(ValueError):
        org._execute({"kind": "fly"}, [])
    with pytest.raises(ValueError):
        org._execute({"kind": "click", "id": 5}, [])


def test_loop_waits_are_not_a_loop():
    (ok, text), _, _ = run(['{"kind":"wait"}'] * 5 + ['{"done":true,"say":"ok"}'])
    assert ok and text == "ok"                        # slow window: five waits are fine
    (ok, text), _, _ = run(['{"kind":"wait"}'] * 8)
    assert not ok and "Зациклилась" in text


def test_type_into_edit_selects_old_text(org, monkeypatch):
    calls = []
    org.ctrl = type("C", (), {"click": lambda self, *a, **k: calls.append("click"),
                              "hotkey": lambda self, *k: calls.append("+".join(k)),
                              "type": lambda self, t: calls.append("type:" + t)})()
    org.uia = type("U", (), {"center": staticmethod(lambda e: (5, 5))})()
    org._win = type("W", (), {"virtual_desktop": staticmethod(lambda: (0, 0, 100, 100))})()
    e = {"id": 1, "name": "Адрес", "type": "EditControl", "rect": [0, 0, 10, 10]}
    org._execute({"kind": "type", "id": 1, "text": "x"}, [e])
    assert calls == ["click", "ctrl+a", "type:x"]
