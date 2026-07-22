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


@tool("model_export")
def model_export(model: str, path: str, fmt: str = "step") -> dict[str, Any]:
    """Build the model and export the final feature's shape to STEP or STL —
    the mechanical manufacturing deliverable."""
    doc = Document.loads(model)
    if not len(doc):
        raise ValueError("model has no features")
    kernel = get_kernel()
    shapes = doc.build(kernel)
    final = shapes[doc.features[-1].id]
    if fmt == "step":
        kernel.export_step(final, path)
    elif fmt == "stl":
        kernel.export_stl(final, path)
    else:
        raise ValueError(f"unknown format {fmt!r} (want step|stl)")
    return {"path": path, "format": fmt, "kernel": kernel.name}


@tool("model_drawing")
def model_drawing(model: str, path: str, title: str = "part", sheet: str = "A3") -> dict[str, Any]:
    """Build the model and emit a dimensioned 2D drawing (SVG or PDF by file
    extension) of the final feature — front/top/right/iso, third angle."""
    from gitcad.drawing import make_drawing

    doc = Document.loads(model)
    if not len(doc):
        raise ValueError("model has no features")
    kernel = get_kernel()
    shapes = doc.build(kernel)
    d = make_drawing(shapes[doc.features[-1].id], title=title, sheet=sheet)
    if path.lower().endswith(".pdf"):
        with open(path, "wb") as f:
            f.write(d.to_pdf())
    else:
        with open(path, "w", newline="\n") as f:
            f.write(d.to_svg())
    return {"path": path, "scale": d.scale, "sheet": d.sheet, "views": [v.name for v in d.views]}


@tool("board_validate")
def board_validate(board: str) -> dict[str, Any]:
    """Fab-readiness checks on a board document. Machine-readable."""
    from gitcad.ecad import Board

    b = Board.loads(board)
    r = b.validate()
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


@tool("board_export_fab")
def board_export_fab(board: str, outdir: str) -> dict[str, Any]:
    """Validate and write the full fabrication package: Gerber X2 layers,
    Excellon drill, pick-and-place CSV, manifest."""
    from gitcad.ecad import Board, export_fab

    b = Board.loads(board)
    files = export_fab(b, outdir)
    return {"files": files, "board": b.name}


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
