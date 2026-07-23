"""Requirements as code — the traceability matrix that actually executes.

A requirements document is canonical text binding named requirements to
machine checks over the design: mass and volume limits, bbox envelopes,
ERC/envelope/DRC cleanliness, rail utilization. ``verify`` runs every one
and reports measured-vs-limit per requirement — pass/fail history rides in
git next to the design that satisfies it, and a requirement nobody wired
to a check is visibly ``unchecked``, never silently green.

Aerospace/medical teams pay fortunes for traceability spreadsheets that
are lies by the second week. This is ~200 lines because the checks
already exist; requirements are just names bound to them.
"""

from __future__ import annotations

import json
from pathlib import Path

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError

SCHEMA = "gitcad/requirements@1"


def load_requirements(text: str) -> list[dict]:
    doc = json.loads(text)
    if doc.get("schema") != SCHEMA:
        raise GitcadError(f"unsupported requirements schema {doc.get('schema')!r}")
    reqs = doc.get("requirements", [])
    seen = set()
    for r in reqs:
        if "id" not in r or "text" not in r:
            raise GitcadError("every requirement needs id and text")
        if r["id"] in seen:
            raise GitcadError(f"duplicate requirement id {r['id']!r}")
        seen.add(r["id"])
    return reqs


def _load_target(root: Path, target: str):
    """'model:file.json' / 'schematic:file.json' / 'board:file.json'."""
    kind, _, rel = target.partition(":")
    path = root / rel
    if not path.is_file():
        raise GitcadError(f"target file not found: {rel}")
    text = path.read_text(encoding="utf-8")
    if kind == "model":
        from gitcad.document import Document

        return Document.loads(text)
    if kind == "schematic":
        from gitcad.ecad import Schematic

        return Schematic.loads(text)
    if kind == "board":
        from gitcad.ecad import Board

        return Board.loads(text)
    raise GitcadError(f"unknown target kind {kind!r} (want model|schematic|board)")


def _run_check(check: dict, root: Path) -> dict:
    """One requirement's check. Returns {ok, measured, limit, detail?}."""
    kind = check.get("kind")
    if kind in ("mass_max_g", "volume_max_mm3", "bbox_max_mm"):
        from gitcad.kernel import get_kernel

        kernel = get_kernel()
        doc = _load_target(root, check["target"])
        shape = doc.build(kernel).final(doc)
        if kind == "bbox_max_mm":
            lo, hi = kernel.bbox(shape)
            dims = [round(hi[i] - lo[i], 6) for i in range(3)]
            limit = list(check["limit"])
            return {"ok": all(d <= lim + 1e-9 for d, lim in zip(dims, limit)),
                    "measured": dims, "limit": limit,
                    "geometry_verified": not kernel.name.startswith("null")}
        vol = kernel.measure(shape).get("volume")
        if vol is None:
            return {"ok": False, "measured": None, "limit": check["limit"],
                    "detail": "volume unavailable on this kernel"}
        if kind == "volume_max_mm3":
            return {"ok": vol <= check["limit"] + 1e-9,
                    "measured": round(vol, 3), "limit": check["limit"],
                    "geometry_verified": not kernel.name.startswith("null")}
        mass = vol * check.get("density_g_cm3", 1.0) / 1000.0
        return {"ok": mass <= check["limit"] + 1e-9,
                "measured": round(mass, 3), "limit": check["limit"],
                "geometry_verified": not kernel.name.startswith("null")}

    if kind == "interference_clear":
        # the cross-domain fit check: every instance of an assembly —
        # mech models AND board-backed PCBAs (populated envelopes) —
        # pairwise boolean-intersected within a clash budget
        from gitcad.kernel import get_kernel
        from gitcad.part.interference import check_interference
        from gitcad.viewer.server import resolve_assembly_shapes

        kernel = get_kernel()
        target = check["target"]
        kind2, _, rel = target.partition(":")
        if kind2 != "assembly":
            raise GitcadError("interference_clear target must be 'assembly:<file>'")
        path = root / rel
        if not path.is_file():
            raise GitcadError(f"target file not found: {rel}")
        resolved = resolve_assembly_shapes(path, kernel)
        instances = {n: (s, t, r) for n, (s, t, r, _p) in resolved.items()}
        tol = float(check.get("tol_mm3", 0.0))
        rep = check_interference(kernel, instances, tol_mm3=tol or None)
        worst = max(rep.checks["overlaps_mm3"].values(), default=0.0)
        return {"ok": rep.ok, "measured": worst, "limit": tol,
                "detail": rep.checks["overlaps_mm3"] or "no overlaps",
                "geometry_verified": not kernel.name.startswith("null")}

    if kind == "erc_clean":
        sch = _load_target(root, check["target"])
        r = sch.erc()
        return {"ok": r.ok, "measured": len(r.violations), "limit": 0,
                "detail": r.violations[:10]}
    if kind == "envelope_clean":
        from gitcad.ecad import check_envelopes

        r = check_envelopes(_load_target(root, check["target"]))
        return {"ok": r.ok, "measured": len(r.violations), "limit": 0,
                "detail": r.violations[:10],
                "coverage_pins": r.checks["pins_with_specs"]}
    if kind == "rail_utilization_max":
        from gitcad.ecad import power_budget

        budget = power_budget(_load_target(root, check["target"]))
        rail = budget.get(check["net"])
        if rail is None or rail.get("utilization") is None:
            return {"ok": False, "measured": None, "limit": check["limit"],
                    "detail": f"rail {check['net']!r} has no spec'd source/loads"}
        return {"ok": rail["utilization"] <= check["limit"] + 1e-9,
                "measured": rail["utilization"], "limit": check["limit"]}
    if kind == "drc_clean":
        from gitcad.ecad.drc import run_drc

        r = run_drc(_load_target(root, check["target"]))
        return {"ok": r.ok, "measured": len(r.violations), "limit": 0,
                "detail": r.violations[:10]}
    raise GitcadError(f"unknown check kind {kind!r}")


