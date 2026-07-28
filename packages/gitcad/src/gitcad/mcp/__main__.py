"""``python -m gitcad.mcp`` — the PATH-proof spelling of ``gitcad-mcp``
(Windows per-user installs land console scripts off PATH, issue #5)."""

from gitcad.mcp.server import main

if __name__ == "__main__":
    main()
