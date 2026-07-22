"""GOLDEN: mechanical manufacturing outputs — STEP export and drawings.

All OCCT-backed; skipped when the kernel isn't installed.
"""

from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def part():
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    plate = k.box(60, 40, 8)
    hole = k.transform(k.cylinder(3.2, 8), translate=(15, 20, 0))
    return k, k.boolean("cut", plate, hole)


def test_boolean_volume_is_exact(part) -> None:
    k, shape = part
    expected = 60 * 40 * 8 - math.pi * 3.2**2 * 8
    assert k.measure(shape)["volume"] == pytest.approx(expected, rel=1e-6)


def test_step_export_is_valid_iso10303(part, tmp_path) -> None:
    k, shape = part
    path = str(tmp_path / "part.step")
    k.export_step(shape, path)
    text = open(path).read()
    assert text.startswith("ISO-10303-21;")
    assert "END-ISO-10303-21;" in text


def test_stl_export_writes_mesh(part, tmp_path) -> None:
    k, shape = part
    path = str(tmp_path / "part.stl")
    k.export_stl(shape, path)
    assert (tmp_path / "part.stl").stat().st_size > 1000


def test_hlr_projections_are_dimensionally_correct(part) -> None:
    from gitcad.drawing.hlr import bounds, project

    _, shape = part
    for view, (w, h) in {"front": (60, 8), "top": (60, 40), "right": (40, 8)}.items():
        b = bounds(project(shape, view)["visible"])
        assert b[2] - b[0] == pytest.approx(w, abs=1e-3), view
        assert b[3] - b[1] == pytest.approx(h, abs=1e-3), view


def test_drawing_renders_svg_and_pdf(part) -> None:
    from gitcad.drawing import make_drawing

    _, shape = part
    d = make_drawing(shape, title="test part")
    svg = d.to_svg()
    assert svg.startswith("<svg") and "polyline" in svg and "test part" in svg
    pdf = d.to_pdf()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert len(d.views) == 4 and len(d.dims) == 3


def test_fillet_reduces_volume_and_stays_valid(part) -> None:
    k, shape = part
    filleted = k.fillet(shape, None, 1.0)
    assert k.validate(filleted).ok
    assert k.measure(filleted)["volume"] < k.measure(shape)["volume"]
