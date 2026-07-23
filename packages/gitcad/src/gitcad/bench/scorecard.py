"""Kernel scorecard — the benchmark that makes improvement provable
(ADR-0018 W0; owner requirement: "show we are actually improving").

Runs the corpus on a named backend and emits a snapshot: per-model
build result, wall time, volume/bbox/topology metrics, validation.
With two backends, emits deltas. Snapshots are dated JSON committed
under bench/; TREND.md regenerates from them so every improvement
claim has a number in git history behind it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from gitcad.bench.corpus import CORPUS

_REL_TOL = 1e-9


def _get_kernel(name: str):
    if name == "occt":
        from gitcad.kernel.occt import OcctKernel
        return OcctKernel()
    if name == "null":
        from gitcad.kernel.null import NullKernel
        return NullKernel()
    if name == "ref":
        from gitcad.kernel.ref import RefKernel
        return RefKernel()
    if name == "forge":
        from gitcad.kernel.rustref import RustKernel
        return RustKernel()
    if name == "auto":
        from gitcad.kernel.auto import AutoKernel
        return AutoKernel()
    raise ValueError(f"unknown backend {name!r} (occt|null|ref|forge|auto)")


def run_backend(backend: str) -> dict[str, Any]:
    """Build every corpus model on one backend; never raises — failures
    are data (that is the point of a robustness benchmark)."""
    kernel = _get_kernel(backend)
    models: dict[str, Any] = {}
    for name, classes, build in CORPUS:
        entry: dict[str, Any] = {"classes": list(classes)}
        t0 = time.perf_counter()
        try:
            doc = build()
            result = doc.build(kernel)
            shape = result.final(doc)
            entry["ok"] = True
            entry["seconds"] = round(time.perf_counter() - t0, 4)
            try:
                mp = kernel.mass_props(shape)
                entry["volume"] = mp.get("volume")
            except Exception as exc:                     # metric, not fatal
                entry["volume_error"] = f"{type(exc).__name__}: {exc}"
            try:
                (x0, y0, z0), (x1, y1, z1) = kernel.bbox(shape)
                entry["bbox"] = [round(v, 6) for v in
                                 (x0, y0, z0, x1, y1, z1)]
            except Exception:
                pass
            try:
                entry["faces"] = len(kernel.entities(shape, "face"))
                entry["edges"] = len(kernel.entities(shape, "edge"))
            except Exception:
                pass
            try:
                v = kernel.validate(shape)
                entry["valid"] = bool(v.ok)
            except Exception:
                pass
        except Exception as exc:
            entry["ok"] = False
            entry["seconds"] = round(time.perf_counter() - t0, 4)
            entry["error"] = f"{type(exc).__name__}: {exc}"
        models[name] = entry

    by_class: dict[str, dict[str, int]] = {}
    for name, entry in models.items():
        for cls in entry["classes"]:
            c = by_class.setdefault(cls, {"total": 0, "ok": 0, "valid": 0})
            c["total"] += 1
            c["ok"] += 1 if entry.get("ok") else 0
            c["valid"] += 1 if entry.get("valid") else 0
    return {"backend": backend, "models": models, "by_class": by_class,
            "capability_pct": round(
                100 * sum(1 for m in models.values() if m.get("ok"))
                / len(models), 1)}


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Deltas of run b against oracle run a (volume rel-delta, topology
    count diffs, disagreement list)."""
    out: dict[str, Any] = {"oracle": a["backend"], "subject": b["backend"],
                           "models": {}, "disagreements": []}
    for name, ea in a["models"].items():
        eb = b["models"].get(name, {})
        row: dict[str, Any] = {"oracle_ok": ea.get("ok"),
                               "subject_ok": eb.get("ok")}
        va, vb = ea.get("volume"), eb.get("volume")
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va:
            row["volume_rel_delta"] = abs(vb - va) / abs(va)
            if row["volume_rel_delta"] > 1e-6:
                out["disagreements"].append(
                    f"{name}: volume {va:.6g} vs {vb:.6g}")
        if ea.get("ok") != eb.get("ok"):
            out["disagreements"].append(
                f"{name}: ok {ea.get('ok')} vs {eb.get('ok')}")
        for k in ("faces", "edges"):
            if k in ea and k in eb and ea[k] != eb[k]:
                row[f"{k}_diff"] = (ea[k], eb[k])
        out["models"][name] = row
    return out


def snapshot(backends: list[str], outdir: str = "bench", *,
             stamp: str) -> dict[str, Any]:
    """Run + persist one dated benchmark snapshot; regenerate TREND.md."""
    runs = {b: run_backend(b) for b in backends}
    payload: dict[str, Any] = {"stamp": stamp, "runs": runs}
    if len(backends) == 2:
        payload["compare"] = compare(runs[backends[0]], runs[backends[1]])
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{stamp}-{'-vs-'.join(backends)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    newline="\n")
    _render_trend(out)
    return payload


def _render_trend(outdir: Path) -> None:
    rows: list[str] = ["# Kernel benchmark trend", "",
                       "Regenerated from bench/*.json — every improvement "
                       "claim has a snapshot behind it.", "",
                       "| snapshot | backend | capability % | torture ok | "
                       "models ok | total s |",
                       "|---|---|---|---|---|---|"]
    for p in sorted(outdir.glob("*.json")):
        data = json.loads(p.read_text())
        for backend, run in sorted(data.get("runs", {}).items()):
            models = run["models"]
            torture = [m for m in models.values() if "torture" in m["classes"]]
            rows.append(
                f"| {data['stamp']} | {backend} | {run['capability_pct']} | "
                f"{sum(1 for m in torture if m.get('ok'))}/{len(torture)} | "
                f"{sum(1 for m in models.values() if m.get('ok'))}/{len(models)} | "
                f"{round(sum(m.get('seconds', 0) for m in models.values()), 2)} |")
    (outdir / "TREND.md").write_text("\n".join(rows) + "\n", newline="\n")


def main() -> None:  # pragma: no cover - CLI entry
    import argparse
    from datetime import date

    ap = argparse.ArgumentParser(description="kernel benchmark scorecard")
    ap.add_argument("backends", nargs="+", help="occt | null | ref")
    ap.add_argument("--outdir", default="bench")
    ap.add_argument("--stamp", default=str(date.today()))
    args = ap.parse_args()
    payload = snapshot(args.backends, args.outdir, stamp=args.stamp)
    for b, run in payload["runs"].items():
        print(f"{b}: capability {run['capability_pct']}% "
              f"({sum(1 for m in run['models'].values() if m.get('ok'))}"
              f"/{len(run['models'])} models)")
    for d in payload.get("compare", {}).get("disagreements", []):
        print("DISAGREE:", d)


if __name__ == "__main__":
    main()
