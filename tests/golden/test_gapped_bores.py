"""Two coaxial blind bores separated by a slab of material — the W6 family.

A plate drilled r=2 up from the bottom (z 0..3) and r=3 down from the top
(z 9..12) has two voids and NO shoulder: the bands never touch. The canonical
converter's shoulder loop used to walk ``zip(bands, bands[1:])`` with only an
equal-radius skip, so this shape grew a phantom annulus at z=3 hanging in
solid material. ``mass_props`` (which measures the canonical form) came back
off by exactly 5π while ``validate().ok`` stayed True — a silent wrong number
wearing a green check, the class this kernel exists to make impossible.

The oracle is the independent closed form, not anything the kernel printed:

    V = 20*20*12 − π·2²·3 − π·3²·3 = 4800 − 39π = 4677.477886509998…

Both bores are honest cylinders removed in full from a box; nothing overlaps.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("forgekernel")

from gitcad.kernel.ref import RefKernel

TRUTH = 4800 - 39 * math.pi


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def gapped(k):
    plate = k.box(20, 20, 12)
    d1 = k.boolean("cut", plate,
                   k.transform(k.cylinder(2, 3), translate=(10, 10, 0)))
    return k.boolean("cut", d1,
                     k.transform(k.cylinder(3, 3), translate=(10, 10, 9)))


def test_mass_props_matches_the_closed_form(k, gapped) -> None:
    assert k.mass_props(gapped)["volume"] == pytest.approx(TRUTH, abs=1e-9)


def test_measure_agrees_with_mass_props(k, gapped) -> None:
    m = k.measure(gapped)
    assert m["volume"] == pytest.approx(TRUTH, abs=1e-9)
    assert (m["dx"], m["dy"], m["dz"]) == (20.0, 20.0, 12.0)


def test_validate_ok_is_earned_not_asserted(k, gapped) -> None:
    """ok=True is only meaningful because the canonical form now audits clean:
    every edge paired, volume positive, mesh watertight."""
    from forgekernel import body as B

    rep = k.validate(gapped)
    assert rep.ok and not rep.violations
    assert B.manifold_violations(B.to_body(gapped)) == []


def test_the_mesh_is_watertight(k, gapped) -> None:
    mesh = k.tessellate(gapped, deflection=0.2)
    from collections import Counter

    seen: Counter = Counter()
    for tri in mesh["triangles"]:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            seen[(a, b)] += 1
    assert all(seen.get((b, a), 0) == n for (a, b), n in seen.items())
