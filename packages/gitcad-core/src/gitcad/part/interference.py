"""Real interference checking — co-design upgraded from "probably fits" to
"provably fits" (list item 4).

Envelope AABBs (Assembly.validate) are the fast pre-filter; this module is
the exact check: place each instance's real geometry with its transform and
boolean-intersect every pair. A nonzero common volume is a collision, with
the overlap measured in mm³ — not a guess, a measurement. Face-on-face
contact (mated parts touching) intersects with zero volume and passes.
"""

from __future__ import annotations

from gitcad.errors import KernelError, ValidationReport
from gitcad.seams import Kernel, Shape

_VOL_TOL = 1e-6  # mm^3 — below this, "intersection" is contact/noise


def _sampled_verdict(kernel, sa, sb, na, nb, tol, overlaps, where,
                     violations, undetermined) -> bool:
    """Try a SAMPLED intersect for a pair the exact engine refused (ADR-0024).

    Returns True if it produced a verdict (recorded into the caller's dicts),
    False to fall through to UNDETERMINED. Fail-closed by the bracket: a clash
    needs the overlap's lower bound above tol; a clear needs its upper bound
    below; anything straddling is left UNDETERMINED, never a false pass.
    """
    prev = getattr(kernel, "allow_sampled", False)
    key = f"{na}<->{nb}"
    try:
        kernel.allow_sampled = True
        common = kernel.boolean("intersect", sa, sb)
        mp = kernel.mass_props(common)
    except Exception:                                 # noqa: BLE001
        return False
    finally:
        kernel.allow_sampled = prev
    vol = float(mp.get("volume", 0.0))
    hw = float(mp.get("volume_halfwidth", 0.0))
    lo, hi = vol - hw, vol + hw
    if lo > tol:                                      # provably a clash
        overlaps[key] = round(vol, 4)
        where[key] = {"sampled": True, "halfwidth_mm3": round(hw, 4)}
        violations.append(
            f"interference:{na}<->{nb}:overlap~{float(vol):.3f}mm3 "
            f"(sampled +-{float(hw):.3f}, ADR-0024)")
        return True
    if hi <= tol:                                     # provably clear
        if vol > _VOL_TOL:
            overlaps[key] = round(vol, 4)
        return True
    return False                                      # straddles -> undetermined


def check_interference(
    kernel: Kernel,
    instances: dict[str, tuple[Shape, tuple[float, float, float], float]],
    *,
    ignore: set[frozenset[str]] | None = None,
    tol_mm3: float | None = None,
    sampled: bool = False,
) -> ValidationReport:
    """``instances``: name -> (shape, translate, rotate_z_deg). ``ignore``:
    pairs (as frozensets of names) intentionally in contact/overlap.
    ``tol_mm3``: allowed overlap volume per pair (None = exact, the strict
    default; a clash budget like 1.0 matches common enclosure practice).
    The pairwise overlap matrix is always reported — a passing check still
    shows HOW CLOSE it passed.

    ``sampled`` (ADR-0024): when the exact intersect refuses — which it does for
    ANY curved pair (a shaft in a bore, a boss on a wall), the reason "does it
    fit?" was previously unanswerable for real machine parts — fall back to a
    Monte-Carlo intersect with a reported error bracket. The verdict stays
    FAIL-CLOSED: a clash only when the bracket's LOWER bound clears the
    tolerance, clear only when its UPPER bound is under it, and UNDETERMINED
    when the bracket straddles — so sampling never turns an unproven clearance
    into a false pass, it only answers the pairs the exact engine cannot."""
    ignore = ignore or set()
    tol = _VOL_TOL if tol_mm3 is None else tol_mm3

    placed: dict[str, Shape] = {}
    boxes: dict[str, tuple] = {}
    for name, (shape, translate, rot_z) in instances.items():
        s = kernel.transform(shape, translate=translate,
                             rotate_axis=(0, 0, 1), rotate_deg=rot_z)
        placed[name] = s
        boxes[name] = kernel.bbox(s)

    def aabb_overlaps(a, b) -> bool:
        (alo, ahi), (blo, bhi) = a, b
        return all(alo[i] <= bhi[i] and blo[i] <= ahi[i] for i in range(3))

    violations: list[str] = []
    overlaps: dict[str, float] = {}
    where: dict[str, dict] = {}
    undetermined: dict[str, str] = {}
    names = sorted(placed)
    checked = 0
    for i, na in enumerate(names):
        for nb in names[i + 1:]:
            if frozenset({na, nb}) in ignore:
                continue
            if not aabb_overlaps(boxes[na], boxes[nb]):
                continue   # envelope pre-filter: cannot collide
            checked += 1
            try:
                common = kernel.boolean("intersect", placed[na], placed[nb])
            except KernelError as exc:
                if sampled and _sampled_verdict(
                        kernel, placed[na], placed[nb], na, nb, tol,
                        overlaps, where, violations, undetermined):
                    continue
                # A pair the kernel cannot evaluate is UNDETERMINED, never
                # clear. Reporting ok for it would repeat, one layer up, the
                # exact defect that motivated this branch: an unsound AABB
                # let `check_interference` certify a peg sitting entirely
                # inside a cone, because the boolean was skipped rather than
                # run. A clearance check that cannot compute an answer has not
                # found clearance — so it fails closed and says which pair and
                # why.
                undetermined[f"{na}<->{nb}"] = getattr(exc, "stage", "") or str(exc)
                violations.append(
                    f"interference:{na}<->{nb}:UNDETERMINED — the kernel could "
                    f"not intersect these shapes ({undetermined[f'{na}<->{nb}']}); "
                    "clearance is unproven, not established")
                continue
            vol = kernel.measure(common).get("volume", 0.0)
            if vol > _VOL_TOL:
                key = f"{na}<->{nb}"
                overlaps[key] = round(vol, 4)
                where[key] = _locate(kernel, common)
            if vol > tol:
                violations.append(f"interference:{na}<->{nb}:overlap={float(vol):.3f}mm3")

    return ValidationReport(
        ok=not violations,
        checks={"instances": len(instances), "pairs_intersected": checked,
                "overlaps_mm3": overlaps, "overlap_where": where,
                "undetermined": undetermined,
                "tol_mm3": tol,
                "method": "exact-boolean-common", "kernel": kernel.name},
        violations=violations,
    )


def _locate(kernel: Kernel, common: Shape) -> dict:
    """WHERE the clash is, in the assembly frame.

    A volume alone does not say what to change: 15.658 mm3 between a ring
    gear and a planet is equally consistent with wrong backlash, wrong tooth
    phasing, wrong centre distance and an axial fault, and each implies a
    different edit. The kernel has already built the common solid to measure
    it — reading its bounding box and centroid off before discarding it costs
    one call and turns the number into a lead.

    Never fatal: a shape whose bbox/centroid the kernel cannot produce still
    reports its volume, which is the pre-existing behaviour.
    """
    out: dict = {}
    try:
        lo, hi = kernel.bbox(common)
        out["bbox"] = [[round(float(c), 4) for c in lo],
                       [round(float(c), 4) for c in hi]]
        out["size"] = [round(float(b - a), 4) for a, b in zip(lo, hi)]
    except Exception:                        # noqa: BLE001 - advisory only
        pass
    try:
        props = kernel.mass_props(common)
        if "centroid" in props:
            out["centroid"] = [round(float(c), 4) for c in props["centroid"]]
    except Exception:                        # noqa: BLE001 - advisory only
        pass
    return out
