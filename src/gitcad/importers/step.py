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


def import_step_file(path: str, kernel: Kernel) -> tuple[Document, ImportReport]:
    """Import a STEP file. Returns (document, report). The document references
    the original file — keep it alongside the model (it is source now)."""
    report = ImportReport(source=path, format="step")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()

    doc = Document()
    doc.add(Feature(op="import", params={"format": "step", "file": path, "sha256": digest}))

    # Build once now: verifies the file parses and gives honest counts.
    result = doc.build(kernel)
    shape = result.final(doc)
    report.count("solids_or_bodies", 1)
    for kind in ("face", "edge"):
        try:
            report.count(f"{kind}s", len(kernel.entities(shape, kind)))
        except NotImplementedError:
            pass
    report.warnings.append(
        "imported geometry is a base body: parametric history from the source "
        "system is not present in STEP and was not imported"
    )
    return doc, report
