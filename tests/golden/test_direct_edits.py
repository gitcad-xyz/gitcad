"""GOLDEN: direct editing — move_face / offset_face / delete_face (+ heal).

SolidWorks-parity direct edits recorded as INTENT (ADR-0022): the feature says
WHICH face (by lineage-stable id) and BY HOW MUCH — never the rebuilt boolean —
and the kernel implements the edit as a RE-PARAMETERIZATION of the owning
representation, never a boolean.

The topology law (the spec these tests pin): a direct edit must be a
homeomorphism of the boundary graph. Any event — an edge collapsing, two faces
merging coplanar, a neighbour face flipping its material side, the target face
vanishing from the result — is a structured REFUSAL carrying the measured
distance to the event, never a silently different solid.

Every volume below is checked against an INDEPENDENT closed form computed in
the test (Steiner, Pappus/Green, prism areas), not against the kernel's own
output. The three worked examples and five refusal traps come from the #132
derivation, all verified by execution before this file was written:

  * drilled plate 8000-90pi: bore offset -70pi, top+2 = 9600-108pi (adjacency
    extension), heal = exactly 8000;
  * filleted box 3328+488/3 pi: heal = 4000, top+3 delta = 1152+12pi;
  * counterbore 8000-76pi: shoulder-2 = -24pi, delete(shoulder) has TWO valid
    heals 120pi apart so auto must refuse;
  * traps: DrilledSolid's z-clamp silently swallowing a shoulder pushed past
    the bottom; an L-prism wall moved past its step building a watertight
    wrong solid (1440) with a flipped shelf face; the exact-coplanar case
    crashing 'collinear points' instead of refusing.
"""

from __future__ import annotations

from fractions import Fraction as Q

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.brep import Solid
from forgekernel.quadric import PiVal, RevolveSolid
from forgekernel.surd import SurdVal
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _refusal(fn) -> KernelError:
    with pytest.raises(KernelError) as e:
        fn()
    return e.value


def _face(k, shape, **want):
    """Index of the single face whose descriptor matches every given item."""
    hits = [i for i, d in enumerate(k.entities(shape, "face"))
            if all(d.get(key) == val for key, val in want.items())]
    assert len(hits) == 1, f"want exactly one face {want}, got {hits}"
    return hits[0]


def _faces(k, shape, **want):
    return [i for i, d in enumerate(k.entities(shape, "face"))
            if all(d.get(key) == val for key, val in want.items())]


def _drilled_plate(k):
    """40x20x10 plate, through bore r=3 at (15,10): V = 8000 - 90pi."""
    plate = k.box(40, 20, 10)
    tool = k.transform(k.cylinder(3, 10), translate=(15, 10, 0))
    return k.boolean("cut", plate, tool)


def _counterbored_plate(k):
    """pilot r=2 z 0..10 + cbore r=4 z 7..10: V = 8000 - 76pi."""
    p = k.box(40, 20, 10)
    p = k.boolean("cut", p, k.transform(k.cylinder(2, 10), translate=(15, 10, 0)))
    return k.boolean("cut", p, k.transform(k.cylinder(4, 3), translate=(15, 10, 7)))


# ---------------------------------------------------------------------------
# Worked example 1: the drilled plate
# ---------------------------------------------------------------------------

def test_offset_bore_wall_enlarges_the_bore_exactly(k) -> None:
    d = _drilled_plate(k)
    assert d.volume() == PiVal(8000, -90)
    wall = _face(k, d, surface="cylinder")
    out = k.offset_face(d, [wall], -1)          # -1 = remove material: r 3->4
    # independent: -pi (4^2 - 3^2) * 10 = -70 pi
    assert out.volume() == PiVal(8000, -160)
    assert out.volume() - d.volume() == PiVal(0, -70)


def test_offset_bore_wall_positive_shrinks_the_bore(k) -> None:
    d = _drilled_plate(k)
    out = k.offset_face(d, [_face(k, d, surface="cylinder")], 1)   # r 3->2
    assert out.volume() == PiVal(8000, -40)


