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


def import_fcstd(path: str, kernel: Kernel, assets_dir: str) -> tuple[Document, ImportReport]:
    """Import an .FCStd file. Extracted geometry is consolidated into one
    content-addressed ``.brep`` in ``assets_dir`` (which becomes source — keep
    it with the model). Returns (document, report)."""
    report = ImportReport(source=path, format="fcstd")
    assets = Path(assets_dir)
    assets.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        brep_members = [n for n in names if n.lower().endswith(".brep")]
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
