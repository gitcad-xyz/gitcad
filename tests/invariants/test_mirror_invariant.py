"""Every operation commutes with reflection.

Shelling is defined by DISTANCE; chamfering and filleting by the faces
themselves; a boolean by point-set membership. None of those notice a change
of handedness, so for any isometry σ:

    op(σS)  ≡  σ op(S)

and in particular the two have the SAME VOLUME. A disagreement is therefore a
bug with no appeal to implementation detail — it needs nobody to have guessed
which configuration would break.

This is why the file exists. On 2026-07-28 this sweep found ``shell`` of a
tapered solid returning **206.04 mm³ where the truth is 418.04 — 50.7% wrong**,
with ``valid=True``, shipped in 0.9.10 and earlier. A 1545-test suite, the
answer audit, and a 345-cell capability grid had all scored that cell as
working. The invariant found it in one pass, because it does not need to know
what a right prism is.

An INVARIANT, not a regression: it is architecture-independent and outlives any
particular kernel (CLAUDE.md — ``tests/invariants/`` is the real spec).

Two outcomes count as agreement:
  * both succeed with equal volume, or
  * both refuse.
A shape that builds one way up and refuses mirrored is a capability gap, not a
wrong number; those are tracked in #89 and listed in ``ASYMMETRIC_KNOWN`` so
this file fails on anything NEW rather than on the backlog.
"""

from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from gitcad.bench.capability import representations
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def shapes(k):
    return {n: s for n, s in representations(k).items()
            if not isinstance(s, tuple)}


def _mid(k, s):
    lo, hi = k.bbox(s)
    return [(float(lo[i]) + float(hi[i])) / 2 for i in range(3)]


def _ops(k):
    return {
        "shell": lambda s: k.shell(s, [], 1),
        "chamfer": lambda s: k.chamfer(s, None, 1),
        "fillet": lambda s: k.fillet(s, None, 1),
        "cut": lambda s: k.boolean("cut", s, k.transform(
            k.box(2, 2, 500), translate=(_mid(k, s)[0], _mid(k, s)[1], -250))),
    }


#: (shape, op) pairs that build one way up and REFUSE mirrored — capability
#: gaps, not wrong numbers (#89 part 3). Listed so a NEW asymmetry fails here.
#: chamfer/loft is the one open WRONG NUMBER (#89 part 2) and is xfailed below.
#: 34 pairs, measured 2026-07-28 — not hand-listed. Every one is a CURVED or
#: composite representation whose mirror image the feature path cannot take;
#: none is a wrong number. The list shrinks as ADR-0021 lands, and shrinking it
#: is the point — do NOT grow it to silence a new failure without first
#: proving the new case is a gap rather than a wrong answer.
ASYMMETRIC_KNOWN = {
    ("bored boss", "chamfer"), ("bored boss", "fillet"),
    ("bored boss", "shell"),
    ("cone", "chamfer"), ("cone", "shell"),
    ("counterbore", "chamfer"), ("counterbore", "fillet"),
    ("counterbore", "shell"),
    ("cylinder", "chamfer"), ("cylinder", "cut"),
    ("cylinder", "fillet"), ("cylinder", "shell"),
    ("disjoint union (boss)", "chamfer"), ("disjoint union (boss)", "cut"),
    ("disjoint union (boss)", "fillet"), ("disjoint union (boss)", "shell"),
    ("drilled (blind)", "chamfer"), ("drilled (blind)", "fillet"),
    ("drilled (blind)", "shell"),
    ("drilled (through)", "chamfer"), ("drilled (through)", "cut"),
    ("drilled (through)", "fillet"), ("drilled (through)", "shell"),
    ("filleted box", "chamfer"), ("filleted box", "cut"),
    ("filleted box", "fillet"), ("filleted box", "shell"),
    ("revolve", "chamfer"), ("revolve", "cut"),
    ("revolve", "fillet"), ("revolve", "shell"),
    ("sphere", "chamfer"), ("sphere", "fillet"), ("sphere", "shell"),
}

#: #89 part 2 — chamfer of a tapered solid disagrees with its own mirror
#: (100.548 vs 98.593). Proven wrong; not yet fixed, because the true value
#: has not been independently derived and pinning an unverified number would
#: be the same mistake in the other direction.
KNOWN_WRONG = {("loft", "chamfer")}


def _outcome(fn, shape):
    try:
        return fn(shape)
    except KernelError:
        return "refused"
    except Exception as exc:                      # noqa: BLE001
        return f"CRASH {type(exc).__name__}: {exc}"


@pytest.mark.parametrize("plane", ["xy", "yz"])
@pytest.mark.parametrize("op", ["shell", "chamfer", "fillet", "cut"])
def test_every_op_commutes_with_reflection(k, shapes, op, plane):
    fn = _ops(k)[op]
    problems = []
    for name, s in shapes.items():
        if (name, op) in KNOWN_WRONG:
            continue
        try:
            m = k.mirror(s, plane)
        except Exception:                         # noqa: BLE001
            continue                              # mirror itself unsupported
        # a reflection is an isometry: the SOLID's volume must survive it,
        # or nothing below means anything
        assert k.mass_props(s)["volume"] == k.mass_props(m)["volume"], \
            f"{name}: mirror changed the solid's own volume"

        a, b = _outcome(fn, s), _outcome(fn, m)
        for x in (a, b):
            if isinstance(x, str) and x.startswith("CRASH"):
                problems.append(f"{name}: {x}")
        if isinstance(a, str) or isinstance(b, str):
            if (a == "refused") != (b == "refused"):
                if (name, op) not in ASYMMETRIC_KNOWN:
                    problems.append(
                        f"{name}: builds one way, refuses mirrored "
                        f"({'refused' if a == 'refused' else 'built'} vs "
                        f"{'refused' if b == 'refused' else 'built'})")
            continue
        va, vb = k.mass_props(a)["volume"], k.mass_props(b)["volume"]
        if va != vb:
            problems.append(
                f"{name}: {va} vs {vb} (delta {abs(va - vb):.6g}) — one of "
                f"these is a WRONG NUMBER; a reflection preserves volume")
    assert not problems, "\n  ".join([f"{op}/{plane} violations:"] + problems)


@pytest.mark.xfail(reason="#89 part 2: chamfer of a tapered solid disagrees "
                          "with its mirror (100.548 vs 98.593); true value "
                          "not yet derived", strict=True)
def test_chamfer_of_a_tapered_solid_is_still_inconsistent(k, shapes):
    s = shapes["loft"]
    a = k.mass_props(k.chamfer(s, None, 1))["volume"]
    b = k.mass_props(k.chamfer(k.mirror(s, "xy"), None, 1))["volume"]
    assert a == b