def test_offset_bore_wall_to_zero_radius_refuses(k) -> None:
    d = _drilled_plate(k)
    err = _refusal(lambda: k.offset_face(d, [_face(k, d, surface="cylinder")], 3))
    assert err.predicate == "topology_event"


def test_move_top_face_extends_the_adjacent_through_bore(k) -> None:
    """The bore wall is ADJACENT to the moved cap, so it extends: the hole
    stays a through hole. 9600 - 108pi, NOT the blind reading 9600 - 90pi."""
    d = _drilled_plate(k)
    top = _face(k, d, lineage="box.top")
    out = k.move_face(d, [top], (0, 0, 2))
    assert out.volume() == PiVal(9600, -108)    # 12*800 - pi*9*12


def test_offset_lateral_wall_replays_the_clearance_guard(k) -> None:
    d = _drilled_plate(k)
    right = _face(k, d, lineage="box.right")
    ok = k.offset_face(d, [right], -21)         # wall x=40 -> x=19
    assert ok.volume() == PiVal(3800, -90)
    err = _refusal(lambda: k.offset_face(d, [right], -22))  # x=18: tangent bore
    assert "wall" in str(err)


def test_delete_bore_wall_heals_by_undrilling_exactly(k) -> None:
    d = _drilled_plate(k)
    out = k.delete_face(d, [_face(k, d, surface="cylinder")])
    assert isinstance(out, Solid)
    assert out.volume() == Q(8000)


def test_move_bore_wall_in_plane_moves_the_hole(k) -> None:
    d = _drilled_plate(k)
    out = k.move_face(d, [_face(k, d, surface="cylinder")], (5, 0, 0))
    assert out.volume() == PiVal(8000, -90)     # volume invariant
    moved = k.entities(out, "face")[_face(k, out, surface="cylinder")]
    assert moved["axis_origin"][:2] == [20.0, 10.0]


def test_move_bore_wall_along_z_refuses(k) -> None:
    d = _drilled_plate(k)
    err = _refusal(lambda: k.move_face(
        d, [_face(k, d, surface="cylinder")], (0, 0, 3)))
    assert "shoulder" in (err.remedy or "") or "cap" in (err.remedy or "")


def test_move_bore_wall_into_a_lateral_wall_replays_the_guard(k) -> None:
    d = _drilled_plate(k)
    err = _refusal(lambda: k.move_face(
        d, [_face(k, d, surface="cylinder")], (23, 0, 0)))   # axis x=38, r=3
    assert "wall" in str(err)


# ---------------------------------------------------------------------------
# Worked example 3: the counterbore — shoulders, ambiguity, the clamp trap
# ---------------------------------------------------------------------------

def test_counterbore_enumerates_its_shoulder_face(k) -> None:
    cb = _counterbored_plate(k)
    assert cb.volume() == PiVal(8000, -76)
    sh = k.entities(cb, "face")[_face(k, cb, lineage="bore.shoulder")]
    assert sh["z"] == 7.0
    assert sorted([sh["r_inner"], sh["r_outer"]]) == [2.0, 4.0]


def test_move_shoulder_down_deepens_the_counterbore_exactly(k) -> None:
    cb = _counterbored_plate(k)
    sh = _face(k, cb, lineage="bore.shoulder")
    out = k.move_face(cb, [sh], (0, 0, -2))
    # independent: -pi (4^2 - 2^2) * 2 = -24 pi
    assert out.volume() == PiVal(8000, -100)
    assert out.volume() - cb.volume() == PiVal(0, -24)


def test_move_shoulder_past_the_bottom_refuses_instead_of_clamping(k) -> None:
    """THE CLAMP TRAP: DrilledSolid clamps tools to the base z-extent, so a
    naive rebuild returns 8000-160pi with the pilot wall and shoulder silently
    gone. The op must refuse with the measured distance to the event."""
    cb = _counterbored_plate(k)
    sh = _face(k, cb, lineage="bore.shoulder")
    err = _refusal(lambda: k.move_face(cb, [sh], (0, 0, -8)))   # z 7 -> -1
    assert err.predicate == "topology_event"
    assert err.measured is not None


