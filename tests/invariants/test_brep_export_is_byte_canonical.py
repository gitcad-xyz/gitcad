"""INVARIANT (ADR-0004 / CLAUDE.md hard rule 2): text is source, and the
serialized form is BYTE-canonical — semantically equal solids produce
identical bytes, or hashing stops meaning identity and every git diff of a
model file becomes noise.

Docket S1 pinned the live violation: a 360-degree rotation is a geometric
no-op, but a rigid map leaves every coordinate SurdVal-typed even when the
surd part is zero, and forge's ``_num`` branched on the TYPE — so the rotated
export respelled every rational as ``S:a/1:0/1:1/1`` and the file went
16838 -> 30998 bytes with zero geometry change. Ordinary edits reach
``kernel.rotate`` for every non-Solid representation, so this was not a
hostile-input corner: it rewrote committed files on routine transforms.
"""

from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from gitcad.kernel.ref import RefKernel

pytestmark = pytest.mark.invariant


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def test_a_full_turn_does_not_rewrite_a_committed_brep(k, tmp_path) -> None:
    rb = k.fillet(k.box(20, 20, 12), (), 3)
    p1, p2 = tmp_path / "a.brep", tmp_path / "b.brep"
    k.export_brep(rb, str(p1))
    k.export_brep(k.transform(rb, rotate_axis=(0, 0, 1), rotate_deg=360),
                  str(p2))
    assert p1.read_bytes() == p2.read_bytes()


def test_repeat_export_is_byte_stable(k, tmp_path) -> None:
    shape = k.boolean("cut", k.box(40, 20, 5), k.transform(
        k.cylinder(4, 5), translate=(20, 10, 0)))
    p1, p2 = tmp_path / "a.brep", tmp_path / "b.brep"
    k.export_brep(shape, str(p1))
    k.export_brep(shape, str(p2))
    assert p1.read_bytes() == p2.read_bytes()
