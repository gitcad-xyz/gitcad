"""A shell answer is the shell that was asked for, or a refusal. Never a third
thing.

Dogfood #20 was the third thing: ``shell(frustum, [bottom], 2)`` reached the
open-shell-on-a-box branch, cut the inward-inset BOUNDING-BOX void, and returned
1480 mm^3 with ``geometry_verified: true`` where the true 2 mm shell is
~5514 mm^3. Every layer below this one accepted it, and had to:

- the ANSWER AUDIT checks that the returned body is closed, oriented and
  positive — the bbox-void solid was all three. A well-formed wrong solid is
  invisible to it (test_shell_erosion learned the same lesson by construction).
- the GOLDEN suite pins requests someone curated. The wrong solid came from a
  request nobody had written down.
- the REGRESSION test for #20 pins today's capability boundary — "a non-box
  base refuses" — which is exactly what ADR-0005 says a regression test is: a
  disposable pin on the current implementation. The day a K4.x lands that CAN
  shell a frustum, that pin is rightly deleted, and nothing is left demanding
  that the new answer be the RIGHT frustum shell rather than the next
  plausible void.

So this file pins the seam contract itself, in a form no capability change can
outgrow. ``Kernel.shell(base, remove_faces, t)`` means: the base, minus the
material deeper than ``t`` from the retained boundary, the removed faces
becoming openings. From that meaning alone, over a corpus of requests:

    every ANSWER must stay inside its base, must have removed material, must
    still be material within t/2 behind each retained face, must be void
    behind an opening and at depth >= 2t, and must land on the closed-form
    volume where one is banked. A REFUSAL (any GitcadError) always passes:
    honesty about a gap is the contract working. Any OTHER exception is a
    crash and fails — a refusal is an answer, a TypeError is not (#10).

The void probes sit >= 2t from every retained face so they are void under any
defensible thickness convention (metric erosion and per-plane offset agree
there); the wall probes sit at t/2, inside the wall under all of them. Probe
membership is asked with the kernel's own booleans, chamfer-invariant style;
where a boolean cannot yet take the answer's representation (lathe shells
return a ``Body`` the boolean refuses today) the probe is skipped as a
measurement gap and the banked closed form carries the case — and the ratchet
below keeps "skipped" from quietly becoming "all of them".

Only public seam surface is used: ``get_kernel`` and ``Kernel`` methods. No
``RefKernel``, no ``forgekernel`` types — a replacement backend inherits this
file unchanged.
"""

from __future__ import annotations

import math

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from gitcad.errors import GitcadError
from gitcad.kernel import get_kernel

PROBE = 0.25                      # probe-cube side; << every corpus thickness
PROBE_VOL = PROBE ** 3


@pytest.fixture(scope="module")
def k():
    # require= : this file is ABOUT the geometry kernel. Falling back to the
    # null backend would turn every case into a refusal and prove nothing.
    return get_kernel(require="forge")


def _vol(k, s) -> float:
    return float(k.mass_props(s)["volume"])


def _probe_removed(k, solid, p):
    """Volume a tiny cube centered at ``p`` removes from ``solid`` — the
    membership question asked with the kernel's own boolean. ``None`` when the
    boolean refuses the operands (a measurement gap, not a wrong answer)."""
    h = PROBE / 2
    cube = k.transform(k.box(PROBE, PROBE, PROBE),
                       translate=(p[0] - h, p[1] - h, p[2] - h))
    try:
        return _vol(k, solid) - _vol(k, k.boolean("cut", solid, cube))
    except GitcadError:
        return None


def _planar_faces(k, shape):
    """(index, centroid, unit normal) for every face descriptor that carries
    both — the faces we can aim a wall probe at. Orientation of the normal is
    NOT trusted; the probe resolves inward against the base itself."""
    out = []
    for i, f in enumerate(k.entities(shape, "face")):
        if f.get("surface") != "plane":
            continue
        c, n = f.get("centroid"), f.get("plane")
        if c is None or n is None:
            continue
        norm = math.sqrt(sum(v * v for v in n))
        out.append((i, [float(v) for v in c], [float(v) / norm for v in n]))
    return out


