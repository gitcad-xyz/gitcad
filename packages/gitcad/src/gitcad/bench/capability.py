"""Kernel capability matrix — every seam operation × every representation.

Why this exists: the forge_gap list was assembled REACTIVELY, from whatever the
test suite happened to exercise. That finds gaps only where a test already
looks, which is why fundamental holes (STEP export of any drilled part) sat
undiscovered. This probe is the systematic alternative: it calls every
``Kernel`` seam operation against a representative of every solid
representation forge can produce, and records what actually happens.

Four outcomes, and the distinction is the point:

``ok``        the operation returned a result
``refused``   an honest, stage-named ``NotYetImplemented`` (the charter's
              preferred failure — a known gap, correctly reported)
``bad-input`` a ``BadInput`` KernelError (the argument was wrong, not the kernel)
``CRASH``     a raw exception escaped the seam — always a DEFECT, whether or not
              the underlying capability exists, because callers cannot handle it

The matrix is the roadmap: ``refused`` cells are the capability backlog in
priority order, and ``CRASH`` cells are bugs to fix now. Run it with
``python -m gitcad.bench.capability`` (add ``--md`` for the markdown table).

There are TWO tiers, and the public number is their PAIR (#10):

* **single-op** — every seam operation against a freshly built solid;
* **composed** — every operation CHAIN (rotate-then-boolean, boolean-result
  reuse, cutting with a transformed tool, export of a transformed solid)
  against the same representations.

The single-op grid alone overstates real coverage: it scored ``rotate 90``
✅ while the rotated solid could no longer be a boolean operand or a STEP
export, so a first real model contradicted the headline within minutes.
``headline()`` prints the pair; neither number travels without the other.
"""

from __future__ import annotations

import math
from typing import Any

from gitcad.errors import KernelError


def representations(k) -> dict[str, Any]:
    """One representative solid per forge representation, built through the
    public seam exactly as a user's document would."""
    out: dict[str, Any] = {}

    def add(name, fn):
        try:
            out[name] = fn()
        except Exception as exc:                      # noqa: BLE001
            out[name] = ("<unbuildable>", exc)

    add("planar box", lambda: k.box(20, 20, 10))
    add("planar prism", lambda: k.extrude(
        {"start": [0, 0], "segments": [{"kind": "line", "to": [30, 0]},
                                       {"kind": "line", "to": [30, 10]},
                                       {"kind": "line", "to": [10, 10]},
                                       {"kind": "line", "to": [10, 30]},
                                       {"kind": "line", "to": [0, 30]},
                                       {"kind": "line", "to": [0, 0]}]}, 8))
    add("cylinder", lambda: k.cylinder(5, 12))
    add("sphere", lambda: k.sphere(6))
    add("cone", lambda: k.cone(6, 2, 10))
    add("drilled (through)", lambda: k.boolean(
        "cut", k.box(40, 20, 5), k.transform(k.cylinder(4, 5),
                                             translate=(20, 10, 0))))
    add("drilled (blind)", lambda: k.boolean(
        "cut", k.box(30, 30, 10), k.transform(k.cylinder(3, 6),
                                              translate=(15, 15, 4))))
    add("counterbore", lambda: k.boolean(
        "cut", k.boolean("cut", k.box(30, 30, 10),
                         k.transform(k.cylinder(2, 10), translate=(15, 15, 0))),
        k.transform(k.cylinder(4, 3), translate=(15, 15, 7))))
    add("disjoint union (boss)", lambda: k.boolean(
        "union", k.box(30, 30, 3), k.transform(k.cylinder(4, 6),
                                               translate=(15, 15, 3))))
    add("bored boss", lambda: k.boolean(
        "cut", k.boolean("union", k.box(30, 30, 3),
                         k.transform(k.cylinder(4, 6), translate=(15, 15, 3))),
        k.transform(k.cylinder(1, 5), translate=(15, 15, 4))))
    add("revolve", lambda: k.revolve(
        {"start": [0, 0], "segments": [{"kind": "line", "to": [5, 0]},
                                       {"kind": "line", "to": [5, 10]},
                                       {"kind": "line", "to": [0, 10]},
                                       {"kind": "line", "to": [0, 0]}]}))
    add("filleted box", lambda: k.fillet(k.box(20, 20, 20), [], 3))
    add("chamfered box", lambda: k.chamfer(k.box(20, 20, 20), [], 2))
    add("shelled box", lambda: k.shell(k.box(20, 20, 20), [], 2))
    add("loft", lambda: k.loft([
        ({"start": [0, 0], "segments": [{"kind": "line", "to": [10, 0]},
                                        {"kind": "line", "to": [10, 10]},
                                        {"kind": "line", "to": [0, 10]},
                                        {"kind": "line", "to": [0, 0]}]}, 0.0),
        ({"start": [2, 2], "segments": [{"kind": "line", "to": [8, 2]},
                                        {"kind": "line", "to": [8, 8]},
                                        {"kind": "line", "to": [2, 8]},
                                        {"kind": "line", "to": [2, 2]}]}, 12.0)],
        ruled=True))
    return out


