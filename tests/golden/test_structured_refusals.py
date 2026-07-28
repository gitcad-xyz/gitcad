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

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.brep import Solid
from forgekernel.quadric import (AxisStack, Cone, Cyl, DrilledSolid,
                                 RevolveSolid, RoundedBox)
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
    """The useful answer is WHICH height binds and by how much.

    (The bait used to be a tapering cone — #14's profile subtraction now
    BUILDS that as a truncation, so the bait is a part the bore genuinely
    severs: an hourglass necked to r=1, bored r=2. The refusal must still
    carry the neck's numbers.)"""
    from forgekernel.quadric import RevolveSolid

    hourglass = RevolveSolid([(0, 0), (5, 0), (1, 10), (5, 20), (0, 20)], 0, 0)
    err = _refusal(lambda: k.boolean(
        "cut", hourglass,
        k.transform(k.cylinder(2, 100), translate=(0, 0, -50))))
    assert err.predicate == "bore_inside_material"
    m = err.measured
    assert m["tool_radius"] == 2.0
    assert m["wall_radius"] == pytest.approx(1.0)  # the neck
    assert m["at_z"] == pytest.approx(10.0)
    assert "1" in err.remedy


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


def test_a_clipped_blind_floor_names_its_own_stack(k) -> None:
    """"A bore refused" is not actionable when the part has nine holes.

    Since #120 a blind bore's floor is shelled EXACTLY when it clears 2t (the
    erosion torus fits) — this plate's t=2 puts the z=4 floor exactly AT 2t,
    the clipped regime whose volume carries an arcsin — and the refusal must
    say which stack tripped it and by how much."""
    plate = DrilledSolid(Solid.box(30, 30, 10), [])
    plate = plate.cut(Cyl(8, 8, 2, 0, 10)).cut(Cyl(22, 22, 3, 4, 10))
    err = _refusal(lambda: k.shell(plate, [], 2))
    assert err.predicate == "floor_clears_two_t"
    assert err.measured["stack_xy"] == [22.0, 22.0]
    assert err.measured["floor_height"] == 4.0
    assert err.measured["t"] == 2.0


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


# --- docket R7: degenerate inputs must refuse, never crash raw or degrade ---
#
# `tessellate(cyl, deflection=0.0)` escaped as a raw MemoryError, `-0.5` as a
# raw OverflowError, and NaN sailed straight through every comparison (each is
# False) to SILENTLY return the default-quality mesh — a caller asking for an
# impossible tolerance got 124 triangles and no signal. `shell(box, ['top'],
# 2)` leaked a raw TypeError from `idx >= len(ordered)`. A refusal is a
# finished answer; a raw crash is not.

DEGENERATE_DEFLECTIONS = [0.0, -0.5, float("nan"), float("inf"), 5e-10, "0.1"]


@pytest.mark.parametrize("bad", DEGENERATE_DEFLECTIONS,
                         ids=["zero", "negative", "nan", "inf",
                              "below-floor", "string"])
def test_a_degenerate_deflection_refuses_by_name(k, bad) -> None:
    err = _refusal(lambda: k.tessellate(Cyl(0, 0, 5, 0, 12), deflection=bad))
    assert err.signature.diagnostic == "BadInput"
    assert "deflection" in str(err)


def test_export_stl_checks_the_deflection_before_meshing(k, tmp_path) -> None:
    err = _refusal(lambda: k.export_stl(Cyl(0, 0, 5, 0, 12),
                                        str(tmp_path / "c.stl"),
                                        deflection=float("nan")))
    assert err.signature.diagnostic == "BadInput"
    assert "deflection" in str(err)
    assert not (tmp_path / "c.stl").exists()   # refused BEFORE writing


def test_shell_with_a_named_face_names_the_supported_form(k) -> None:
    """`remove_faces` are indices into entities(shape, 'face'); a string like
    'top' used to hit `idx >= len(ordered)` and leak a raw TypeError."""
    err = _refusal(lambda: k.shell(Solid.box(10, 10, 10), ["top"], 2))
    assert err.signature.diagnostic == "BadInput"
    assert "index" in str(err) or "indices" in str(err)


def test_shell_with_a_negative_face_index_refuses_instead_of_wrapping(k) -> None:
    """Python list semantics made -1 silently mean 'the last face' — an
    ordinal accident, not an answer (ADR-0003 forbids ordinal identity)."""
    err = _refusal(lambda: k.shell(Solid.box(10, 10, 10), [-1], 2))
    assert "out of range" in str(err)


def _flanged_pipe():
    """A Ø25-bore, Ø40-OD pipe run with a Ø70 x 12 flange at each end, as a
    RevolveSolid — what `cylinder -> hole -> boss -> boss` builds today."""
    F_ = Fraction
    return RevolveSolid([(F_(25, 2), F_(0)), (F_(35), F_(0)), (F_(35), F_(12)),
                         (F_(20), F_(12)), (F_(20), F_(138)), (F_(35), F_(138)),
                         (F_(35), F_(150)), (F_(25, 2), F_(150))])


def test_a_bolt_circle_in_a_lathe_says_how_far_off_axis_it_is(k) -> None:
    """Every flange has one, and it is off-axis by definition.

    The refusal used to be `remedy: null`, which reads as "keep guessing":
    nothing said the guard was about COAXIALITY rather than, say, the bore
    diameter or the wall thickness.
    """
    err = _refusal(lambda: k.boolean("cut", _flanged_pipe(),
                                     Cyl(Fraction(55, 2), 0, Fraction(9, 2),
                                         0, Fraction(12))))
    assert err.stage == "K2.2"
    assert err.predicate == "bore_is_coaxial_with_the_lathe"
    assert err.measured["bore_offset_mm"] == pytest.approx(27.5)
    assert err.measured["bore_diameter_mm"] == pytest.approx(9.0)
    assert "27.500" in err.remedy and "coaxial" in err.remedy.lower()


def test_re_boring_a_collared_lathe_names_the_ordering_that_works(k) -> None:
    """`cylinder -> boss -> hole` refuses; `cylinder -> hole -> boss` builds.

    The refusal is correct — an AxisStack has no bore path — but the useful
    fact is that the caller does not need a different design, only a different
    order.
    """
    stack = AxisStack(0, 0, [Cyl(0, 0, Fraction(20), 0, Fraction(150)),
                             Cyl(0, 0, Fraction(35), 0, Fraction(12))])
    err = _refusal(lambda: k.boolean("cut", stack,
                                     Cyl(0, 0, Fraction(25, 2), 0, Fraction(150))))
    assert err.stage == "K2.2"
    assert err.predicate == "base_accepts_a_bore"
    assert err.measured["bore_diameter_mm"] == pytest.approx(25.0)
    assert "order" in err.remedy.lower()


def test_a_quadric_pair_with_no_specialised_path_still_says_something(k) -> None:
    """The fallback must stay actionable rather than reverting to null."""
    err = _refusal(lambda: k.boolean("cut", Cone.make(10, 4, 20), Cone.make(3, 3, 40)))
    assert err.stage == "K2.2"
    assert err.predicate == "operand_pair_has_an_exact_path"
    assert err.remedy and "prism" in err.remedy
