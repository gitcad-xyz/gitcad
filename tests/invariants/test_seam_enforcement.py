"""INVARIANT: the kernel seam is real — OCP imports exist ONLY in kernel/occt.py.

CLAUDE.md's most-stated rule, enforced mechanically (ADR-0002). A seam rule
without a test erodes one convenient import at a time; this is the 10-line
test that makes it permanent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

PACKAGES = Path(__file__).resolve().parent.parent.parent / "packages"
ALLOWED = {PACKAGES / "gitcad-mech" / "src" / "gitcad" / "kernel" / "occt.py"}
_OCP_IMPORT = re.compile(r"^\s*(from|import)\s+OCP\b", re.MULTILINE)


def test_workspace_layout_exists() -> None:
    """Guard against this test passing vacuously if the tree moves again."""
    assert (PACKAGES / "gitcad-core" / "src" / "gitcad").is_dir()
    assert next(ALLOWED.__iter__()).exists()


def test_ocp_is_imported_only_in_the_occt_backend() -> None:
    sources = [p for p in PACKAGES.rglob("*.py") if "__pycache__" not in p.parts]
    assert len(sources) > 20, "suspiciously few sources — layout moved?"
    offenders = [
        str(path.relative_to(PACKAGES))
        for path in sources
        if path not in ALLOWED and _OCP_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"OCP imported outside the kernel seam: {offenders}"


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
