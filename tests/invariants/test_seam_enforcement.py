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
