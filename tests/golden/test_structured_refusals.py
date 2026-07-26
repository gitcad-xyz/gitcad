"""A refusal an agent has to parse out of prose is a refusal it cannot act on.

Every guard here already refused correctly. What was missing was the data to do
anything about it: which predicate fired, what it measured, and what would make
it work. Without those an agent hitting "the pocket does not sit strictly inside
one flat face" has to read the kernel source to learn whether to shrink the
hole, move it, or give up.

The measured values are LOCAL ONLY — they are user coordinates, so they stay
off the FailureSignature, which is the part designed to leave the machine
(ADR-0006/0007).
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from forgekernel.brep import Solid
from forgekernel.quadric import Cone, Cyl, DrilledSolid, RoundedBox
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _refusal(fn) -> KernelError:
    with pytest.raises(KernelError) as e:
        fn()
    return e.value


def test_a_pocket_off_its_flat_says_how_far_off_and_which_way(k) -> None:
    """RoundedBox(20,20,10,2) has a top flat of [2,18]x[2,18]; a Ø4 bore at
    (10,1) hangs 3 mm past its y edge."""
    err = _refusal(lambda: k.boolean("cut", RoundedBox(20, 20, 10, 2),
                                     Cyl(10, 1, 2, -5, 15)))
    assert err.predicate == "mouth_inside_cap"
    assert err.stage == "K2.2"
    m = err.measured
    assert m["flat"] == [[2.0, 2.0], [18.0, 18.0]]
    assert m["clearance"] == pytest.approx(-3.0)   # 3 mm outside, signed
    assert [10.0, -1.0] in m["outside_probes"]     # the y-min extreme of the bore
    assert "3" in err.remedy and "mm" in err.remedy


def test_a_bore_wider_than_the_wall_names_the_height_and_the_radius(k) -> None:
    """A cone tapers, so 'too wide' is only true at some heights — the useful
    answer is WHICH height and by how much."""
    err = _refusal(lambda: k.boolean(
        "cut", Cone(0, 0, 2, 5, 0, 10),
        k.transform(k.cylinder(3, 100), translate=(0, 0, -50))))
    assert err.predicate == "bore_inside_material"
    m = err.measured
    assert m["tool_radius"] == 3.0
    assert m["wall_radius"] == pytest.approx(2.0)  # the r=2 end of the taper
    assert m["at_z"] == pytest.approx(0.0)
    assert "2" in err.remedy


def test_a_prism_reaching_the_wall_says_what_width_would_fit(k) -> None:
    """The tool's CORNER is the binding constraint, not its half-width — so
    the actionable number is the inscribed square of the thinnest wall."""
    err = _refusal(lambda: k.boolean(
        "cut", Cone(0, 0, 1, 3, 0, 10),
        k.transform(k.box(2, 2, 100), translate=(0, 0, 5))))
    assert err.predicate == "prism_inside_material"
    m = err.measured
    # the tool spans x,y in [0,2], so its far corner sits at r = 2*sqrt(2)…
    assert m["tool_corner_radius"] == pytest.approx(2 * math.sqrt(2))
    # …where the cone's wall is only r = 2 (it tapers 1 -> 3 over z 0..10)
    assert m["thinnest_wall_radius"] == pytest.approx(2.0)
    assert "fits" in err.remedy


SHELLS = [
    ("rounded box", lambda k: k.shell(RoundedBox(20, 20, 10, 2), [], 5),
     "cavity_is_positive", 5.0),
    ("drilled plate", lambda k: k.shell(
        DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)]), [], 4),
     "cavity_is_positive", 2.5),
]


@pytest.mark.parametrize("label,fn,predicate,limit", SHELLS,
                         ids=[s[0] for s in SHELLS])
def test_too_thick_a_shell_says_the_thickness_that_would_work(
        k, label, fn, predicate, limit) -> None:
    err = _refusal(lambda: fn(k))
    assert err.predicate == predicate
    assert err.measured["thickness"] > 0
    assert f"{limit:.4g}" in err.remedy, err.remedy


def test_a_blind_bore_lists_which_bores_are_blind(k) -> None:
    """"A blind bore" is not actionable when the part has nine holes."""
    plate = DrilledSolid(Solid.box(30, 30, 10), [])
    plate = plate.cut(Cyl(8, 8, 2, 0, 10)).cut(Cyl(22, 22, 3, 4, 10))
    err = _refusal(lambda: k.shell(plate, [], 2))
    assert err.predicate == "every_bore_is_through"
    blind = err.measured["blind_bores"]
    assert len(blind) == 1, "only the z=4..10 bore is blind"
    assert blind[0]["xy"] == [22.0, 22.0]
    assert err.measured["solid_z"] == [0.0, 10.0]


def test_the_refusal_serialises_for_an_agent_and_the_live_rail(k) -> None:
    err = _refusal(lambda: k.shell(RoundedBox(20, 20, 10, 2), [], 5))
    d = err.as_dict()
    assert set(d) == {"message", "op", "stage", "predicate", "measured",
                      "remedy"}
    import json

    json.dumps(d)                      # must survive the wire, floats not Fractions


def test_measurements_never_reach_the_signature(k) -> None:
    """The signature is the part that LEAVES the machine, and it is derived
    only from what went wrong — never from the user's coordinates."""
    err = _refusal(lambda: k.boolean("cut", RoundedBox(20, 20, 10, 2),
                                     Cyl(10, 1, 2, -5, 15)))
    blob = err.signature.key() + err.signature.diagnostic + err.signature.op
    for value in (10, 1, 2, 18):
        assert f"{value}.0" not in blob
    assert err.measured, "…while the caller still gets them locally"


