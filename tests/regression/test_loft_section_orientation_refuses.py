"""Dogfood #39: a loft section's ``rotate_deg`` was accepted, persisted, ignored.

``_dispatch`` built the loft with ``[(s["profile"], s["z"]) for s in sections]``.
Every other key of a section dict was dropped on the floor — silently. So
``rotate_deg: 30`` round-tripped through ``Document.dumps()`` into the
byte-canonical source text, was reported buildable, and produced geometry
identical to the unrotated loft (measured through the MCP registry: volume
1600.0, dx 20.0, dy 8.0 with and without it). The same held for ``scale``,
``offset``, and for keys that mean nothing at all (``twist_deg``).

That is the worst of both worlds: the document of record claims an intent the
build never honoured, and a reader of the text — human, or the parametric
re-build story — cannot tell which of its numbers are load-bearing.

Why refuse rather than apply. A ruled loft rules straight lines between
INDEX-MATCHED section vertices. Rotating a section makes those lateral quads
non-planar, and forge builds the solid by triangulating them, so the answer
depends on which diagonal the triangulation picks. Measured on this kernel with
the rotation baked into the coordinates by hand (a 20x8 rectangle lofted to the
same rectangle rotated, h=10):

    +30 deg -> 1141.88 mm^3
    -30 deg -> 1915.21 mm^3   (the exact MIRROR IMAGE of the +30 solid,
                               so its volume MUST be identical)
    true ruled volume -> 1528.55 mm^3

Applying rotate_deg would therefore have replaced a silently-ignored input with
a silently-wrong number, which is worse (ADR-0006: a wrong number is the only
true failure). So the parameter refuses BY NAME, naming the stage that would
bring it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.kernel.ref import RefKernel


@pytest.fixture()
def k() -> RefKernel:
    return RefKernel()


def _rect(hx: float, hy: float) -> dict:
    return {"start": [-hx, -hy],
            "segments": [{"kind": "line", "to": [hx, -hy]},
                         {"kind": "line", "to": [hx, hy]},
                         {"kind": "line", "to": [-hx, hy]},
                         {"kind": "line", "to": [-hx, -hy]}]}


def _doc(top_extra: dict) -> tuple[Document, str]:
    top = {"profile": _rect(10.0, 4.0), "z": 10.0}
    top.update(top_extra)
    d = Document()
    fid = d.add(Feature(op="loft", params={
        "ruled": True,
        "sections": [{"profile": _rect(10.0, 4.0), "z": 0.0}, top]}))
    return d, fid


def test_plain_loft_still_builds(k) -> None:
    d, fid = _doc({})
    assert d.build(k).shapes[fid].volume() == 1600


@pytest.mark.parametrize("key, value", [
    ("rotate_deg", 30.0),
    ("scale", 0.5),
    ("offset", [3.0, 0.0]),
])
def test_unapplied_section_orientation_refuses_by_name(k, key, value) -> None:
    """Named in #39 as the wanted shape of a fix — until the kernel can do it
    exactly, each must refuse by its own name rather than be dropped."""
    d, _ = _doc({key: value})
    with pytest.raises(GitcadError) as exc:
        d.build(k)
    msg = str(exc.value)
    assert key in msg, msg
    assert "loft section" in msg, msg


def test_meaningless_section_key_refuses_by_name(k) -> None:
    """The class, not just the three keys: any key the build does not read is
    a claim in the source text that the geometry never honoured."""
    d, _ = _doc({"twist_deg": 30.0})
    with pytest.raises(GitcadError) as exc:
        d.build(k)
    assert "twist_deg" in str(exc.value)


def test_zero_rotation_is_not_a_rotation(k) -> None:
    """rotate_deg: 0 asks for nothing, so it is honoured, not refused —
    a refusal there would be noise, and it is what a family's default
    configuration looks like."""
    d, fid = _doc({"rotate_deg": 0.0})
    assert d.build(k).shapes[fid].volume() == 1600


def test_identity_scale_and_offset_are_honoured(k) -> None:
    d, fid = _doc({"scale": 1.0, "offset": [0.0, 0.0]})
    assert d.build(k).shapes[fid].volume() == 1600


def test_missing_section_z_refuses_instead_of_leaking_keyerror(k) -> None:
    """#28's lesson applied here: the seam refuses BY NAME, it does not leak
    a bare KeyError out of a dict subscript."""
    d = Document()
    d.add(Feature(op="loft", params={
        "ruled": True,
        "sections": [{"profile": _rect(10.0, 4.0), "z": 0.0},
                     {"profile": _rect(10.0, 4.0)}]}))
    with pytest.raises(GitcadError) as exc:
        d.build(k)
    assert "z" in str(exc.value)


def test_missing_section_profile_refuses_instead_of_leaking_keyerror(k) -> None:
    d = Document()
    d.add(Feature(op="loft", params={
        "ruled": True,
        "sections": [{"profile": _rect(10.0, 4.0), "z": 0.0}, {"z": 10.0}]}))
    with pytest.raises(GitcadError) as exc:
        d.build(k)
    assert "profile" in str(exc.value)