def operations(k, tmpdir: str) -> dict[str, Any]:
    """Every Kernel seam operation, as a callable taking one shape."""
    import os

    def out(name):
        return os.path.join(tmpdir, name)

    return {
        "measure": lambda s: k.measure(s),
        "mass_props": lambda s: k.mass_props(s),
        "bbox": lambda s: k.bbox(s),
        "validate": lambda s: k.validate(s),
        "tessellate": lambda s: k.tessellate(s),
        "entities(face)": lambda s: k.entities(s, "face"),
        "entities(edge)": lambda s: k.entities(s, "edge"),
        "translate": lambda s: k.transform(s, translate=(1, 2, 3)),
        "rotate 90": lambda s: k.transform(s, rotate_axis=(0, 0, 1),
                                           rotate_deg=90),
        "rotate 45": lambda s: k.transform(s, rotate_axis=(0, 0, 1),
                                           rotate_deg=45),
        "mirror": lambda s: k.mirror(s, "xy"),
        "scale": lambda s: k.scale(s, 2),
        "cut cylinder": lambda s: k.boolean(
            "cut", s, k.transform(k.cylinder(1, 100), translate=_mid(k, s))),
        "cut box": lambda s: k.boolean(
            "cut", s, k.transform(k.box(2, 2, 100), translate=_mid(k, s))),
        "union box": lambda s: k.boolean(
            "union", s, k.transform(k.box(2, 2, 2), translate=_far(k, s))),
        "fillet(all)": lambda s: k.fillet(s, [], 1),
        "chamfer(all)": lambda s: k.chamfer(s, [], 1),
        "shell": lambda s: k.shell(s, [], 1),
        "hlr_project": lambda s: k.hlr_project(s, (0, -1, 0), (1, 0, 0)),
        "section_polys": lambda s: k.section_polys(s, (1, 0, 0), (0, 1, 0),
                                                   _mid(k, s)[0]),
        "export_step": lambda s: k.export_step(s, out("p.step")),
        "export_stl": lambda s: k.export_stl(s, out("p.stl")),
        "export_brep": lambda s: k.export_brep(s, out("p.brep")),
    }


def _mid(k, s):
    (lo, hi) = k.bbox(s)
    return tuple((float(lo[i]) + float(hi[i])) / 2 for i in range(3))


def _far(k, s):
    (lo, hi) = k.bbox(s)
    return (float(hi[0]) + 10, float(lo[1]), float(lo[2]))


