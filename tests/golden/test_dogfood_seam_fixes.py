"""Seam-hardening fixes surfaced by dogfooding real parts (not the synthetic
bench): crashes, mislabels, dead-ends, and blind assembly checks."""

from __future__ import annotations

import tempfile
import os

import pytest

pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel import get_kernel
from gitcad.part.interference import check_interference


@pytest.fixture(scope="module")
def k():
    return get_kernel()


def test_entities_carry_a_selection_index_and_fillet_rejects_dicts(k):
    b = k.box(10, 10, 10)
    es = k.entities(b, "edge")
    assert all("index" in e for e in es)
    # the obvious pipeline used to CRASH with a raw TypeError; now clean BadInput
    with pytest.raises(KernelError) as ei:
        k.fillet(b, es, 1.0)
    assert ei.value.signature.diagnostic == "BadInput"
    # and the indices actually select
    out = k.fillet(b, [e["index"] for e in es[:4]], 1.0)
    assert out is not None


def test_a_none_shape_is_clean_bad_input_not_a_raw_traceback(k):
    for call in (lambda: k.mass_props(None),
                 lambda: k.bbox(None),
                 lambda: k.boolean("cut", k.box(4, 4, 4), None)):
        with pytest.raises(KernelError) as ei:
            call()
        assert ei.value.signature.diagnostic == "BadInput", str(ei.value)


def test_a_coaxial_union_can_be_rendered_and_exported(k):
    # coaxial union -> AxisStack, which used to measure but never tessellate or
    # export (a dead end). It now voxel-surfaces for display/export.
    hub = k.boolean("union", k.cylinder(5, 3),
                    k.transform(k.cylinder(2, 6), translate=(0, 0, 3)))
    prev = k.allow_sampled
    k.allow_sampled = True                     # voxel render/export is opt-in
    try:
        mesh = k.tessellate(hub, deflection=0.4)
    finally:
        k.allow_sampled = prev
    seen: dict = {}
    for t in mesh["triangles"]:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            seen[(a, b)] = seen.get((a, b), 0) + 1
    assert sum(1 for (a, b), n in seen.items()
               if seen.get((b, a), 0) != n) == 0, "voxel mesh not watertight"
    prev = k.allow_sampled
    try:
        k.allow_sampled = True
        with tempfile.TemporaryDirectory() as d:
            k.export_step(hub, os.path.join(d, "hub.step"))
            assert os.path.getsize(os.path.join(d, "hub.step")) > 0
    finally:
        k.allow_sampled = prev


def test_sampled_interference_answers_a_shaft_in_a_bore(k):
    # "does it fit?" was UNDETERMINED for any curved pair; sampled answers it,
    # fail-closed: a fitting shaft clears, an oversize one clashes.
    tube = k.boolean("cut", k.cylinder(15, 20), k.cylinder(8, 20))
    fits = check_interference(
        k, {"tube": (tube, (0, 0, 0), 0),
            "shaft": (k.cylinder(7, 20), (0, 0, 0), 0)},
        sampled=True, tol_mm3=1.0)
    assert fits.ok, fits.violations
    clash = check_interference(
        k, {"tube": (tube, (0, 0, 0), 0),
            "shaft": (k.cylinder(9, 20), (0, 0, 0), 0)},
        sampled=True, tol_mm3=1.0)
    assert not clash.ok and clash.checks["overlaps_mm3"]
