"""Release machinery + semantic diff — the git-native thesis, completed.

``release()`` is Project-Releaser-as-code (feature-map A8/B5): run EVERY
check the project defines — model validation, ERC, schematic-board parity,
DRC, fab-readiness — and only on all-green produce the immutable artifact
set (STEP/STL/drawings for models, Gerber/drill/PnP for boards) plus a
manifest pinning every input and output by sha256. A release either passes
everything or it does not exist; there is no "release with known failures".

``semantic_diff()`` is the PR review surface ADR-0004 promised: not a text
diff but a *meaning* diff — features added/removed/changed by stable id,
volume delta from real geometry, board item deltas, and for parts the
interface-semver classification with the required version bump.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from gitcad.canonical import canonical_json
from gitcad.document import Document
from gitcad.errors import GitcadError
from gitcad.kernel import get_kernel
from gitcad.seams import Kernel

from gitcad._version import __version__ as _gitcad_version


def _kind(text: str) -> str:
    schema = json.loads(text).get("schema", "")
    for k in ("document", "board", "schematic", "part"):
        if schema.startswith(f"gitcad/{k}"):
            return k
    raise GitcadError(f"unknown schema {schema!r}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -- semantic diff ------------------------------------------------------------

def semantic_diff(old_text: str, new_text: str, kernel: Kernel | None = None) -> dict:
    """A meaning-level diff between two revisions of the same document."""
    kind_old, kind_new = _kind(old_text), _kind(new_text)
    if kind_old != kind_new:
        return {"kind": "mixed", "error": f"cannot diff {kind_old} against {kind_new}"}
    out: dict = {"kind": kind_old}

    if kind_old == "document":
        old, new = Document.loads(old_text), Document.loads(new_text)
        old_ids = {f.id: f for f in old.features}
        new_ids = {f.id: f for f in new.features}
        out["features_added"] = [{"id": i, "op": new_ids[i].op} for i in new_ids if i not in old_ids]
        out["features_removed"] = [{"id": i, "op": old_ids[i].op} for i in old_ids if i not in new_ids]
        out["features_changed"] = [
            {"id": i, "op": new_ids[i].op}
            for i in new_ids
            if i in old_ids and canonical_json(new_ids[i].to_dict()) != canonical_json(old_ids[i].to_dict())
        ]
        kernel = kernel or get_kernel()
        if not kernel.name.startswith("null"):
            try:
                v_old = kernel.measure(old.build(kernel).final(old))["volume"] if len(old) else 0.0
                v_new = kernel.measure(new.build(kernel).final(new))["volume"] if len(new) else 0.0
                out["volume_mm3"] = {"old": round(v_old, 3), "new": round(v_new, 3),
                                     "delta": round(v_new - v_old, 3)}
            except Exception as exc:
                out["volume_mm3"] = {"error": f"{type(exc).__name__}: {exc}"}

    elif kind_old == "board":
        from gitcad.ecad import Board

        old_b, new_b = Board.loads(old_text), Board.loads(new_text)
        old_refs = {c.ref for c in old_b.components}
        new_refs = {c.ref for c in new_b.components}
        out["components_added"] = sorted(new_refs - old_refs)
        out["components_removed"] = sorted(old_refs - new_refs)
        out["tracks"] = {"old": len(old_b.tracks), "new": len(new_b.tracks)}
        out["vias"] = {"old": len(old_b.vias), "new": len(new_b.vias)}
        out["outline_changed"] = old_b.outline != new_b.outline

    elif kind_old == "part":
        from gitcad.part import PartManifest, classify_change

        old_p, new_p = PartManifest.loads(old_text), PartManifest.loads(new_text)
        bump, reasons = classify_change(old_p.interface, new_p.interface)
        out["required_bump"] = bump
        out["reasons"] = reasons
        out["version"] = {"old": old_p.version, "new": new_p.version}

    else:  # schematic
        from gitcad.ecad import Schematic

        old_s, new_s = Schematic.loads(old_text), Schematic.loads(new_text)
        out["components_added"] = sorted({c.ref for c in new_s.components}
                                         - {c.ref for c in old_s.components})
        out["components_removed"] = sorted({c.ref for c in old_s.components}
                                           - {c.ref for c in new_s.components})
        out["nets"] = {"old": len(old_s.nets), "new": len(new_s.nets)}

    out["identical"] = old_text == new_text
    return out


# -- release ------------------------------------------------------------------

@dataclass
class ReleaseResult:
    version: str
    ok: bool
    checks: dict = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)   # name -> sha256
    manifest_path: str = ""


def release(sources: list[str], outdir: str, version: str) -> ReleaseResult:
    """Check everything, then (and only then) produce the artifact set."""
    out = Path(outdir)
    result = ReleaseResult(version=version, ok=False)
    kernel = None

    docs: list[tuple[Path, str, str]] = []   # (path, kind, text)
    for src in sources:
        p = Path(src)
        text = p.read_text(encoding="utf-8")
        docs.append((p, _kind(text), text))

    schematics = [(p, t) for p, k, t in docs if k == "schematic"]
    boards = [(p, t) for p, k, t in docs if k == "board"]

    # -- phase 1: every check must pass ---------------------------------------
    for p, kind, text in docs:
        label = p.name
        if kind == "document":
            kernel = kernel or get_kernel(require="occt")
            doc = Document.loads(text)
            build = doc.build(kernel)
            for fid, shape in build.shapes.items():
                r = kernel.validate(shape)
                if not r.ok:
                    result.failures.append(f"{label}:validate:{fid}:{r.violations}")
            result.checks[f"{label}:validate"] = "ok"
        elif kind == "board":
            from gitcad.ecad import Board, check_connectivity, run_drc

            board = Board.loads(text)
            r = board.validate()
            if not r.ok:
                result.failures.extend(f"{label}:fab:{v}" for v in r.violations)
            d = run_drc(board)
            if not d.ok:
                result.failures.extend(f"{label}:drc:{v}" for v in d.violations)
            c = check_connectivity(board)
            if not c.ok:
                result.failures.extend(f"{label}:connectivity:{v}" for v in c.violations)
            result.checks[f"{label}:fab"] = "ok" if r.ok else "FAIL"
            result.checks[f"{label}:drc"] = "ok" if d.ok else "FAIL"
            result.checks[f"{label}:connectivity"] = "ok" if c.ok else "FAIL"
        elif kind == "schematic":
            from gitcad.ecad import Schematic

            r = Schematic.loads(text).erc()
            if not r.ok:
                result.failures.extend(f"{label}:erc:{v}" for v in r.violations)
            result.checks[f"{label}:erc"] = "ok" if r.ok else "FAIL"

    # cross-checks: every schematic against every board (parity)
    if schematics and boards:
        from gitcad.ecad import Board, Schematic, board_parity

        for sp, st in schematics:
            for bp, bt in boards:
                r = board_parity(Schematic.loads(st), Board.loads(bt))
                key = f"parity:{sp.name}<->{bp.name}"
                result.checks[key] = "ok" if r.ok else "FAIL"
                if not r.ok:
                    result.failures.extend(f"{key}:{v}" for v in r.violations)

    if result.failures:
        return result   # no artifacts on red — a release either passes or isn't

    # -- phase 2: artifacts ----------------------------------------------------
    out.mkdir(parents=True, exist_ok=True)
    for p, kind, text in docs:
        stem = p.name.replace(".gitcad.json", "").replace(".json", "")
        if kind == "document":
            from gitcad.drawing import make_drawing

            doc = Document.loads(text)
            shape = doc.build(kernel).final(doc)
            step = out / f"{stem}.step"
            kernel.export_step(shape, str(step))
            stl = out / f"{stem}.stl"
            kernel.export_stl(shape, str(stl))
            pdf = out / f"{stem}.pdf"
            pdf.write_bytes(make_drawing(shape, kernel, title=f"{stem} {version}").to_pdf())
            for f in (step, stl, pdf):
                result.artifacts[f.name] = _sha(f)
        elif kind == "board":
            from gitcad.ecad import Board, export_fab

            files = export_fab(Board.loads(text), str(out / f"{stem}-fab"))
            for _, fpath in files.items():
                fp = Path(fpath)
                result.artifacts[f"{stem}-fab/{fp.name}"] = _sha(fp)

    manifest = {
        "generator": f"gitcad {_gitcad_version}",
        "version": version,
        "sources": {p.name: hashlib.sha256(t.encode()).hexdigest() for p, _, t in docs},
        "checks": result.checks,
        "artifacts": result.artifacts,
    }
    mpath = out / "release-manifest.json"
    mpath.write_text(canonical_json(manifest, indent=2) + "\n", newline="\n", encoding="utf-8")
    result.manifest_path = str(mpath)
    result.ok = True
    return result
