"""Golden: interference tolerance matrix, render CLI (real-Altair benchmark
round 2). (Multi-body FCStd access was removed with the OCCT .brp reader —
ADR-0020.)
"""

from pathlib import Path

import pytest

from gitcad.render import find_browser, render


def test_interference_tolerance_and_matrix(tmp_path):
    from gitcad.kernel.ref import RefKernel
    from gitcad.part.interference import check_interference

    k = RefKernel()
    inst = {"a": (k.box(10, 10, 10), (0.0, 0.0, 0.0), 0.0),
            "b": (k.box(10, 10, 10), (9.9, 0.0, 0.0), 0.0)}   # 0.1x10x10 = 10mm3
    strict = check_interference(k, inst)
    assert not strict.ok
    assert strict.checks["overlaps_mm3"]["a<->b"] == pytest.approx(10.0)
    budget = check_interference(k, inst, tol_mm3=15.0)
    assert budget.ok                                   # within the clash budget
    assert budget.checks["overlaps_mm3"]["a<->b"] == pytest.approx(10.0)  # still shown


def test_interference_says_where_the_overlap_is(tmp_path):
    """A volume alone is not actionable — the report must localize the clash.

    Two 10 mm cubes overlapping by a 0.1 mm slab: the answer a user needs is
    'a thin wall at x 9.9..10', which the bbox says and the float 10.0 does
    not. The common solid is built anyway to measure it; this reads it.
    """
    from gitcad.kernel.ref import RefKernel
    from gitcad.part.interference import check_interference

    k = RefKernel()
    inst = {"a": (k.box(10, 10, 10), (0.0, 0.0, 0.0), 0.0),
            "b": (k.box(10, 10, 10), (9.9, 0.0, 0.0), 0.0)}
    rep = check_interference(k, inst)
    w = rep.checks["overlap_where"]["a<->b"]
    assert w["bbox"] == [[9.9, 0.0, 0.0], [10.0, 10.0, 10.0]]
    assert w["size"] == [pytest.approx(0.1), 10.0, 10.0]
    assert w["centroid"] == [pytest.approx(9.95), 5.0, 5.0]
    # a clear pair contributes nothing: no phantom entries
    clear = check_interference(
        k, {"a": (k.box(10, 10, 10), (0.0, 0.0, 0.0), 0.0),
            "b": (k.box(10, 10, 10), (50.0, 0.0, 0.0), 0.0)})
    assert clear.ok and clear.checks["overlap_where"] == {}


def _sch_file(tmp_path) -> Path:
    from gitcad.ecad.schematic import Pin, SchComponent, Schematic

    sch = Schematic(name="r")
    sch.components = [SchComponent(ref="R1", value="10k",
                                   pins=[Pin("1", "1"), Pin("2", "2")])]
    sch.connect("A", "R1.1")
    sch.connect("B", "R1.2")
    p = tmp_path / "r.sch"
    p.write_text(sch.dumps(), encoding="utf-8")
    return p


def test_render_svg_direct(tmp_path):
    out = render(str(_sch_file(tmp_path)), str(tmp_path / "r.svg"))
    assert Path(out).read_text(encoding="utf-8").startswith("<svg")


@pytest.mark.skipif(find_browser() is None, reason="no local Chrome/Edge")
def test_render_png_via_browser(tmp_path):
    out = render(str(_sch_file(tmp_path)), str(tmp_path / "r.png"),
                 width=640, height=480)
    data = Path(out).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_png_without_browser_is_loud(tmp_path, monkeypatch):
    import gitcad.render as R

    monkeypatch.setattr(R, "find_browser", lambda: None)
    from gitcad.errors import GitcadError

    with pytest.raises(GitcadError, match="Chrome/Edge"):
        R.render(str(_sch_file(tmp_path)), str(tmp_path / "r.png"))


def test_pcba_mesh_has_per_component_groups(tmp_path):
    from gitcad.ecad import Board, Component, Footprint, Pad
    from gitcad.kernel.ref import RefKernel
    from gitcad.viewer.server import pcba_mesh_payload

    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)],
                   courtyard=(2.4, 1.4), height=0.6)
    b = Board(name="x", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [Component("R1", fp, x=5, y=5),
                     Component("C7", fp, x=15, y=5)]
    payload = pcba_mesh_payload(b, RefKernel())
    names = [g["name"] for g in payload["groups"]]
    assert names == ["board", "R1", "C7"]      # cross-probe substrate


def test_client_ships_cross_probe():
    from gitcad.viewer.page import PAGE

    assert "syncSheetHighlight" in PAGE        # 3D -> sheet highlight
    assert 'getElementById("sheets").addEventListener("click"' in PAGE
    assert "applySelection" in PAGE            # select-by-name entry point