def _square(half):
    return {"start": [-half, -half],
            "segments": [{"kind": "line", "to": [half, -half]},
                         {"kind": "line", "to": [half, half]},
                         {"kind": "line", "to": [-half, half]},
                         {"kind": "line", "to": [-half, -half]}]}


def _face_at_z(k, shape, z):
    return next(i for i, c, _n in _planar_faces(k, shape)
                if c[2] == pytest.approx(z))


# --------------------------------------------------------------------------
# The corpus. Each case: build -> (base, remove_faces), thickness, banked
# closed-form volume (None = nobody has derived one; probes carry it),
# deep-void points (each >= 2t inside the retained boundary), and an explicit
# behind-the-opening point for open shells (>= 2t from every retained face,
# so it is void under any offset convention).
#
# Frustum closed form, derived not fitted: base |x|,|y| <= 20 - z/2,
# z in [0, 20]; sloped plane 2x + z = 40 has unit normal (2,0,1)/sqrt5, so the
# perpendicular-t offset shifts it by t*sqrt5/2 horizontally. With t=2 and the
# bottom removed, the void is the convex frustum |x|,|y| <= 20 - z/2 - sqrt5,
# z in [0, 18]: volume ((40-2sqrt5)^3 - (22-2sqrt5)^3)/12 * ... integrated,
# = 18144 - 2232*sqrt5. Shell = 56000/3 - 18144 + 2232*sqrt5 ~ 5513.5704.
# Verified against an independent Monte-Carlo membership test
# (dist(p, retained boundary) >= t, 400k samples, seed 987654321):
# MC 5501 +/- 19 (1 sigma). The #20 report's "~3900 mm^3" was itself a wrong
# number; the bbox void measured 1480 mm^3 either way.
# --------------------------------------------------------------------------

def _box_open(k):
    base = k.box(10, 10, 10)
    return base, [_face_at_z(k, base, 10.0)]


def _box_closed(k):
    return k.box(10, 10, 10), []


def _cyl_closed(k):
    return k.cylinder(5, 10), []


def _cyl_open(k):
    base = k.cylinder(5, 10)
    return base, [_face_at_z(k, base, 10.0)]


def _sphere_closed(k):
    return k.sphere(6.0), []


def _frustum_open(k):
    base = k.loft([(_square(20.0), 0.0), (_square(10.0), 20.0)], ruled=True)
    return base, [_face_at_z(k, base, 0.0)]


def _lshape_open(k):
    base = k.boolean("union", k.box(20, 20, 10),
                     k.transform(k.box(10, 20, 10), translate=(0, 0, 10)))
    return base, [_face_at_z(k, base, 0.0)]


CASES = [
    # id, build, t, exact volume, deep-void points, behind-the-opening point
    ("box open top", _box_open, 1.0,
     1000 - 8 * 8 * 9, [(5, 5, 5)], (5, 5, 9.5)),
    ("box closed", _box_closed, 1.0,
     1000 - 8 * 8 * 8, [(5, 5, 5)], None),
    ("cylinder closed", _cyl_closed, 1.0,
     math.pi * (5 * 5 * 10 - 4 * 4 * 8), [(0, 0, 5)], None),
    ("cylinder open top", _cyl_open, 1.0,
     math.pi * (5 * 5 * 10 - 4 * 4 * 9), [(0, 0, 5)], (0, 0, 9.5)),
    ("sphere closed", _sphere_closed, 1.0,
     4 * math.pi / 3 * (6 ** 3 - 5 ** 3), [(0, 0, 0)], None),
    ("frustum open bottom", _frustum_open, 2.0,
     56000 / 3 - 18144 + 2232 * math.sqrt(5), [(0, 0, 8)], (0, 0, 1)),
    # the L's reentrant corner erodes as a quarter-cylinder fillet; no closed
    # form banked, so the probes alone carry this case if it is ever answered
    ("L open bottom", _lshape_open, 2.0,
     None, [(15, 10, 5)], (5, 10, 1)),
]
IDS = [c[0] for c in CASES]


