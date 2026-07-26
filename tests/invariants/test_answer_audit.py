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

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

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


def test_the_positivity_check_survives_a_volume_outside_Q_pi() -> None:
    """The audit must decide the SIGN of a volume in any exact field it meets,
    not just ℚ[π].

    A napkin ring's volume is (140/3)√35·π — a ``PiVal`` whose π coefficient is
    a ``SurdVal``. Ordering that against a bare 0 used to raise "'<=' not
    supported between instances of 'PiVal' and 'int'", because
    ``PiPoly.from_pival`` forced both coefficients through the stdlib
    ``Fraction`` and ``PiVal._cmp`` swallowed the resulting ``TypeError`` into
    ``NotImplemented``. The audit could not check the one thing it exists to
    check, and it announced that as an operator-protocol message three modules
    from the cause.

    Both directions are pinned: the sound ring passes, and the same ring turned
    inside out is still caught — a widened field must not widen the hole.
    """
    from forgekernel.surdrev import NapkinRing

    body = B.to_body(NapkinRing(6, 1))
    assert B.volume(body).sign() == 1
    assert _audited(body, "test") is body

    flipped = B.Body(tuple(B.Face(f.surface, f.loops, not f.sense)
                           for f in body.faces))
    with pytest.raises(GeometryInvalidError, match="volume is not positive"):
        _audited(flipped, "test")


def test_a_torus_body_is_no_longer_exempt_from_pairing(k) -> None:
    """#130 landed: a lathe's torus faces carry their rims as loops, so the
    pairing audit sees filleted lathes whole — and the blanket exemption for
    any body containing a torus (a pardon for exactly the bodies most likely
    to be hand-assembled wrong) is gone with the gap that excused it."""
    filleted = k.fillet(k.cylinder(5, 12), [], 1)
    body = filleted if isinstance(filleted, B.Body) else B.to_body(filleted)
    assert any(isinstance(f.surface, B.Torus) for f in body.faces)
    assert B.manifold_violations(body) == [], "#130: rims must pair"
    _audited(body, "test")
    # …and the PUBLIC validate agrees. Before #130 it reported this sound body
    # ok=False with four "edge arc used by 1 face(s), not 2" violations — a
    # false negative that contradicted the internal audit on the same body.
    assert k.validate(filleted).ok

    # …and a torus body that IS open must now refuse. Stripping the torus's
    # loops changes nothing the mesh check can see (the torus meshes from its
    # surface k0/span, not its loops) and nothing the volume check can see —
    # ONLY edge pairing catches it, so this pins that pairing actually runs.
    stripped = B.Body(tuple(
        B.Face(f.surface, (), f.sense) if isinstance(f.surface, B.Torus)
        else f for f in body.faces))
    with pytest.raises(GeometryInvalidError, match="invalid body"):
        _audited(stripped, "test")


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


def test_a_drilled_cut_whose_canonical_form_is_torn_refuses(k, monkeypatch):
    """W6's escape route, closed. The drilled-cut path returned
    ``base.cut(b)`` UNAUDITED, so when ``from_drilled`` grew a phantom
    shoulder between two gapped coaxial bores, the wrong body reached
    ``mass_props`` (off by an exact pi multiple) with ``validate().ok`` —
    the worst class this kernel has: a silent wrong number wearing a green
    check. The geometry defect is fixed in forge (the shoulder loop now
    skips non-touching bands); this pins the NET, by reinstating the defect
    at the converter and requiring the cut to refuse rather than return."""
    from forgekernel import body as fb

    real = fb.from_drilled

    def phantom(d):
        body = real(d)
        # hang one face's worth of extra annulus in the material: the exact
        # signature of the W6 defect (rims used 3x and 1x, volume off by 5*pi)
        cx, cy, z, rin, rout = fb.F(10), fb.F(10), fb.F(3), fb.F(2), fb.F(3)
        outer = fb._circle_at(cx, cy, z, rout)
        inner = fb._circle_at(cx, cy, z, rin)
        vo, vi = (cx + rout, cy, z), (cx + rin, cy, z)
        shoulder = fb.Face(fb.Plane((fb.F(0), fb.F(0), fb.F(1)), z),
                           (fb.Loop((fb.Edge(outer, vo, vo),)),
                            fb.Loop((fb.Edge(inner, vi, vi),))), True)
        return fb.Body(body.faces + (shoulder,))

    plate = k.box(20, 20, 12)
    d1 = k.boolean("cut", plate,
                   k.transform(k.cylinder(2, 3), translate=(10, 10, 0)))
    monkeypatch.setattr(fb, "from_drilled", phantom)
    with pytest.raises(GeometryInvalidError, match="invalid body"):
        k.boolean("cut", d1,
                  k.transform(k.cylinder(3, 3), translate=(10, 10, 9)))