def test_move_shoulder_onto_the_bottom_face_refuses_tangency(k) -> None:
    cb = _counterbored_plate(k)
    sh = _face(k, cb, lineage="bore.shoulder")
    err = _refusal(lambda: k.move_face(cb, [sh], (0, 0, -7)))   # z 7 -> 0
    assert err.predicate == "topology_event"


def test_delete_shoulder_auto_refuses_naming_both_heals(k) -> None:
    """Two valid closures 120pi apart (8000-160pi vs 8000-40pi): an auto heal
    that picks one is a silent wrong answer."""
    cb = _counterbored_plate(k)
    sh = _face(k, cb, lineage="bore.shoulder")
    err = _refusal(lambda: k.delete_face(cb, [sh]))
    assert err.predicate == "heal_ambiguous"
    vols = sorted(c["volume"] for c in err.measured["candidates"])
    assert vols == pytest.approx([float(PiVal(8000, -160)),
                                  float(PiVal(8000, -40))])
    assert "absorb" in (err.remedy or "")


def test_delete_shoulder_with_absorb_picks_the_named_heal(k) -> None:
    cb = _counterbored_plate(k)
    sh = _face(k, cb, lineage="bore.shoulder")
    walls = _faces(k, cb, surface="cylinder")
    by_r = {k.entities(cb, "face")[i]["radius"]: i for i in walls}
    wide = k.delete_face(cb, [sh], absorb=by_r[4.0])
    assert wide.volume() == PiVal(8000, -160)
    narrow = k.delete_face(cb, [sh], absorb=by_r[2.0])
    assert narrow.volume() == PiVal(8000, -40)


def test_delete_cbore_wall_uncounterbores(k) -> None:
    cb = _counterbored_plate(k)
    cwall = _face(k, cb, surface="cylinder", radius=4.0)
    out = k.delete_face(cb, [cwall])
    assert out.volume() == PiVal(8000, -40)


def test_move_bore_onto_another_bores_axis_refuses(k) -> None:
    """Coaxial cuts are LEGAL, so a hole moved exactly onto another hole's
    axis would silently fuse two stacks into one — a topology event no
    downstream guard would catch. Refused at the edit."""
    p = k.box(60, 20, 10)
    p = k.boolean("cut", p, k.transform(k.cylinder(3, 10), translate=(15, 10, 0)))
    p = k.boolean("cut", p, k.transform(k.cylinder(3, 10), translate=(45, 10, 0)))
    walls = _faces(k, p, surface="cylinder")
    err = _refusal(lambda: k.move_face(p, [walls[0]], (30, 0, 0)))
    assert err.predicate == "topology_event"


def test_offset_shoulder_moves_it_along_its_outward_normal(k) -> None:
    """The shoulder's outward material normal points INTO the wider void
    (+z for a counterbore from the top), so offset +2 makes the cbore
    shallower: removed = pi*4*10 + pi*(16-4)*1 = 52 pi."""
    cb = _counterbored_plate(k)
    out = k.offset_face(cb, [_face(k, cb, lineage="bore.shoulder")], 2)
    assert out.volume() == PiVal(8000, -52)


# ---------------------------------------------------------------------------
# Planar solids: vertex re-solve and its topology-law guards
# ---------------------------------------------------------------------------

def test_move_both_caps_translates_the_slab_exactly(k) -> None:
    """move_face is a TRANSLATE: moving top and bottom by the same vector
    slides the slab (volume invariant); growing both ways is offset_face."""
    box = k.box(40, 20, 10)
    top, bot = _face(k, box, lineage="box.top"), _face(k, box, lineage="box.bottom")
    out = k.move_face(box, [top, bot], (0, 0, 2))
    assert out.volume() == Q(8000)
    assert out.bbox()[0][2] == 2 and out.bbox()[1][2] == 12
    grown = k.offset_face(box, [top, bot], 2)
    assert grown.volume() == Q(11200)                    # 40*20*14

