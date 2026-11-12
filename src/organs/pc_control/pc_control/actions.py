"""Mouse and keyboard through SendInput. Every action first passes Safety.check and keeps
checking while it runs (Pause aborts mid-way). Coordinates: 'shot' (pixels of the snapshot the
model saw) or 'norm' (0..1000, as Qwen-VL)."""
import time

from . import win
from .capture import Frame, grab
from .safety import Safety

_NAMED = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "pause": 0x13,
}
_EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5B}


def vk_of(name: str) -> int:
    n = name.lower()
    if n in _NAMED:
        return _NAMED[n]
    if len(n) == 1 and n.isalnum() and n.isascii():
        return ord(n.upper())
    if n[0] == "f" and n[1:].isdigit() and 1 <= int(n[1:]) <= 12:
        return 0x70 + int(n[1:]) - 1
    raise ValueError(f"unknown key: {name!r}")


def _kbd(vk, up=False):
    fl = (win.KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0) | (win.KEYEVENTF_KEYUP if up else 0)
    return win.key_input(vk=vk, flags=fl)


def _utf16_units(text):
    b = text.encode("utf-16-le")
    return [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)]


class Controller:
    def __init__(self, safety: Safety, frame: Frame = None, step_delay=0.01, key_delay=0.01):
        self.safety = safety
        self.frame = frame
        self.step_delay, self.key_delay = step_delay, key_delay
        self.sender = win.send_inputs      # tests replace it

    # -- helpers --
    def see(self, **kw):
        """Take a snapshot and remember its frame (coordinates 'shot' refer to the latest one)."""
        shot = grab(**kw)
        self.frame = shot.frame
        self.safety.log("snapshot", frame=vars(shot.frame))
        return shot

    def _frame(self):
        if self.frame is None:
            self.see()
        return self.frame

    def _screen_xy(self, x, y, space):
        f = self._frame()
        if space == "norm":
            return f.norm_to_screen(x, y)
        if space == "shot":
            return f.shot_to_screen(x, y)
        raise ValueError("space must be 'shot' or 'norm'")

    def _abs_move(self, px, py):
        vx, vy, vw, vh = win.virtual_desktop()
        nx = round((px - vx) * 65535 / max(vw - 1, 1))
        ny = round((py - vy) * 65535 / max(vh - 1, 1))
        self.sender([win.mouse_input(nx, ny, win.MOUSEEVENTF_MOVE | win.MOUSEEVENTF_ABSOLUTE
                                     | win.MOUSEEVENTF_VIRTUALDESK)])

    def _begin(self, action):
        self.safety.check(action)
        return self.safety.epoch

    def _tick(self, epoch):
        self.safety.ensure_active(epoch)

    def _done(self, action):
        self.safety.log("action", action=action)

    def _sleep(self, s):
        if s:
            time.sleep(s)

    def _click_at(self, kind, x, y, space, label):
        a = {"type": kind, "x": x, "y": y, "space": space, "label": label}
        ep = self._begin(a)
        px, py = self._screen_xy(x, y, space)
        self._abs_move(px, py)
        self._sleep(self.step_delay)
        self._tick(ep)
        down, up = ((win.MOUSEEVENTF_RIGHTDOWN, win.MOUSEEVENTF_RIGHTUP) if kind == "right_click"
                    else (win.MOUSEEVENTF_LEFTDOWN, win.MOUSEEVENTF_LEFTUP))
        for _ in range(2 if kind == "double_click" else 1):
            self.sender([win.mouse_input(flags=down)])
            self.sender([win.mouse_input(flags=up)])
            self._sleep(self.step_delay)
        self._done(a)

    # -- mouse --
    def move(self, x, y, space="shot"):
        a = {"type": "move", "x": x, "y": y, "space": space}
        self._begin(a)
        self._abs_move(*self._screen_xy(x, y, space))
        self._done(a)

    def click(self, x, y, space="shot", label=None):
        self._click_at("click", x, y, space, label)

    def right_click(self, x, y, space="shot", label=None):
        self._click_at("right_click", x, y, space, label)

    def double_click(self, x, y, space="shot", label=None):
        self._click_at("double_click", x, y, space, label)

    def drag(self, x1, y1, x2, y2, space="shot", steps=12, label=None):
        a = {"type": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "space": space, "label": label}
        ep = self._begin(a)
        (sx, sy), (ex, ey) = self._screen_xy(x1, y1, space), self._screen_xy(x2, y2, space)
        self._abs_move(sx, sy)
        self.sender([win.mouse_input(flags=win.MOUSEEVENTF_LEFTDOWN)])
        try:
            for i in range(1, steps + 1):
                self._tick(ep)
                self._abs_move(round(sx + (ex - sx) * i / steps), round(sy + (ey - sy) * i / steps))
                self._sleep(self.step_delay)
        finally:
            self.sender([win.mouse_input(flags=win.MOUSEEVENTF_LEFTUP)])    # never leave the button held
        self._done(a)

    def scroll(self, clicks, x=None, y=None, space="shot", horizontal=False):
        """clicks > 0: up (or right), < 0: down (or left)."""
        a = {"type": "scroll", "clicks": clicks, "x": x, "y": y, "space": space, "horizontal": horizontal}
        self._begin(a)
        if x is not None and y is not None:
            self._abs_move(*self._screen_xy(x, y, space))
        fl = win.MOUSEEVENTF_HWHEEL if horizontal else win.MOUSEEVENTF_WHEEL
        self.sender([win.mouse_input(flags=fl, data=int(clicks * 120))])
        self._done(a)

    # -- keyboard --
    def type(self, text, label=None):
        """Unicode typing (any language). '\\n' presses Enter."""
        a = {"type": "type", "text": text, "label": label}
        ep = self._begin(a)
        for ch in text:
            self._tick(ep)
            if ch == "\n":
                self.sender([_kbd(0x0D), _kbd(0x0D, up=True)])
            elif ch == "\t":
                self.sender([_kbd(0x09), _kbd(0x09, up=True)])
            else:
                for u in _utf16_units(ch):
                    self.sender([win.key_input(scan=u, flags=win.KEYEVENTF_UNICODE),
                                 win.key_input(scan=u, flags=win.KEYEVENTF_UNICODE | win.KEYEVENTF_KEYUP)])
            self._sleep(self.key_delay)
        self._done({**a, "text": text})

    def hotkey(self, *keys, label=None):
        """hotkey('ctrl', 's'). Modifiers are held in order and always released."""
        a = {"type": "hotkey", "keys": [k.lower() for k in keys], "label": label}
        ep = self._begin(a)
        vks = [vk_of(k) for k in keys]
        pressed = []
        try:
            for vk in vks:
                self._tick(ep)
                self.sender([_kbd(vk)])
                pressed.append(vk)
        finally:
            for vk in reversed(pressed):
                self.sender([_kbd(vk, up=True)])
        self._done(a)

    PUBLIC = ("move", "click", "right_click", "double_click", "drag", "scroll", "type", "hotkey")

    # -- a queue of actions: Pause cancels what is left --
    def run(self, actions):
        """actions: list of dicts {'do': 'click', ...args}. Returns the number executed."""
        n = 0
        ep = self.safety.epoch
        for item in actions:
            self.safety.ensure_active(ep)
            item = dict(item)
            name = item.pop("do")
            if name not in self.PUBLIC:
                raise ValueError(f"unknown action: {name!r}")
            fn = getattr(self, name)
            args = item.pop("keys", None)
            fn(*args, **item) if args is not None else fn(**item)
            n += 1
        return n
