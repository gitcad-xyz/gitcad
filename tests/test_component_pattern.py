"""Component patterns — linear and circular arrays of a placed instance
(SolidWorks "linear/circular component pattern"). These stay inside the v1
placement model (translate + rotate-about-Z), so a patterned assembly is
still validated by ordinary interface checking.
"""

from __future__ import annotations

import math

import pytest

from gitcad.errors import GitcadError
from gitcad.part import Assembly, PartManifest
from gitcad.part.interface import Interface


def _part(pid="prt_0000000000000abc") -> PartManifest:
    return PartManifest(id=pid, name="widget", domain="mech", version="1.0.0",
                        interface=Interface(envelope={"origin": [0, 0, 0],
                                                      "dx": 2, "dy": 2, "dz": 2}))


def test_linear_pattern_places_evenly_spaced_copies() -> None:
    asm = Assembly("rail")
    asm.add("w", _part(), translate=(0, 0, 0))
    made = asm.pattern_linear("w", direction=(1, 0, 0), spacing=10, count=4)
    assert [m.name for m in made] == ["w#1", "w#2", "w#3"]
    assert len(asm.instances) == 4
    assert asm.instances["w#3"].translate == pytest.approx((30, 0, 0))


def test_linear_pattern_normalizes_direction() -> None:
    asm = Assembly("diag")
    asm.add("w", _part(), translate=(1, 1, 0))
    asm.pattern_linear("w", direction=(3, 4, 0), spacing=5, count=2)
    # unit (0.6,0.8) * 5 = (3,4) added to the seed at (1,1)
    assert asm.instances["w#1"].translate == pytest.approx((4, 5, 0))


def test_circular_full_ring_drops_redundant_last_copy() -> None:
    asm = Assembly("hub")
    asm.add("w", _part(), translate=(10, 0, 0))
    made = asm.pattern_circular("w", center=(0, 0), count=4, total_angle_deg=360)
    assert len(made) == 3                       # seed + 3 = 4 around the ring
    # 90° copy: (10,0) -> (0,10), rotate_z advances 90°
    p1 = asm.instances["w#1"]
    assert p1.translate == pytest.approx((0, 10, 0), abs=1e-9)
    assert p1.rotate_z_deg == pytest.approx(90.0)
    # 180° copy back on the -x axis
    assert asm.instances["w#2"].translate == pytest.approx((-10, 0, 0), abs=1e-9)


def test_circular_partial_arc_keeps_both_ends() -> None:
    asm = Assembly("fan")
    asm.add("w", _part(), translate=(10, 0, 0))
    asm.pattern_circular("w", center=(0, 0), count=3, total_angle_deg=90)
    # 3 copies over 90° => steps of 45°: seed@0, #1@45, #2@90
    p2 = asm.instances["w#2"]
    assert p2.translate == pytest.approx((0, 10, 0), abs=1e-9)
    assert p2.rotate_z_deg == pytest.approx(90.0)


def test_patterned_assembly_still_validates() -> None:
    asm = Assembly("grid")
    asm.add("w", _part(), translate=(0, 0, 0))
    asm.pattern_linear("w", direction=(0, 1, 0), spacing=20, count=3)
    rep = asm.validate()
    assert rep.ok
    assert rep.checks["instances"] == 3


def test_pattern_errors() -> None:
    asm = Assembly("bad")
    asm.add("w", _part())
    with pytest.raises(GitcadError, match="no seed"):
        asm.pattern_linear("missing", direction=(1, 0, 0), spacing=1, count=2)
    with pytest.raises(GitcadError, match="zero-length direction"):
        asm.pattern_linear("w", direction=(0, 0, 0), spacing=1, count=2)
    with pytest.raises(GitcadError, match="count must be"):
        asm.pattern_circular("w", count=0)
    # re-running the same pattern collides on the generated names
    asm.pattern_linear("w", direction=(1, 0, 0), spacing=1, count=2)
    with pytest.raises(GitcadError, match="duplicate copy name"):
        asm.pattern_linear("w", direction=(1, 0, 0), spacing=1, count=2)
