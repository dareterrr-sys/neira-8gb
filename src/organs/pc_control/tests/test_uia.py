from pc_control import uia


def el(name, t="ButtonControl", rect=(0, 0, 10, 10), **kw):
    return {"name": name, "type": t, "rect": list(rect), **kw}


def test_select_drops_noise_numbers_from_one():
    raw = [el("Файл"), el(""), el("Файл"), el("пароль", "EditControl", password=True), el("", "EditControl"),
           el("x", "PaneControl"), el("Ещё", rect=(5, 5, 20, 20))]
    out = uia.select(raw)
    assert [e["name"] for e in out] == ["Файл", "", "Ещё"]       # nameless edit field is kept, password one is not
    assert [e["id"] for e in out] == [1, 2, 3]


def test_select_limit_keeps_interactive_first_in_tree_order():
    raw = [el(f"t{i}", "TextControl", rect=(i, 0, i + 5, 5)) for i in range(100)]
    raw.insert(50, el("Кнопка", rect=(500, 0, 510, 5)))
    out = uia.select(raw, limit=10)
    assert len(out) == 10 and any(e["name"] == "Кнопка" for e in out)
    assert [e["id"] for e in out] == list(range(1, 11))


def test_to_text_and_center():
    out = uia.select([el("OK", rect=(0, 0, 100, 40), state="недоступно")])
    assert uia.to_text(out) == '1. кнопка "OK" [недоступно]'
    assert uia.center(out[0]) == (50, 20)


def test_walk_keeps_elements_on_second_monitor():
    """Regression 10.11: the filter used the primary screen size, so windows on a right/left monitor came out empty."""
    from pc_control import uia

    class R:
        def __init__(s, l, t, r, b): s.left, s.top, s.right, s.bottom = l, t, r, b
        def width(s): return s.right - s.left
        def height(s): return s.bottom - s.top

    class Fake:
        ControlTypeName = "ButtonControl"; IsOffscreen = False; IsEnabled = True
        def __init__(s, name, rect, kids=()): s.Name, s.BoundingRectangle, s._k = name, rect, kids
        def GetChildren(s): return list(s._k)

    win = Fake("w", R(2991, 257, 4029, 944), [Fake("Дисплей", R(3000, 300, 3100, 330)), Fake("далеко", R(9000, 1, 9100, 20))])
    out = []
    uia._walk(win, out, bounds=(0, 0, 5120, 1440))
    assert [e["name"] for e in out] == ["w", "Дисплей"]
