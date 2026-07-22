"""Fab-lot traceability — git bisect for hardware bugs.

A lot record binds a PHYSICAL build (fab order, date, vendor) to the exact
release that produced it: the git commit, the release manifest, and the
sha256 of every artifact that went to the fab. Years later, "units from
lot 7" resolves to a commit — and a field failure becomes::

    git bisect start <bad-lot-commit> <good-lot-commit>
    git bisect run gitcad-verify requirements.json

with the executing requirements suite as the oracle. PLM systems charge
six figures to approximate this badly; here it is a hash-pinned JSON file
in the repo.

``verify_lot`` re-hashes the artifacts on disk against the record — a
swapped Gerber can never silently claim a lot's provenance.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError

SCHEMA = "gitcad/lot@1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head_commit(repo: Path) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitcadError("lot records need a git repo — provenance IS the point")
    return proc.stdout.strip()


def _dirty(repo: Path) -> bool:
    proc = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                          capture_output=True, text=True)
    return bool(proc.stdout.strip())


def record_lot(release_dir: str, lot_id: str, *, vendor: str = "",
               date: str = "", quantity: int | None = None,
               notes: str = "", repo: str = ".") -> str:
    """Create ``lot-<id>.json`` next to the release manifest. Refuses a
    dirty worktree — a lot pinned to a commit that doesn't contain what
    was actually sent would be provenance theater."""
    root = Path(repo)
    rel = Path(release_dir)
    manifest = rel / "release-manifest.json"
    if not manifest.is_file():
        # fall back to any *-manifest.json in the release dir
        candidates = sorted(rel.glob("*manifest*.json"))
        if not candidates:
            raise GitcadError(f"no release manifest found in {release_dir!r}")
        manifest = candidates[0]
    if _dirty(root):
        raise GitcadError(
            "worktree is dirty — commit first; a lot must pin a commit that "
            "contains exactly what was sent to the fab")

    artifacts = {p.name: _sha(p) for p in sorted(rel.iterdir())
                 if p.is_file() and not p.name.startswith("lot-")}
    doc = {"schema": SCHEMA, "lot": {
        "id": lot_id, "vendor": vendor, "date": date,
        **({"quantity": quantity} if quantity is not None else {}),
        **({"notes": notes} if notes else {}),
        "commit": _head_commit(root),
        "manifest": manifest.name,
        "artifacts": artifacts,
    }}
    out = rel / f"lot-{lot_id}.json"
    if out.exists():
        raise GitcadError(f"lot {lot_id!r} already recorded — lots are immutable; "
                          "record a new lot id for a re-run")
    out.write_text(canonical_json(doc, indent=2) + "\n", encoding="utf-8")
    return str(out)


def verify_lot(lot_path: str) -> dict:
    """Re-hash the artifacts against the lot record. Any mismatch is named —
    a swapped file can never silently claim this lot's provenance."""
    p = Path(lot_path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        raise GitcadError(f"unsupported lot schema {doc.get('schema')!r}")
    lot = doc["lot"]
    mismatches: list[str] = []
    missing: list[str] = []
    for name, want in sorted(lot["artifacts"].items()):
        f = p.parent / name
        if not f.is_file():
            missing.append(name)
        elif _sha(f) != want:
            mismatches.append(name)
    ok = not (mismatches or missing)
    return {"ok": ok, "lot": lot["id"], "commit": lot["commit"],
            "artifacts": len(lot["artifacts"]),
            "mismatched": mismatches, "missing": missing}


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="gitcad lots — fab-lot provenance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="record a lot against a release dir")
    rec.add_argument("release_dir")
    rec.add_argument("lot_id")
    rec.add_argument("--vendor", default="")
    rec.add_argument("--date", default="")
    rec.add_argument("--quantity", type=int)
    rec.add_argument("--notes", default="")
    rec.add_argument("--repo", default=".")
    ver = sub.add_parser("verify", help="re-hash artifacts against a lot record")
    ver.add_argument("lot_file")
    args = ap.parse_args()
    if args.cmd == "record":
        path = record_lot(args.release_dir, args.lot_id, vendor=args.vendor,
                          date=args.date, quantity=args.quantity,
                          notes=args.notes, repo=args.repo)
        print(f"recorded {path}")
    else:
        r = verify_lot(args.lot_file)
        print(json.dumps(r, indent=2))
        sys.exit(0 if r["ok"] else 1)
