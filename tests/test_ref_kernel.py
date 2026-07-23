"""ADR-0018: the ref (forgekernel) backend behind the seam — skipped
when forgekernel is not installed (it lives in gitcad-xyz/forge)."""

import pytest

forgekernel = pytest.importorskip("forgekernel")

from gitcad.document import Document, Feature  # noqa: E402
from gitcad.kernel.ref import RefKernel  # noqa: E402


def test_ref_builds_planar_documents_exactly() -> None:
    k = RefKernel()
    d = Document()
    a = d.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    b = d.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    bm = d.add(Feature(op="move", params={"translate": [5, 5, 5]}, inputs=[b]))
    d.add(Feature(op="boolean", params={"kind": "union"}, inputs=[a, bm]))
    result = d.build(k)
    assert k.mass_props(result.final(d))["volume"] == 1875.0
    assert k.validate(result.final(d)).ok


def test_ref_builds_spring_with_certified_volume() -> None:
    # K3.0 (ADR-0019): helix + pipe = coil spring, the first transcendental
    # geometry — built as a *certified* solid, volume π ρ² L bracketed.
    import math

    from gitcad.bench.corpus import spring

    k = RefKernel()
    d = spring()
    shape = d.build(k).final(d)
    mp = k.mass_props(shape)
    rho, L = 0.75, 6 * math.sqrt((2 * math.pi * 8) ** 2 + 16)
    want = math.pi * rho * rho * L
    assert abs(mp["volume"] - want) < 1e-6           # matches analytic value
    assert mp["volume_halfwidth"] < 1e-30            # certified, very tight
    v = k.validate(shape)
    assert v.ok and v.checks["provenance"] == "certified"


def test_ref_refuses_unearned_ops_with_stage() -> None:
    from gitcad.errors import KernelError

    k = RefKernel()
    with pytest.raises(KernelError, match="K3"):
        k.loft([], ruled=False)          # cylinder K2.0, sphere/cone K2.1
    # helix/pipe GRADUATED at K3.0; planar import_step at K3.6; ruled
    # multi-loft at K3.6. SMOOTH (spline-fit) multi-section lofts hold
    # the K3.7 line.
    sq = {"start": [0, 0], "segments": [
        {"kind": "line", "to": [1, 0]}, {"kind": "line", "to": [1, 1]},
        {"kind": "line", "to": [0, 1]}, {"kind": "line", "to": [0, 0]}]}
    with pytest.raises(KernelError, match="K3.7"):
        k.loft([(sq, 0), (sq, 1), (sq, 2)], ruled=False)


def test_ref_drills_holes_exactly() -> None:
    k = RefKernel()
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 60, "dy": 40, "dz": 4}))
    prev = base
    for i in range(4):
        prev = d.add(Feature(op="hole", params={
            "x": 10 + 13 * i, "y": 20, "top_z": 4, "depth": 4,
            "diameter": 5}, inputs=[prev]))
    result = d.build(k)
    import math

    vol = k.mass_props(result.final(d))["volume"]
    assert vol == 9600 - 100 * math.pi   # float of the EXACT 9600-100π
    faces = k.entities(result.final(d), "face")
    cyls = [f for f in faces if f["surface"] == "cylinder"]
    assert len(cyls) == 4 and cyls[0]["radius"] == 2.5
