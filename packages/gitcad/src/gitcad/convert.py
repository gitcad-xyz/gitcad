"""gitcad-convert — one-command onboarding from other CAD.

Currently: multi-body FreeCAD .FCStd -> a full gitcad project (per-body
.model + .part, content-addressed assets/, and a .gitcad product root
instancing everything at as-modeled positions). From there the whole
toolchain applies: viewer + explode, interference with clash budgets,
review gates, release.
"""

from __future__ import annotations


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    from gitcad.importers.fcstd import fcstd_to_project
    from gitcad.kernel import get_kernel

    ap = argparse.ArgumentParser(
        description="gitcad convert — foreign CAD file to a gitcad project")
    ap.add_argument("file", help="an .FCStd file (more formats to come)")
    ap.add_argument("-o", "--out", required=True, help="project directory")
    ap.add_argument("--name", help="project name (default: file stem)")
    args = ap.parse_args()
    result = fcstd_to_project(args.file, args.out,
                              get_kernel(require="occt"), name=args.name)
    print(f"converted {result['project']}: {len(result['bodies'])} bodies")
    for rel in result["written"]:
        print(f"  {rel}")
    print(f"open it: gitcad-view {args.out}/{result['root']}")
