"""What KIND of problem is each composed refusal? — the denominator probe.

`capability.py` counts the gaps. This says what they ARE, and the distinction
decides the roadmap, because "101 composed gaps" silently bundles three
families whose costs differ by an order of magnitude:

``plane x quadric``    a plane meeting a quadric in a CONIC. Elementary. This
                       is exactly what K2.x rung 1 (a flat on a round bar) and
                       rung 2 (a plane cutting a sphere) already do, one narrow
                       recogniser at a time.
``quadric x quadric``  general SSI — two curved surfaces meeting in a space
                       curve with no elementary parameterisation.
``never a boolean``    shell / fillet / export, which are K4.2 / K5.2 / K3.7 and
                       not this problem at all.

WHY THIS IS INSTRUMENTED RATHER THAN GREPPED. The refusal strings name a stage
and a blocker, and reading them back is how the backlog got the previous
estimate — "~77 of the 101 remaining gaps: one problem, K2.x/K7, real
mathematics". That reading is wrong in both directions, and only the operands
show it: a message saying "quadric operands (RevolveSolid)" is a plane cutting
a revolve, not two quadrics meeting. So this wraps `RefKernel.boolean`, keeps
the operands of the call that actually RAISED — a chain like "cut then cut"
makes several and only the escaping one defines the cell — and reads each
operand's real surface inventory through forge's canonical `to_body`.

THE THIRD CATEGORY THE STRINGS CANNOT SHOW. A cell being `plane x quadric` says
the intersection CURVES are conics; it does not say the VOLUME lands in an
exact field. For a straight-walled prism through a sphere or a cone it provably
does not — `capability._EXACT_FIELD_BOUNDARY` carries those two proofs already
(an arcsin, and ln(1+sqrt2) by Baker). Cells whose representation has such a
tier-1 proof are reported separately as WALL CANDIDATES: they are arguments for
`_EXACT_FIELD_BOUNDARY_COMPOSED` to grow a transfer proof, not work for the
geometry roadmap. Counting them as tractable would overstate the prize, which
is the same failure mode as counting them as gaps.

Run it with ``python -m gitcad.bench.refusals``.
"""

from __future__ import annotations

import collections
import tempfile

from gitcad.errors import KernelError

from . import capability


def _surface_types():
    from forgekernel import body as fbody

    return fbody, (fbody.Cylinder, fbody.Cone, fbody.SphereS, fbody.Torus)


def inventory(s) -> tuple[collections.Counter, str]:
    """(surface-kind counter, how we know) for one boolean operand.

    Three routes, most authoritative first: the canonical B-rep's own faces, a
    conversion through forge's `to_body`, and — only if neither works — nothing
    at all. A guess is never returned as a measurement; an operand we cannot
    read comes back empty and is counted as unknown.
    """
    from forgekernel.brep import Solid

    fbody, _ = _surface_types()
    c: collections.Counter = collections.Counter()
    if isinstance(s, fbody.Body):
        for f in s.faces:
            c[type(f.surface).__name__] += 1
        return c, "Body.faces"
    if isinstance(s, Solid):
        # a Solid is polygon soup by construction: every face is planar. This
        # is the .faces/.polys split the whole classification rests on.
        c["Plane"] += len(getattr(s, "polys", ()))
        return c, "Solid.polys"
    try:
        b = fbody.to_body(s)
        for f in b.faces:
            c[type(f.surface).__name__] += 1
        return c, "to_body()"
    except Exception as exc:                                    # noqa: BLE001
        return c, f"opaque:{type(s).__name__} ({type(exc).__name__})"


def classify(ia: collections.Counter, ib: collections.Counter) -> str:
    _, quads = _surface_types()
    qn = {t.__name__ for t in quads}

    def curved(c):
        return sum(n for k, n in c.items() if k in qn)

    if not ia or not ib:
        return "unknown"
    ca, cb = curved(ia), curved(ib)
    if ca and cb:
        return "quadric x quadric"
    if ca or cb:
        return "plane x quadric"
    return "plane x plane"


