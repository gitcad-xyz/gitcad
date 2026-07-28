"""``gitcad`` — the post-install "now what" (issue #13).

``pip install gitcad`` used to leave a user holding a package with no
application to open and no hint that the thing installed is an MCP server that
must be wired into an agent before it does anything. This command is the
answer: what this is, the exact client wiring (both forms), the viewer story,
and where the docs live. Terse, factual, stdout only — and reachable as
``python -m gitcad`` when console scripts are off PATH (issue #5).
"""

from __future__ import annotations

WIRING_CMD = "claude mcp add gitcad -- gitcad-mcp"
WIRING_JSON = '{ "mcpServers": { "gitcad": { "command": "gitcad-mcp" } } }'
WIRING_JSON_PATHPROOF = ('{ "mcpServers": { "gitcad": { "command": "python", '
                         '"args": ["-m", "gitcad.mcp"] } } }')

# The guide is deliberately pure ASCII: it prints through whatever code page
# the user's console happens to have (cp437 on a stock cmd.exe pipe).
GUIDE = f"""\
gitcad - headless, git-native B-rep CAD (mechanical + electrical).

This package is an MCP server. There is no application to open: wire
`gitcad-mcp` into an MCP client (Claude Code, Claude Desktop, any MCP host)
and the agent drives it. It speaks JSON-RPC over stdio, so running it by hand
only looks like a hang.

Wire it up (either form):

    {WIRING_CMD}

    {WIRING_JSON}

If `gitcad-mcp` is not recognized (Windows per-user installs put console
scripts in a Scripts directory that is typically off PATH), use the
PATH-proof spelling:

    {WIRING_JSON_PATHPROOF}

First contact: once connected, the agent calls the `get_started` tool. It
scans the working directory for existing designs and returns the next steps.

Viewer: the agent opens a live browser viewer with the `viewer_open` tool
(or run `gitcad-view` inside a project). One viewer per project, every part
in-page; it live-reloads as the model files change, and it outlives the
agent session.

Docs: https://gitcad.xyz (start guide + docs) and
https://github.com/gitcad-xyz/gitcad
Console tools: gitcad-init, gitcad-render, gitcad-view, gitcad-review,
gitcad-merge, gitcad-verify, gitcad-convert, gitcad-explore, gitcad-lot,
gitcad-mcp.
"""


def main(argv: list[str] | None = None) -> None:
    import argparse

    import gitcad

    ap = argparse.ArgumentParser(
        prog="gitcad",
        description="Print what gitcad is and how to wire its MCP server "
                    "into a client.")
    ap.add_argument("--version", action="version",
                    version=f"gitcad {gitcad.__version__}")
    ap.parse_args(argv)
    print(GUIDE)


if __name__ == "__main__":  # pragma: no cover
    main()
