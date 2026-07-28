"""INVARIANT: OCP (OCCT) is imported NOWHERE — forge is the sole kernel.

Originally OCP was allowed only in kernel/occt.py (ADR-0002 seam). ADR-0020 cut
OCCT entirely, so the invariant strengthens: no source may import OCP at all.
A seam rule without a test erodes one convenient import at a time; this is the
test that makes the cut permanent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

PACKAGES = Path(__file__).resolve().parent.parent.parent / "packages"
_OCP_IMPORT = re.compile(r"^\s*(from|import)\s+OCP\b", re.MULTILINE)


def test_workspace_layout_exists() -> None:
    """Guard against this test passing vacuously if the tree moves again, and
    assert the OCCT backend is truly gone (ADR-0020)."""
    assert (PACKAGES / "gitcad-core" / "src" / "gitcad").is_dir()
    occt = PACKAGES / "gitcad-mech" / "src" / "gitcad" / "kernel" / "occt.py"
    assert not occt.exists(), "kernel/occt.py should have been removed (ADR-0020)"


def test_ocp_is_imported_nowhere() -> None:
    sources = [p for p in PACKAGES.rglob("*.py") if "__pycache__" not in p.parts]
    assert len(sources) > 20, "suspiciously few sources — layout moved?"
    offenders = [
        str(path.relative_to(PACKAGES))
        for path in sources
        if _OCP_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"OCP imported (OCCT was cut — ADR-0020): {offenders}"


_CORE = PACKAGES / "gitcad-core" / "src" / "gitcad"
_MECH_ECAD_IMPORT = re.compile(
    r"^\s*from gitcad\.(document|kernel|sketch|drawing|ecad|derive|viewer|release|mcp)\b|"
    r"^\s*import gitcad\.(document|kernel|sketch|drawing|ecad|derive|viewer|release|mcp)\b",
    re.MULTILINE)
# reduce/scrub are documented lazy mech-dependents (not re-exported by core).
_CORE_EXEMPT = {_CORE / "report" / "reduce.py", _CORE / "report" / "scrub.py"}


def test_core_is_self_contained() -> None:
    """gitcad-core must import standalone (the registry installs ONLY core) —
    the exact failure the 2026-07-22 registry CI caught when part/__init__
    reached into the mech document model."""
    offenders = [
        str(p.relative_to(_CORE))
        for p in _CORE.rglob("*.py")
        if "__pycache__" not in p.parts and p not in _CORE_EXEMPT
        and _MECH_ECAD_IMPORT.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"core imports domain modules: {offenders}"


@pytest.mark.kernel   # drives the capability probe; the rest of this file is
                      # a pure source lint and must keep running with no kernel
def test_no_operation_crashes_through_the_kernel_seam() -> None:
    """INVARIANT: every seam op on every representation either works or refuses
    HONESTLY. A raw exception escaping the seam is always a defect — callers
    cannot handle it, and it hides a capability gap from the census that drives
    the roadmap (docs/kernel-roadmap.md). 55 such crashes once hid behind
    duck-typing on the planar Solid API."""
    from gitcad.bench.capability import probe

    r = probe()
    crashes = [(s, o, r["detail"].get((s, o), ""))
               for s, row in r["grid"].items()
               for o, v in row.items() if v == "CRASH"]
    assert crashes == [], f"raw exceptions through the seam: {crashes[:5]}"


@pytest.mark.kernel
def test_no_composed_operation_crashes_through_the_kernel_seam() -> None:
    """INVARIANT: the same honesty rule holds for COMPOSED operations (#10) —
    the result of one seam op used as the operand of the next. This is where
    a real modelling session lives, and where 11 crashes hid when the census
    only ever probed fresh solids (a rotated drilled plate cut by a box died
    in `SurdVal ** int`; shelling a cut boss died unpacking a None bbox).
    A refusal is a finished answer; a raw TypeError never is."""
    from gitcad.bench.capability import probe_composed

    r = probe_composed()
    crashes = [(s, o, r["detail"].get((s, o), ""))
               for s, row in r["grid"].items()
               for o, v in row.items() if v == "CRASH"]
    assert crashes == [], f"raw exceptions through the seam: {crashes[:5]}"