def test_a_refusal_lands_on_the_live_rail(k, tmp_path) -> None:
    """A person watching should see WHY the agent stopped, not only that it
    did."""
    from gitcad import activity as A

    (tmp_path / ".git").mkdir()
    act = A.narrate_to(tmp_path)
    try:
        with pytest.raises(KernelError):
            k.shell(RoundedBox(20, 20, 10, 2), [], 5)
    finally:
        A.narrate_to(None)
    problems = [e for e in act.state()["events"] if e["kind"] == "problem"]
    assert problems and problems[-1]["predicate"] == "cavity_is_positive"
    assert problems[-1]["remedy"]


# --- k.can(): plan without committing ----------------------------------------

def test_can_answers_without_raising(k) -> None:
    """An agent planning a feature tree otherwise commits to each step and
    unwinds when the kernel refuses three features later."""
    good = k.can("boolean", "cut", RoundedBox(20, 20, 10, 2), Cyl(10, 10, 2, 6, 15))
    assert good == {"ok": True, "op": "boolean"}

    bad = k.can("boolean", "cut", RoundedBox(20, 20, 10, 2), Cyl(10, 1, 2, -5, 15))
    assert bad["ok"] is False
    assert bad["predicate"] == "mouth_inside_cap"
    assert bad["measured"]["clearance"] == pytest.approx(-3.0)
    assert "3" in bad["remedy"]


def test_can_lets_an_agent_repair_its_own_design(k) -> None:
    """The point of the whole structured-refusal chain: the verdict says what
    to change, so the next attempt is derived rather than guessed."""
    base = RoundedBox(20, 20, 10, 2)
    verdict = k.can("boolean", "cut", base, Cyl(10, 1, 2, -5, 15))
    assert not verdict["ok"]
    fix = -verdict["measured"]["clearance"]
    # The guard is STRICT, so the reported clearance is a bound, not a recipe:
    # moving by exactly that much lands tangent and refuses again. The remedy
    # says "MORE than", because a remedy whose own number does not work costs
    # the caller a second attempt to find that out.
    assert "MORE than" in verdict["remedy"]
    assert not k.can("boolean", "cut", base, Cyl(10, 1 + fix, 2, -5, 15))["ok"]
    assert k.can("boolean", "cut", base,
                 Cyl(10, 1 + fix + Fraction(1, 100), 2, -5, 15))["ok"]


def test_can_does_not_mutate_or_leak(k) -> None:
    box = RoundedBox(20, 20, 10, 2)
    before = float(k.mass_props(box)["volume"])
    k.can("boolean", "cut", box, Cyl(10, 10, 2, 6, 15))
    assert float(k.mass_props(box)["volume"]) == before


def test_an_unknown_operation_is_answered_not_raised(k) -> None:
    v = k.can("teleport", 1, 2)
    assert v["ok"] is False and "teleport" in v["remedy"]
