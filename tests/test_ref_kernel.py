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
    with pytest.raises(KernelError, match="K2"):
        k.cylinder(5, 10)
    with pytest.raises(KernelError, match="K5"):
        k.fillet(k.box(1, 1, 1), None, 0.5)
