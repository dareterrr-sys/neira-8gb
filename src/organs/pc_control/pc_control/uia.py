"""UI Automation as text: a numbered list of the visible elements of a window (role, name, state) for the brain.
Main path of the agent loop (stage 2 measurement: 25/25 choices by number vs 20-28 % by picture)."""
import ctypes

MAX_ELEMS = 80
MAX_NAME = 60

# role -> short Russian-free tag the brain sees
ROLES = {
    "ButtonControl": "кнопка", "EditControl": "поле", "TabItemControl": "вкладка", "MenuItemControl": "пункт меню",
    "ListItemControl": "элемент списка", "CheckBoxControl": "флажок", "RadioButtonControl": "переключатель",
    "ComboBoxControl": "выпадающий список", "HyperlinkControl": "ссылка", "TreeItemControl": "элемент дерева",
    "SplitButtonControl": "кнопка", "DataItemControl": "строка", "TextControl": "текст", "DocumentControl": "документ",
}
# interactive first: when the window is big, these survive the cut
PRIORITY = {"ButtonControl": 0, "EditControl": 0, "TabItemControl": 0, "MenuItemControl": 0, "CheckBoxControl": 0,
            "RadioButtonControl": 0, "ComboBoxControl": 0, "HyperlinkControl": 0, "SplitButtonControl": 0,
            "ListItemControl": 1, "TreeItemControl": 1, "DataItemControl": 1, "DocumentControl": 1, "TextControl": 2}


def screen_size():
    """Bounds of the whole virtual desktop (all monitors): (left, top, right, bottom)."""
    g = ctypes.windll.user32.GetSystemMetrics
    x, y = g(76), g(77)                       # SM_XVIRTUALSCREEN / SM_YVIRTUALSCREEN
    return x, y, x + g(78), y + g(79)         # + SM_CXVIRTUALSCREEN / SM_CYVIRTUALSCREEN


def select(raw, limit=MAX_ELEMS):
    """raw: [{name,type,rect,state?,password?}] in tree order. Drops nameless/duplicated/password fields, keeps the
    interactive ones first when over the limit, returns the list in tree order with 1-based 'id'."""
    seen, kept = set(), []
    for e in raw:
        name = (e.get("name") or "").strip().replace("\n", " ")[:MAX_NAME]
        if e.get("password") or e["type"] not in ROLES:
            continue
        if not name and e["type"] != "EditControl":
            continue
        key = (e["type"], name, tuple(e["rect"]))
        if key in seen:
            continue
        seen.add(key)
        kept.append({**e, "name": name})
    if len(kept) > limit:
        order = sorted(range(len(kept)), key=lambda i: (PRIORITY.get(kept[i]["type"], 3), i))[:limit]
        kept = [kept[i] for i in sorted(order)]
    for i, e in enumerate(kept, 1):
        e["id"] = i
    return kept


def center(e):
    l, t, r, b = e["rect"]
    return (l + r) // 2, (t + b) // 2


def to_text(elems):
    lines = []
    for e in elems:
        st = e.get("state") or ""
        lines.append(f'{e["id"]}. {ROLES.get(e["type"], e["type"])} "{e["name"]}"' + (f" [{st}]" if st else ""))
    return "\n".join(lines)


def _walk(root, out, depth=0, max_depth=14, cap=700, bounds=None):
    if len(out) >= cap or depth > max_depth:
        return
    try:
        r = root.BoundingRectangle
        if root.IsOffscreen or r.width() <= 0 or r.height() <= 0:
            return
        t = root.ControlTypeName
        if t in ROLES and r.right > bounds[0] and r.bottom > bounds[1] and r.left < bounds[2] and r.top < bounds[3]:
            state = []
            try:
                if t == "EditControl":
                    from uiautomation import PropertyId
                    if root.GetPropertyValue(PropertyId.IsPasswordProperty):
                        out.append({"name": "", "type": t, "rect": [r.left, r.top, r.right, r.bottom], "password": True})
                        state = None
                if state is not None and not root.IsEnabled:
                    state.append("недоступно")
            except Exception:
                pass
            if state is not None:
                out.append({"name": root.Name or "", "type": t, "rect": [r.left, r.top, r.right, r.bottom],
                            "state": ",".join(state)})
        for ch in root.GetChildren():
            _walk(ch, out, depth + 1, max_depth, cap, bounds)
    except Exception:
        return


def dump_window(win, cap=700):
    out = []
    _walk(win, out, cap=cap, bounds=screen_size())
    return out


def focused_is_password() -> bool:
    """UIA check for the focused element (covers browsers/Qt, which the Win32 ES_PASSWORD check does not)."""
    try:
        import uiautomation as auto
        from uiautomation import PropertyId
        c = auto.GetFocusedControl()
        return bool(c and c.GetPropertyValue(PropertyId.IsPasswordProperty))
    except Exception:
        return False
