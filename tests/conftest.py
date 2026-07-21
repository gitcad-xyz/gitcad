"""Shared fixtures. The base suite runs against the pure-Python null kernel, so
no OCCT wheel is needed. Tests that require real geometry use the ``occt`` marker
and skip automatically when the backend is unavailable.
"""

from __future__ import annotations

import pytest

from gitcad.kernel.null import NullKernel


@pytest.fixture
def kernel() -> NullKernel:
    return NullKernel()


@pytest.fixture(autouse=True)
def _skip_occt_if_unavailable(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("occt"):
        try:
            import OCP  # noqa: F401
        except Exception:
            pytest.skip("OCCT (cadquery-ocp) not installed")