L_LOOP = [(0, 0), (30, 0), (30, 10), (10, 10), (10, 20), (0, 20)]


def test_move_prism_wall_inward_is_exact(k) -> None:
    pr = Solid.prism(L_LOOP, 8)
    wall = _face(k, pr, lineage="prism.side1")          # x=30, spans y 0..10
    out = k.move_face(pr, [wall], (-5, 0, 0))
    assert out.volume() == Q(2800)                       # 3200 - 5*10*8
    assert not out.watertight_violations()


def test_move_prism_wall_to_the_step_refuses_not_crashes(k) -> None:
    """At exactly x=10 the naive rebuild dies with 'collinear points do not
    define a plane' — a crash-class error. The op catches the merge event
    BEFORE constructing and refuses with the measurement."""
    pr = Solid.prism(L_LOOP, 8)
    wall = _face(k, pr, lineage="prism.side1")
    err = _refusal(lambda: k.move_face(pr, [wall], (-20, 0, 0)))
    assert err.predicate == "topology_event"


def test_move_prism_wall_past_the_step_refuses_with_distance(k) -> None:
    """Past x=10 a watertight solid of volume 1440 builds with the shelf face
    silently flipped — a valid, WRONG solid. Refuse with distance-to-event."""
    pr = Solid.prism(L_LOOP, 8)
    wall = _face(k, pr, lineage="prism.side1")
    err = _refusal(lambda: k.move_face(pr, [wall], (-22, 0, 0)))
    assert err.predicate == "topology_event"
    # the event (the step plane at x=10) sits 20 of the requested 22 away
    assert err.measured["fraction_to_event"] == pytest.approx(20 / 22)


def test_offset_box_face_outward_grows_the_box(k) -> None:
    box = k.box(40, 20, 10)
    out = k.offset_face(box, [_face(k, box, lineage="box.top")], 2)
    assert out.volume() == Q(9600)
    lo, hi = out.bbox()
    assert hi[2] == 12


def test_move_box_face_in_plane_is_the_exact_identity(k) -> None:
    box = k.box(40, 20, 10)
    out = k.move_face(box, [_face(k, box, lineage="box.top")], (5, 0, 0))
    assert out.volume() == Q(8000)
    assert out.bbox() == box.bbox()


def test_box_slab_collapse_refuses(k) -> None:
    box = k.box(40, 20, 10)
    err = _refusal(lambda: k.move_face(
        box, [_face(k, box, lineage="box.top")], (0, 0, -10)))
    assert err.predicate == "topology_event"


def test_delete_box_top_has_no_bounded_heal(k) -> None:
    """The four walls are parallel to the removed face's normal and never
    meet: the heal search must PROVE unboundedness, not extrude to infinity."""
    box = k.box(40, 20, 10)
    err = _refusal(lambda: k.delete_face(
        box, [_face(k, box, lineage="box.top")]))
    assert err.predicate == "heal_unbounded"


def test_delete_prism_wall_between_parallel_neighbours_refuses(k) -> None:
    pr = Solid.prism(L_LOOP, 8)
    err = _refusal(lambda: k.delete_face(
        pr, [_face(k, pr, lineage="prism.side1")]))     # neighbours y=0, y=10
    assert err.predicate == "heal_unbounded"


def test_delete_corner_facet_unchamfers_the_prism(k) -> None:
    """Neighbour-extension heal: deleting a diagonal corner wall re-solves the
    two neighbour walls to their sharp meet — the exact un-chamfer."""
    loop = [(0, 0), (28, 0), (30, 2), (30, 10), (10, 10), (10, 20), (0, 20)]
    pr = Solid.prism(loop, 8)
    # independent: L-area (30*10 + 10*10) minus the 2x2/2 corner triangle,
    # extruded 8: (400 - 2) * 8
    assert pr.volume() == Q(3184)
    diag = _face(k, pr, lineage="prism.side1")           # (28,0)->(30,2)
    out = k.delete_face(pr, [diag])
    assert out.volume() == Q(3200)                       # the sharp L-prism
    assert not out.watertight_violations()


