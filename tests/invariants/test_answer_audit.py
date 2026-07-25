"""Check the ANSWER, not the input. The burn-down's one rule, enforced.

Every silent wrong number this kernel produced came from validating the INPUT
by sampling instead of validating the OUTPUT — a guard probed four points of a
footprint, or asked whether a tool's volume matched its bbox, and a shape that
satisfied the probe but not the property sailed through. A property test can
always be satisfied by something that is not the thing. The constructed body
cannot lie about what it is.

So every op that hand-builds topology now audits what it is about to return,
and this file is the proof that the audit is not decorative: it must reject the
broken bodies below, and it must accept every body the corpus actually builds.
"""

from __future__ import annotations

import pytest

from forgekernel import body as B
from forgekernel.brep import Solid
from forgekernel.quadric import Cyl, DrilledSolid, RoundedBox
from gitcad.errors import GeometryInvalidError
from gitcad.kernel.ref import RefKernel, _audited


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def test_a_dropped_face_is_refused_not_returned() -> None:
    """A body missing a face has four edges used once. That is the shape of a
    rim minted twice, a T-junction left unsplit, or a face lost in a merge —
    the whole family this catches."""
    body = B.to_body(Solid.box(10, 10, 10))
    with pytest.raises(GeometryInvalidError, match="invalid body"):
        _audited(B.Body(body.faces[:-1]), "test")


def test_an_inside_out_body_is_refused() -> None:
    body = B.to_body(Solid.box(10, 10, 10))
    flipped = B.Body(tuple(B.Face(f.surface, f.loops, not f.sense)
                           for f in body.faces))
    with pytest.raises(GeometryInvalidError, match="volume is not positive"):
        _audited(flipped, "test")


def test_the_refusal_says_it_is_a_kernel_defect_not_a_bad_request() -> None:
    """These two are different things and an agent must not confuse them: a
    refusal means "ask differently", an audit failure means "the kernel is
    broken". Retrying with a smaller hole would be pointless here."""
    body = B.to_body(Solid.box(10, 10, 10))
    with pytest.raises(GeometryInvalidError) as e:
        _audited(B.Body(body.faces[:-1]), "test")
    assert e.value.predicate == "answer_is_a_closed_solid"
    assert "report" in e.value.remedy


def test_a_sound_body_passes_through_untouched() -> None:
    body = B.to_body(Solid.box(10, 10, 10))
    assert _audited(body, "test") is body


def test_a_torus_body_is_exempt_from_pairing_but_not_from_volume(k) -> None:
    """Torus faces carry no boundary loops yet (#130), so their rims read as
    unpaired. Failing on a known gap would turn a working op into a refusal —
    the volume check still applies, and the exemption disappears when #130
    lands."""
    filleted = k.fillet(k.cylinder(5, 12), [], 1)
    body = filleted if isinstance(filleted, B.Body) else B.to_body(filleted)
    assert any(isinstance(f.surface, B.Torus) for f in body.faces)
    assert B.manifold_violations(body), "the known gap is still present"
    _audited(body, "test")                    # …and yet it must pass


AUDITED_OPS = [
    ("lathe pocket", lambda k: k.boolean(
        "cut", Cyl(0, 0, 5, 0, 12),
        k.transform(k.box(2, 2, 100), translate=(-1, -1, 6)))),
    ("rounded-box pocket", lambda k: k.boolean(
        "cut", RoundedBox(20, 20, 10, 2), Cyl(10, 10, 2, 6, 15))),
    ("through hole", lambda k: k.boolean(
        "cut", RoundedBox(20, 20, 10, 2), Cyl(10, 10, 2, -5, 15))),
    ("rounded-box shell", lambda k: k.shell(RoundedBox(20, 20, 20, 3), [], 1)),
    ("drilled-plate collar shell", lambda k: k.shell(
        DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)]), [], 1)),
    ("filleted drilled plate", lambda k: k.fillet(
        DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)]), [], 1)),
    ("filleted counterbore", lambda k: k.fillet(
        DrilledSolid(Solid.box(30, 30, 10), [])
        .cut(Cyl(15, 15, 2, 0, 10)).cut(Cyl(15, 15, 4, 7, 10)), [], 1)),
    ("hollow sphere", lambda k: k.shell(k.sphere(10), [], 2)),
]


@pytest.mark.parametrize("label,build", AUDITED_OPS,
                         ids=[a[0] for a in AUDITED_OPS])
def test_every_hand_built_construction_survives_its_own_audit(k, label, build):
    """The audit runs INSIDE these ops, so reaching this line at all means it
    passed. Asserting the result is a real solid states what that bought."""
    out = build(k)
    body = out if isinstance(out, B.Body) else B.to_body(out)
    assert B.volume(body) > 0
    assert k.validate(out).ok
