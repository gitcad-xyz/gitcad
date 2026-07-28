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
