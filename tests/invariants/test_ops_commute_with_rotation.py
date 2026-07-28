"""Turning a part before machining it does not change the part.

The mirror invariant's other half. A rotation is an isometry, so for any
orientation-free operation ``op(R S) ≡ R op(S)`` — and in particular the
VOLUME cannot move. Unlike most invariants this one needs no oracle at all,
because a box's chamfer and shell have closed forms:

    chamfer(box a×b×c, d) = abc − 2(a+b+c)d² + 6d³
    shell(box a×b×c, t)   = abc − (a−2t)(b−2t)(c−2t)

so every rotation of a box has a number that was known before the kernel ran.

What this caught: an exact rotation types every coordinate as ℚ[√d] EVEN WHERE
THE VALUE IS RATIONAL — a 20 mm edge turned 45° has dx = dy = 10√2 and
l² = 400 — and three separate places read ``.numerator`` off that or handed it
to ``Fraction()``. Two crashed raw through the seam (``shell`` of a rotated
box, ``TypeError``), one became a KernelError whose entire message was
``'SurdVal' object has no attribute 'numerator'``. Rotating a box 45° and
hollowing it is not an exotic thing to ask of a CAD kernel.

The fix is one function — ``forgekernel.exact.as_fraction`` — asked in every
one of those places instead of assumed. It is the companion to ``F``: ``F``
widens, ``as_fraction`` asks whether what came back is rational, and getting
that wrong has gone BOTH ways here (assume-rational crashed; assume-irrational
silently dropped a radical and reported 960 for 960 − 20√3).
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

#: every rotation the kernel represents exactly, about z
ANGLES = (0, 30, 45, 60, 90, 120, 135, 150, 180, 270)

A, B, C = 20, 20, 10
CHAMFER_D = 1
SHELL_T = 1
CHAMFER_V = A * B * C - 2 * (A + B + C) * CHAMFER_D ** 2 + 6 * CHAMFER_D ** 3
SHELL_V = A * B * C - (A - 2 * SHELL_T) * (B - 2 * SHELL_T) * (C - 2 * SHELL_T)


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _rot(k, s, deg):
    return s if deg == 0 else k.transform(s, rotate_axis=(0, 0, 1),
                                          rotate_deg=deg)


def test_the_closed_forms_are_what_we_think(k):
    """Check the oracle before using it, on the case it is trivially right
    about: an unrotated box."""
    box = k.box(A, B, C)
    assert CHAMFER_V == 3906 and SHELL_V == 1408
    assert k.mass_props(k.chamfer(box, None, CHAMFER_D))["volume"] == CHAMFER_V
    assert k.mass_props(k.shell(box, [], SHELL_T))["volume"] == SHELL_V


@pytest.mark.parametrize("deg", ANGLES)
def test_a_rotated_box_chamfers_to_its_closed_form(k, deg):
    out = k.chamfer(_rot(k, k.box(A, B, C), deg), None, CHAMFER_D)
    assert k.mass_props(out)["volume"] == CHAMFER_V, f"at {deg}°"
    assert k.validate(out).ok


@pytest.mark.parametrize("deg", ANGLES)
def test_a_rotated_box_shells_to_its_closed_form(k, deg):
    out = k.shell(_rot(k, k.box(A, B, C), deg), [], SHELL_T)
    assert k.mass_props(out)["volume"] == SHELL_V, f"at {deg}°"
    assert k.validate(out).ok


@pytest.mark.parametrize("deg", ANGLES)
def test_a_rotation_never_crashes_the_seam(k, deg):
    """The defect class, stated as a property: a rotated solid may be
    REFUSED by any op — that is a roadmap entry — but a raw exception through
    the seam is always a defect, whether or not the capability exists."""
    shapes = {"box": k.box(A, B, C),
              "prism": k.extrude({"start": [0, 0], "segments": [
                  {"kind": "line", "to": [30, 0]},
                  {"kind": "line", "to": [30, 10]},
                  {"kind": "line", "to": [10, 10]},
                  {"kind": "line", "to": [10, 30]},
                  {"kind": "line", "to": [0, 30]},
                  {"kind": "line", "to": [0, 0]}]}, 8),
              "cylinder": k.cylinder(5, 12)}
    ops = {"chamfer": lambda s: k.chamfer(s, None, 1),
           "shell": lambda s: k.shell(s, [], 1),
           "fillet": lambda s: k.fillet(s, None, 1),
           "mass_props": lambda s: k.mass_props(s),
           "tessellate": lambda s: k.tessellate(s),
           "validate": lambda s: k.validate(s)}
    for name, s in shapes.items():
        try:
            r = _rot(k, s, deg)
        except KernelError:
            continue
        for op, fn in ops.items():
            try:
                fn(r)
            except KernelError:
                pass                     # a refusal is honest
            except Exception as raw:     # pragma: no cover - the regression
                pytest.fail(f"{name}/{op} at {deg}°: raw "
                            f"{type(raw).__name__}: {raw}")


@pytest.mark.parametrize("deg", ANGLES)
def test_a_refusal_never_reads_like_an_internal_error(k, deg):
    """``chamfer`` once refused with the whole message ``'SurdVal' object has
    no attribute 'numerator'``. A refusal is part of the API — it has to name
    a stage a caller can act on, not leak a traceback line."""
    r = _rot(k, k.box(A, B, C), deg)
    for fn in (lambda s: k.chamfer(s, None, 1), lambda s: k.shell(s, [], 1),
               lambda s: k.fillet(s, None, 1)):
        try:
            fn(r)
        except KernelError as e:
            msg = str(e)
            assert "has no attribute" not in msg, msg
            assert "object at 0x" not in msg, msg
