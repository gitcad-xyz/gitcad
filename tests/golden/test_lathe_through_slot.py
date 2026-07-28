"""Issue #48: a prism open at both ends of a lathe was refused as "splits the
lathe". It does not split it.

`_pocket_solid` already corrected exactly this reading for general bodies
("Open at BOTH ends is a HOLE, not a split"). `_pocket_lathe` kept the old
one, and it fired BEFORE the wall guard — so the refusal asserted
disconnection from the tool's z extent alone, without ever asking whether
the footprint reaches the wall.

A footprint strictly inside the wall cannot disconnect a solid of
revolution: the remaining material runs all the way round the slot. The
guards that decide that already exist; this pins that they, and not the z
extent, are what answers the question.
"""
from __future__ import annotations

import math

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.document import Document, Feature
from gitcad.errors import KernelError
from gitcad.kernel import get_kernel

# a plain Ø20 x 20 lathe: profile (r, z) up the axis and back down the wall
CYL = {"start": [0.0, 0.0], "segments": [
    {"kind": "line", "to": [10.0, 0.0]},
    {"kind": "line", "to": [10.0, 20.0]},
    {"kind": "line", "to": [0.0, 20.0]},
    {"kind": "line", "to": [0.0, 0.0]}]}


def _slot(dz, z0, *, dx=6.0, dy=4.0, prof=None):
    """Ø20 x 20 lathe minus a dx x dy prism placed at (-dx/2, -dy/2, z0)."""
    d = Document()
    lathe = d.add(Feature(op="revolve", params={"profile": prof or CYL}))
    tool = d.add(Feature(op="box", params={"dx": dx, "dy": dy, "dz": dz}))
    placed = d.add(Feature(op="move", inputs=[tool],
                           params={"translate": [-dx / 2, -dy / 2, z0]}))
    cut = d.add(Feature(op="boolean", params={"kind": "cut"},
                        inputs=[lathe, placed]))
    kernel = get_kernel()
    return kernel, d, d.build(kernel), cut


def test_a_through_slot_builds_and_removes_exactly_its_own_volume():
    kernel, _d, built, cut = _slot(dz=22.0, z0=-1.0)
    props = kernel.mass_props(built.shapes[cut])
    # the slot spans the full height, so it removes 6 x 4 x 20 exactly
    assert props["volume"] == pytest.approx(math.pi * 100 * 20 - 6 * 4 * 20,
                                            rel=1e-12)


def test_the_through_slot_is_one_valid_watertight_solid():
    kernel, _d, built, cut = _slot(dz=22.0, z0=-1.0)
    r = kernel.validate(built.shapes[cut])
    assert r.ok, r.violations
    (x0, y0, z0), (x1, y1, z1) = kernel.bbox(built.shapes[cut])
    # it did NOT fall in two: the outer wall is untouched all the way round
    assert (x0, x1, y0, y1, z0, z1) == (-10.0, 10.0, -10.0, 10.0, 0.0, 20.0)


def test_a_through_slot_exports_step_and_stl(tmp_path):
    kernel, _d, built, cut = _slot(dz=22.0, z0=-1.0)
    step = tmp_path / "slot.step"
    kernel.export_step(built.shapes[cut], str(step))
    body = step.read_text(encoding="utf-8")
    assert "MANIFOLD_SOLID_BREP" in body
    stl = tmp_path / "slot.stl"
    kernel.export_stl(built.shapes[cut], str(stl))
    assert stl.read_text(encoding="utf-8").count("facet normal") > 0


def test_a_slot_that_reaches_the_wall_still_refuses():
    """The wall guard is what decides, and it is unchanged."""
    with pytest.raises(KernelError) as e:
        _slot(dz=22.0, z0=-1.0, dx=21.0)
    assert "reaches the lathe's wall" in str(e.value)


def test_a_blind_slot_is_unchanged():
    kernel, _d, built, cut = _slot(dz=6.0, z0=15.0)     # open at the top only
    props = kernel.mass_props(built.shapes[cut])
    assert props["volume"] == pytest.approx(math.pi * 100 * 20 - 6 * 4 * 5,
                                            rel=1e-12)


def test_a_pocket_open_at_neither_end_is_still_an_internal_cavity():
    with pytest.raises(KernelError) as e:
        _slot(dz=6.0, z0=7.0)
    assert "internal cavity" in str(e.value)


def test_a_through_slot_in_a_TUBE_still_refuses_on_the_bore():
    """The keyway case in #48 -- a coaxial bore runs through the column, so
    the guard that catches it is unchanged by this fix."""
    tube = {"start": [6.0, 0.0], "segments": [
        {"kind": "line", "to": [13.0, 0.0]},
        {"kind": "line", "to": [13.0, 24.0]},
        {"kind": "line", "to": [6.0, 24.0]},
        {"kind": "line", "to": [6.0, 0.0]}]}
    with pytest.raises(KernelError) as e:
        _slot(dz=26.0, z0=-1.0, dx=4.0, dy=4.0, prof=tube)
    assert "a coaxial bore runs through it" in str(e.value)
