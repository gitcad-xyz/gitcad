"""SILENT WRONG (found 2026-07-28, shipped in 0.9.10 and earlier).

``shell`` of a LOFTED (tapered) solid returned a well-formed, `valid=True`
solid holding 206.04 mm³ where the truth is 418.04 — **50.7% wrong**, in the
unsafe direction: the walls are far thinner than the caller asked for.

Root cause. ``_prism_shell`` admitted any wall polygon whose VERTICES sit on
the two caps. A loft's slanted wall satisfies that — its vertices are exactly
on z0 and z1 — so a frustum took the right-prism path and was inset in xy by t
as though its walls were vertical. For a slanted wall the inward offset is
along the wall's own unit normal, which moves it further in xy than t.

Found by a MIRROR INVARIANT sweep, not by any test: shelling commutes with
isometries, so shell(mirror(S)) must equal mirror(shell(S)). It did not —
206.04 against 624.0 for the same solid reflected — and a disagreement there
is a bug regardless of implementation. Neither number was right.

The truth, by two independent methods on the corpus loft (10×10 at z=0 to 6×6
at z=12, volume 784):

  the solid is CONVEX, so distance-to-boundary is the min over six half-space
  distances; the cavity is the points at distance >= t. Its cross-section at
  height z is a square of side 10 − z/3 − √37/3, over z in [1, 11]:

    cavity = ∫₁¹¹ (c − z/3)² dz = (c−1/3)³ − (c−11/3)³,  c = 10 − √37/3
           = 365.9564
    shell  = 784 − 365.9564 = 418.0436

  Monte Carlo, 4M samples: solid 784.157 (exact 784), shell 418.167.

Note the exact answer needs ℚ[√37] — the slanted face normal is (6,0,1)/√37 —
so a general tapered shell is not a ℚ computation, and different tapers bring
different radicals (K3.1). Computing it is real work; RETURNING A WRONG NUMBER
is not an acceptable stand-in, so this refuses.

This costs a capability-grid cell: `loft / shell` was scored "working" while
being 50.7% wrong. A gap that is honest is worth more than a green that lies —
the same lesson as 0.9.6, where the matrix scored blank drawings `ok`.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

TRUE_SHELL = 418.0436          # closed form, corroborated by 4M-sample MC


@pytest.fixture()
def k():
    return RefKernel()


def _frustum(k):
    """The capability corpus's loft: 10×10 at z=0 to 6×6 at z=12."""
    return k.loft([
        ({"start": [0, 0], "segments": [{"kind": "line", "to": [10, 0]},
                                        {"kind": "line", "to": [10, 10]},
                                        {"kind": "line", "to": [0, 10]},
                                        {"kind": "line", "to": [0, 0]}]}, 0.0),
        ({"start": [2, 2], "segments": [{"kind": "line", "to": [8, 2]},
                                        {"kind": "line", "to": [8, 8]},
                                        {"kind": "line", "to": [2, 8]},
                                        {"kind": "line", "to": [2, 2]}]}, 12.0)],
        ruled=True)


def test_the_solid_itself_is_the_frustum_we_derived_against(k):
    """Guard the guard: if the corpus loft ever changes, TRUE_SHELL is stale
    and every assertion below is meaningless."""
    assert k.mass_props(_frustum(k))["volume"] == 784
    assert k.bbox(_frustum(k)) == ((0.0, 0.0, 0.0), (10.0, 10.0, 12.0))


def test_a_tapered_solid_refuses_rather_than_returning_206(k):
    with pytest.raises(KernelError) as exc:
        k.shell(_frustum(k), [], 1)
    assert "taper" in str(exc.value).lower() or "prism" in str(exc.value).lower()


def test_it_must_never_return_the_old_wrong_number(k):
    """Pins the DEFECT, not the refusal: if a future tapered-shell lands, it
    must not reproduce 206.04 (or its mirror image 624.0)."""
    try:
        v = k.mass_props(k.shell(_frustum(k), [], 1))["volume"]
    except KernelError:
        return                                  # refusing is acceptable
    assert v != pytest.approx(206.037, abs=1e-2), "the wrong number is back"
    assert v != pytest.approx(624.0, abs=1e-2), "the mirrored wrong number"
    assert v == pytest.approx(TRUE_SHELL, rel=1e-4)


def test_shelling_commutes_with_reflection(k):
    """The invariant that found this. Whatever shell does with a tapered
    solid — compute or refuse — it must do the SAME thing to its mirror."""
    s = _frustum(k)
    m = k.mirror(s, "xy")
    assert k.mass_props(s)["volume"] == k.mass_props(m)["volume"]

    def outcome(shape):
        try:
            return k.mass_props(k.shell(shape, [], 1))["volume"]
        except KernelError:
            return "refused"

    assert outcome(s) == outcome(m)


def test_right_prisms_are_unaffected(k):
    """The fix must not cost the cases that were always correct."""
    assert k.mass_props(k.shell(k.box(20, 20, 10), [], 2))["volume"] == 2464
    bored = k.boolean("cut", k.box(20, 20, 10),
                      k.transform(k.box(4, 4, 100), translate=(8, 8, -50)))
    assert k.mass_props(k.shell(bored, [], 2))["volume"] == 2688