def composed_operations(k, tmpdir: str) -> dict[str, Any]:
    """Tier 2 — the COMPOSED grid: every column is a CHAIN of seam
    operations, probing whether the RESULT of one operation is still a
    usable operand for the next (#10).

    The single-op grid scores ``rotate 90`` ✅ if ``transform`` returns and
    metrics still work on it; it never asks whether the rotated solid can
    still be a boolean operand or a STEP export — which is where a real
    modelling session actually fails. These chains are the ten-minutes-of-
    real-use cases: transform-then-boolean (tool orientation), boolean
    where the TOOL was transformed, boolean-result reuse (cut → cut,
    cut → shell), and export/tessellate of a transformed or cut solid.
    """
    import os

    def out(name):
        return os.path.join(tmpdir, name)

    def rot(s, deg, axis=(0, 0, 1)):
        return k.transform(s, rotate_axis=axis, rotate_deg=deg)

    def cutbox(s):
        return k.boolean("cut", s,
                         k.transform(k.box(2, 2, 100), translate=_mid(k, s)))

    def loft_tool(s):
        """A skewed ruled loft — the crankbait lip-slot tool shape (#11)."""
        return k.transform(k.loft([
            ({"start": [0, 0], "segments": [{"kind": "line", "to": [4, 0]},
                                            {"kind": "line", "to": [4, 4]},
                                            {"kind": "line", "to": [0, 4]},
                                            {"kind": "line", "to": [0, 0]}]},
             -50.0),
            ({"start": [3, 3], "segments": [{"kind": "line", "to": [7, 3]},
                                            {"kind": "line", "to": [7, 7]},
                                            {"kind": "line", "to": [3, 7]},
                                            {"kind": "line", "to": [3, 3]}]},
             50.0)], ruled=True), translate=_mid(k, s))

    return {
        "rot90 then cut": lambda s: cutbox(rot(s, 90)),
        "rot45 then cut": lambda s: cutbox(rot(s, 45)),
        "rot90x then cut": lambda s: cutbox(rot(s, 90, (1, 0, 0))),
        "translate then cut": lambda s: cutbox(
            k.transform(s, translate=(3, 5, 7))),
        "mirror then cut": lambda s: cutbox(k.mirror(s, "xy")),
        "scale then cut": lambda s: cutbox(k.scale(s, 2)),
        "cut by rot45 tool": lambda s: k.boolean(
            "cut", s, k.transform(rot(k.box(2, 2, 100), 45),
                                  translate=_mid(k, s))),
        "cut by loft tool": lambda s: k.boolean("cut", s, loft_tool(s)),
        "cut then cut": lambda s: k.boolean(
            "cut", cutbox(s), k.transform(k.cylinder(1, 100),
                                          translate=_mid(k, s))),
        "cut then union": lambda s: k.boolean(
            "union", cutbox(s), k.transform(k.box(2, 2, 2),
                                            translate=_far(k, s))),
        "cut then shell": lambda s: k.shell(cutbox(s), [], 1),
        "cut then fillet": lambda s: k.fillet(cutbox(s), [], 1),
        "cut then export_step": lambda s: k.export_step(cutbox(s),
                                                        out("cc.step")),
        "rot90 then export_step": lambda s: k.export_step(rot(s, 90),
                                                          out("r90.step")),
        "rot45 then export_step": lambda s: k.export_step(rot(s, 45),
                                                          out("r45.step")),
        "rot90 then tessellate": lambda s: k.tessellate(rot(s, 90)),
        "rot45 then measure": lambda s: k.measure(rot(s, 45)),
    }


# Cells that are OUTSIDE ANY EXACT FIELD, permanently. These are not backlog
# and never will be: under ADR-0019 the refusal IS the finished answer, and
# counting them as gaps makes the matrix read as 345 achievable cells when it
# is not. Each entry says why, in terms of the number that would be needed.
_EXACT_FIELD_BOUNDARY = {
    ("sphere", "cut box"):
        "a square prism through a sphere has an arcsin in its volume — not "
        "algebraic, so no extension of ℚ[π] holds it",
    ("chamfered box", "chamfer(all)"):
        "a chamfered box's faces have normals of length √2, so chamfering "
        "them again offsets a plane by an irrational distance",
    ("cone", "fillet(all)"):
        "a fillet arc off the axis contributes its TURN ANGLE linearly to "
        "∮r²dz; this cone's rim turns through π−arctan(5/2), and arctan(5/2) "
        "is transcendental (Lindemann) — by Niven only 90° and 45°/135° lathe "
        "corners have a turn angle in ℚ·π at all",
    ("cone", "cut box"):
        "the tool wall's crossing angle arccos(2/r(z)) varies with z on the "
        "slant and is INTEGRATED, emitting the constant ln(1+√2) = arcsinh(1): "
        "removed V = 40 − (20/3)√2 − (5/3)π − (20/3)·ln(1+√2), and by Baker "
        "1, iπ, ln(1+√2) are independent over the algebraic numbers, so V lies "
        "outside every ℚ[√d][π] taken linearly in π (and outside every "
        "algebraic extension of ℚ[π] under Schanuel) — a logarithm is not a "
        "surd times π",
    ("loft", "fillet(all)"):
        "a fillet's toroidal patch contributes its SWEEP ANGLE linearly to "
        "the volume; this loft's slanted faces meet the caps at dihedrals "
        "with cos = ±1/√37 and each other at cos = 1/37 — cos² is rational, "
        "but by Niven neither cosine puts the angle in ℚ·π, and by "
        "Gelfond–Schneider arccos(1/√37)/π is transcendental outright, so no "
        "extension of ℚ[√d][π] holds the sweep",
}


