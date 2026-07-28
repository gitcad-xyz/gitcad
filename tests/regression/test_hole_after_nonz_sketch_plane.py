"""Dogfood #49: hole CRASHED with a bare TypeError after a non-z sketch plane.

``_dispatch`` implements ``plane.normal == "x"`` as an exact 120° rotation about
(1,1,1) — a true axis permutation, but one that leaves the placed prism's
vertex coordinates as ``SurdVal`` rather than rationals. Drilling that body
reached forge's ``quadric._seg_dist2``::

    return (px - qx) ** 2 + (py - qy) ** 2

and ``SurdVal`` had no ``__pow__``, so it died with

    TypeError: unsupported operand type(s) for ** or pow(): 'SurdVal' and 'int'

``feature_add`` catches ``GitcadError | ValueError | KeyError |
NotImplementedError``, so a ``TypeError`` escaped the refusal wrapper entirely:
the MCP call raised, with no structured reason and no fingerprint, and the
caller could not tell a wall from a crash. Zero-crash rule (ADR-0019): the seam
answers with geometry or with a named refusal, never a traceback.

Root cause and fix are in forge, not here: ℚ[√d] is closed under
multiplication, so an integer power never leaves the field and the operator was
simply missing — the same half-built-type gap ``SurdVal.__abs__`` was added to
close, and it too only fires once a solid has been ROTATED. With ``__pow__`` the
drill does not merely stop crashing, it is EXACT.

The volume below is an independent closed form, not the kernel's own output:

    box            40 * 40 * 10                        = 16000
    boss           an x-normal 5 x 6 rect extruded 4,  = +80
                   protruding 4 above the box top       (only Z in [10,14] is new)
    hole           pi * 1.5^2 * 5                      = -45/4 pi

    total = 16080 - (45/4)pi, held exactly as a PiVal.
"""

from __future__ import annotations

from fractions import Fraction as Q

import pytest

pytest.importorskip("forgekernel")

from forgekernel.quadric import PiVal

from gitcad.document import Document, Feature
from gitcad.kernel.ref import RefKernel


def _rect(x0: float, y0: float, w: float, h: float) -> dict:
    return {"start": [x0, y0],
            "segments": [{"kind": "line", "to": [x0 + w, y0]},
                         {"kind": "line", "to": [x0 + w, y0 + h]},
                         {"kind": "line", "to": [x0, y0 + h]},
                         {"kind": "line", "to": [x0, y0]}]}


@pytest.fixture()
def k() -> RefKernel:
    return RefKernel()


def test_hole_through_a_normal_x_body_is_exact_not_a_crash(k) -> None:
    d = Document()
    box = d.add(Feature(op="box", params={"dx": 40, "dy": 40, "dz": 10}))
    # sketch plane normal x: sketch (u, v) -> (Y, Z). Y in [2,7], Z in [8,14],
    # extruded 4 along +X. The Z in [10,14] part protrudes above the box top,
    # so the union is a real union and the drilled body really does carry the
    # rotation's surd coordinates.
    boss = d.add(Feature(op="extrude", inputs=[box], params={
        "profile": _rect(2, 8, 5, 6), "height": 4,
        "plane": {"normal": "x", "offset": 0.0}, "mode": "add"}))
    hole = d.add(Feature(op="hole", inputs=[boss], params={
        "x": 20, "y": 20, "top_z": 10, "depth": 5, "diameter": 3}))

    res = d.build(k)
    assert res.shapes[boss].volume() == 16000 + 80
    assert res.shapes[hole].volume() == PiVal(16080, Q(-45, 4))


def test_the_issues_own_repro_no_longer_raises(k) -> None:
    """#49 verbatim: the boss sits entirely INSIDE the box, so it adds nothing
    — the point is only that the drill completes and removes exactly one
    cylinder."""
    d = Document()
    box = d.add(Feature(op="box", params={"dx": 40, "dy": 40, "dz": 10}))
    boss = d.add(Feature(op="extrude", inputs=[box], params={
        "profile": _rect(2, 2, 5, 5), "height": 4,
        "plane": {"normal": "x", "offset": 0.0}, "mode": "add"}))
    hole = d.add(Feature(op="hole", inputs=[boss], params={
        "x": 20, "y": 20, "top_z": 10, "depth": 5, "diameter": 3}))

    res = d.build(k)
    assert res.shapes[boss].volume() == 16000
    assert res.shapes[hole].volume() == PiVal(16000, Q(-45, 4))


def test_normal_y_sketch_plane_drills_too(k) -> None:
    """The other permutation, which carries the same surds."""
    d = Document()
    box = d.add(Feature(op="box", params={"dx": 40, "dy": 40, "dz": 10}))
    boss = d.add(Feature(op="extrude", inputs=[box], params={
        "profile": _rect(2, 8, 5, 6), "height": 4,
        "plane": {"normal": "y", "offset": 0.0}, "mode": "add"}))
    hole = d.add(Feature(op="hole", inputs=[boss], params={
        "x": 20, "y": 20, "top_z": 10, "depth": 5, "diameter": 3}))

    res = d.build(k)
    drilled = res.shapes[hole].volume()
    assert drilled == PiVal(res.shapes[boss].volume(), 0) - PiVal(0, Q(45, 4))


def test_drill_delta_is_independent_of_the_sketch_plane(k) -> None:
    """The invariant the crash hid: the same hole in the same place removes
    the same cylinder whether or not an earlier feature used a rotated
    sketch plane."""
    def drilled_delta(plane: dict | None) -> object:
        d = Document()
        prev = d.add(Feature(op="box", params={"dx": 40, "dy": 40, "dz": 10}))
        if plane is not None:
            prev = d.add(Feature(op="extrude", inputs=[prev], params={
                "profile": _rect(2, 8, 5, 6), "height": 4,
                "plane": plane, "mode": "add"}))
        hole = d.add(Feature(op="hole", inputs=[prev], params={
            "x": 20, "y": 20, "top_z": 10, "depth": 5, "diameter": 3}))
        res = d.build(k)
        # PiVal(x, 0) on the left: a bare Fraction on the left of a PiVal has
        # no __rsub__ to reflect to — the same half-built-type gap this file
        # is about, one type over.
        return PiVal(res.shapes[prev].volume(), 0) - res.shapes[hole].volume()

    plain = drilled_delta(None)
    assert plain == PiVal(0, Q(45, 4))
    assert drilled_delta({"normal": "x", "offset": 0.0}) == plain
    assert drilled_delta({"normal": "y", "offset": 0.0}) == plain
