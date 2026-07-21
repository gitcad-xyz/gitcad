"""The MCP surface — gitcad's PRIMARY interface.

Design rule (ADR-0002): the MCP tool surface is designed first and the Python
API is a thin binding over the same handlers, not the reverse. If MCP is the
primary interface it never rots, because it is the interface everything (agents,
the web UI, humans) actually uses.

:mod:`gitcad.mcp.server` defines the tool handlers as plain, importable
functions (a registry) so they are unit-testable with no ``mcp`` dependency, and
wraps them as MCP tools only when the optional ``mcp`` package is present.
"""

from gitcad.mcp.server import REGISTRY, main

__all__ = ["REGISTRY", "main"]
