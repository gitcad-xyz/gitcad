"""Golden: multi-body FCStd access, interference tolerance matrix,
render CLI (real-Altair benchmark round 2).
"""

from pathlib import Path

import pytest

from gitcad.render import find_browser, render


def _fcstd(tmp_path) -> Path:
    """A synthetic two-body FCStd (zip with two .Shape.brp members)."""
    import zipfile

    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    a = tmp_path / "a.brep"
    b = tmp_path / "b.brep"
    k.export_brep(k.box(10, 10, 10), str(a))
    k.export_brep(k.transform(k.box(5, 5, 5), translate=(20, 0, 0)), str(b))
    f = tmp_path / "two.FCStd"
    with zipfile.ZipFile(f, "w") as zf:
        zf.write(a, "Lid.Shape.brp")
        zf.write(b, "Base.Shape.brp")
        zf.writestr("Document.xml", '<Document><Object name="Lid"/>'
                                    '<Object name="Base"/></Document>')
    return f


@pytest.mark.occt
def test_fcstd_bodies_named_access(tmp_path):
    from gitcad.importers.fcstd import import_fcstd_bodies
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    bodies = import_fcstd_bodies(str(_fcstd(tmp_path)), k)
    assert [n for n, _ in bodies] == ["Base", "Lid"]
    vols = {n: k.measure(s)["volume"] for n, s in bodies}
    assert vols["Lid"] == pytest.approx(1000.0)
    assert vols["Base"] == pytest.approx(125.0)


@pytest.mark.occt
def test_interference_tolerance_and_matrix(tmp_path):
    from gitcad.kernel.occt import OcctKernel
    from gitcad.part.interference import check_interference

    k = OcctKernel()
    inst = {"a": (k.box(10, 10, 10), (0.0, 0.0, 0.0), 0.0),
            "b": (k.box(10, 10, 10), (9.9, 0.0, 0.0), 0.0)}   # 0.1x10x10 = 10mm3
    strict = check_interference(k, inst)
    assert not strict.ok
    assert strict.checks["overlaps_mm3"]["a<->b"] == pytest.approx(10.0)
    budget = check_interference(k, inst, tol_mm3=15.0)
    assert budget.ok                                   # within the clash budget
    assert budget.checks["overlaps_mm3"]["a<->b"] == pytest.approx(10.0)  # still shown


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
