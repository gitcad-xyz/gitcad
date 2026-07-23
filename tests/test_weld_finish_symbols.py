"""Drawing weld + surface-finish symbols (ISO 1302 / 2553)."""

from gitcad.drawing.sheet import Drawing, SurfaceFinish, WeldSymbol


def _sheet():
    return Drawing(sheet="A4", width=120, height=90, scale=1.0, title="t")


def test_surface_finish_renders_tick_and_ra() -> None:
    d = _sheet().surface_finish(20, 55, 3.2, all_around=True)
    assert isinstance(d.surface_finishes[0], SurfaceFinish)
    svg = d.to_svg()
    assert "Ra 3.2" in svg
    assert "<circle" in svg               # all-around ring
    assert svg.count("<path") >= 1        # the tick path


def test_weld_symbol_types_render() -> None:
    d = _sheet()
    d.weld(20, 30, 30, 15, weld="fillet", size=5)
    d.weld(55, 30, 65, 15, weld="vee", size=3)
    d.weld(90, 30, 100, 15, weld="square", size=4)
    assert all(isinstance(w, WeldSymbol) for w in d.welds)
    svg = d.to_svg()
    assert 'fill="black"' in svg          # fillet triangle flag
    assert ">5<" in svg and ">3<" in svg and ">4<" in svg  # sizes


def test_symbols_survive_empty_drawing() -> None:
    assert "<svg" in _sheet().to_svg()    # no symbols → still valid
