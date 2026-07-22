"""Fabrication package assembly — every file a fab + assembler needs, one call.

``export_fab(board, outdir)`` validates the board (refusing to emit a package
that a fab would bounce), then writes Gerber X2 layers, the Excellon drill
file, a pick-and-place CSV, and a manifest. File naming follows the widely
accepted Protel/KiCad-style extensions fabs auto-recognize.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from gitcad._version import __version__ as _gitcad_version
from gitcad.ecad import excellon, gerber
from gitcad.ecad.board import Board
from gitcad.errors import GitcadError


def pick_and_place(board: Board) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Designator", "Value", "Package", "PosX", "PosY", "Rotation", "Side"])
    for c in sorted(board.components, key=lambda c: c.ref):
        w.writerow([c.ref, c.value, c.footprint.name,
                    f"{c.x:.3f}", f"{c.y:.3f}", f"{c.rot:.1f}", c.side])
    return buf.getvalue()


def export_fab(board: Board, outdir: str) -> dict[str, str]:
    """Write the full fab package. Returns {file kind: path}. Raises if the
    board fails fab-readiness validation — never ship a known-bad package."""
    report = board.validate()
    if not report.ok:
        raise GitcadError(f"board failed fab validation: {report.violations}")

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    n = board.name
    files = {
        "copper_top": (f"{n}.gtl", gerber.copper(board, "top")),
        "copper_bottom": (f"{n}.gbl", gerber.copper(board, "bottom")),
        "mask_top": (f"{n}.gts", gerber.mask(board, "top")),
        "mask_bottom": (f"{n}.gbs", gerber.mask(board, "bottom")),
        "silk_top": (f"{n}.gto", gerber.silkscreen(board, "top")),
        "profile": (f"{n}.gko", gerber.profile(board)),
        "drill": (f"{n}.drl", excellon.drills(board)),
        "drill_npth": (f"{n}-npth.drl", excellon.npth_drills(board)),
        "pick_and_place": (f"{n}-pnp.csv", pick_and_place(board)),
    }
    written: dict[str, str] = {}
    for kind, (fname, content) in files.items():
        path = out / fname
        path.write_text(content, newline="\n")
        written[kind] = str(path)

    manifest = {
        "board": n,
        "generator": f"gitcad {_gitcad_version}",
        "layers": 2,
        "files": {k: Path(v).name for k, v in written.items()},
        "checks": report.checks,
    }
    mpath = out / f"{n}-manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", newline="\n")
    written["manifest"] = str(mpath)
    return written
