"""A bounding box may be loose. It may never be wrong.

Round 10 found `bbox` losing a pointed cone's apex. `bbox` walks each face's
loops, edges and vertices — and a cone's apex is a singular point lying on NO
edge, so it was never visited and the box collapsed along the axis:

    k.scale(k.cone(6, 0, 10), 2)   ->   bbox z-extent 0.0, for a 20 mm solid

The same shape had already been special-cased twice, for `Torus` (a fillet that
eats its neighbour leaves the extreme only on the torus) and for `SphereS` (a
whole sphere carries no loops). The cone apex is the third instance of one
pattern: geometry whose extreme is not on any edge.

WHY THIS MATTERS MORE THAN A LOOSE BOX. `part.interference` uses the AABB as a
skip-filter — `if not aabb_overlaps(...): continue` — so an unsound box does not
merely mis-report a dimension, it silently skips the boolean. A peg sitting
ENTIRELY inside a cone came back `ok=True` with 0 pairs intersected. That is a
wrong answer to a safety question, produced by a routine that never ran.

So this test does not check any particular surface type. It checks the property
that makes an AABB usable at all — the mesh must fit inside it — across the
corpus and under transforms, which is where the collapse actually appeared
(`translate` and z-rotations keep the `Cone` representation and were fine; only
paths converting to a canonical `Body` exposed it).
"""

from __future__ import annotations

import pytest

from gitcad.bench.capability import representations
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def corpus(k):
    out = {}
    for name, shape in representations(k).items():
        if isinstance(shape, tuple) and shape and shape[0] == "<unbuildable>":
            continue
        out[name] = shape
    # The capability corpus's cone is TRUNCATED (r_top=2), so it carries two
    # circular loops and never exercises the singular apex. That is precisely
    # why the defect survived every existing sweep, so the pointed cases are
    # named here rather than left to the corpus to happen to cover.
    out["pointed cone"] = k.cone(6, 0, 10)
    out["pointed cone (wide)"] = k.cone(10, 0, 4)
    out["inverted pointed cone"] = k.cone(0, 6, 10)
    return out


# The transforms that force a conversion to the canonical Body. A plain
# translate keeps the special representation, which is exactly why the defect
# hid: the corpus was only ever bbox-checked in its natural pose.
CASES = [
    ("as built", lambda k, s: s),
    ("scaled 2", lambda k, s: k.scale(s, 2)),
    ("mirrored", lambda k, s: k.mirror(s, "xy")),
    ("rot z 45", lambda k, s: k.transform(s, rotate_axis=(0, 0, 1),
                                          rotate_deg=45)),
]


@pytest.mark.parametrize("label,fn", CASES, ids=[c[0] for c in CASES])
def test_every_mesh_vertex_lies_inside_the_reported_bbox(k, corpus, label, fn):
    """The defining property of a bound. Report every offender at once — one
    broken surface type usually breaks several shapes, and seeing which ones
    names the cause."""
    bad = []
    for name, shape in corpus.items():
        try:
            s = fn(k, shape)
            (lo, hi) = k.bbox(s)
            verts = k.tessellate(s, deflection=0.05)["vertices"]
        except Exception:                       # noqa: BLE001
            continue                            # a refusal is not a wrong bound
        if not verts:
            continue
        lo = [float(v) for v in lo]
        hi = [float(v) for v in hi]
        # a generous float slack: we are catching collapse, not rounding
        tol = 1e-6 * max(1.0, max(hi[i] - lo[i] for i in range(3)))
        for v in verts:
            for i in range(3):
                if v[i] < lo[i] - tol or v[i] > hi[i] + tol:
                    bad.append(
                        f"{name} [{label}]: mesh axis-{i} reaches {v[i]:.4f}, "
                        f"bbox says [{lo[i]:.4f}, {hi[i]:.4f}]")
                    break
            else:
                continue
            break
    assert bad == [], ("the bbox does not contain the solid:\n  "
                       + "\n  ".join(bad))


@pytest.mark.parametrize("label,fn", CASES, ids=[c[0] for c in CASES])
def test_no_bbox_collapses_on_an_axis(k, corpus, label, fn):
    """A zero-width bound on a solid with volume is the specific failure the
    cone apex produced, and it is worth naming separately because it is what
    silently disables the interference pre-filter."""
    bad = []
    for name, shape in corpus.items():
        try:
            s = fn(k, shape)
            (lo, hi) = k.bbox(s)
            vol = float(k.mass_props(s)["volume"])
        except Exception:                       # noqa: BLE001
            continue
        if vol <= 0:
            continue
        for i in range(3):
            if float(hi[i]) - float(lo[i]) <= 0:
                bad.append(f"{name} [{label}]: axis-{i} extent is "
                           f"{float(hi[i]) - float(lo[i])} but volume is {vol}")
    assert bad == [], "a solid with volume cannot be flat:\n  " + "\n  ".join(bad)


def test_interference_does_not_clear_a_peg_that_is_inside_a_cone(k) -> None:
    """The consequence, pinned end to end.

    The peg is entirely within the cone: at z=16 the cone's radius is 2.4 and
    the peg's is 2. Overlap is the peg's whole volume, pi*2^2*10. This came
    back `ok=True` with zero pairs even attempted, because the AABB filter
    rejected the pair before any boolean ran.
    """
    from gitcad.part.interference import check_interference

    cone = k.scale(k.cone(6, 0, 10), 2)          # base r=12 at z=0, apex z=20
    peg = k.cylinder(2, 10)
    rep = check_interference(k, {"cone": (cone, (0, 0, 0), 0.0),
                                 "peg": (peg, (0, 0, 6), 0.0)})
    assert rep.checks["pairs_intersected"] >= 1, (
        "the pair was never tested — the AABB pre-filter rejected a genuine "
        "overlap")
    assert not rep.ok and rep.violations, (
        "a peg fully inside a cone must be reported as interference")
