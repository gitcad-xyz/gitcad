"""Importers — onboarding existing work, honestly.

The biggest adoption roadblock is a blank slate. These importers bring in what
users already have — and every importer returns an :class:`ImportReport`
stating exactly what was imported, approximated, and dropped. Silent data loss
is never acceptable: an import that quietly discards a copper layer is worse
than one that refuses.

- :mod:`gitcad.importers.step`  — STEP → document (mech, universal interchange)
- :mod:`gitcad.importers.fcstd` — FreeCAD .FCStd → document (reads the embedded
  .brep objects directly; FreeCAD itself is NOT required)
- :mod:`gitcad.importers.kicad` — KiCad .kicad_pcb → Board (ecad)
"""

from gitcad.importers.report import ImportReport
from gitcad.importers.step import import_step_file
from gitcad.importers.fcstd import import_fcstd
from gitcad.importers.kicad import import_kicad_pcb

__all__ = ["ImportReport", "import_step_file", "import_fcstd", "import_kicad_pcb"]
