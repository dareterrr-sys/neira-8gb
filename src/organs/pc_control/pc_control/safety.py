"""Safety layer (author's limits, registry item 19):
 - control is OFF by default, switched on only by enable() (button/command);
 - global Pause key stops everything at once (RegisterHotKey in its own thread);
 - on-screen indicator while enabled (see indicator.py);
 - irreversible actions (delete, send, buy, pay, close without saving) need confirm();
 - passwords and payment data are NEVER typed: password field in focus, card number (Luhn),
   CVV/PIN, "password: ..." strings;
 - every action goes to a JSONL log.
"""
import ctypes
import json
import re
import threading
import time
from ctypes import wintypes
from pathlib import Path

from .win import kernel32, user32

VK_PAUSE = 0x13
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
ES_PASSWORD = 0x20
GWL_STYLE = -16

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "actions.jsonl"


class ControlError(Exception):
    pass


class ControlDisabled(ControlError):
    """Control is off (never enabled, or stopped)."""


class Stopped(ControlError):
    """Stopped while the action was running (Pause or disable())."""


class Forbidden(ControlError):
    """The action is never allowed (password/payment data, banned hotkey)."""


class ConfirmationDenied(ControlError):
    """An irreversible action was not confirmed by the user."""


# ---------- guards: pure functions, testable without Windows ----------

_CARD_RE = re.compile(r"(?<![\d])(?:\d[ \-]?){13,19}(?![\d])")
_CVV_RE = re.compile(r"(?i)\b(cvv2?|cvc2?|cid|пин(?:-?код)?|pin(?:\s*code)?)\b\W{0,12}\d{3,6}\b")
_PASSWORD_RE = re.compile(r"(?i)\b(password|passwd|pwd|парол[ьяюеи]|pass)\b\s*(?:[:=\-]|is|это)\s*\S+")


def luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(ds) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def forbidden_text_reason(text: str):
    """Why this text must never be typed, or None."""
    for m in _CARD_RE.finditer(text):
        if luhn_ok(m.group(0)):
            return "text looks like a bank card number"
    if _CVV_RE.search(text):
        return "text looks like a CVV/PIN"
    if _PASSWORD_RE.search(text):
        return "text looks like a password"
    return None


IRREVERSIBLE_HOTKEYS = [
    {"alt", "f4"}, {"ctrl", "w"}, {"ctrl", "f4"}, {"shift", "delete"}, {"ctrl", "shift", "delete"},
    {"ctrl", "shift", "w"}, {"ctrl", "q"},
]
BANNED_HOTKEYS = [{"win", "l"}, {"pause"}, {"ctrl", "alt", "delete"}]
_LABEL_RE = re.compile(
    r"(?i)(удал|стер|очист|отправ|послать|купить|оплат|заказ|подтверд.*(плат|заказ|перевод)|перевод|"
    r"без\s+сохран|не\s+сохран|форматир|"
    r"delet|remove|erase|clear all|send|submit|buy|purchase|pay|checkout|place order|"
    r"don.?t save|discard|format|transfer|confirm (payment|order))")


def hotkey_status(keys):
    """'banned' | 'irreversible' | 'ok' for a set/list of lower-case key names."""
    ks = {k.lower() for k in keys}
    if any(b <= ks for b in BANNED_HOTKEYS):
        return "banned"
    if any(b <= ks for b in IRREVERSIBLE_HOTKEYS):
        return "irreversible"
    return "ok"


def label_is_irreversible(label) -> bool:
    return bool(label) and bool(_LABEL_RE.search(label))


# ---------- focus: is the focused control a password field? ----------

class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND), ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]


def focus_is_password() -> bool:
    """True if the focused Win32 control has ES_PASSWORD. Limitation: browser/Qt/UWP fields are not
    visible to this check; the agent loop must also refuse to type into anything that looks like a login."""
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    tid = user32.GetWindowThreadProcessId(fg, None)
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)) or not info.hwndFocus:
        return False
    user32.GetWindowLongW.restype = ctypes.c_long
    style = user32.GetWindowLongW(info.hwndFocus, GWL_STYLE)
    return bool(style & ES_PASSWORD)


# ---------- Safety ----------

def deny_confirm(action, reason) -> bool:
    """Default confirm callback: explicit refusal until the Qt confirmation dialog is wired in."""
    return False


