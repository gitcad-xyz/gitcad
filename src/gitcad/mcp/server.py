"""gitcad MCP server — the primary, agent-facing interface.

Handlers are plain functions in ``REGISTRY`` so they can be called and tested
directly (no ``mcp`` install needed). ``main()`` exposes them over MCP when the
optional dependency is present.

The tool surface is deliberately intent-level and verification-first: an agent
builds, then *inspects* and *measures*, closing the loop rather than modeling
blind. Every handler returns plain JSON-able dicts.
"""

from __future__ import annotations

from typing import Any, Callable

from gitcad.document import Document, Feature
from gitcad.kernel import get_kernel

Handler = Callable[..., dict[str, Any]]
REGISTRY: dict[str, Handler] = {}


def tool(name: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        REGISTRY[name] = fn
        return fn

    return deco


@tool("model_new")
def model_new() -> dict[str, Any]:
    """Create an empty model; returns its canonical text form."""
    return {"model": Document().dumps()}


@tool("feature_add")
def feature_add(model: str, op: str, params: dict[str, Any] | None = None,
                inputs: list[str] | None = None) -> dict[str, Any]:
    """Append an intent-level feature. Returns the new model text and the stable
    id assigned to the feature (never an ordinal index)."""
    doc = Document.loads(model)
    fid = doc.add(Feature(op=op, params=params or {}, inputs=inputs or []))
    return {"model": doc.dumps(), "feature_id": fid}


@tool("model_measure")
def model_measure(model: str) -> dict[str, Any]:
    """Build against the best available kernel and return mass properties per
    feature — the deterministic oracle an agent verifies against."""
    doc = Document.loads(model)
    kernel = get_kernel()
    shapes = doc.build(kernel)
    return {
        "kernel": kernel.name,
        "measures": {fid: kernel.measure(shape) for fid, shape in shapes.items()},
    }


@tool("model_validate")
def model_validate(model: str) -> dict[str, Any]:
    """Build and run geometric validity checks per feature (watertight,
    self-intersection, ...). Machine-readable so the agent can act on it."""
    doc = Document.loads(model)
    kernel = get_kernel()
    shapes = doc.build(kernel)
    out: dict[str, Any] = {}
    for fid, shape in shapes.items():
        r = kernel.validate(shape)
        out[fid] = {"ok": r.ok, "checks": r.checks, "violations": r.violations}
    return {"kernel": kernel.name, "results": out}


def main() -> None:  # pragma: no cover - process entrypoint
    """Serve the registry over MCP (requires the optional ``mcp`` dependency)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "The MCP server needs the optional dependency. Install with:\n"
            "    pip install 'gitcad[mcp]'\n"
            f"(import error: {exc!r})"
        )

    server = FastMCP("gitcad")
    for name, fn in REGISTRY.items():
        server.add_tool(fn, name=name)
    server.run()
