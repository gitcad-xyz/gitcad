"""Issue #9: a refusal must name the representation mismatch, not quote Python.

Two 0.9.9 refusals crossed the seam correctly wrapped as KernelError but with
raw Python exception text as their diagnostic:

    ref kernel does not implement boolean on Solid yet —
      unsupported representation ('Body' object has no attribute 'polys')

    ref kernel does not implement export_step on Body
      (argument should be a string or a Rational instance) yet — K3.7 ...

``'Body' object has no attribute 'polys'`` and ``as_integer_ratio`` are
internals of the implementation, not facts about the model. The contract this
file pins: a representation-mismatch refusal names WHAT representation cannot
take WHAT op, carries the stage that brings it, and offers a remedy — and
never quotes a Python exception at the caller (CLAUDE.md: refuse *by name*).

Both repros go through the same door: tilting a quadric routes it into the
canonical B-rep (a ``Body``, ADR-0021).

Since then the two halves have diverged, and the file records both outcomes
rather than pretending they are still one story. The STEP half was never a
missing capability — only a missing NUMERAL: ``Fraction(x)`` cannot hold a
ℚ[√3] coordinate, and that TypeError was being reported as an unsupported
representation. A tilted cylinder now exports as a real CYLINDRICAL_SURFACE.
The BOOLEAN half is a genuine gap (a general-axis quadric boolean) and still
refuses by name.
"""

from __future__ import annotations

import math
import re

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

# Fragments of raw Python diagnostics that must never reach a caller.
RAW_LEAKS = ("has no attribute", "object at 0x", "as_integer_ratio",
             "Rational instance", "Traceback", "AttributeError", "TypeError")


@pytest.fixture()
def k() -> RefKernel:
    return RefKernel()


@pytest.fixture()
def tilted(k):
    """A cylinder tilted 30° about x: exact (ℚ[√3] rotation), living in the
    canonical B-rep. The planar boolean still cannot take it; the exact STEP
    writer now can, since the wall there was a missing numeral rather than a
    missing capability."""
    t = k.transform(k.cylinder(5, 40), rotate_axis=(1, 0, 0), rotate_deg=30)
    assert type(t).__name__ == "Body", (
        "precondition: a tilted quadric converts to the canonical B-rep; if "
        "this ever becomes a native representation, this file needs new bait")
    return t


def test_boolean_on_a_transformed_body_names_the_mismatch(k, tilted) -> None:
    with pytest.raises(KernelError) as ei:
        k.boolean("cut", k.box(20, 20, 20), tilted)
    err = ei.value
    msg = str(err)
    for leak in RAW_LEAKS:
        assert leak not in msg, f"raw Python diagnostic leaked: {leak!r} in {msg!r}"
    # the mismatch, by name: the op and BOTH operand representations
    assert "boolean" in msg
    assert "Body" in msg and "Solid" in msg, msg
    # the stage that brings it: booleans over general B-rep solids are K7
    assert err.stage and "K7" in err.stage, err.stage
    assert err.remedy, "a refusal an agent can act on carries a remedy"


@pytest.fixture()
def side_plane_prism(k):
    """The body a ``plane={"normal": "y"}`` sketch produces (#49).

    ``document._dispatch`` implements the side sketch planes as a 120/240
    degree rotation about (1,1,1). That is exact, and the result is still a
    planar ``Solid`` — but its vertex coordinates now live in a wider exact
    field (``SurdVal``), which the rational drill predicates cannot read.
    """
    prof = {"start": [-30, -30],
            "segments": [{"kind": "line", "to": [30, -30]},
                         {"kind": "line", "to": [30, 30]},
                         {"kind": "line", "to": [-30, 30]}]}
    p = k.transform(k.extrude(prof, 40.0), rotate_axis=(1, 1, 1),
                    rotate_deg=240.0, translate=(0, -20, 0))
    assert type(p).__name__ == "Solid", (
        "precondition: a side-plane sketch is still a planar Solid; only its "
        "coordinates left the rationals")
    return p


def test_the_side_plane_drill_now_succeeds_exactly(k, side_plane_prism) -> None:
    """#49's own case is no longer a refusal — it is an exact answer.

    This test asserted a structured refusal, which was right when the only
    fix available was to convert forge's bare ``TypeError: unsupported
    operand type(s) for ** or pow(): 'SurdVal' and 'int'`` into one. The
    TypeError was then fixed AT SOURCE instead: ``SurdVal`` gained an exact
    ``__pow__`` (square-and-multiply, exact reciprocal for negative
    exponents), so the drill computes rather than declines. Refusing here now
    would be pinning the worse of two behaviours.

    The guard this file is really about is still exercised — see the test
    below, which drives it directly rather than through a case that has since
    been made to work."""
    tool = k.transform(k.cylinder(5, 61), translate=(0, 0, -30))
    out = k.boolean("cut", side_plane_prism, tool)
    vol = k.mass_props(out)["volume"]
    # closed form: the 60x60 profile extruded 40 is 144000; the Ø10 tool runs
    # clean through 60 mm of it, so it removes pi*5^2*60 = 1500pi. Derived
    # from the fixture, not read off the implementation.
    assert vol == pytest.approx(144000 - 1500 * math.pi, rel=1e-12)