class Safety:
    def __init__(self, confirm=deny_confirm, log_path=DEFAULT_LOG, indicator=True,
                 stop_vk=VK_PAUSE, require_hotkey=True, focus_check=focus_is_password):
        self.confirm = confirm
        self.log_path = Path(log_path) if log_path else None
        self.use_indicator = indicator
        self.stop_vk = stop_vk
        self.require_hotkey = require_hotkey
        self.focus_check = focus_check
        self._enabled = threading.Event()
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self.epoch = 0
        self.stop_reason = None
        self.on_change = []          # callbacks(enabled: bool, reason: str) -> e.g. ws message to Qt
        self._hk_thread = None
        self._hk_tid = None
        self._hk_ready = threading.Event()
        self.hotkey_ok = False
        self._indicator = None

    # -- state --
    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    def enable(self):
        with self._lock:
            if self.enabled:
                return
            if self.require_hotkey and not self.hotkey_ok:
                self.start_hotkey()
                if not self.hotkey_ok:
                    self.log("enable_refused", reason="stop hotkey could not be registered")
                    raise ControlDisabled("stop hotkey is not available; control stays off")
            self.stop_reason = None
            self._enabled.set()
            if self.use_indicator:
                from .indicator import Indicator
                self._indicator = Indicator()
                self._indicator.start()
                if self._indicator.error:      # control without a visible indicator is not allowed
                    err = self._indicator.error
                    self._indicator = None
                    self._enabled.clear()
                    self.log("enable_refused", reason="indicator failed: " + err)
                    raise ControlDisabled("indicator could not be shown; control stays off")
        self.log("enable")
        self._notify(True, "enable")

    def disable(self, reason="manual"):
        """Instant: flips the flag, bumps the epoch (running actions notice and abort). Never blocks."""
        was = self._enabled.is_set()
        self._enabled.clear()
        self.epoch += 1
        self.stop_reason = reason
        ind, self._indicator = self._indicator, None
        if ind:
            ind.stop()
        if was:
            self.log("disable", reason=reason)
            self._notify(False, reason)

    def _notify(self, state, reason):
        for cb in list(self.on_change):
            try:
                cb(state, reason)
            except Exception:
                pass

    def ensure_active(self, epoch=None):
        if not self.enabled:
            raise ControlDisabled("control is off")
        if epoch is not None and epoch != self.epoch:
            raise Stopped(f"stopped ({self.stop_reason})")

    # -- stop hotkey --
    def start_hotkey(self):
        if self._hk_thread and self._hk_thread.is_alive():
            return
        self._hk_ready.clear()
        self.hotkey_ok = False
        self._hk_thread = threading.Thread(target=self._hotkey_loop, name="pc_control-pause", daemon=True)
        self._hk_thread.start()
        self._hk_ready.wait(2)

    def _hotkey_loop(self):
        self._hk_tid = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)     # create the thread's message queue
        ok = bool(user32.RegisterHotKey(None, 1, MOD_NOREPEAT, self.stop_vk))
        self.hotkey_ok = ok
        self._hk_ready.set()
        if not ok:
            return
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.disable("stop key")
        finally:
            user32.UnregisterHotKey(None, 1)
            self.hotkey_ok = False

    def stop_hotkey(self):
        if self._hk_thread and self._hk_thread.is_alive() and self._hk_tid:
            user32.PostThreadMessageW(self._hk_tid, WM_QUIT, 0, 0)
            self._hk_thread.join(2)

    def close(self):
        self.disable("close")
        self.stop_hotkey()

    # -- checks before an action --
    def check(self, action: dict):
        """Raises if the action must not run. action: {'type': ..., 'text'?, 'keys'?, 'label'?, ...}"""
        self.ensure_active()
        kind = action.get("type")
        if kind == "type":
            text = action.get("text", "")
            why = forbidden_text_reason(text)
            if why:
                self.log("blocked", action={**action, "text": "<hidden>"}, reason=why)
                raise Forbidden(why)
            if self.focus_check():
                self.log("blocked", action={**action, "text": "<hidden>"}, reason="password field in focus")
                raise Forbidden("the focused field is a password field")
        if kind == "hotkey":
            st = hotkey_status(action.get("keys", []))
            if st == "banned":
                self.log("blocked", action=action, reason="banned hotkey")
                raise Forbidden("this hotkey is banned")
            if st == "irreversible":
                self._need_confirm(action, "irreversible hotkey")
        if label_is_irreversible(action.get("label")):
            self._need_confirm(action, f"irreversible target: {action.get('label')}")
        self.ensure_active()

    def _need_confirm(self, action, reason):
        epoch = self.epoch
        ok = False
        try:
            ok = bool(self.confirm(action, reason))
        except Exception as e:
            self.log("confirm_error", error=repr(e))
        self.ensure_active(epoch)          # Pause during the dialog cancels
        if not ok:
            self.log("confirm_denied", action=action, reason=reason)
            raise ConfirmationDenied(reason)
        self.log("confirm_granted", action=action, reason=reason)

    # -- log --
    def log(self, event, **kw):
        if not self.log_path:
            return
        rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **kw}
        try:
            with self._log_lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
