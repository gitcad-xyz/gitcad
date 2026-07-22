"""Shared fixtures. The base suite runs against the pure-Python null kernel, so
no OCCT wheel is needed. Tests marked ``occt`` are skipped at collection time
when the backend is unavailable — collection-time (not fixture-time) skipping
matters because module-scoped fixtures would otherwise instantiate before any
function-scoped skip fixture runs.
"""

from __future__ import annotations

import pytest

from gitcad.kernel.null import NullKernel


@pytest.fixture
def kernel() -> NullKernel:
    return NullKernel()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    try:
        import OCP  # noqa: F401
        return
    except Exception:
        skip = pytest.mark.skip(reason="OCCT (cadquery-ocp) not installed")
        for item in items:
            if item.get_closest_marker("occt"):
                item.add_marker(skip)