# COMPOSED cells outside any exact field, permanently — ONLY entries whose
# tier-1 proof carries verbatim through the composing operation (an isometry
# maps the whole configuration to a congruent one, and a rational scaling
# keeps the volume in the same field). Anything without such an argument
# stays an honest gap; classifying it here without proof would be gaming
# the number. In particular the "cut then …" chains on sphere/cone stay
# gaps even though their FIRST step is a proven wall: a certified-interval
# answer (ADR-0019) to step one would unblock them, so they are not
# permanent in the same sense.
_SPHERE_WALL = _EXACT_FIELD_BOUNDARY[("sphere", "cut box")]
_CONE_WALL = _EXACT_FIELD_BOUNDARY[("cone", "cut box")]
_EXACT_FIELD_BOUNDARY_COMPOSED: dict[tuple[str, str], str] = {
    # a sphere is invariant under every rotation and reflection about its
    # center, and the probe tool is placed relative to the (moved) bbox —
    # each of these configurations is CONGRUENT to tier-1 (sphere, cut box)
    ("sphere", "rot90 then cut"): _SPHERE_WALL,
    ("sphere", "rot45 then cut"): _SPHERE_WALL,
    ("sphere", "rot90x then cut"): _SPHERE_WALL,
    ("sphere", "translate then cut"): _SPHERE_WALL,
    ("sphere", "mirror then cut"): _SPHERE_WALL,
    # rotating the square tool about its own vertical axis and cutting a
    # sphere is the tier-1 configuration rotated 45° whole
    ("sphere", "cut by rot45 tool"): _SPHERE_WALL,
    # the proof is generic in the sphere's radius (a square prism through a
    # sphere has an arcsin in its volume), so the 2× sphere hits it too
    ("sphere", "scale then cut"): _SPHERE_WALL,
    # the cone is axisymmetric about z and the tool tracks the bbox, so a
    # z-rotation or a translation maps tier-1 (cone, cut box) congruently;
    # NOT carried: mirror (cuts the other half — different integral),
    # rot90x (cone on its side), scale (tool no longer scales with it)
    ("cone", "rot90 then cut"): _CONE_WALL,
    ("cone", "rot45 then cut"): _CONE_WALL,
    ("cone", "translate then cut"): _CONE_WALL,
}


def probe(k=None) -> dict:
    """Run every operation against every representation; classify each cell."""
    return _probe(k, operations, _EXACT_FIELD_BOUNDARY)


def probe_composed(k=None) -> dict:
    """The COMPOSED tier (#10): every op CHAIN against every representation.

    Same classification, same honesty rules — but each cell exercises two or
    three operations composed, scoring whether results stay usable. Reported
    ALONGSIDE the single-op number, never blended into it: the pair is the
    honest headline, because a fresh-solid grid alone overstates what a real
    modelling session can do."""
    return _probe(k, composed_operations, _EXACT_FIELD_BOUNDARY_COMPOSED)


def _probe(k, make_ops, boundary) -> dict:
    import tempfile

    if k is None:
        from gitcad.kernel import get_kernel

        k = get_kernel()
    tmpdir = tempfile.mkdtemp()
    shapes = representations(k)
    ops = make_ops(k, tmpdir)
    grid: dict[str, dict[str, str]] = {}
    detail: dict[tuple[str, str], str] = {}
    for sname, shape in shapes.items():
        row: dict[str, str] = {}
        if isinstance(shape, tuple) and shape and shape[0] == "<unbuildable>":
            for oname in ops:
                row[oname] = "n/a"
            detail[(sname, "*")] = f"could not build: {shape[1]}"
            grid[sname] = row
            continue
        for oname, fn in ops.items():
            try:
                fn(shape)
                row[oname] = "ok"
            except KernelError as exc:
                diag = getattr(getattr(exc, "signature", None), "diagnostic", "")
                row[oname] = {"NotYetImplemented": "refused",
                              "BadInput": "bad-input"}.get(diag, "refused")
                detail[(sname, oname)] = str(exc)
                if (sname, oname) in boundary:
                    # a permanent, correct answer — not a gap to be closed
                    row[oname] = "exact-field"
                    detail[(sname, oname)] = boundary[(sname, oname)]
            except NotImplementedError as exc:
                row[oname] = "refused"
                detail[(sname, oname)] = str(exc)
            except Exception as exc:                  # noqa: BLE001 - the point
                row[oname] = "CRASH"
                detail[(sname, oname)] = f"{type(exc).__name__}: {exc}"
        grid[sname] = row
    return {"grid": grid, "detail": detail,
            "shapes": list(shapes), "ops": list(ops)}


