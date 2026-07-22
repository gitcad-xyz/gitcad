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
        from gitcad.report.fingerprint import fingerprint

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


@tool("sketch_solve")
def sketch_solve(points: dict[str, list[float]],
                 constraints: list[list],
                 profile: list[str] | None = None) -> dict[str, Any]:
    """Solve a 2D constraint sketch (ADR-0013) and return exact coordinates
    — authoring-time only; the solved profile is what goes in the document.
    points: {name: [x, y]} rough positions (they pin the solution branch).
    constraints: [[kind, ...args]] with kinds fix(p,x,y), coincident(p,q),
    horizontal(p,q), vertical(p,q), distance(p,q,d), angle(p,q,deg),
    parallel(p,q,r,s), perpendicular(p,q,r,s), equal_length(p,q,r,s).
    profile: optional point order to emit a closed Profile params dict."""
    from gitcad.sketch_solver import ConstraintSketch

    s = ConstraintSketch()
    for name, (x, y) in points.items():
        s.point(name, x, y)
    two_line = {"parallel", "perpendicular", "equal_length"}
    for c in constraints:
        kind, args = c[0], c[1:]
        if kind in two_line:
            getattr(s, kind)((args[0], args[1]), (args[2], args[3]))
        else:
            getattr(s, kind)(*args)
    result = s.solve()
    out: dict[str, Any] = {"points": {k: list(v) for k, v in result.points.items()},
                           "dof": result.dof, "iterations": result.iterations,
                           "converged": result.converged}
    if profile:
        out["profile"] = s.profile(*profile).to_params()
    return out