def verify(requirements_text: str, root: str) -> dict:
    rootp = Path(root)
    results = []
    ok = True
    for req in load_requirements(requirements_text):
        entry = {"id": req["id"], "text": req["text"]}
        check = req.get("check")
        if not check:
            # a requirement without a check is VISIBLE debt, not silent green
            entry.update({"status": "unchecked"})
            ok = False
        else:
            try:
                r = _run_check(check, rootp)
                entry.update({"status": "pass" if r.pop("ok") else "fail", **r})
                if entry["status"] == "fail":
                    ok = False
            except Exception as exc:
                entry.update({"status": "error",
                              "detail": f"{type(exc).__name__}: {exc}"})
                ok = False
        results.append(entry)
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in ("pass", "fail", "error", "unchecked")}
    return {"ok": ok, "requirements": results, "summary": counts}


def to_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [f"## requirements — {'ALL PASS' if report['ok'] else 'NOT MET'}",
             f"{s['pass']} pass · {s['fail']} fail · {s['error']} error · "
             f"{s['unchecked']} unchecked", "",
             "| id | requirement | status | measured | limit |",
             "|----|-------------|--------|----------|-------|"]
    for r in report["requirements"]:
        lines.append(f"| {r['id']} | {r['text']} | **{r['status']}** | "
                     f"{r.get('measured', '—')} | {r.get('limit', '—')} |")
    return "\n".join(lines) + "\n"


def new_requirements_doc(requirements: list[dict]) -> str:
    return canonical_json({"schema": SCHEMA, "requirements": requirements},
                          indent=2) + "\n"


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="gitcad requirements — the traceability matrix that executes")
    ap.add_argument("file", help="requirements.json")
    ap.add_argument("--root", default=".", help="design tree targets resolve against")
    args = ap.parse_args()
    report = verify(Path(args.file).read_text(encoding="utf-8"), args.root)
    print(to_markdown(report))
    sys.exit(0 if report["ok"] else 1)