_MARK = {"ok": "✅", "refused": "🚧", "bad-input": "·", "CRASH": "💥",
         "exact-field": "∎", "n/a": "—"}


def tally(result: dict) -> dict[str, int]:
    t: dict[str, int] = {}
    for row in result["grid"].values():
        for v in row.values():
            t[v] = t.get(v, 0) + 1
    return t


def summary(result: dict) -> str:
    t = tally(result)
    total = sum(t.values()) or 1
    return (f"{t.get('ok', 0)}/{total} "
            f"({float(100 * t.get('ok', 0) / total):.0f}%) working, "
            f"{t.get('refused', 0)} gaps, "
            f"{t.get('exact-field', 0)} at the exact-field boundary "
            f"(permanent), {t.get('CRASH', 0)} crashes")


def headline(single: dict, composed: dict) -> str:
    """THE public number — the honest pair (#10). The single-op grid alone
    overstates real coverage (every cell starts from a fresh solid); the
    composed grid is where a modelling session actually lives. Neither
    number is allowed to travel without the other."""
    return (f"single-op {summary(single)} · composed {summary(composed)}")


def to_markdown(result: dict, title: str | None = None) -> str:
    grid, ops = result["grid"], result["ops"]
    lines = []
    if title:
        lines += [f"### {title}", ""]
    lines += ["| representation | " + " | ".join(ops) + " |",
              "| --- |" + " --- |" * len(ops)]
    for sname, row in grid.items():
        lines.append(f"| {sname} | "
                     + " | ".join(_MARK.get(row[o], row[o]) for o in ops) + " |")
    lines.append("")
    lines.append("Legend: ✅ works · 🚧 honest refusal (capability gap) · "
                 "· bad-input · 💥 raw crash through the seam (DEFECT) · "
                 "∎ outside any exact field, permanently · — n/a")
    lines.append("")
    lines.append(f"**Coverage: {summary(result)}.**")
    return "\n".join(lines)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    ap = argparse.ArgumentParser(
        prog="gitcad-capability",
        description="Probe the kernel: every seam operation x every solid "
                    "representation. The refused cells are the roadmap; the "
                    "crash cells are bugs.")
    ap.add_argument("--md", action="store_true", help="markdown table")
    ap.add_argument("--crashes", action="store_true",
                    help="list only the raw-crash cells (defects)")
    ap.add_argument("--single", action="store_true",
                    help="single-op tier only (skip the composed grid)")
    args = ap.parse_args()
    r = probe()
    rc = None if args.single else probe_composed()
    if args.crashes:
        for res in (r, rc) if rc else (r,):
            for (s, o), msg in sorted(res["detail"].items()):
                if res["grid"].get(s, {}).get(o) == "CRASH":
                    print(f"{s:24} {o:24} {msg}")
        return
    if args.md:
        out = [to_markdown(r, title="single operations (fresh solid)")]
        if rc:
            out.append("")
            out.append(to_markdown(rc, title="composed operations "
                                             "(result-of-an-op as operand — #10)"))
            out.append("")
            out.append(f"**Headline (the honest pair): {headline(r, rc)}.**")
        print("\n".join(out))
    else:
        chunks = [_plain(r)]
        if rc:
            chunks.append(_plain(rc))
            chunks.append(f"headline: {headline(r, rc)}")
        print("\n".join(c for c in chunks if c))


def _plain(r: dict) -> str:
    rows = []
    for sname, row in r["grid"].items():
        for oname, v in row.items():
            if v in ("refused", "CRASH"):
                rows.append(f"{v:8} {sname:24} {oname:16} "
                            f"{r['detail'].get((sname, oname), '')[:70]}")
    return "\n".join(rows)


if __name__ == "__main__":  # pragma: no cover
    main()