def collect() -> list[dict]:
    """One record per composed gap, carrying the operands that refused."""
    from gitcad.kernel import get_kernel
    from gitcad.kernel.ref import RefKernel

    fbody, quads = _surface_types()
    qn = {t.__name__ for t in quads}

    k = get_kernel()
    tmpdir = tempfile.mkdtemp()
    shapes = capability.representations(k)
    ops = capability.composed_operations(k, tmpdir)
    boundary = capability._EXACT_FIELD_BOUNDARY_COMPOSED
    tier1 = capability._EXACT_FIELD_BOUNDARY

    last: dict = {}
    real = RefKernel.boolean

    def spy(self, op, a, b):
        try:
            return real(self, op, a, b)
        except KernelError:
            last["operands"] = (op, a, b)
            raise

    RefKernel.boolean = spy
    out: list[dict] = []
    try:
        for sname, shape in shapes.items():
            if isinstance(shape, tuple) and shape and shape[0] == "<unbuildable>":
                continue
            for oname, fn in ops.items():
                last.clear()
                try:
                    fn(shape)
                except KernelError as exc:
                    diag = getattr(getattr(exc, "signature", None),
                                   "diagnostic", "")
                    if diag == "BadInput" or (sname, oname) in boundary:
                        continue
                    rec = {"rep": sname, "op": oname, "msg": str(exc)}
                    if "operands" in last:
                        _, a, b = last["operands"]
                        ia, howa = inventory(a)
                        ib, howb = inventory(b)
                        rec.update(kind=classify(ia, ib), a=ia, b=ib,
                                   how=(howa, howb),
                                   types=(type(a).__name__, type(b).__name__),
                                   body=any(isinstance(x, fbody.Body)
                                            for x in (a, b)))
                        if rec["kind"] == "plane x quadric":
                            curved = ia if any(x in qn for x in ia) else ib
                            rec["families"] = tuple(
                                sorted(x for x in curved if x in qn))
                            rec["tool_is_planar"] = curved is ia
                            # a straight prism through THIS representation is
                            # already a proven wall at tier 1 — so this cell is
                            # a candidate for the composed boundary, not for
                            # the roadmap, pending a transfer proof
                            rec["wall_candidate"] = (sname, "cut box") in tier1
                    else:
                        rec["kind"] = "never a boolean"
                        # export_step refuses ON a Body — the canonical B-rep is
                        # still the operand even though no boolean ran, and
                        # missing that is what made the Body tally read 78
                        rec["body"] = " on Body" in rec["msg"]
                    out.append(rec)
                except Exception:                               # noqa: BLE001
                    pass                                        # CRASH, not a gap
    finally:
        RefKernel.boolean = real
    return out


def report(rows: list[dict] | None = None) -> str:
    rows = collect() if rows is None else rows
    n = len(rows)
    kinds = collections.Counter(r["kind"] for r in rows)
    boolean = [r for r in rows if r["kind"] != "never a boolean"]
    pxq = [r for r in boolean if r["kind"] == "plane x quadric"]
    walls = [r for r in pxq if r.get("wall_candidate")]
    live = [r for r in pxq if not r.get("wall_candidate")]
    ssi = [r for r in boolean if r["kind"] == "quadric x quadric"]

    L = [f"composed gaps: {n}", ""]
    for kk, v in kinds.most_common():
        L.append(f"  {v:4}  {kk}")
    L += ["", f"of the {len(boolean)} that are BOOLEAN refusals:",
          f"  {len(pxq):4}  plane x quadric  (conic intersections)",
          f"  {len(ssi):4}  quadric x quadric  (general SSI)", ""]
    L += [f"and splitting the {len(pxq)} plane x quadric by whether an exact "
          f"answer can exist at all:",
          f"  {len(live):4}  LIVE — cylinder-bearing, elementary closed forms",
          f"  {len(walls):4}  WALL CANDIDATES — this representation's straight-"
          f"prism cut is",
          f"        ALREADY a proven tier-1 transcendence. Each needs "
          f"adjudicating",
          f"        one way or the other: a transfer proof moves it to",
          f"        _EXACT_FIELD_BOUNDARY_COMPOSED, and a proof that does NOT",
          f"        transfer (a cone on its side is not the upright integral)",
          f"        hands it back to the roadmap. Neither counting them as",
          f"        tractable nor as gaps is honest until that is done.", ""]

    fams = collections.Counter(" + ".join(r["families"]) for r in live)
    L.append(f"the {len(live)} live cells, by quadric family:")
    for kk, v in fams.most_common():
        L.append(f"  {v:4}  plane x [{kk}]")
    side = collections.Counter(
        "planar operand is the TOOL" if r["tool_is_planar"]
        else "planar operand is the TARGET" for r in live)
    L.append("")
    for kk, v in side.most_common():
        L.append(f"  {v:4}  {kk}")

    L += ["", f"the {len(ssi)} general-SSI cells:"]
    for r in ssi:
        L.append(f"  {r['rep']:22} {r['op']:16} "
                 f"{dict(r['a'])} x {dict(r['b'])}")

    L += ["", f"the {kinds['never a boolean']} gaps that never reach a "
              f"boolean:"]
    nb = collections.Counter(r["msg"].split("(")[0][:52]
                             for r in rows if r["kind"] == "never a boolean")
    for kk, v in nb.most_common():
        L.append(f"  {v:4}  {kk}")

    nbody = sum(1 for r in rows if r.get("body"))
    L += ["", f"BODY: {n - nbody} of {n} composed gaps never involve a Body "
              f"operand; {nbody} do.",
          f"  ({sum(1 for r in boolean if r.get('body'))} as a boolean "
          f"operand, {sum(1 for r in rows if r['kind'] == 'never a boolean' and r.get('body'))} "
          f"as an export_step operand)"]
    return "\n".join(L)


def main() -> None:  # pragma: no cover - CLI
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    print(report())


if __name__ == "__main__":  # pragma: no cover
    main()
