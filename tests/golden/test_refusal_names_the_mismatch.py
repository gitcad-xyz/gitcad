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
canonical B-rep (a ``Body``, ADR-0021), which the planar boolean and the exact
STEP writer cannot take yet.
"""

from __future__ import annotations

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
    """A cylinder tilted 30° about x: exact (ℚ[√3] rotation), but the result
    lives in the canonical B-rep — the representation neither the planar
    boolean nor the exact STEP writer reaches yet."""
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


def test_exact_scalar_arithmetic_refuses_instead_of_crashing(
        k, side_plane_prism) -> None:
    """#49: drilling that body used to raise a bare
    ``TypeError: unsupported operand type(s) for ** or pow(): 'SurdVal' and
    'int'`` from inside forge, which is neither a KernelError nor anything
    ``feature_add`` catches — the MCP tool died with a traceback and the
    caller got no refusal, no fingerprint and no model back."""
    tool = k.transform(k.cylinder(5, 61), translate=(0, 0, -30))
    with pytest.raises(KernelError) as ei:
        k.boolean("cut", side_plane_prism, tool)
    err = ei.value
    msg = str(err)
    for leak in RAW_LEAKS:
        assert leak not in msg, f"raw Python diagnostic leaked: {leak!r} in {msg!r}"
    assert "boolean" in msg and "SurdVal" in msg, msg
    assert err.stage and "K3.1" in err.stage, err.stage
    assert err.predicate == "coordinates_are_rational", err.predicate
    assert err.remedy, "a refusal an agent can act on carries a remedy"


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


def test_feature_add_returns_a_refusal_for_a_side_plane_drill(tmp_path) -> None:
    """End to end: the MCP tool answers, rather than raising (#49, #12)."""
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
    assert out["ok"] is False and out["buildable"] is False
    assert out["refusal"]["predicate"] == "coordinates_are_rational"
    assert out["model"] == model, "a refused feature must not be added"
    assert out["fingerprint"].startswith("fp_")


def test_export_step_on_a_transformed_body_names_the_mismatch(
        k, tilted, tmp_path) -> None:
    out = tmp_path / "tilted.step"
    with pytest.raises(KernelError) as ei:
        k.export_step(tilted, str(out))
    err = ei.value
    msg = str(err)
    for leak in RAW_LEAKS:
        assert leak not in msg, f"raw Python diagnostic leaked: {leak!r} in {msg!r}"
    assert "export_step" in msg and "Body" in msg, msg
    assert err.stage and "K3.7" in err.stage, err.stage
    assert err.remedy, "a refusal an agent can act on carries a remedy"
    assert not out.exists(), "refusal must not leave a partial file behind"