# ---------------------------------------------------------------------------
# Lathes: caps slide along the slant, walls offset perpendicular (surds ok)
# ---------------------------------------------------------------------------

def test_move_lathe_cap_extends_along_the_slant(k) -> None:
    fr = RevolveSolid([(0, 0), (8, 0), (2, 8), (0, 8)])   # frustum, 224 pi
    assert fr.volume() == PiVal(0, 224)
    cap = _face(k, fr, surface="plane", z=8.0)
    out = k.move_face(fr, [cap], (0, 0, 2))
    # independent (Green): r(10) = 8 - (3/4)*10 = 1/2; pi*10*(64+4+1/4)/3... no:
    # pi/3 * h * (r1^2 + r1 r2 + r2^2) = pi/3 * 10 * (64 + 4 + 1/4) = 455/2 pi
    assert out.volume() == PiVal(0, Q(455, 2))


def test_offset_lathe_wall_pythagorean_slant_stays_rational(k) -> None:
    fr = RevolveSolid([(0, 0), (8, 0), (2, 8), (0, 8)])
    wall = _face(k, fr, surface="cone")
    out = k.offset_face(fr, [wall], 1)                    # 3-4-5: sec = 5/4
    # independent: radii grow by 5/4: pi*8*((37/4)^2+(37/4)(13/4)+(13/4)^2)/3
    r1, r2 = Q(37, 4), Q(13, 4)
    assert out.volume() == PiVal(0, 8 * (r1 * r1 + r1 * r2 + r2 * r2) / 3)
    assert out.volume() == PiVal(0, Q(673, 2))


def test_offset_lathe_wall_45_degrees_costs_one_radical(k) -> None:
    fr = RevolveSolid([(0, 0), (7, 0), (1, 6), (0, 6)])   # 45-deg wall, 114 pi
    assert fr.volume() == PiVal(0, 114)
    out = k.offset_face(fr, [_face(k, fr, surface="cone")], 1)
    # independent: radii grow by sqrt2: r1=7+s2, r2=1+s2;
    # sum of squares/products = 63 + 24 s2; V = pi*6*(63+24*s2)/3
    assert out.volume() == PiVal(0, SurdVal(126, 48, 2))


def test_delete_lathe_cap_untruncates_to_the_apex(k) -> None:
    fr = RevolveSolid([(0, 0), (8, 0), (2, 8), (0, 8)])
    out = k.delete_face(fr, [_face(k, fr, surface="plane", z=8.0)])
    # independent: wall r = 8-(3/4)z hits the axis at z=32/3:
    # V = pi r1^2 h/3 = pi * 64 * (32/3) / 3 = 2048/9 pi
    assert out.volume() == PiVal(0, Q(2048, 9))


def test_delete_cylinder_lathe_cap_is_unbounded(k) -> None:
    cyl = RevolveSolid([(0, 0), (5, 0), (5, 8), (0, 8)])
    err = _refusal(lambda: k.delete_face(
        cyl, [_face(k, cyl, surface="plane", z=8.0)]))
    assert err.predicate == "heal_unbounded"


def test_offset_tube_inner_wall_follows_the_material_normal(k) -> None:
    """A tube's inner wall faces its axis, so offset -1 (remove material)
    ENLARGES the bore — same convention as a drilled plate's bore wall."""
    ann = RevolveSolid([(2, 0), (5, 0), (5, 8), (2, 8)])
    assert ann.volume() == PiVal(0, 168)                 # (25-4)*8
    inner = _face(k, ann, surface="cylinder", radius=2.0)
    out = k.offset_face(ann, [inner], -1)
    assert out.volume() == PiVal(0, 128)                 # (25-9)*8


