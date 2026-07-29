"""How much of the PARAMETER SPACE does a green cell actually cover?

`capability.py` scores a cell green when one representative solid meets one
representative operation. That is the right instrument for "can the kernel do
this at all", and it is silent about the question a user actually has: will it
answer for MY hole position, MY flat depth. Those are different questions, and
for the exact rungs they have wildly different answers.

The gap is not hypothetical. `flat.py` (K2.x rung 1, a flat milled on a round
bar) is a green cell whose admissible set is FIVE depths out of a continuum:
the removed area is r^2(t - sin t cos t) with t = arccos(h/r), and by Niven an
arc angle lands in Q*pi only at multiples of 30 degrees. Rung 2 (a plane
cutting a sphere) is a green cell that answers everywhere, because its closed
form is a polynomial in the cut height and contains no angle at all. Both are
one green cell each on the matrix. One of them is a capability and the other
is a demonstration.

So the discriminator is not which quadric is involved, nor even which curve
the surfaces meet in — it is whether the ANSWER carries an arc angle. This
sweep measures that directly, and it is the number to watch when deciding
whether a rung is worth building exactly or belongs on ADR-0019's certified
path.

Run it with ``python -m gitcad.bench.coverage``.
"""

from __future__ import annotations

from fractions import Fraction as F

from gitcad.errors import KernelError

#: a big tool, used as a half-space by placing one wall in the material
_BIG = F(400)


def _families(k):
    """(name, what the parameter is, sweep, build) for each rung.

    Every build takes one exact rational and returns a solid or raises. The
    sweeps are rationals with small denominators — the numbers a person types,
    not adversarial ones.
    """

    def half_space(along: int, at, positive: bool):
        """A tool filling the half-space beyond `at` on axis `along`."""
        t = [-_BIG / 2] * 3
        t[along] = at if positive else at - _BIG
        return k.transform(k.box(_BIG, _BIG, _BIG), translate=tuple(t))

    def flat_on_bar(h):
        return k.boolean("cut", k.cylinder(5, 12), half_space(0, h, True))

    def cap_on_sphere(hc):
        return k.boolean("cut", k.sphere(5), half_space(2, hc, True))

    def face_off_a_box(x):
        return k.boolean("cut", k.box(20, 20, 10), half_space(0, x, True))

    def drill_a_plate(x):
        """A through bore whose CENTRE walks toward the plate's wall."""
        return k.boolean("cut", k.box(40, 20, 5),
                         k.transform(k.cylinder(4, 20), translate=(x, 10, -1)))

    def pocket_a_bar(z):
        """A square pocket sunk into the end of a round bar, depth swept."""
        return k.boolean("cut", k.cylinder(5, 12),
                         k.transform(k.box(4, 4, 20), translate=(-2, -2, z)))

    def slot_through_a_bar(x):
        """The COMPOSED GRID'S OWN SHAPE: a narrow prism driven clean through
        a round bar, its offset swept. Both walls cross the barrel, so the
        remaining cross-section is a disc minus a rectangle — two circular
        SEGMENTS, and therefore two arc angles."""
        return k.boolean("cut", k.cylinder(5, 12),
                         k.transform(k.box(2, 40, 40), translate=(x, -20, -20)))

    def bore_across_a_wall(x):
        """A bore whose centre walks OUT through the plate's wall — the
        17-cell "bore crosses a lateral wall" family. Where it crosses, the
        removed cross-section is a partial disc."""
        return k.boolean("cut", k.box(40, 20, 5),
                         k.transform(k.cylinder(4, 20), translate=(x, 10, -1)))

    quarters = [F(n, 4) for n in range(-16, 17)]
    return [
        ("face off a box (planar control)", "cut plane x",
         [F(n, 4) for n in range(1, 78)], face_off_a_box),
        ("cap on a sphere (rung 2)", "cut height z", quarters, cap_on_sphere),
        ("drill a plate (bore fully inside)", "bore centre x",
         [F(n, 4) for n in range(20, 61)], drill_a_plate),
        ("pocket into a bar", "pocket floor z", [F(n, 4) for n in range(1, 40)],
         pocket_a_bar),
        ("flat on a bar (rung 1)", "flat depth x", quarters, flat_on_bar),
        ("slot through a bar (the grid's shape)", "slot offset x",
         [F(n, 4) for n in range(-12, 13)], slot_through_a_bar),
        ("bore across a plate wall (17-cell family)", "bore centre x",
         [F(n, 4) for n in range(-8, 25)], bore_across_a_wall),
    ]


def sweep(k=None) -> list[dict]:
    if k is None:
        from gitcad.kernel import get_kernel

        k = get_kernel()
    out = []
    for name, param, values, build in _families(k):
        ok, refused, other = [], 0, 0
        for v in values:
            try:
                build(v)
                ok.append(v)
            except KernelError:
                refused += 1
            except Exception:                                # noqa: BLE001
                other += 1
        out.append({"family": name, "parameter": param, "n": len(values),
                    "ok": ok, "refused": refused, "other": other})
    return out


def report(rows: list[dict] | None = None) -> str:
    rows = sweep() if rows is None else rows
    L = ["parameter-space coverage — a green CELL is not a green FAMILY", ""]
    w = max(len(r["family"]) for r in rows)
    for r in rows:
        n, got = r["n"], len(r["ok"])
        pct = 100 * got / n if n else 0
        L.append(f"  {r['family']:<{w}}  {got:3}/{n:<3} ({float(pct):3.0f}%)  "
                 f"over {r['parameter']}")
    L.append("")
    for r in rows:
        got = len(r["ok"])
        if got and got < r["n"]:
            vals = ", ".join(str(v) for v in r["ok"][:12])
            L.append(f"  {r['family']} answers ONLY at: {vals}"
                     + (" ..." if got > 12 else ""))
    L += ["",
          "THE SPLIT IS NOT ABOUT WHICH QUADRIC. It is about whether the cut",
          "leaves a circular SEGMENT. A full disc removed (a bore inside the",
          "material), a polygon (a pocket), or a plane cutting a sphere all",
          "have polynomial closed forms and answer everywhere. A chord across",
          "a disc leaves r^2(t - sin t cos t) with t = arccos(h/r), and by",
          "Niven that is exact only at twelfths — measure zero.",
          "",
          "So a family in single digits is not a rung that needs finishing.",
          "It is a rung that cannot be finished exactly, and belongs on",
          "ADR-0019's certified path instead."]
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
