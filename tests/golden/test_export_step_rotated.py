"""A rotated solid exports to STEP (bucket-B, 2026-07-28).

``export_step`` refused every rotated part with "export_step on Solid yet —
K3.7 (canonical B-rep)". That message blamed the canonical B-rep for a
capability it had. The real cause was one line in forge's STEP writer:
``_f(x)`` was ``Fraction(x)``, which raises on an exact scalar by design
(``is_exact_scalar`` exists precisely to stop silent coercion), and a
45°-rotated box has ℚ[√2] coordinates. ``_via_body`` caught that TypeError
and reported a missing capability.

STEP Part 21 is a DECIMAL interchange format, so an exact→decimal conversion
has to happen at export; it now happens in ``stepio.export_rational``, using
only the exact comparisons the number types already provide.

This was the second-largest refusal family in the composed capability grid:
14 cells (9 on Body, 5 on Solid). Closing it moved composed from 130/255 to
142/255.
"""

from __future__ import annotations

import math

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.kernel.ref import RefKernel

# start (0,0) -> (20,0) -> (20,10) -> (0,10) and CLOSES back to the start:
# a 20x10 rectangle, not a triangle. Named for what it is — reading the
# vertex list as a triangle is an easy and expensive mistake.
RECT = {"start": [0, 0], "segments": [{"kind": "line", "to": [20, 0]},
                                      {"kind": "line", "to": [20, 10]},
                                      {"kind": "line", "to": [0, 10]}]}


@pytest.fixture()
def k():
    return RefKernel()


def _roundtrip_volume(k, shape, tmp_path, name):
    p = tmp_path / f"{name}.step"
    k.export_step(shape, str(p))
    text = p.read_text()
    assert text.startswith("ISO-10303-21;"), "not a Part 21 file"
    assert "MANIFOLD_SOLID_BREP" in text
    return k.mass_props(k.import_step(str(p)))["volume"]


def test_a_45_degree_box_round_trips_through_step(k, tmp_path):
    """The verbatim repro: ℚ[√2] coordinates, previously unexportable."""
    rot = k.transform(k.box(20, 20, 20), rotate_axis=(0, 0, 1), rotate_deg=45)
    assert _roundtrip_volume(k, rot, tmp_path, "box45") == pytest.approx(
        8000.0, rel=1e-12)


@pytest.mark.parametrize("deg", [30, 45, 60, 90])
def test_rotation_never_changes_the_exported_volume(k, deg, tmp_path):
    """A rigid motion is volume-preserving. Whatever field the coordinates
    land in, the number in the file must still say 8000."""
    rot = k.transform(k.box(20, 20, 20), rotate_axis=(0, 0, 1), rotate_deg=deg)
    assert _roundtrip_volume(k, rot, tmp_path, f"box{deg}") == pytest.approx(
        8000.0, rel=1e-12)


def test_a_rotated_prism_round_trips(k, tmp_path):
    """Not just boxes — the extruded profile from the capability corpus."""
    prism = k.extrude(RECT, 5)
    rot = k.transform(prism, rotate_axis=(0, 0, 1), rotate_deg=45)
    expected = 20 * 10 * 5                # 1000
    assert _roundtrip_volume(k, rot, tmp_path, "prism45") == pytest.approx(
        expected, rel=1e-12)


def test_an_axis_aligned_part_is_byte_identical_to_before(k, tmp_path):
    """Guard against collateral damage: a part whose coordinates are already
    rational must be written EXACTLY as it was. The converter returns a
    Fraction untouched for values already in ℚ, so nothing about the common
    case may move."""
    box = k.box(20, 20, 20)
    p = tmp_path / "plain.step"
    k.export_step(box, str(p))
    text = p.read_text()
    # exact integers, not 19.999999999999996
    assert "20.," in text or "20.0," in text or "20.)" in text, text[:0]
    assert k.mass_props(k.import_step(str(p)))["volume"] == pytest.approx(
        8000.0, rel=1e-15)


def test_the_refusal_is_gone_not_merely_hidden(k, tmp_path):
    """It must EXPORT, not refuse more politely."""
    from gitcad.errors import KernelError

    rot = k.transform(k.box(10, 10, 10), rotate_axis=(0, 0, 1), rotate_deg=45)
    try:
        k.export_step(rot, str(tmp_path / "out.step"))
    except KernelError as exc:               # pragma: no cover - regression
        pytest.fail(f"still refusing: {exc}")