def _run_case(k, build, t):
    """Build the request, ask, and return (base, remove, answer|None)."""
    base, remove = build(k)
    try:
        return base, remove, k.shell(base, remove, t)
    except GitcadError:
        # the honest refusal: always an acceptable answer to any request.
        # Anything OTHER than a GitcadError propagates and fails the test —
        # a crash is not a refusal.
        return base, remove, None


@pytest.mark.parametrize("name,build,t,exact,deep,opening", CASES, ids=IDS)
def test_an_answered_shell_is_the_solid_that_was_asked_for(
        k, name, build, t, exact, deep, opening) -> None:
    base, remove, out = _run_case(k, build, t)
    if out is None:
        return                             # an honest refusal proves nothing

    bad = []
    vb = _vol(k, base)
    vo = _vol(k, out)

    # (a) hollowing removed material and invented none: 0 < vol < base
    if not 0 < vo < vb:
        bad.append(f"volume {vo} not strictly inside (0, base={vb})")

    # (b) containment: nothing of the answer lies outside its base
    try:
        leftover = _vol(k, k.boolean("cut", out, base))
        if leftover > 1e-9 * vb:
            bad.append(f"answer sticks out of its base by {leftover} mm^3")
    except GitcadError:
        pass                               # measurement gap; ratcheted below

    # (c) the banked closed form, where one exists
    if exact is not None and vo != pytest.approx(exact, rel=1e-9):
        bad.append(f"volume {vo}, closed form {exact}")

    # (d) walls: material within t/2 behind every retained planar face
    for i, c, n in _planar_faces(k, base):
        if i in remove:
            continue
        for sgn in (1.0, -1.0):
            p = [c[j] + sgn * n[j] * (t / 2) for j in range(3)]
            if _probe_removed(k, base, p) == pytest.approx(PROBE_VOL):
                got = _probe_removed(k, out, p)     # p is INSIDE the wall
                if got is not None and got != pytest.approx(PROBE_VOL):
                    bad.append(f"face {i}: wall at {p} is missing material "
                               f"(probe removed {got} of {PROBE_VOL})")
                break

    # (e) the hollow is hollow, and the opening is open
    for label, p in ([("deep void", q) for q in deep]
                     + ([("behind the opening", opening)] if opening else [])):
        got = _probe_removed(k, out, p)
        if got is not None and got != pytest.approx(0.0, abs=1e-12):
            bad.append(f"{label} at {p} still holds {got} mm^3 of material")

    assert bad == [], (f"shell({name}, t={t}) answered a DIFFERENT solid:\n  "
                       + "\n  ".join(bad))


def test_the_dichotomy_is_not_satisfied_vacuously(k) -> None:
    """A corpus where every case refuses — or where every probe hits a
    measurement gap — would pass the test above while checking nothing. Pin
    how much real work it does, as a RATCHET, at the measured numbers:
    today 4 of 7 requests are answered and 14 probes actually run (11 walls
    and 3 voids, all on the planar answers; the lathe answers refuse the
    probe boolean and are carried by their closed forms). Raise the floors
    when coverage genuinely improves — never lower them to make a red suite
    green."""
    answered, probes = 0, 0
    for name, build, t, exact, deep, opening in CASES:
        base, remove, out = _run_case(k, build, t)
        if out is None:
            continue
        answered += 1
        for i, c, n in _planar_faces(k, base):
            if i in remove:
                continue
            for sgn in (1.0, -1.0):
                p = [c[j] + sgn * n[j] * (t / 2) for j in range(3)]
                if _probe_removed(k, base, p) == pytest.approx(PROBE_VOL):
                    if _probe_removed(k, out, p) is not None:
                        probes += 1
                    break
        for p in list(deep) + ([opening] if opening else []):
            if _probe_removed(k, out, p) is not None:
                probes += 1
    assert answered >= 4, f"only {answered} corpus requests answered"
    assert probes >= 14, f"only {probes} membership probes actually ran"