def test_offset_cylinder_wall_is_a_radius_change(k) -> None:
    c = k.cylinder(3, 10)
    out = k.offset_face(c, [_face(k, c, surface="cylinder")], 1)
    assert out.volume() == PiVal(0, 160)                  # pi * 16 * 10
    err = _refusal(lambda: k.offset_face(
        c, [_face(k, c, surface="cylinder")], -3))
    assert err.predicate == "topology_event"


def test_move_cylinder_cap_edits_the_height(k) -> None:
    c = k.cylinder(3, 10)
    out = k.move_face(c, [_face(k, c, lineage="cyl.top")], (0, 0, 5))
    assert out.volume() == PiVal(0, 135)                  # pi * 9 * 15
    err = _refusal(lambda: k.move_face(
        c, [_face(k, c, lineage="cyl.top")], (0, 0, -10)))
    assert err.predicate == "topology_event"


# ---------------------------------------------------------------------------
# Worked example 2: the filleted family — blend-follow
# ---------------------------------------------------------------------------

def _steiner(p, q, s, r):
    """Independent oracle: RoundedBox volume by Steiner's formula."""
    rational = p * q * s + 2 * r * (p * q + q * s + s * p)
    return PiVal(rational, r * r * (p + q + s) + Q(4, 3) * r ** 3)


def test_move_rounded_box_top_blend_follows(k) -> None:
    fb = k.fillet(k.box(20, 20, 10), None, 2)
    assert fb.volume() == _steiner(Q(16), Q(16), Q(6), Q(2))
    top = _face(k, fb, lineage="rounded.top")
    out = k.move_face(fb, [top], (0, 0, 3))
    assert out.volume() == _steiner(Q(16), Q(16), Q(9), Q(2))
    # the derivation's pinned delta, against the independent oracle
    assert out.volume() - fb.volume() == PiVal(1152, 12)


def test_move_rounded_box_top_to_the_flat_consumption_refuses(k) -> None:
    """At c = 2r the four side flats vanish and the cap blends go tangent —
    the constructor still accepts c = 4, so the OP must refuse at c <= 2r."""
    fb = k.fillet(k.box(20, 20, 10), None, 2)
    top = _face(k, fb, lineage="rounded.top")
    ok = k.move_face(fb, [top], (0, 0, -5))               # c=5: still legal
    assert ok.volume() == _steiner(Q(16), Q(16), Q(1), Q(2))
    err = _refusal(lambda: k.move_face(fb, [top], (0, 0, -6)))   # c=4=2r
    assert err.predicate == "topology_event"
    err2 = _refusal(lambda: k.move_face(fb, [top], (0, 0, -61 / 10)))
    assert err2.predicate == "topology_event"


def test_offset_a_blend_face_refuses_naming_the_remedy(k) -> None:
    """Offsetting a blend by d breaks tangency with both neighbours: no exact
    same-topology answer exists. The intent-level edit is re-valuing the
    fillet radius — the refusal says so."""
    fb = k.fillet(k.box(20, 20, 10), None, 2)
    blends = [i for i, d in enumerate(k.entities(fb, "face"))
              if d["surface"].startswith("blend")]
    err = _refusal(lambda: k.offset_face(fb, [blends[0]], 1))
    assert err.predicate == "blend_face_tangency"
    assert "radius" in (err.remedy or "")
    err2 = _refusal(lambda: k.move_face(fb, [blends[0]], (0, 0, 1)))
    assert err2.predicate == "blend_face_tangency"


def test_delete_all_blends_sharpens_to_the_exact_box(k) -> None:
    fb = k.fillet(k.box(20, 20, 10), None, 2)
    blends = [i for i, d in enumerate(k.entities(fb, "face"))
              if d["surface"].startswith("blend")]
    assert len(blends) == 20                              # 12 edges + 8 corners
    out = k.delete_face(fb, blends)
    assert isinstance(out, Solid)
    assert out.volume() == Q(4000)
    assert not out.watertight_violations()


