"""UI Automation ground truth: names and rectangles (physical px) of the visible elements of a window."""
import ctypes

import uiautomation as auto

WANT = {"ButtonControl", "EditControl", "TabItemControl", "MenuItemControl", "ListItemControl", "CheckBoxControl",
        "RadioButtonControl", "ComboBoxControl", "HyperlinkControl", "TreeItemControl", "TextControl", "SplitButtonControl",
        "DataItemControl", "DocumentControl"}


def screen_size():
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def foreground_window():
    return auto.GetForegroundControl()


def top_windows():
    """Titles of visible top-level windows (what the model should be able to say is open)."""
    out = []
    for w in auto.GetRootControl().GetChildren():
        try:
            r = w.BoundingRectangle
            if w.Name and r.width() > 50 and r.height() > 50 and not w.IsOffscreen:
                out.append({"name": w.Name, "class": w.ClassName, "rect": [r.left, r.top, r.right, r.bottom]})
        except Exception:
            pass
    return out


def dump(root, max_elems=400, max_depth=12):
    """Visible named elements under root. Returns [{name,type,rect}]."""
    sw, sh = screen_size()
    out = []

    def walk(c, depth):
        if len(out) >= max_elems or depth > max_depth:
            return
        try:
            r = c.BoundingRectangle
            if c.IsOffscreen or r.width() <= 0 or r.height() <= 0:
                return
            t = c.ControlTypeName
            name = (c.Name or "").strip()
            if t in WANT and name and r.right > 0 and r.bottom > 0 and r.left < sw and r.top < sh:
                out.append({"name": name[:80], "type": t, "rect": [r.left, r.top, r.right, r.bottom]})
            for ch in c.GetChildren():
                walk(ch, depth + 1)
        except Exception:
            return
    walk(root, 0)
    return out


def pick_targets(elems, k=3):
    """Deterministic pick of clickable, uniquely named, not tiny elements spread over the window."""
    sw, sh = screen_size()
    names = [e["name"] for e in elems]
    ok = []
    for e in elems:
        l, t, r, b = e["rect"]
        w, h = r - l, b - t
        if (e["type"] in ("ButtonControl", "EditControl", "TabItemControl", "MenuItemControl", "ListItemControl",
                          "CheckBoxControl", "HyperlinkControl", "TreeItemControl", "SplitButtonControl", "ComboBoxControl")
                and 2 <= len(e["name"]) <= 30 and names.count(e["name"]) == 1
                and w >= 16 and h >= 12 and w < sw * 0.6 and h < sh * 0.5
                and l >= 0 and t >= 0 and r <= sw and b <= sh):
            ok.append(e)
    if len(ok) <= k:
        return ok
    step = len(ok) / k
    return [ok[int(i * step + step / 2)] for i in range(k)]
