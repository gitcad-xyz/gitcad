"""Golden: mate_solve (ADR-0014) — authoring-time placement from mate intent.

Kernel-free. Scrambled instance positions must solve so every mated port
pair coincides (verified by the assembly's own validate, the independent
checker); over-constrained disagreements are reported with the gap, never
silently "fixed"; instances with no mate path stay put and are listed.
"""

import pytest

from gitcad.part import (Assembly, Frame, Interface, Port, bought_part,
                         mate_solve)


def _part(pid: str, ports: dict[str, tuple[float, float, float]]):
    iface = Interface()
    iface.envelope = {"dx": 10, "dy": 10, "dz": 5}
    iface.frames = {"origin": Frame()}
    iface.frames.update({n: Frame(origin=o) for n, o in ports.items()})
    iface.ports = {n: Port(name=n, type="mech.bolt", frame=n) for n in ports}
    return bought_part(f"MPN-{pid}", "ACME", f"prt_ms_{pid}", interface=iface)


def _chain():
    """base --(right port at x=10)--> mid --(right at x=8)--> tip, scrambled."""
    asm = Assembly("chain")
    asm.add("base", _part("base", {"r": (10, 0, 0)}))
    asm.add("mid", _part("mid", {"l": (0, 0, 0), "r": (8, 0, 0)}),
            translate=(99, -3, 7))                      # deliberately wrong
    asm.add("tip", _part("tip", {"l": (0, 0, 0)}), translate=(-40, 40, 0))
    asm.mate("base.r", "mid.l")
    asm.mate("mid.r", "tip.l")
    return asm


def test_scrambled_chain_solves_to_coincident_ports():
    asm = _chain()
    report = mate_solve(asm, base="base")               # anchor chosen explicitly
    assert report.ok
    assert report.base == "base"
    assert report.solved == ["mid", "tip"]
    assert asm.instances["mid"].translate == (10, 0, 0)
    assert asm.instances["tip"].translate == (18, 0, 0)
    # the independent checker agrees: every mate coincides
    assert asm.validate().ok


def test_rotation_is_respected_not_solved():
    asm = Assembly("rot")
    asm.add("base", _part("b2", {"r": (10, 0, 0)}))
    asm.add("arm", _part("a2", {"l": (5, 0, 0)}), rotate_z_deg=90.0)
    asm.mate("base.r", "arm.l")
    report = mate_solve(asm)
    assert report.ok
    # arm's port local offset (5,0,0) rotated 90 -> (0,5,0); translate
    # compensates so the port still lands on (10,0,0)
    assert asm.instances["arm"].translate == pytest.approx((10, -5, 0))
    assert asm.instances["arm"].rotate_z_deg == 90.0    # untouched
    assert asm.validate().ok


def test_over_constrained_conflict_reported_not_moved():
    asm = _chain()
    # a third mate that disagrees: tip.l cannot be at base.r too
    asm.mate("base.r", "tip.l")
    report = mate_solve(asm, base="base")
    assert not report.ok
    assert len(report.conflicts) == 1
    assert "gap=8" in report.conflicts[0]
    # the BFS placement itself still happened deterministically
    assert asm.instances["mid"].translate == (10, 0, 0)


def test_unmated_instances_stay_put_and_are_listed():
    asm = _chain()
    asm.add("loose", _part("loose", {}), translate=(70, 70, 70))
    report = mate_solve(asm, base="base")
    assert report.unreachable == ["loose"]
    assert asm.instances["loose"].translate == (70, 70, 70)
