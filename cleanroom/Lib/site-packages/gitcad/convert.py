"""gitcad-convert — one-command onboarding from other CAD.

Currently: multi-body FreeCAD .FCStd -> a full gitcad project (per-body
.model + .part, content-addressed assets/, and a .gitcad product root
instancing everything at as-modeled positions). From there the whole
toolchain applies: viewer + explode, interference with clash budgets,
review gates, release.
"""

from __future__ import annotations


def main() -> None:  # pragma: no cover - CLI entrypoint
    import sys

    sys.stderr.write(
        "gitcad-convert imported multi-body FreeCAD .FCStd projects by reading "
        "their OCCT-format .brp geometry. gitcad no longer bundles that reader "
        "(forge is the sole kernel — ADR-0020).\n\n"
        "Migration path: export STEP from FreeCAD (File > Export > STEP) and "
        "import each body with the model_import tool — planar solids come in "
        "exactly, on exact arithmetic.\n"
    )
    raise SystemExit(2)