def test_an_exact_scalar_typeerror_still_becomes_a_refusal(k) -> None:
    """The mechanism, driven directly.

    Fixing #49 at source removed the one caller that reached this guard, but
    the guard is the general answer: ANY predicate written for ℚ that meets a
    ℚ[√d]/ℚ[π] coordinate raises this shape of TypeError, and it must cross
    the seam as a refusal rather than a traceback. Exercised on the seam's own
    classifier so it cannot silently rot once its original case works."""
    from gitcad.kernel.ref import _exact_scalar_mismatch

    for msg, expected in [
        ("unsupported operand type(s) for ** or pow(): 'SurdVal' and 'int'",
         "SurdVal"),
        ("'<' not supported between instances of 'PiVal' and 'Fraction'",
         "PiVal"),
        ("unsupported operand type(s) for +: 'BiSurd' and 'int'", "BiSurd"),
        # an ordinary bad argument must NOT be claimed by the guard
        ("can only concatenate str (not \"int\") to str", None),
        ("unsupported operand type(s) for +: 'dict' and 'int'", None),
    ]:
        assert _exact_scalar_mismatch(TypeError(msg)) == expected, msg


@pytest.mark.parametrize("call, expected", [
    (lambda k: k.box("a", 2, 3), (ValueError, TypeError)),
    (lambda k: k.cylinder(5, None), (ValueError, TypeError)),
    (lambda k: k.transform(k.box(1, 1, 1), translate="xyz"), (ValueError, TypeError)),
])
def test_an_ordinary_bad_argument_keeps_its_own_meaning(k, call, expected) -> None:
    """The exact-scalar guard must not become a catch-all: a caller passing a
    string where a length belongs is a bad argument, not a missing capability,
    and mislabelling it "NotYetImplemented" would send the agent to fix the
    kernel instead of its own call."""
    with pytest.raises(expected) as ei:
        call(k)
    assert not isinstance(ei.value, KernelError), (
        f"bad argument was converted into a capability refusal: {ei.value}")


def test_feature_add_answers_for_a_side_plane_drill(tmp_path) -> None:
    """End to end: the MCP tool ANSWERS rather than raising (#49, #12).

    Originally asserted a refusal payload. Since the underlying TypeError was
    fixed at source (exact ``SurdVal.__pow__``), the honest end-to-end claim is
    the stronger one: the feature is added and the model comes back. What must
    never happen — a bare traceback out of the tool — is what is pinned."""
    from gitcad.mcp.server import REGISTRY

    prof = {"start": [-30, -30],
            "segments": [{"kind": "line", "to": [30, -30]},
                         {"kind": "line", "to": [30, 30]},
                         {"kind": "line", "to": [-30, 30]}]}
    model = REGISTRY["model_new"]()["model"]
    out = REGISTRY["feature_add"](
        model=model, op="extrude",
        params={"profile": prof, "height": 40.0,
                "plane": {"normal": "y", "offset": -20.0}})
    model, fid = out["model"], out["feature_id"]
    out = REGISTRY["feature_add"](
        model=model, op="hole", inputs=[fid],
        params={"x": 0, "y": 0, "top_z": 20, "depth": 41, "diameter": 10.0})
    assert "traceback" not in repr(out).lower()
    assert out.get("ok", True) is not False, out
    assert out["model"] != model, "the drill succeeds, so the model advances"
    assert out["feature_id"]


def test_export_step_on_a_transformed_body_now_writes_the_quadric(
        k, tilted, tmp_path) -> None:
    """A tilted cylinder EXPORTS, and exports as a real quadric.

    This asserted a refusal, and the refusal was honest at the time: the STEP
    writer's coordinate helper was ``Fraction(x)``, which raises on the ℚ[√3]
    coordinates a 30° tilt produces, and ``_via_body`` reported that as
    "export_step on Body yet — K3.7". The capability was there; only the
    NUMERAL was missing. ``stepio.export_rational`` now supplies it, by exact
    comparison rather than a float cast.

    Checked against the exact geometry rather than against the writer, since
    the writer is what changed: forge's own importer cannot read an analytic
    CYLINDRICAL_SURFACE back on the freeform path (a separate, honestly
    refused gap), so a round-trip would prove nothing here.
    """
    out = tmp_path / "tilted.step"
    k.export_step(tilted, str(out))
    text = out.read_text()

    assert text.startswith("ISO-10303-21;")
    assert "MANIFOLD_SOLID_BREP" in text
    # a cylinder must survive as a cylinder, not be faceted into a prism
    radii = re.findall(r"CYLINDRICAL_SURFACE\('',#\d+,([-0-9.E+]+)\)", text)
    assert radii and all(float(r) == pytest.approx(5.0, abs=1e-12)
                         for r in radii), radii

    # the axis of a 30° tilt about x is exactly (0, -1/2, √3/2)
    dirs = {tuple(float(c) for c in d)
            for d in re.findall(
                r"DIRECTION\('',\(([-0-9.E+]+),([-0-9.E+]+),([-0-9.E+]+)\)\)",
                text)}
    want = (0.0, -0.5, math.sqrt(3) / 2)
    best = min(dirs, key=lambda d: sum((a - b) ** 2 for a, b in zip(d, want)))
    assert math.dist(best, want) < 1e-12, f"axis {best} != exact {want}"

    # and the far cap sits at exactly 40·cos30°
    zs = {round(float(z), 9) for _, _, z in re.findall(
        r"CARTESIAN_POINT\('',\(([-0-9.E+]+),([-0-9.E+]+),([-0-9.E+]+)\)\)",
        text)}
    assert any(abs(z - 40 * math.sqrt(3) / 2) < 1e-8 for z in zs), sorted(zs)


def test_a_boolean_on_a_transformed_body_still_refuses_honestly(k, tilted):
    """The export half is fixed; the BOOLEAN half is not, and must keep
    saying so. This is the 43-cell family the capability grid still reports —
    a general-axis quadric boolean, which is real ADR-0021 work rather than
    the numeral bug the export turned out to be."""
    with pytest.raises(KernelError) as ei:
        k.boolean("cut", k.box(20, 20, 20), tilted)
    assert "Body" in str(ei.value)
