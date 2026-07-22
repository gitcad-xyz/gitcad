"""PR review packaging — what a gitcad pull request shows a reviewer.

``review_range`` compares every changed design document between two git
refs and produces, per file: the semantic diff (feature/component-level,
volume delta), the CHECK DELTA (violations introduced or fixed — ERC,
envelopes, board validation, DRC), and before/after renders. The rollup's
``gate_ok`` is the merge gate: any NEW violation fails it. A regression
that was already red on base doesn't block (it isn't this PR's fault) but
still shows.

Binary CAD formats can't do any of this; canonical text + headless checks
make it a ~300-line module. Emit markdown for a PR comment via
``to_markdown``, or a self-contained HTML page via ``to_html``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from gitcad.release import _kind, semantic_diff


def _git_show(repo: Path, ref: str, relpath: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{relpath}"],
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


# Design-document extensions: the json-free names are canonical (directory
# legibility); .json variants stay accepted forever — kind detection is by
# CONTENT (the schema field), extensions only scope the scan.
DESIGN_EXTENSIONS = (".json", ".gitcad", ".model", ".sch", ".board", ".part",
                     ".pcba", ".reqs")


def _changed_files(repo: Path, base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", f"{base}...{head}"],
        capture_output=True, text=True, check=True)
    return [ln.strip().replace("\\", "/") for ln in proc.stdout.splitlines()
            if ln.strip().endswith(DESIGN_EXTENSIONS)
            and not ln.strip().endswith(".kicad_sch")]


def _checks(kind: str, text: str) -> list[str]:
    """The check suite for one document kind — violation strings."""
    try:
        if kind == "schematic":
            from gitcad.ecad import Schematic, check_envelopes

            sch = Schematic.loads(text)
            return sch.erc().violations + check_envelopes(sch).violations
        if kind == "board":
            from gitcad.ecad import Board
            from gitcad.ecad.drc import run_drc

            board = Board.loads(text)
            return board.validate().violations + run_drc(board).violations
        if kind == "document":
            from gitcad.document import Document
            from gitcad.kernel import get_kernel

            doc = Document.loads(text)
            kernel = get_kernel()
            result = doc.build(kernel)
            report = kernel.validate(result.final(doc)) if len(doc) else None
            return list(report.violations) if report and not report.ok else []
        return []   # part manifests: interface-semver rides in the diff
    except Exception as exc:
        return [f"check-error:{type(exc).__name__}:{exc}"]


def _render(kind: str, text: str) -> str | None:
    """A reviewable SVG for one revision of a document, or None."""
    try:
        if kind == "schematic":
            from gitcad.ecad import Schematic, schematic_to_svg

            return schematic_to_svg(Schematic.loads(text))
        if kind == "board":
            from gitcad.ecad import Board
            from gitcad.viewer.boardsvg import board_to_svg

            return board_to_svg(Board.loads(text))
        if kind == "document":
            from gitcad.document import Document
            from gitcad.drawing.sheet import make_drawing
            from gitcad.kernel import get_kernel

            kernel = get_kernel()
            if kernel.name.startswith("null"):
                return None   # no fake geometry renders
            doc = Document.loads(text)
            return make_drawing(doc.build(kernel).final(doc), kernel,
                                title="review", sheet="A4").to_svg()
    except Exception:
        return None
    return None


def review_range(repo: str, base: str, head: str = "HEAD") -> dict:
    root = Path(repo)
    files = []
    gate_ok = True
    for rel in _changed_files(root, base, head):
        old = _git_show(root, base, rel)
        new = _git_show(root, head, rel)
        if new is None and old is None:
            continue
        kind = _kind(new if new is not None else old)
        if kind not in ("document", "board", "schematic", "part"):
            continue
        entry: dict = {"file": rel, "kind": kind,
                       "status": ("added" if old is None else
                                  "removed" if new is None else "modified")}
        if old is not None and new is not None:
            entry["diff"] = semantic_diff(old, new)
        old_v = _checks(kind, old) if old is not None else []
        new_v = _checks(kind, new) if new is not None else []
        entry["violations_introduced"] = sorted(set(new_v) - set(old_v))
        entry["violations_fixed"] = sorted(set(old_v) - set(new_v))
        entry["violations_preexisting"] = sorted(set(new_v) & set(old_v))
        if entry["violations_introduced"]:
            gate_ok = False
        entry["render_old"] = _render(kind, old) if old is not None else None
        entry["render_new"] = _render(kind, new) if new is not None else None
        files.append(entry)
    return {"base": base, "head": head, "files": files, "gate_ok": gate_ok,
            "summary": {
                "changed": len(files),
                "introduced": sum(len(f["violations_introduced"]) for f in files),
                "fixed": sum(len(f["violations_fixed"]) for f in files)}}


def to_markdown(report: dict) -> str:
    s = report["summary"]
    gate = "PASS" if report["gate_ok"] else "FAIL"
    lines = [f"## gitcad review — {report['base']}...{report['head']}",
             f"**gate: {gate}** · {s['changed']} design file(s) changed · "
             f"{s['introduced']} violation(s) introduced · {s['fixed']} fixed", ""]
    for f in report["files"]:
        lines.append(f"### `{f['file']}` ({f['kind']}, {f['status']})")
        d = f.get("diff", {})
        for key in ("features_added", "features_removed", "features_changed",
                    "components_added", "components_removed"):
            if d.get(key):
                items = [x["id"] if isinstance(x, dict) else x for x in d[key]]
                lines.append(f"- {key.replace('_', ' ')}: {', '.join(map(str, items))}")
        if "volume_mm3" in d and "delta" in d.get("volume_mm3", {}):
            v = d["volume_mm3"]
            lines.append(f"- volume: {v['old']} → {v['new']} mm³ (Δ {v['delta']:+})")
        if d.get("required_bump"):
            lines.append(f"- interface-semver: **{d['required_bump']}** bump required "
                         f"({'; '.join(d.get('reasons', []))})")
        for label, key in (("**introduced**", "violations_introduced"),
                           ("fixed", "violations_fixed")):
            for v in f[key]:
                lines.append(f"- {label}: `{v}`")
        if f["violations_preexisting"]:
            lines.append(f"- pre-existing (not this PR): {len(f['violations_preexisting'])}")
        lines.append("")
    return "\n".join(lines)


def to_html(report: dict) -> str:
    cards = []
    for f in report["files"]:
        panes = ""
        if f["render_old"] or f["render_new"]:
            for title, svg in (("base", f["render_old"]), ("head", f["render_new"])):
                inner = svg if svg else '<p class="none">(no render)</p>'
                panes += f'<div class="pane"><h4>{title}</h4>{inner}</div>'
            panes = f'<div class="sxs">{panes}</div>'
        vio = "".join(f'<li class="bad">{v}</li>' for v in f["violations_introduced"])
        vio += "".join(f'<li class="good">fixed: {v}</li>' for v in f["violations_fixed"])
        cards.append(f'<section><h3>{f["file"]} <small>({f["kind"]}, {f["status"]})'
                     f'</small></h3><ul>{vio}</ul>{panes}</section>')
    gate = "PASS" if report["gate_ok"] else "FAIL"
    color = "#3fb950" if report["gate_ok"] else "#f85149"
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>gitcad review</title><style>"
        "body{font:14px ui-monospace,Consolas,monospace;margin:2rem;background:#0d1117;color:#c9d1d9}"
        "section{margin-bottom:2rem;border:1px solid #21262d;border-radius:6px;padding:1rem}"
        ".sxs{display:flex;gap:12px;flex-wrap:wrap}"
        ".pane{flex:1;min-width:320px;background:#fff;border-radius:4px;padding:8px}"
        ".pane h4{color:#57606a;margin:0 0 6px}.pane svg{max-width:100%;height:auto}"
        ".bad{color:#f85149}.good{color:#3fb950}.none{color:#8b949e}"
        "small{color:#8b949e}</style></head><body>"
        f"<h1>gitcad review <span style='color:{color}'>{gate}</span></h1>"
        f"<p>{report['base']}...{report['head']} · "
        f"{report['summary']['changed']} file(s) · "
        f"{report['summary']['introduced']} introduced · "
        f"{report['summary']['fixed']} fixed</p>"
        + "".join(cards) + "</body></html>")


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="gitcad review — semantic + check + visual diff between git refs")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--md", help="write a Markdown report (PR comment) here")
    ap.add_argument("--html", help="write a self-contained HTML report here")
    args = ap.parse_args()
    report = review_range(args.repo, args.base, args.head)
    if args.md:
        Path(args.md).write_text(to_markdown(report), encoding="utf-8")
    if args.html:
        Path(args.html).write_text(to_html(report), encoding="utf-8")
    print(to_markdown(report))
    sys.exit(0 if report["gate_ok"] else 1)
