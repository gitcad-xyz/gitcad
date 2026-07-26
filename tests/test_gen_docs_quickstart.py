"""The docs generator must not resurrect the pre-ADR-0020 install story.

gitcad.xyz/docs/ regenerates automatically from scripts/gen_docs.py, and the
site's hand-corrected install section (site commit dc3c9ee) was overwritten by
the very next sync because the QUICKSTART string embedded in the generator
still carried the stale text: an `[occt]` extra that ADR-0020 removed, an
`[mcp]` extra that is now a base dependency, and "until the PyPI release
lands" when six packages are live.

These run with no kernel installed — the quickstart is plain text.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _gen_docs():
    spec = importlib.util.spec_from_file_location(
        "gen_docs", ROOT / "scripts" / "gen_docs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_docs"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_quickstart_carries_no_pre_adr_0020_install_text() -> None:
    q = _gen_docs().QUICKSTART
    assert "gitcad[occt]" not in q, "the [occt] extra was removed by ADR-0020"
    assert "gitcad[mcp]" not in q, "the MCP server is a base dependency now"
    assert "Until the PyPI release lands" not in q, "six packages are live"


def test_the_quickstart_matches_the_published_install_story() -> None:
    q = _gen_docs().QUICKSTART
    assert "pip install gitcad" in q
    for pkg in ("gitcad-core", "gitcad-mech", "gitcad-ecad", "gitcad-mcp",
                "forgekernel"):
        assert pkg in q, f"the install paragraph names all six packages ({pkg})"
    assert "adr/0020-forge-sole-kernel.html" in q, "and links ADR-0020"


def test_the_advertised_version_is_read_from_the_metapackage() -> None:
    """A hardcoded version string is the same defect one release later."""
    mod = _gen_docs()
    pyproject = (ROOT / "packages" / "gitcad" / "pyproject.toml").read_text(
        encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert f"({version})" in mod.QUICKSTART
