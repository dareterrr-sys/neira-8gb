import base64
import io

import pytest
from PIL import Image

from pc_control import capture
from pc_control.capture import Frame, make_shot


def test_downscale_keeps_ratio_and_never_upscales():
    big = Image.new("RGB", (2560, 1440))
    small = capture.downscale(big, 1280)
    assert small.size == (1280, 720)
    tiny = Image.new("RGB", (800, 600))
    assert capture.downscale(tiny, 1280).size == (800, 600)


def test_frame_maps_back_to_physical_pixels():
    s = make_shot(Image.new("RGB", (2560, 1440)), left=0, top=0, long_side=1280)
    f = s.frame
    assert (f.img_w, f.img_h, f.scale_x, f.scale_y) == (1280, 720, 2.0, 2.0)
    assert f.shot_to_screen(640, 360) == (1280, 720)
    assert f.shot_to_screen(1280, 720) == (2559, 1439)       # clamped inside the screen


def test_frame_offset_for_second_monitor_and_norm():
    f = Frame(-1920, 0, 1920, 1080, 1280, 720)
    assert f.shot_to_screen(0, 0) == (-1920, 0)
    assert f.norm_to_screen(500, 500) == (-960, 540)


def test_points_outside_are_rejected():
    f = Frame(0, 0, 2560, 1440, 1280, 720)
    with pytest.raises(ValueError):
        f.shot_to_screen(1281, 10)
    with pytest.raises(ValueError):
        f.norm_to_screen(1001, 0)


def test_base64_roundtrip_jpeg_and_png():
    for fmt, mime in (("jpeg", "image/jpeg"), ("png", "image/png")):
        s = make_shot(Image.new("RGB", (400, 200), (10, 200, 30)), 0, 0, fmt=fmt)
        assert s.mime == mime and s.data_url.startswith(f"data:{mime};base64,")
        img = Image.open(io.BytesIO(base64.b64decode(s.b64)))
        assert img.size == (400, 200)


def test_grab_real_screen_smoke():
    """Reading the screen is harmless (no input is sent)."""
    s = capture.grab(long_side=640)
    assert max(s.image.size) <= 640 and s.frame.width >= s.image.width
    assert len(s.data) > 500