# --- round 9, tier 1: two wrong numbers through the public seam --------------

COMPOUNDS = [
    ("two overlapping boxes", lambda k: [k.box(2, 2, 2),
                                         k.transform(k.box(2, 2, 2),
                                                     translate=(1, 1, 1))], 15),
    ("disjoint (the fast path)", lambda k: [k.box(2, 2, 2),
                                            k.transform(k.box(2, 2, 2),
                                                        translate=(10, 10, 10))], 16),
    ("touching face to face", lambda k: [k.box(2, 2, 2),
                                         k.transform(k.box(2, 2, 2),
                                                     translate=(2, 0, 0))], 16),
    ("one nested inside the other", lambda k: [k.box(10, 10, 10),
                                               k.transform(k.box(4, 4, 4),
                                                           translate=(3, 3, 3))], 1000),
    ("identical twice", lambda k: [k.box(3, 3, 3), k.box(3, 3, 3)], 27),
]


@pytest.mark.parametrize("label,build,truth", COMPOUNDS,
                         ids=[c[0] for c in COMPOUNDS])
def test_a_compound_measures_its_point_set_not_its_faces(k, label, build,
                                                         truth) -> None:
    """`compound` was a poly SOUP — every member's faces piled together. For
    disjoint bodies that is right and cheap; for overlapping ones the interior
    faces are still faces, and volume is a divergence sum over faces, so the
    overlap got counted twice.

    Two boxes sharing a unit corner reported 16 for a true 15, and cuts against
    such a tool were wrong about 0.5% of the time over random compounds — two
    thirds of those returning MATERIAL where the answer had to be empty, with
    validate() saying ok throughout."""
    assert k.mass_props(k.compound(build(k)))["volume"] == pytest.approx(truth)


def test_cutting_with_an_overlapping_compound_is_right(k) -> None:
    """The tool is a nested pair, so the naive soup counted its inner shell a
    second time, inverted."""
    tool = k.compound([k.transform(k.box(10, 10, 10), translate=(10, 10, 10)),
                       k.transform(k.box(20, 20, 30), translate=(10, 10, 0))])
    assert k.mass_props(tool)["volume"] == pytest.approx(12000)
    cut = k.boolean("cut", k.box(30, 30, 30), tool)
    assert k.mass_props(cut)["volume"] == pytest.approx(15000)


LAMINATED = [
    ("three plates, bore through", [0, 5, 10], (20, 20, 5), 15, 6000, 60),
    ("two pairs with a gap", [0, 1, 8, 9], (20, 20, 1), 10, 1600, 16),
]


@pytest.mark.parametrize("label,zs,dims,h,solid,bore", LAMINATED,
                         ids=[l[0] for l in LAMINATED])
def test_a_laminated_stack_counts_every_plate_it_drills(k, label, zs, dims, h,
                                                        solid, bore) -> None:
    """`_column_slabs` keyed its level set on z ALONE, so a shared interface —
    which contributes an up-facing cap AND a down-facing one at the same height
    — was counted once, and the floor/ceiling parity inverted from there up.

    Three stacked plates drilled through recorded two bores instead of three
    (5853.39 against a true 5811.50); four plates in two pairs billed 6 mm of
    pure air as metal. The kernel already knew better — `union` of the same
    plates gave the right answer — it simply was not asked.

    The fix sweeps the caps with a depth counter, so a shared interface opens
    and closes in the same breath and cancels."""
    import math

    stack = k.compound([k.transform(k.box(*dims), translate=(0, 0, z))
                        for z in zs])
    assert k.mass_props(stack)["volume"] == pytest.approx(solid)
    out = k.boolean("cut", stack,
                    k.transform(k.cylinder(2, h), translate=(10, 10, 0)))
    assert k.mass_props(out)["volume"] == pytest.approx(solid - bore * math.pi)


def test_a_shelled_plate_still_bores_through_two_slabs(k) -> None:
    """The case the parity code was written for, which must keep working: an
    outer top and bottom plus the void's ceiling and floor is genuinely two
    slabs, and only the walls carry material."""
    import math

    sh = k.shell(k.box(20, 20, 10), [], 2)
    out = k.boolean("cut", sh, k.transform(k.cylinder(2, 12),
                                           translate=(10, 10, -1)))
    assert k.mass_props(out)["volume"] == pytest.approx(
        float(k.mass_props(sh)["volume"]) - 4 * math.pi * 4)
