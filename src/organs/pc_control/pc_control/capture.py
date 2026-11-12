"""Screen capture: DPI-aware, downscaled to a long side N, with factors to map coordinates back."""
import base64
import io
from dataclasses import dataclass

import mss
from PIL import Image

from .win import set_dpi_aware

DEFAULT_LONG_SIDE = 1280


@dataclass(frozen=True)
class Frame:
    """Region of the physical screen that a snapshot shows, plus the snapshot size."""
    left: int
    top: int
    width: int      # region size in physical pixels
    height: int
    img_w: int      # snapshot size the model sees
    img_h: int

    @property
    def scale_x(self) -> float:
        return self.width / self.img_w

    @property
    def scale_y(self) -> float:
        return self.height / self.img_h

    def shot_to_screen(self, x: float, y: float):
        """Coordinates in the snapshot -> physical screen pixels."""
        if not (0 <= x <= self.img_w and 0 <= y <= self.img_h):
            raise ValueError(f"point ({x}, {y}) is outside the snapshot {self.img_w}x{self.img_h}")
        return (self.left + min(round(x * self.scale_x), self.width - 1),
                self.top + min(round(y * self.scale_y), self.height - 1))

    def norm_to_screen(self, x: float, y: float):
        """Normalised 0..1000 (as Qwen-VL) -> physical screen pixels."""
        if not (0 <= x <= 1000 and 0 <= y <= 1000):
            raise ValueError(f"normalised point ({x}, {y}) is outside 0..1000")
        return (self.left + min(round(x / 1000 * self.width), self.width - 1),
                self.top + min(round(y / 1000 * self.height), self.height - 1))


@dataclass
class Shot:
    image: Image.Image
    frame: Frame
    fmt: str
    data: bytes

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @property
    def mime(self) -> str:
        return "image/jpeg" if self.fmt == "jpeg" else "image/png"

    @property
    def data_url(self) -> str:
        return f"data:{self.mime};base64,{self.b64}"


def list_monitors():
    with mss.mss() as s:
        return [dict(m) for m in s.monitors]   # [0] = all monitors, [1:] = each


def _pick(monitors, which):
    if which == "all":
        return monitors[0]
    if which == "primary":
        for m in monitors[1:]:
            if m["left"] == 0 and m["top"] == 0:
                return m
        return monitors[1]
    if isinstance(which, int) and 1 <= which < len(monitors):
        return monitors[which]
    raise ValueError(f"unknown monitor: {which!r} (have 1..{len(monitors) - 1}, 'primary', 'all')")


def downscale(img: Image.Image, long_side: int = DEFAULT_LONG_SIDE) -> Image.Image:
    w, h = img.size
    if long_side <= 0 or max(w, h) <= long_side:
        return img
    k = long_side / max(w, h)
    return img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)


def encode(img: Image.Image, fmt: str = "jpeg", quality: int = 85) -> bytes:
    buf = io.BytesIO()
    if fmt == "jpeg":
        img.convert("RGB").save(buf, "JPEG", quality=quality)
    elif fmt == "png":
        img.save(buf, "PNG")
    else:
        raise ValueError("fmt must be 'jpeg' or 'png'")
    return buf.getvalue()


def make_shot(raw: Image.Image, left: int, top: int, long_side=DEFAULT_LONG_SIDE, fmt="jpeg", quality=85) -> Shot:
    small = downscale(raw, long_side)
    frame = Frame(left, top, raw.width, raw.height, small.width, small.height)
    return Shot(small, frame, fmt, encode(small, fmt, quality))


def grab(monitor="primary", long_side: int = DEFAULT_LONG_SIDE, fmt: str = "jpeg", quality: int = 85) -> Shot:
    """Snapshot of the primary monitor (default), a monitor number, or 'all'."""
    set_dpi_aware()
    with mss.mss() as s:
        m = _pick(s.monitors, monitor)
        px = s.grab(m)
        raw = Image.frombytes("RGB", px.size, px.bgra, "raw", "BGRX")
    return make_shot(raw, m["left"], m["top"], long_side, fmt, quality)
