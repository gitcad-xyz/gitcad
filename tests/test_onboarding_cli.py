"""Issues #5/#13: what a user holds right after ``pip install gitcad``.

The package is an MCP server, and nothing in the install path used to say so:
no top-level ``__version__``, no plain ``gitcad`` command, ``--help`` without
the client wiring, and install docs silent on the two Windows/namespace traps
(scripts off PATH, ``gitcad.__file__`` being ``None`` without the metapackage).

These run with no kernel installed — onboarding is plain text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The one wiring line and the one JSON snippet, verbatim, everywhere a user
# might look for them (issue #13: both forms, exactly).
WIRING_CMD = "claude mcp add gitcad -- gitcad-mcp"
WIRING_JSON = '"mcpServers": { "gitcad": { "command": "gitcad-mcp" } }'


def test_the_metapackage_exposes_a_version() -> None:
    import gitcad

    v = gitcad.__version__
    assert isinstance(v, str) and v and v[0].isdigit(), v


def test_the_namespace_still_merges_all_portions() -> None:
    """The pkgutil-style ``__init__`` that carries ``__version__`` must not
    break the four-portion namespace (core, mech, ecad + metapackage)."""
    import gitcad

    assert len(list(gitcad.__path__)) >= 1
    # one module from each sibling portion still imports
    import gitcad.errors      # gitcad-core
    import gitcad.kernel      # gitcad-mech (package import only; no kernel needed)
    import gitcad.ecad        # gitcad-ecad
    import gitcad.bench       # the metapackage itself


def test_the_gitcad_command_says_what_this_is_and_how_to_wire_it(capsys) -> None:
    from gitcad.cli import main

    main([])
    out = capsys.readouterr().out
    assert "MCP server" in out, "the first thing it says is what this is"
    assert WIRING_CMD in out
    assert WIRING_JSON in out
    assert "viewer" in out.lower(), "the viewer story"
    assert "https://gitcad.xyz" in out, "where the docs live"
    assert "get_started" in out, "the first tool an agent should call"


def test_the_gitcad_command_prints_its_version(capsys) -> None:
    import gitcad
    from gitcad.cli import main

    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0
    assert gitcad.__version__ in capsys.readouterr().out


def test_the_gitcad_entry_point_is_declared() -> None:
    pyproject = (ROOT / "packages" / "gitcad" / "pyproject.toml").read_text(
        encoding="utf-8")
    assert re.search(r'^gitcad = "gitcad\.cli:main"$', pyproject, re.M), (
        "the plain `gitcad` console script must ship with the metapackage")


def test_gitcad_mcp_help_prints_transport_and_client_wiring(
        capsys, monkeypatch) -> None:
    """#5: `--help` exits (it used to block on stdin); #13: it prints the
    wiring, both forms, so the terminal is enough to get connected."""
    from gitcad.mcp import server

    monkeypatch.setattr("sys.argv", ["gitcad-mcp", "--help"])
    with pytest.raises(SystemExit) as ei:
        server.main()
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "stdio" in out, "names the transport"
    assert WIRING_CMD in out
    assert WIRING_JSON in out


def test_python_dash_m_gitcad_is_the_path_proof_spelling(
        capsys, monkeypatch) -> None:
    """Windows per-user installs put gitcad-mcp off PATH; `python -m gitcad`
    always resolves, so onboarding must be reachable that way too."""
    import runpy

    monkeypatch.setattr("sys.argv", ["gitcad"])
    runpy.run_module("gitcad", run_name="__main__")
    out = capsys.readouterr().out
    assert "MCP server" in out


@pytest.mark.parametrize("readme", [
    ROOT / "README.md",
    ROOT / "packages" / "gitcad" / "README.md",
], ids=["repo", "metapackage"])
def test_the_readme_install_story_matches(readme: Path) -> None:
    text = readme.read_text(encoding="utf-8")
    assert "gitcad[occt]" not in text, "the [occt] extra was removed (ADR-0020)"
    assert WIRING_CMD in text
    assert WIRING_JSON in text
    assert "PATH" in text and "Scripts" in text, (
        "Windows per-user installs land console scripts off PATH (#5); the "
        "install section must say so and give the escape hatch")
    assert "python -m gitcad" in text, (
        "the PATH-proof spelling of the same command")
    assert "__file__" in text, (
        "the namespace-package caveat: gitcad.__file__ is not a reliable "
        "introspection anchor (#5)")