@tool("model_mass")
def model_mass(model: str, density_g_cm3: float = 1.0) -> dict[str, Any]:
    """Physical mass properties of the model's final body: volume (mm^3),
    mass (g) at the given density (g/cm^3), center of mass, and the
    unit-density inertia tensor about the COM. The engineering numbers a
    drawing title block or a motion study starts from."""
    doc = Document.loads(model)
    kernel = get_kernel()
    result = doc.build(kernel)
    props = kernel.mass_props(result.final(doc))
    out: dict[str, Any] = {"kernel": kernel.name,
                           "geometry_verified": not kernel.name.startswith("null"),
                           "density_g_cm3": density_g_cm3, **props}
    if "volume" in props:
        out["mass_g"] = props["volume"] * density_g_cm3 / 1000.0  # mm^3 -> cm^3
    return out


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
def model_entities(model: str, feature_id: str, kind: str = "edge",
                   select: str | None = None) -> dict[str, Any]:
    """Stable entity ids + descriptors for a feature's topology (ADR-0003).
    ``select`` filters with the query DSL (e.g. "plane,zmax" = the back face;
    "cylinder"; "line,zmin") instead of manual centroid filtering."""
    doc = Document.loads(model)
    kernel = get_kernel()
    result = doc.build(kernel)
    if feature_id not in result.entities:
        raise ValueError(f"unknown feature {feature_id!r}")
    indexed = result.entities[feature_id].get(kind, [])
    picks = range(len(indexed))
    if select:
        from gitcad.select import select_entities

        picks = select_entities([d for _, d in indexed], select)
    return {
        "kernel": kernel.name,
        "entities": [{"id": indexed[i][0], **indexed[i][1]} for i in picks],
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


@tool("board_pad_position")
def board_pad_position(board: str, pad: str) -> dict[str, Any]:
    """Resolve "REF.pad_name" to absolute board coordinates + side/through/net
    — no more mental pad arithmetic (dogfood friction #1)."""
    from gitcad.ecad import Board, pad_position

    return pad_position(Board.loads(board), pad)


@tool("board_route")
def board_route(board: str, net: str, points: list[dict[str, Any]],
                width: float = 0.4) -> dict[str, Any]:
    """Route a net through waypoints ({"pad": "REF.name"} or {"x","y"},
    optional "layer") — auto-vias on layer changes, wrong-net pads refused,
    SMD side enforced. Returns the updated board text."""
    from gitcad.ecad import Board, route

    b = Board.loads(board)
    r = route(b, net, points, width=width)
    return {"board": b.dumps(), "added": r}


@tool("board_to_model")
def board_to_model_tool(board: str) -> dict[str, Any]:
    """The board as a 3D mech model (outline x thickness, mounting holes cut)
    — ready for assemblies, interference, STEP, and the viewer."""
    from gitcad.bridge import board_to_model
    from gitcad.ecad import Board

    return {"model": board_to_model(Board.loads(board)).dumps()}


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
    lower = path.lower()
    if lower.endswith((".sldprt", ".sldasm", ".slddrw")):
        raise ValueError(
            "SolidWorks files are a proprietary Parasolid-based format no "
            "open-source library can read. Full-fidelity path: export STEP "
            "from SolidWorks (File > Save As > .step), or bulk-convert a whole "
            "library with scripts/sw-batch-export.ps1 (drives your installed "
            "SolidWorks via COM), then import the STEP files."
        )
    kernel = get_kernel(require="occt")
    if fmt == "auto":
        fmt = "fcstd" if lower.endswith(".fcstd") else "step"
    if fmt == "step":
        from gitcad.importers.step import import_step_file

        doc, report = import_step_file(path, kernel)
    elif fmt == "fcstd":
        # Parametric-first: recover the FreeCAD feature tree when it maps and
        # proves out; fall back to geometry-only with the reason reported.
        from gitcad.importers.fcstd_tree import import_fcstd_tree

        doc, report = import_fcstd_tree(path, kernel, assets_dir)
    else:
        raise ValueError(f"unknown import format {fmt!r} (want step|fcstd)")
    return {"model": doc.dumps(), "report": report.to_dict(), "kernel": kernel.name}


@tool("model_recognize")
def model_recognize(model: str) -> dict[str, Any]:
    """Convert dead imported geometry back into a parameterized model — WITH
    PROOF. Recognizes plate-with-holes shapes; the returned model rebuilds to
    exactly the input geometry (symmetric-difference residual ~0) with real,
    editable dimensions. Unrecognizable shapes are reported honestly."""
    from gitcad.importers.recognize import recognize

    doc = Document.loads(model)
    kernel = get_kernel(require="occt")
    r = recognize(doc, kernel)
    out: dict[str, Any] = {"recognized": r.recognized, "proof": r.proof,
                           "holes": [{"x": h.x, "y": h.y, "radius": h.radius} for h in r.holes]}
    if r.recognized:
        out["model"] = r.document.dumps()
    else:
        out["reason"] = r.reason
    return out


@tool("board_import")
def board_import(path: str) -> dict[str, Any]:
    """Import an existing KiCad board (.kicad_pcb) into a gitcad board.
    Pure Python — no kernel needed. The report lists every approximation and
    drop (zones, arcs, complex outlines); nothing is lost silently."""
    from gitcad.importers.kicad import import_kicad_pcb

    board, report = import_kicad_pcb(path)
    validation = board.validate()
    return {"board": board.dumps(), "report": report.to_dict(),
            "valid": validation.ok, "violations": validation.violations}


@tool("schematic_import")
def schematic_import(path: str) -> dict[str, Any]:
    """Import a KiCad schematic (.kicad_sch) into a gitcad schematic. The
    netlist is derived the way KiCad derives it — geometrically, from
    wire-pin connectivity, junctions, labels and power symbols — and the
    report's wire_end_hit_pct self-checks the symbol transforms. Pure
    Python — no kernel needed."""
    from gitcad.importers.kicad_sch import import_kicad_sch

    sch, report = import_kicad_sch(path)
    erc = sch.erc()
    out = {"schematic": sch.dumps(), "report": report.to_dict(),
           "erc_ok": erc.ok, "erc_violations": erc.violations}
    try:
        from gitcad.ecad.schsvg import sheet_to_svg

        out["sheet_svg"] = sheet_to_svg(sch)   # the sheet exactly as drawn
    except GitcadError:
        pass  # no graphics (unusual) — netlist import still succeeds
    return out


@tool("schematic_author")
def schematic_author(name: str, ops: list[list]) -> dict[str, Any]:
    """Author a DRAWN schematic sheet — symbols placed, wires routed, labels
    and power flags set — and get back the netlist derived from the drawing
    (same engine as the KiCad importer), ERC, sheet parity, and a KiCad-style
    SVG. ops is a sequence of:
      ["place", ref, kind, x, y, {value, rot, footprint, pin_types, left,
       right, n}]  (kinds: resistor|capacitor|led|diode|ic|header)
      ["connect", refA, pinA, refB, pinB, [via points...]]
      ["wire", [[x, y], ...]]   ["junction", x, y]
      ["label", net, x, y]      ["power", net, x, y]"""
    from gitcad.ecad.netderive import sheet_parity
    from gitcad.ecad.schsvg import sheet_to_svg
    from gitcad.ecad.sheetedit import SheetEditor

    e = SheetEditor(name)
    for op in ops:
        kind, args = op[0], op[1:]
        if kind == "place":
            kw = args[4] if len(args) > 4 else {}
            e.place(args[0], args[1], args[2], args[3], **kw)
        elif kind == "connect":
            via = [tuple(p) for p in (args[4] if len(args) > 4 else [])]
            e.connect((args[0], args[1]), (args[2], args[3]), *via)
        elif kind == "wire":
            e.wire(*[tuple(p) for p in args[0]])
        elif kind == "junction":
            e.junction(args[0], args[1])
        elif kind == "label":
            e.label(args[0], args[1], args[2])
        elif kind == "power":
            e.power(args[0], args[1], args[2])
        else:
            raise GitcadError(f"unknown sheet op {kind!r}")
    sch = e.finish()
    erc = sch.erc()
    parity = sheet_parity(sch)
    return {"schematic": sch.dumps(), "nets": sch.nets,
            "erc_ok": erc.ok, "erc_violations": erc.violations,
            "parity_ok": parity.ok, "sheet_svg": sheet_to_svg(sch)}


@tool("schematic_sim")
def schematic_sim(schematic: str, checks: list[dict] | None = None) -> dict[str, Any]:
    """Simulation as tests: export the schematic to SPICE (rails become
    ideal sources by the same name contract the envelope checker uses;
    unmodeled parts reported, never dropped) and — when ngspice is
    installed and checks given — run an operating-point analysis asserting
    node voltages: checks=[{"node": "OUT", "min": 3.2, "max": 3.4}]."""
    from gitcad.ecad.schematic import Schematic
    from gitcad.ecad.spice import _find_ngspice, sim_check, to_spice

    sch = Schematic.loads(schematic)
    netlist, report = to_spice(sch)
    out: dict[str, Any] = {"netlist": netlist, "export": report,
                           "simulator": "ngspice" if _find_ngspice() else "unavailable"}
    if checks and _find_ngspice():
        r = sim_check(sch, checks)
        out.update({"ok": r.ok, "checks": r.checks, "violations": r.violations})
    return out


@tool("requirements_verify")
def requirements_verify(requirements: str, root: str) -> dict[str, Any]:
    """Requirements as code: run a canonical requirements document (named
    limits bound to machine checks — mass_max_g, volume_max_mm3,
    bbox_max_mm, erc_clean, envelope_clean, rail_utilization_max,
    drc_clean) against the design tree at root. Every requirement reports
    measured-vs-limit; one without a check shows as 'unchecked' — visible
    debt, never silent green. markdown field = the executing traceability
    matrix."""
    from gitcad.requirements import to_markdown, verify

    report = verify(requirements, root)
    report["markdown"] = to_markdown(report)
    return report


@tool("design_merge")
def design_merge(base: str, ours: str, theirs: str) -> dict[str, Any]:
    """Semantic 3-way merge of a design document (ADR-0016): features by
    stable id for models, components by ref + connectivity by PIN for
    schematics. Parallel edits to different units merge cleanly (a net
    rename merges — pins move together); the same unit changed differently
    returns structured conflicts with both candidates, never text markers.
    Also the git merge driver: gitcad-merge %O %A %B with
    .gitattributes '*.gitcad.json merge=gitcad'."""
    from gitcad.merge3 import merge_documents

    return merge_documents(base, ours, theirs)


@tool("design_review")
def design_review(repo: str, base: str, head: str = "HEAD") -> dict[str, Any]:
    """Review the design changes between two git refs: per-file semantic
    diff (features/components/volume/interface-semver), the CHECK DELTA
    (violations introduced / fixed / pre-existing — ERC, envelopes, board
    validation, DRC), and before/after SVG renders. gate_ok fails on any
    INTRODUCED violation; pre-existing reds don't block (not this PR's
    fault). The markdown field is ready to post as a PR comment."""
    from gitcad.review import review_range, to_markdown

    report = review_range(repo, base, head)
    # renders are large; agents get the verdict + markdown, HTML via CLI
    slim = {**report, "files": [
        {k: v for k, v in f.items() if not k.startswith("render_")}
        for f in report["files"]]}
    slim["markdown"] = to_markdown(report)
    return slim


@tool("board_stats")
def board_stats_tool(board: str) -> dict[str, Any]:
    """Board statistics report: area, component counts by side, SMD/PTH
    pads, routed copper length, vias, zones vs keepouts, drill-size
    histogram — kicad-cli's stats as data."""
    from gitcad.ecad import Board
    from gitcad.ecad.stats import board_stats, net_lengths

    b = Board.loads(board)
    return {"stats": board_stats(b), "net_lengths": net_lengths(b)}


@tool("board_length_match")
def board_length_match(board: str, pairs: list[list],
                       tol_mm: float = 1.0) -> dict[str, Any]:
    """Matched-pair length check (USB, LVDS, clocks): each [netA, netB]
    pair's routed lengths must agree within tol_mm; unrouted members and
    mismatches are named violations."""
    from gitcad.ecad import Board
    from gitcad.ecad.stats import check_length_match

    r = check_length_match(Board.loads(board),
                           [(a, b) for a, b in pairs], tol_mm)
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


@tool("board_back_annotate")
def board_back_annotate(schematic: str, board: str) -> dict[str, Any]:
    """Reverse ECO: board value edits flow back into the schematic source
    (matched by ref); board-only refs are reported, never invented."""
    from gitcad.ecad import Board
    from gitcad.ecad.schematic import Schematic
    from gitcad.ecad.sync import back_annotate

    sch = Schematic.loads(schematic)
    report = back_annotate(sch, Board.loads(board))
    return {"schematic": sch.dumps(), **report}


@tool("schematic_export_kicad")
def schematic_export_kicad(schematic: str) -> dict[str, Any]:
    """Export a KiCad-format netlist (kicadsexpr) — author in gitcad, lay
    out in pcbnew or anything else that reads KiCad netlists."""
    from gitcad.ecad.kicadout import to_kicad_netlist
    from gitcad.ecad.schematic import Schematic

    return {"netlist": to_kicad_netlist(Schematic.loads(schematic))}


@tool("board_ipcd356")
def board_ipcd356(board: str) -> dict[str, Any]:
    """IPC-D-356 electrical test netlist (flying probe / bed-of-nails):
    every netted pad and via as fixed-column records, metric units.
    Structure follows the published layout; not yet conformance-run on a
    physical tester."""
    from gitcad.ecad import Board
    from gitcad.ecad.ipcd356 import to_ipcd356

    return {"ipcd356": to_ipcd356(Board.loads(board))}


@tool("schematic_import_eagle")
def schematic_import_eagle(path: str) -> dict[str, Any]:
    """Import an Eagle .sch (XML): parts + explicit netlist, honest report
    (netlist-only — Eagle pin names stand in for pad numbers until device
    mappings are resolved)."""
    from gitcad.importers.eagle import import_eagle_sch

    sch, report = import_eagle_sch(path)
    erc = sch.erc()
    return {"schematic": sch.dumps(), "report": report.to_dict(),
            "erc_ok": erc.ok, "erc_violations": erc.violations}


@tool("schematic_annotate")
def schematic_annotate_tool(schematic: str) -> dict[str, Any]:
    """Deterministic reference numbering (KiCad-map P4): placeholder refs
    (R?, U?) get the lowest free number per prefix in reading order
    (top-to-bottom, left-to-right); existing numbers never move; nets
    referencing placeholders refuse (ambiguous — annotate before
    connecting). Returns the annotated schematic + the rename map."""
    from gitcad.ecad.annotate import annotate
    from gitcad.ecad.schematic import Schematic

    sch = Schematic.loads(schematic)
    renames = annotate(sch)
    return {"schematic": sch.dumps(), "renames": renames}


@tool("footprint_generate")
def footprint_generate(kind: str, params: dict | None = None) -> dict[str, Any]:
    """Parametric footprint generators (KiCad-map P5) — wizards, agent-first:
    chip(size='0603'), soic(n=8, pitch=1.27), qfn(n=16, pitch=0.5, ep=2.1),
    header(n=6, rows=2). Returns the footprint (pads + courtyard) ready for
    a Board component or footprint_to_part registry publishing."""
    from dataclasses import asdict

    from gitcad.ecad.fpgen import generate

    fp = generate(kind, **(params or {}))
    return {"footprint": asdict(fp)}


@tool("pcba_verify")
def pcba_verify_tool(part: str, root: str) -> dict[str, Any]:
    """Enter a PCBA's electrical workflow as one gate: ERC + electrical
    envelopes per referenced schematic, board validation + DRC + copper
    connectivity, and schematic<->board parity — the Fusion-360 duality:
    a .pcba is mechanical from the outside (envelope, mounting ports, 3D
    body) and this suite is what 'inside' means."""
    from gitcad.pcba import pcba_verify

    return pcba_verify(part, root)


@tool("schematic_envelope")
def schematic_envelope(schematic: str) -> dict[str, Any]:
    """The hardware type system, electrical v1 (ADR-0015): net voltages
    derived from rail names + net_specs, checked against each pin's
    v_abs_max/v_op_min, and rail current draw vs. source capacity —
    overvoltage caught at design time, not bring-up. Coverage is reported
    (pins_with_specs) so green never masquerades as verified. Includes the
    per-rail power budget."""
    from gitcad.ecad.envelope import check_envelopes, power_budget
    from gitcad.ecad.schematic import Schematic

    sch = Schematic.loads(schematic)
    r = check_envelopes(sch)
    out: dict[str, Any] = {"ok": r.ok, "checks": r.checks,
                           "violations": r.violations}
    try:
        out["power_budget"] = power_budget(sch)
    except GitcadError:
        out["power_budget"] = {}   # zero spec coverage — already visible above
    return out


@tool("schematic_system_erc")
def schematic_system_erc(schematics: list[str]) -> dict[str, Any]:
    """Merge multiple board schematics (canonical gitcad text) into one
    system schematic — nets union by NAME (the cross-connector contract) —
    and run ERC on the whole circuit. This is how multi-board designs are
    checked: per-sheet ERC flags interface signals as single-pin; system
    ERC sees the real nets."""
    from gitcad.ecad.schematic import Schematic, merge_schematics

    sheets = [Schematic.loads(s) for s in schematics]
    sys_sch = merge_schematics("system", sheets)
    erc = sys_sch.erc()
    return {"schematic": sys_sch.dumps(), "components": len(sys_sch.components),
            "nets": len(sys_sch.nets), "erc_ok": erc.ok,
            "erc_violations": erc.violations}


@tool("board_annotate")
def board_annotate(board: str, schematic: str,
                   overwrite_conflicts: bool = False) -> dict[str, Any]:
    """Forward annotation (the ECO write path): push the schematic's netlist
    onto board pads, matched by ref + pin number. Mismatches are reported,
    never guessed; existing conflicting nets are kept unless
    overwrite_conflicts. Returns the annotated board text + sync report +
    board_parity result. For multi-board systems pass the merged system
    schematic — refs_missing_on_board then just means 'lives on another
    board'."""
    from gitcad.ecad.board import Board
    from gitcad.ecad.schematic import Schematic, board_parity
    from gitcad.ecad.sync import annotate_board

    b = Board.loads(board)
    sch = Schematic.loads(schematic)
    report = annotate_board(b, sch, overwrite_conflicts=overwrite_conflicts)
    parity = board_parity(sch, b)
    return {"board": b.dumps(), "report": report.to_dict(),
            "parity_ok": parity.ok, "parity_violations": parity.violations}


@tool("board_drc")
def board_drc(board: str, rulepack: str | None = None) -> dict[str, Any]:
    """Design-rule check: clearance, track width, annular ring, drill sizes,
    hole spacing, edge clearance — against a rule pack (default: conservative
    2-layer prototype profile). Rule packs are canonical text and shareable."""
    from gitcad.ecad import Board, RulePack, run_drc

    b = Board.loads(board)
    pack = RulePack.loads(rulepack) if rulepack else None
    r = run_drc(b, pack)
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


@tool("board_connectivity")
def board_connectivity(board: str) -> dict[str, Any]:
    """Copper connectivity check: every net's pads must be joined by actual
    touching copper (tracks/vias), and no copper component may bridge two
    nets. Geometric — catches mislabeled tracks as the shorts they are."""
    from gitcad.ecad import Board, check_connectivity

    r = check_connectivity(Board.loads(board))
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


@tool("schematic_render")
def schematic_render(schematic: str, path: str) -> dict[str, Any]:
    """Render the schematic DIAGRAM (SVG) — symbols, net lanes, junctions:
    the human review surface before layout. Auto-layout; manual placement
    honored via component attrs["at"]."""
    from gitcad.ecad import Schematic, schematic_to_svg

    svg = schematic_to_svg(Schematic.loads(schematic))
    with open(path, "w", newline="\n") as f:
        f.write(svg)
    return {"path": path, "bytes": len(svg)}


@tool("schematic_erc")
def schematic_erc(schematic: str) -> dict[str, Any]:
    """Electrical rule check on a schematic document: pin-type conflicts,
    undriven inputs, unpowered power pins, unconnected pins, degenerate nets.
    'The schematic compiles' as a machine-decidable statement."""
    from gitcad.ecad import Schematic

    s = Schematic.loads(schematic)
    r = s.erc()
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


@tool("schematic_board_parity")
def schematic_board_parity(schematic: str, board: str) -> dict[str, Any]:
    """Schematic <-> board consistency (the ECO check): missing components,
    missing/extra connections, net mismatches — in both directions."""
    from gitcad.ecad import Board, Schematic, board_parity

    r = board_parity(Schematic.loads(schematic), Board.loads(board))
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


@tool("project_release")
def project_release(sources: list[str], outdir: str, version: str) -> dict[str, Any]:
    """Project-Releaser-as-code: run EVERY check (validate/ERC/parity/DRC/fab)
    across the given model/board/schematic documents; only on all-green write
    the full artifact set + sha256 manifest. Red checks = no release."""
    from gitcad.release import release

    r = release(sources, outdir, version)
    return {"ok": r.ok, "version": r.version, "checks": r.checks,
            "failures": r.failures, "artifacts": r.artifacts,
            "manifest": r.manifest_path}


@tool("semantic_diff")
def semantic_diff_tool(old: str, new: str) -> dict[str, Any]:
    """Meaning-level diff between two revisions of the same document text:
    features added/removed/changed by stable id, volume delta, board deltas,
    or interface-semver classification for parts. The PR review surface."""
    from gitcad.release import semantic_diff

    return semantic_diff(old, new)


@tool("assembly_interference")
def assembly_interference(assembly_body: dict[str, Any], models: dict[str, str]) -> dict[str, Any]:
    """EXACT interference check: build each instanced part's real geometry
    (``models``: part id -> model text), place per the assembly transforms,
    boolean-intersect every AABB-overlapping pair. Nonzero common volume =
    collision, measured in mm3. Requires the OCCT kernel."""
    from gitcad.part.interference import check_interference

    kernel = get_kernel(require="occt")
    instances: dict[str, Any] = {}
    for name, inst in assembly_body["instances"].items():
        text = models.get(inst["part"])
        if text is None:
            raise ValueError(f"no model text supplied for part {inst['part']!r}")
        doc = Document.loads(text)
        shape = doc.build(kernel).final(doc)
        instances[name] = (shape, tuple(inst.get("translate", (0, 0, 0))),
                           inst.get("rotate_z_deg", 0.0))
    r = check_interference(kernel, instances)
    return {"ok": r.ok, "checks": r.checks, "violations": r.violations}


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
