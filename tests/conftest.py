"""Shared fixtures. The base suite runs against the pure-Python null kernel;
the real-geometry tests use the exact forge kernel (``forgekernel``), which is
a default dependency (ADR-0020: forge is the sole geometry kernel — OCCT is no
longer bundled).

Tests marked ``forge_gap`` exercise a capability forge does not yet reach (a
named K2.2/K3.7/K5.2 refusal). They are hand-written contracts kept in-tree and
skipped at collection time; when forge lands the op, drop the marker and they
run. Collection-time (not fixture-time) skipping matters because module-scoped
fixtures would otherwise instantiate before any function-scoped skip fixture.
"""

from __future__ import annotations

import pytest

from gitcad.kernel.null import NullKernel


@pytest.fixture
def kernel() -> NullKernel:
    return NullKernel()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="forge capability gap (ADR-0020) — not yet built")
    for item in items:
        if item.get_closest_marker("forge_gap"):
            item.add_marker(skip)
