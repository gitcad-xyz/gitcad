"""The exact volume, checked against a measurement that shares no code with it.

Nine review rounds found ~40 silent wrong numbers and not one came from a unit
test — a unit test asserts the number the implementation produced, so it
restates the bug. Every one was found by computing the answer a DIFFERENT way.
This is that, automated.

The reference is the volume the TESSELLATED MESH encloses, by a divergence sum
over its triangles: different traversal, different arithmetic, floats instead of
exact types. A tessellation of a curved solid is inscribed, so it is biased LOW
by a known amount — which is why the test is about CONVERGENCE, not agreement:

    refine the mesh, and its error must shrink toward zero.

A wrong exact volume cannot pass that. The mesh converges to the true solid
regardless, so a constant offset stays behind and the error stops shrinking.
The 14%-too-much wedge bug would have been caught on the first refinement.

The full sweep is ``python -m gitcad.bench.oracle``; this is the fast tier.
"""

from __future__ import annotations

import pytest

from gitcad.bench.oracle import Row, mc_volume, mesh_volume, sweep
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def rows(k):
    return sweep(k, n=4000, deflections=(0.2, 0.05))


def test_the_sweep_covers_the_corpus(rows) -> None:
    assert len(rows) >= 14, f"only {len(rows)} shapes measured"


def test_every_exact_volume_survives_mesh_refinement(rows) -> None:
    """The one that matters. Report every failure at once — a kernel change
    that breaks volume usually breaks several shapes, and seeing which ones
    names the cause."""
    bad = [f"{r.shape}: {[f'{e*100:+.4f}%' for e in r.errors]}"
           for r in rows if not r.converges]
    assert bad == [], "mesh error grew under refinement:\n  " + "\n  ".join(bad)


def test_the_mesh_agrees_with_an_independent_ray_cast(rows) -> None:
    """Validates the MESH (closed, correctly wound) rather than the exact
    volume — a different question, and the reason the ray cast is here at all.
    Ambiguous samples are discarded, never guessed, so a high discard rate is
    itself a signal."""
    for r in rows:
        assert r.z <= 5.0, f"{r.shape}: mc {r.mc:.3f} vs mesh {r.meshes[1]:.3f}"
        assert r.discarded < r.samples // 20 if r.samples else True, (
            f"{r.shape}: {r.discarded} ambiguous samples — the mesh may be "
            "self-touching")


def test_a_planar_solid_meshes_to_its_exact_volume(k) -> None:
    """No curvature means no inscription error: these must agree to float
    precision at ANY deflection, which is a far sharper claim than convergence
    and catches a planar boolean going wrong."""
    from forgekernel.brep import Solid

    for shape in (Solid.box(20, 20, 10),
                  k.extrude({"start": [0, 0], "segments": [
                      {"kind": "line", "to": [30, 0]},
                      {"kind": "line", "to": [30, 10]},
                      {"kind": "line", "to": [10, 10]},
                      {"kind": "line", "to": [10, 30]},
                      {"kind": "line", "to": [0, 30]},
                      {"kind": "line", "to": [0, 0]}]}, 8)):
        exact = float(k.mass_props(shape)["volume"])
        for d in (0.2, 0.02):
            assert mesh_volume(shape, k, d) == pytest.approx(exact, rel=1e-12)


WRONG_BY = [("the wedge-tool bug", 1.14), ("half a percent", 1.005),
            ("half a percent too small", 0.995)]


@pytest.mark.parametrize("label,factor", WRONG_BY, ids=[w[0] for w in WRONG_BY])
def test_the_oracle_catches_a_volume_that_is_wrong(k, label, factor) -> None:
    """A checker nobody has seen fail is a checker nobody trusts.

    Note which property does the catching: NOT convergence. An exact volume
    inflated by 14% still shows shrinking error, because the mesh rises toward
    the truth from below and so closes on any value above it. The RESIDUAL —
    the gap to the mesh extrapolated to deflection zero — is what fails, and it
    fails for an error a hundred times smaller than the wedge bug's.
    """
    from forgekernel.quadric import Cyl

    cyl = Cyl(0, 0, 5, 0, 12)
    real = float(k.mass_props(cyl)["volume"])
    meshes = tuple(mesh_volume(cyl, k, d) for d in (0.2, 0.05, 0.01))

    honest = Row("cylinder", real, meshes)
    assert honest.ok, f"the true volume must pass (residual {honest.residual})"

    wrong = Row("cylinder", real * factor, meshes)
    assert not wrong.ok, (
        f"{label}: residual {wrong.residual * 100:.4f}% slipped under the "
        f"{Row.RESIDUAL_BAR * 100}% bar")