def test_delete_a_blend_subset_refuses(k) -> None:
    fb = k.fillet(k.box(20, 20, 10), None, 2)
    blends = [i for i, d in enumerate(k.entities(fb, "face"))
              if d["surface"].startswith("blend")]
    err = _refusal(lambda: k.delete_face(fb, blends[:3]))
    assert "blend" in str(err)


# ---------------------------------------------------------------------------
# can() covers the new ops for free (they live in _SEAM_OPS)
# ---------------------------------------------------------------------------

def test_can_answers_for_direct_edits_without_raising(k) -> None:
    d = _drilled_plate(k)
    wall = _face(k, d, surface="cylinder")
    assert k.can("offset_face", d, [wall], -1)["ok"] is True
    no = k.can("offset_face", d, [wall], 3)               # r -> 0
    assert no["ok"] is False and no.get("predicate") == "topology_event"
    cb = _counterbored_plate(k)
    sh = _face(k, cb, lineage="bore.shoulder")
    no2 = k.can("delete_face", cb, [sh])
    assert no2["ok"] is False and no2.get("predicate") == "heal_ambiguous"


def test_unsupported_representation_refuses_by_name(k) -> None:
    s = k.sphere(5)
    with pytest.raises(KernelError):
        k.move_face(s, [0], (0, 0, 1))


# ---------------------------------------------------------------------------
# The document layer: the feature records intent and REPLAYS (ADR-0022)
# ---------------------------------------------------------------------------

def test_direct_edit_replays_when_upstream_parameters_change(k) -> None:
    """The ADR-0022 payoff: re-value an upstream parameter and the recorded
    face edit re-applies to the re-bound face on the NEW geometry — the
    feature stored intent, not the rebuilt result."""
    from gitcad.document import Document, Feature

    d = Document()
    d.set_parameter("W", 40)
    b = d.add(Feature(op="box", params={"dx": "=W", "dy": 20, "dz": 10}))
    h = d.add(Feature(op="hole", params={"x": 15, "y": 10, "top_z": 10,
                                         "depth": 10, "diameter": 6},
                      inputs=[b]))
    result = d.build(k)
    assert result.shapes[h].volume() == PiVal(8000, -90)
    bore_id = next(eid for eid, desc in result.entities[h]["face"]
                   if desc.get("surface") == "cylinder")
    e = d.add(Feature(op="offset_face",
                      params={"faces": [bore_id], "distance": -1},
                      inputs=[h]))
    assert d.build(k).shapes[e].volume() == PiVal(8000, -160)   # r 3 -> 4
    # now re-value the upstream plate width: the edit REPLAYS
    d.set_parameter("W", 50)
    assert d.build(k).shapes[e].volume() == PiVal(10000, -160)


def test_delete_face_absorb_is_recorded_and_resolved(k) -> None:
    """The counterbore shoulder has two valid heals; the document records
    the chosen absorb face by stable id and the build resolves it."""
    from gitcad.document import Document, Feature

    d = Document()
    b = d.add(Feature(op="box", params={"dx": 40, "dy": 20, "dz": 10}))
    h = d.add(Feature(op="hole", params={"x": 15, "y": 10, "top_z": 10,
                                         "depth": 10, "diameter": 4,
                                         "cbore_diameter": 8,
                                         "cbore_depth": 3},
                      inputs=[b]))
    result = d.build(k)
    assert result.shapes[h].volume() == PiVal(8000, -76)
    faces = result.entities[h]["face"]
    shoulder_id = next(eid for eid, desc in faces
                       if desc.get("lineage") == "bore.shoulder")
    wide_id = next(eid for eid, desc in faces
                   if desc.get("surface") == "cylinder"
                   and desc.get("radius") == 4.0)
    e = d.add(Feature(op="delete_face",
                      params={"faces": [shoulder_id],
                              "heal": {"absorb": wide_id}},
                      inputs=[h]))
    assert d.build(k).shapes[e].volume() == PiVal(8000, -160)
