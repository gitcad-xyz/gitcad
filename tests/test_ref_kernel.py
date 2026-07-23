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


def test_ref_refuses_unearned_ops_with_stage() -> None:
    from gitcad.errors import KernelError

    k = RefKernel()
    with pytest.raises(KernelError, match="K3"):
        k.loft([], ruled=False)          # cylinder K2.0, sphere/cone K2.1
    with pytest.raises(KernelError, match="K3"):
        k.sweep({}, [])                  # sweep/loft hold the K3 line


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