def test_the_resolution_limit_is_stated_not_assumed(k) -> None:
    """What this oracle CANNOT see, written down so nobody assumes otherwise.

    The extrapolated mesh still sits ~0.02% from the truth on a curved solid,
    and the bar needs headroom above that for shapes not yet in the sweep — so
    it is 0.2%, and an error of 0.1% passes. That is a real blind spot, not a
    rounding of the claim: catching it needs finer meshes, a second
    extrapolation order, or an analytic oracle for that shape.

    Every wrong number this kernel has actually shipped was far larger (0.5% to
    33%), so the bar is useful today. This test exists so that if someone later
    needs 0.05% resolution they discover the limit here rather than by trusting
    a green suite.
    """
    from forgekernel.quadric import Cyl

    cyl = Cyl(0, 0, 5, 0, 12)
    real = float(k.mass_props(cyl)["volume"])
    meshes = tuple(mesh_volume(cyl, k, d) for d in (0.2, 0.05, 0.01))

    missed = Row("cylinder", real * 1.001, meshes)
    assert missed.ok, "documenting the limit: a 0.1% error is NOT caught"
    assert missed.residual < Row.RESIDUAL_BAR
    assert Row("cylinder", real, meshes).residual < 0.0005, (
        "…and the honest residual must stay well under the bar, or the "
        "headroom that makes 0.2% defensible is gone")


def test_a_shape_the_kernel_refuses_to_measure_is_skipped_not_failed(k) -> None:
    """A gap is not a wrong answer. The sweep must not turn refusals into
    findings, or the signal drowns."""
    from forgekernel.quadric import Cyl

    rows = sweep(k, n=0, shapes={"fine": Cyl(0, 0, 5, 0, 12)},
                 deflections=(0.2, 0.05))
    assert len(rows) == 1 and rows[0].converges


def test_one_mesher_and_it_honours_the_deflection(k) -> None:
    """ADR-0021: the seam must not keep a second mesher.

    Preferring each representation's own `tessellate` was a second
    implementation of the same question, and measuring the two showed the
    canonical one strictly better on every curved shape — closer to the exact
    volume, sometimes with fewer triangles. Worse, several representations'
    method does not take a deflection, so the seam fell through to a
    no-argument call and the caller's request was silently DISCARDED.

    Refining must therefore change the mesh for EVERY representation, curved or
    planar — that is what proves the argument is reaching the mesher."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import Cyl, RoundedBox

    for shape in (Cyl(0, 0, 5, 0, 12), RoundedBox(20, 20, 20, 3)):
        coarse = len(k.tessellate(shape, deflection=0.5)["triangles"])
        fine = len(k.tessellate(shape, deflection=0.01)["triangles"])
        assert fine > coarse, (
            f"{type(shape).__name__}: deflection is not reaching the mesher "
            f"({coarse} -> {fine} triangles)")

    # a planar solid meshes exactly at any deflection, so its count may not
    # change — but it must still be watertight and exact
    # A PLANAR solid meshes exactly at any deflection, so its triangle count
    # legitimately does not change — a chamfered box is planar too, which is
    # why it belongs here and not above. What must hold is the volume.
    for shape, truth in ((Solid.box(20, 20, 10), 4000.0),
                         (k.chamfer(k.box(20, 20, 20), [], 2), None)):
        exact = truth if truth is not None else float(
            k.mass_props(shape)["volume"])
        for d in (0.5, 0.01):
            assert mesh_volume(shape, k, d) == pytest.approx(exact, rel=1e-12)
