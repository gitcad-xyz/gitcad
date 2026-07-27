"""STEP importer — the universal mechanical onboarding path.

Produces a document whose single ``import`` feature pins the file by sha256,
so the model text names exactly one artifact verifiably (rebuilds fail loudly
if the file is swapped or corrupted). Once imported, everything downstream
just works: validate, measure, drawings, STEP/STL re-export, part derivation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from gitcad.document import Document, Feature
from gitcad.importers.report import ImportReport
from gitcad.seams import Kernel


def import_step_file(path: str, kernel: Kernel, *,
                     heal_tolerance: str | None = None) -> tuple[Document, ImportReport]:
    """Import a STEP file. Returns (document, report). The document references
    the original file — keep it alongside the model (it is source now).

    A shell that does not close REFUSES with a gap report in millimetres —
    the import border never silently produces a solid whose volume would be
    an origin-dependent non-number (#135). ``heal_tolerance`` (mm, decimal
    string) is recorded on the import feature as intent (ADR-0022): rebuild
    replays the same exact vertex merge, and the certificate — vertices
    moved, max move, the |ΔV| bound — lands in the report. A heal can never
    invent a face; a missing wall still refuses."""
    report = ImportReport(source=path, format="step")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()

    doc = Document()
    params: dict = {"format": "step", "file": path, "sha256": digest}
    if heal_tolerance is not None:
        params["heal_tolerance"] = heal_tolerance
    doc.add(Feature(op="import", params=params))

    # Build once now: verifies the file parses (and closes!) and gives honest
    # counts. A non-closing shell raises KernelError(NonClosedShell) here —
    # the refusal, gap report attached, IS the import's answer.
    result = doc.build(kernel)
    shape = result.final(doc)
    report.count("solids_or_bodies", 1)
    for kind in ("face", "edge"):
        try:
            report.count(f"{kind}s", len(kernel.entities(shape, kind)))
        except NotImplementedError:
            pass
    # evidence from the border audit: drops and the heal certificate
    krep = getattr(kernel, "last_import_report", None) or {}
    report.dropped.extend(krep.get("dropped", []))
    healed = krep.get("healed")
    if healed:
        report.count("vertices_healed", healed["moved"])
        report.warnings.append(
            f"heal_tolerance={healed['tolerance']} merged {healed['moved']} "
            f"vertex(es), max move {healed['max_move_mm']:.6g} mm; "
            f"|dV| bound {healed['volume_change_bound_mm3']:.6g} mm^3 "
            f"(= affected face area x max move — certified, recorded as "
            f"intent on the import feature)")
    report.warnings.append(
        "imported geometry is a base body: parametric history from the source "
        "system is not present in STEP and was not imported"
    )
    return doc, report
