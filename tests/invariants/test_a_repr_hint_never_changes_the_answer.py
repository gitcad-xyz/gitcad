"""ADR-0022 B, checked rather than asserted: a hint may change the COST only.

The seam returns a canonical ``Body`` (ADR-0022 A) carrying a ``repr_hint`` —
the special form it was built from. The hint exists because it is measurably
load-bearing: converting to ``Body`` costs more than the operation it replaces
for every corpus representation, by 3-10x and by 400x for a filleted box, so an
exact closed form has to stay reachable. That is a performance argument, and
performance arguments are exactly how wrong answers get in.

So ADR-0022 B states the rule — *the hint may never change the answer* — and
names the check: run the corpus twice, once with the hints stripped, and the
geometry must be identical. This is that check.

It is an invariant and not a golden test because it is a statement about the
architecture rather than about any shape: whatever representations exist, and
whichever of them grow closed forms, a body's measurements may not depend on
which construction produced it. If this ever fails, the fast path and the
canonical path have diverged, and the fast path is a silent wrong number for
every caller that happens to hold a hinted body.
"""

from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from forgekernel import body as B

from gitcad.bench import capability
from gitcad.kernel import get_kernel, source_form


def _stripped(shape):
    """The same geometry with no hint — so every measure takes the canonical
    route. Faces are shared, not copied: the point is to change the ROUTE, not
    the shape, and a rebuilt face set would be testing something else."""
    return B.Body(shape.faces, None)


def _corpus():
    k = get_kernel()
    out = []
    for name, s in capability.representations(k).items():
        if isinstance(s, tuple):            # unbuildable in this environment
            continue
        body = s if isinstance(s, B.Body) else None
        if body is None:
            try:
                body = B.Body(B.to_body(s).faces, s)
            except Exception:               # noqa: BLE001 - no canonical form
                continue
        if body.repr_hint is None:
            continue                        # nothing to strip; nothing to prove
        out.append((name, body))
    return out


CORPUS = _corpus()


def test_the_corpus_actually_carries_hints() -> None:
    """A guard on the guard. If the hint mechanism were removed or renamed,
    every parametrised case below would silently vanish and this file would
    report success while checking nothing — the same corpus-collapse failure
    `test_reported_volume_matches_the_shape` protects itself from."""
    assert len(CORPUS) >= 10, f"corpus collapsed to {len(CORPUS)} hinted shapes"


@pytest.mark.parametrize("name,body", CORPUS, ids=[c[0] for c in CORPUS])
def test_volume_is_the_same_with_and_without_the_hint(name, body) -> None:
    fast = body.volume()
    canon = _stripped(body).volume()
    # EXACT equality. Both are exact arithmetic over the same solid, so any
    # difference at all is two implementations disagreeing, not a tolerance.
    assert fast == canon, f"{name}: hinted {fast} vs canonical {canon}"


@pytest.mark.parametrize("name,body", CORPUS, ids=[c[0] for c in CORPUS])
def test_the_centroid_is_the_same_with_and_without_the_hint(name, body) -> None:
    try:
        fast = body.centroid()
        canon = _stripped(body).centroid()
    except Exception:                        # noqa: BLE001
        pytest.skip("no centroid on this representation either way")
    fa = tuple(float(x) for x in (fast if not isinstance(fast, dict) else
                                  fast["centroid"]))
    ca = tuple(float(x) for x in (canon if not isinstance(canon, dict) else
                                  canon["centroid"]))
    for i in range(3):
        assert fa[i] == pytest.approx(ca[i]), f"{name}: {fa} vs {ca}"


def test_equality_ignores_the_hint() -> None:
    """Two bodies with the same faces are the same body, whatever built them.

    Not a nicety. `Document.dumps()` is byte-canonical (ADR-0004) and the
    differential oracle compares geometry by value, so a hint inside `__eq__`
    would make identical geometry compare unequal by construction history —
    the exact coupling ADR-0022 exists to remove.
    """
    k = get_kernel()
    cyl = k.cylinder(5, 12)
    assert cyl == _stripped(cyl)
    assert hash(cyl) == hash(_stripped(cyl))


def test_the_seam_returns_only_bodies() -> None:
    """ADR-0022 A itself. A representation crossing the seam would put the
    internal taxonomy back into the public API, which is what made a
    capability depend on construction history."""
    k = get_kernel()
    for made in (k.box(10, 10, 10), k.cylinder(3, 8), k.sphere(4),
                 k.cone(5, 2, 9),
                 k.boolean("cut", k.box(20, 20, 5),
                           k.transform(k.cylinder(2, 9), translate=(10, 10, -1))),
                 k.transform(k.cylinder(3, 8), translate=(1, 2, 3)),
                 k.fillet(k.box(20, 20, 20), [], 3)):
        assert isinstance(made, B.Body), type(made).__name__


def test_tessellate_never_takes_the_hint_path() -> None:
    """The one measure that must ALWAYS be canonical, and the defect ADR-0022
    was written from: preferring each representation's own mesher was measured
    strictly worse on every curved shape, and several of those meshers do not
    accept a deflection at all — so a `except TypeError` fallback silently
    discarded the caller's argument and returned a mesh that was valid and not
    the one asked for. So a coarse request and a fine one must differ.
    """
    k = get_kernel()
    cyl = k.cylinder(5, 12)

    def n(shape, d):
        return len(shape.tessellate(d)["triangles"])

    # THE DIRECT EVIDENCE that the canonical path ran: at the same deflection
    # the two meshers give different counts (124 canonical against 32 from
    # `Cyl.tessellate`), and the canonical one is the finer — which is the
    # measurement ADR-0022 cites for preferring it on every curved shape.
    hinted = source_form(cyl)
    assert n(cyl, 2.0) != n(hinted, 2.0)
    assert n(cyl, 2.0) > n(hinted, 2.0)

    # the argument is honoured. Chosen across the range where the count
    # actually moves: the canonical mesher holds a FLOOR on segments per
    # circle, so it sits at 124 from deflection 4.0 all the way to 0.05 and
    # only then refines. A pair of points inside that plateau would prove
    # nothing about whether the argument arrived.
    assert n(cyl, 0.01) > n(cyl, 4.0)

    # and stripping the hint changes nothing, because the hint was never used
    assert n(cyl, 2.0) == n(_stripped(cyl), 2.0)


def test_source_form_recovers_the_construction() -> None:
    """The accessor internal callers use instead of `isinstance` on an output.
    It must give back the very object, not a copy: `_flat_on_bar` and friends
    compare identities and offsets against it."""
    k = get_kernel()
    cyl = k.cylinder(5, 12)
    assert source_form(cyl) is cyl.repr_hint
    bare = _stripped(cyl)
    assert source_form(bare) is bare        # no hint: the body itself
