"""On-screen indicator while control is on: red frame + banner, always on top, click-through,
hidden from screen capture (so the model's snapshots stay clean). Own thread (tkinter)."""
import ctypes
import threading

from .win import set_dpi_aware, user32

TEXT = "Нейра управляет  ·  Pause — стоп"
KEY = "#010203"            # colour key = transparent
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x11


class Indicator:
    def __init__(self, text=TEXT, border=4):
        self.text, self.border = text, border
        self._thread = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self.hwnd = 0
        self.error = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="pc_control-indicator", daemon=True)
        self._thread.start()
        self._ready.wait(3)

    def stop(self):
        self._stop.set()          # the tk loop polls this and destroys its window itself

    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self):
        try:
            import tkinter as tk
            set_dpi_aware()
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg=KEY)
            root.attributes("-transparentcolor", KEY)
            w, h = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{w}x{h}+0+0")
            c = tk.Canvas(root, width=w, height=h, bg=KEY, highlightthickness=0)
            c.pack()
            b = self.border
            c.create_rectangle(b // 2, b // 2, w - b // 2, h - b // 2, outline="#e5322d", width=b)
            cx = w // 2
            c.create_rectangle(cx - 190, b, cx + 190, b + 30, fill="#e5322d", outline="")
            c.create_text(cx, b + 15, text=self.text, fill="white", font=("Segoe UI", 12, "bold"))
            root.update()
            hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
            self.hwnd = hwnd
            user32.GetWindowLongW.restype = ctypes.c_long
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                  ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            self._ready.set()
            while not self._stop.is_set():
                root.update()
                self._stop.wait(0.05)
            root.destroy()
        except Exception as e:      # the indicator must never break control itself
            self.error = repr(e)
        finally:
            self.hwnd = 0
            self._ready.set()
