"""FreeCAD .FCStd importer — no FreeCAD installation required.

An .FCStd file is a zip containing ``Document.xml`` (the parametric object
graph) plus one OCCT-native ``.brep`` file per shape-bearing object. Since
gitcad sits on the same OCCT kernel, we read those breps directly: users get
their exact FreeCAD geometry with full fidelity.

What imports: the geometry of every object (combined into one compound, with
per-object names reported). What doesn't: FreeCAD's parametric feature history
(sketches, constraints, expressions) — reported as dropped, never silently.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.importers.report import ImportReport
from gitcad.seams import Kernel


def import_fcstd_bodies(path: str, kernel: Kernel) -> list[tuple[str, "object"]]:
    """Named bodies of a multi-body .FCStd: [(object_name, Shape)].

    FreeCAD stores one ``<Object>.Shape.brp`` per body — the per-part access
    that multi-part enclosure scripts need (the real Altair case is five
    enclosure solids + reference internals in ONE document; per-part STEP
    export and pairwise interference both start here)."""
    import tempfile

    out: list[tuple[str, object]] = []
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist()
                   if n.lower().endswith((".brep", ".brp"))]
        if not members:
            raise GitcadError(f"{path!r} contains no .brep geometry")
        with tempfile.TemporaryDirectory() as td:
            for member in sorted(members):
                name = Path(member).name
                for suffix in (".Shape.brp", ".Shape.brep", ".brp", ".brep"):
                    if name.endswith(suffix):
                        name = name[: -len(suffix)]
                        break
                tmp = Path(td) / ("b_" + Path(member).name)
                tmp.write_bytes(zf.read(member))
                out.append((name, kernel.import_brep(str(tmp))))
    return out


def fcstd_to_project(path: str, out_dir: str, kernel: Kernel,
                     *, name: str | None = None) -> dict:
    """One-command onboarding: a multi-body .FCStd becomes a gitcad project.

    Every body becomes ``<Body>.model`` (import feature pinning a
    content-addressed .brep in assets/) + ``<Body>.part`` (interface derived
    from real geometry), and ``<name>.gitcad`` is the product root
    instancing them all at their as-modeled positions. From there the whole
    toolchain applies: viewer/explode, interference with clash budgets,
    review gates, release.
    """
    from gitcad.derive import model_to_part
    from gitcad.part import Assembly, new_part_id

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assets = out / "assets"
    assets.mkdir(exist_ok=True)
    project = name or Path(path).stem

    bodies = import_fcstd_bodies(path, kernel)
    asm = Assembly(project)
    written: list[str] = []
    for body_name, shape in bodies:
        brep = assets / f"{body_name}.brep"
        kernel.export_brep(shape, str(brep))
        digest = hashlib.sha256(brep.read_bytes()).hexdigest()
        final = assets / f"{body_name}-{digest[:12]}.brep"
        if final.exists():
            brep.unlink()
        else:
            brep.rename(final)
        digest = hashlib.sha256(final.read_bytes()).hexdigest()
        doc = Document()   # project-relative reference (what gets committed)
        doc.add(Feature(op="import", params={
            "format": "brep", "file": f"assets/{final.name}", "sha256": digest}))
        build_doc = Document()   # absolute reference, for derivation here
        build_doc.add(Feature(op="import", params={
            "format": "brep", "file": str(final), "sha256": digest}))
        part = model_to_part(build_doc, kernel,
                             part_id=new_part_id(), name=body_name)
        part.body["model"] = f"{body_name}.model"
        (out / f"{body_name}.model").write_text(doc.dumps(), encoding="utf-8")
        (out / f"{body_name}.part").write_text(part.dumps(), encoding="utf-8")
        written += [f"{body_name}.model", f"{body_name}.part",
                    f"assets/{final.name}"]
        asm.add(body_name, part)     # bodies are already world-positioned

    root = asm.to_manifest(new_part_id())
    (out / f"{project}.gitcad").write_text(root.dumps(), encoding="utf-8")
    written.append(f"{project}.gitcad")
    return {"project": project, "root": f"{project}.gitcad",
            "bodies": [n for n, _ in bodies], "written": written}


def import_fcstd(path: str, kernel: Kernel, assets_dir: str) -> tuple[Document, ImportReport]:
    """Import an .FCStd file. Extracted geometry is consolidated into one
    content-addressed ``.brep`` in ``assets_dir`` (which becomes source — keep
    it with the model). Returns (document, report)."""
    report = ImportReport(source=path, format="fcstd")
    assets = Path(assets_dir)
    assets.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        # FreeCAD writes both extensions: .brep (older) and .brp (current)
        brep_members = [n for n in names if n.lower().endswith((".brep", ".brp"))]
        if not brep_members:
            raise GitcadError(f"{path!r} contains no .brep geometry (empty or unsupported document)")

        # Object labels from Document.xml, best-effort (nice names in the report).
        labels: list[str] = []
        if "Document.xml" in names:
            xml = zf.read("Document.xml").decode("utf-8", errors="replace")
            labels = re.findall(r'<Object\s+name="([^"]+)"', xml)

        shapes = []
        for member in sorted(brep_members):
            tmp = assets / ("_extract_" + Path(member).name)
            tmp.write_bytes(zf.read(member))
            try:
                shapes.append(kernel.import_brep(str(tmp)))
                report.count("objects", 1)
            finally:
                tmp.unlink(missing_ok=True)

    combined = shapes[0] if len(shapes) == 1 else kernel.compound(shapes)

    # Content-addressed artifact: the imported geometry, one file, pinned.
    stem = Path(path).stem
    out_path = assets / f"{stem}.brep"
    kernel.export_brep(combined, str(out_path))
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    final_path = assets / f"{stem}-{digest[:12]}.brep"
    if final_path.exists():
        out_path.unlink()   # content-addressed: same name == same bytes
    else:
        out_path.rename(final_path)
    digest = hashlib.sha256(final_path.read_bytes()).hexdigest()

    doc = Document()
    doc.add(Feature(op="import", params={"format": "brep", "file": str(final_path), "sha256": digest}))

    if labels:
        report.warnings.append(f"objects imported as one compound: {', '.join(labels[:20])}")
    report.dropped.append(
        "FreeCAD parametric history (sketches, constraints, expressions) — "
        "geometry imported at full fidelity, features are not reconstructable from .FCStd"
    )
    return doc, report
