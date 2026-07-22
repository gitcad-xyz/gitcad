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
    """Register a handler, wrapped in the structured-error contract: an agent
    NEVER sees a raw traceback — failures return machine-actionable
    ``{"ok": false, "error": {...}}``, with the dedup fingerprint attached
    when the failure is a kernel/geometry error (feeds the report pipeline)."""

    def deco(fn: Handler) -> Handler:
        import functools
        import json as _json

        from gitcad.errors import GitcadError, KernelError
        from gitcad.report import fingerprint

        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
            try:
                return fn(*args, **kwargs)
            except KernelError as exc:
                return {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)},
                        "fingerprint": fingerprint(exc.signature)}
            except (GitcadError, ValueError, KeyError, FileNotFoundError,
                    _json.JSONDecodeError, NotImplementedError) as exc:
                return {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}

        REGISTRY[name] = wrapped
        return wrapped

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
    result = doc.build(kernel)
    return {
        "kernel": kernel.name,
        "geometry_verified": not kernel.name.startswith("null"),
        "measures": {fid: kernel.measure(shape) for fid, shape in result.shapes.items()},
    }


@tool("model_validate")
def model_validate(model: str) -> dict[str, Any]:
    """Build and run geometric validity checks per feature (watertight,
    self-intersection, ...). ``geometry_verified: false`` means only the null
    backend was available — structure was checked, geometry was NOT."""
    doc = Document.loads(model)
    kernel = get_kernel()
    result = doc.build(kernel)
    out: dict[str, Any] = {}
    for fid, shape in result.shapes.items():
        r = kernel.validate(shape)
        out[fid] = {"ok": r.ok, "checks": r.checks, "violations": r.violations}
    return {
        "kernel": kernel.name,
        "geometry_verified": not kernel.name.startswith("null"),
        "results": out,
    }


@tool("model_entities")
def model_entities(model: str, feature_id: str, kind: str = "edge") -> dict[str, Any]:
    """Stable entity ids + descriptors for a feature's topology (ADR-0003).
    Use the returned ids in entity-referencing params (e.g. fillet ``edges``) —
    they survive upstream edits because identity re-binds by fingerprint."""
    doc = Document.loads(model)
    kernel = get_kernel()
    result = doc.build(kernel)
    if feature_id not in result.entities:
        raise ValueError(f"unknown feature {feature_id!r}")
    return {
        "kernel": kernel.name,
        "entities": [{"id": eid, **desc} for eid, desc in result.entities[feature_id].get(kind, [])],
    }


@tool("model_export")
def model_export(model: str, path: str, fmt: str = "step") -> dict[str, Any]:
    """Build the model and export the final feature's shape to STEP or STL —
    the mechanical manufacturing deliverable."""
    doc = Document.loads(model)
    if not len(doc):
        raise ValueError("model has no features")
    kernel = get_kernel()
    final = doc.build(kernel).final(doc)
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
    d = make_drawing(doc.build(kernel).final(doc), title=title, sheet=sheet)
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


@tool("model_import")
def model_import(path: str, fmt: str = "auto", assets_dir: str = ".") -> dict[str, Any]:
    """Import existing mechanical work (STEP or FreeCAD .FCStd) into a gitcad
    model. Returns the model text plus an honest report of what was imported,
    approximated, and dropped. Requires the OCCT kernel."""
    kernel = get_kernel(require="occt")
    if fmt == "auto":
        lower = path.lower()
        fmt = "fcstd" if lower.endswith(".fcstd") else "step"
    if fmt == "step":
        from gitcad.importers import import_step_file

        doc, report = import_step_file(path, kernel)
    elif fmt == "fcstd":
        from gitcad.importers import import_fcstd

        doc, report = import_fcstd(path, kernel, assets_dir)
    else:
        raise ValueError(f"unknown import format {fmt!r} (want step|fcstd)")
    return {"model": doc.dumps(), "report": report.to_dict(), "kernel": kernel.name}


@tool("board_import")
def board_import(path: str) -> dict[str, Any]:
    """Import an existing KiCad board (.kicad_pcb) into a gitcad board.
    Pure Python — no kernel needed. The report lists every approximation and
    drop (zones, arcs, complex outlines); nothing is lost silently."""
    from gitcad.importers import import_kicad_pcb

    board, report = import_kicad_pcb(path)
    validation = board.validate()
    return {"board": board.dumps(), "report": report.to_dict(),
            "valid": validation.ok, "violations": validation.violations}


@tool("part_check_release")
def part_check_release(old_part: str, new_part: str) -> dict[str, Any]:
    """Interface-semver release gate (ADR-0009): given old and new part.json
    texts, classify the interface change and verify the version bump suffices.
    The check that stops shipping a breaking change as a patch."""
    from gitcad.part import PartManifest, check_release, classify_change

    old, new = PartManifest.loads(old_part), PartManifest.loads(new_part)
    required, reasons = classify_change(old.interface, new.interface)
    violations = check_release(old.version, new.version, old.interface, new.interface)
    return {"ok": not violations, "required_bump": required,
            "reasons": reasons, "violations": violations}


@tool("assembly_validate")
def assembly_validate(assembly_body: dict[str, Any], parts: list[str]) -> dict[str, Any]:
    """Validate an assembly body (instances + mates) against its parts'
    interfaces: port-type compatibility and positional coincidence — the
    cross-domain co-design check (ADR-0008)."""
    from gitcad.part import Assembly, PartManifest

    by_id = {m.id: m for m in (PartManifest.loads(p) for p in parts)}
    asm = Assembly(assembly_body.get("name", "assembly"))
    for name, inst in assembly_body["instances"].items():
        part = by_id.get(inst["part"])
        if part is None:
            raise ValueError(f"instance {name!r} references unknown part {inst['part']!r}")
        asm.add(name, part, translate=tuple(inst.get("translate", (0, 0, 0))),
                rotate_z_deg=inst.get("rotate_z_deg", 0.0))
    for m in assembly_body.get("mates", []):
        asm.mate(m["a"], m["b"])
    r = asm.validate()
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


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
