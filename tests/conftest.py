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

import importlib.util
import os
import pathlib

import pytest

from gitcad.kernel.null import NullKernel


@pytest.fixture
def kernel() -> NullKernel:
    return NullKernel()


# --- the null-kernel base suite (CLAUDE.md, ADR-0002) -------------------------
#
# The constitution says the base suite runs with NO KERNEL INSTALLED. That claim
# had quietly become false: ADR-0018's `@pytest.mark.occt` was deleted in #107
# and nothing replaced it, so there was no way left to say "this test needs
# geometry". The null-kernel CI job went red and stayed red — first aborting at
# collection, then failing 32 tests with 66 errors — while local runs (which
# always have the kernel) stayed green.
#
# Rather than hand-mark hundreds of tests and let the marking drift again, the
# marker is DERIVED: a module that mentions `forgekernel` at all needs geometry.
# That is deliberately conservative — it can mark a test that would have passed
# — because over-skipping costs coverage in one job while under-skipping makes
# the job meaningless, and the whole point of this job is to be trusted.
#
# The floor is enforced: test_null_kernel_suite_is_not_empty asserts the
# surviving selection is substantial, so an over-broad rule that quietly
# selected nothing would fail rather than look green.

def _have_kernel() -> bool:
    """GITCAD_FORCE_NULL_KERNEL=1 reproduces the CI null-kernel job locally.

    Not being able to run that job without uninstalling the kernel is a large
    part of why it rotted: it only ever ran on CI, where nobody was reading it.
    A check you cannot reproduce is a check you will not fix.
    """
    if os.environ.get("GITCAD_FORCE_NULL_KERNEL") == "1":
        return False
    try:
        return importlib.util.find_spec("forgekernel") is not None
    except (ImportError, ValueError):      # not installed, or blocked outright
        return False


# The derived rule scans source for `forgekernel` / `get_kernel`. It CANNOT see
# these: they reach geometry through `Document`, which resolves a kernel
# internally, so the module never names one. Listed explicitly rather than
# widening the rule to `Document` — that word appears in most of the suite, and
# a rule that marks everything tests nothing.
_ALSO_NEEDS_KERNEL = {
    "test_entity_references.py", "test_importers.py", "test_interference.py",
    "test_recognize.py", "test_sketch_extrude.py", "test_model_bom.py",
    "test_p4_ops.py", "test_p8_details_engrave.py", "test_sw_fr1_ops.py",
}

_HAVE_KERNEL = _have_kernel()
_NEEDS_KERNEL: dict[str, bool] = {}


def _module_needs_kernel(path: str) -> bool:
    if path not in _NEEDS_KERNEL:
        try:
            src = pathlib.Path(path).read_text(encoding="utf-8")
            # `forgekernel` covers direct imports; `get_kernel` covers the
            # indirect route, which is the one that kept slipping through --
            # a test can need real geometry without ever naming the package,
            # because the seam hands it whichever kernel is installed.
            _NEEDS_KERNEL[path] = (
                "forgekernel" in src or "get_kernel" in src
                or pathlib.Path(path).name in _ALSO_NEEDS_KERNEL)
        except OSError:
            _NEEDS_KERNEL[path] = False
    return _NEEDS_KERNEL[path]


def pytest_collection_modifyitems(config: pytest.Config,
                                  items: list[pytest.Item]) -> None:
    """ONE collection hook, doing both jobs.

    There were briefly two functions of this name in this file, and Python
    simply binds the second over the first — so the forge_gap skips silently
    stopped happening and 16 skipped became 1, surfacing as 12 "failures" that
    were really unskipped known gaps. Same shape as the defects this suite
    exists to catch: no error, just a quietly wrong answer. Keep it one hook.
    """
    gap = pytest.mark.skip(
        reason="forge capability gap (ADR-0020) — not yet built")
    needs_kernel = pytest.mark.skip(
        reason="needs a real geometry kernel; the base suite runs null "
               "(CLAUDE.md, ADR-0002)")
    for item in items:
        if item.get_closest_marker("forge_gap"):
            item.add_marker(gap)
        if _module_needs_kernel(str(item.fspath)):
            item.add_marker(pytest.mark.kernel)
            if not _HAVE_KERNEL:
                item.add_marker(needs_kernel)
