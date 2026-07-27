"""Freeform hygiene at the seam (#96 gap 11 + item 10's refusal half).

A boolean with a freeform operand (LoftSolid, SplinePrism, TubeSolid) used to
fall through every dispatch path and surface as the catch-all AttributeError
guard's text — ``'LoftSolid' object has no attribute 'polys'`` — with
``stage=None``. Worse, against a quadric tool it was mislabelled as the
QUADRIC gap ("K2.2"), pointing an agent at entirely the wrong backlog item.
The honest answer is a K7-staged structured refusal naming what will bring
the capability.

And ahead of K7's certified results flowing through the seam: ``mass_props``
and ``validate`` carry a ``provenance`` field so a CInterval-backed value
("certified", accompanied by its ``volume_halfwidth`` bracket) can never be
mistaken for an exact one (ADR-0019 — a certified value is labelled
"certified ± e", never a bare float).
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


_SQ = {"start": [0, 0], "segments": [{"kind": "line", "to": [10, 0]},
                                     {"kind": "line", "to": [10, 10]},
                                     {"kind": "line", "to": [0, 10]},
                                     {"kind": "line", "to": [0, 0]}]}
_IN = {"start": [1, 1], "segments": [{"kind": "line", "to": [9, 1]},
                                     {"kind": "line", "to": [9, 9]},
                                     {"kind": "line", "to": [1, 9]},
                                     {"kind": "line", "to": [1, 1]}]}


def _loft(k):
    return k.loft([(_SQ, 0.0), (_IN, 6.0), (_SQ, 12.0)])   # smooth → LoftSolid


def _tube(k):
    return k.pipe(k.helix(10, 4, 3), 2)                    # TubeSolid


def _spline_prism(k):
    return k.extrude({"start": [0, 0], "segments": [
        {"kind": "line", "to": [20, 0]},
        {"kind": "spline", "through": [[20, 5], [18, 10]], "to": [20, 15]},
        {"kind": "line", "to": [0, 15]},
        {"kind": "line", "to": [0, 0]}]}, 5)               # SplinePrism


def _refusal(fn) -> KernelError:
    with pytest.raises(KernelError) as e:
        fn()
    return e.value


# --- the boolean refusal: K7-staged, structured, no leaked CPython text ------

@pytest.mark.parametrize("op", ["cut", "union", "intersect"])
@pytest.mark.parametrize("order", ["freeform-first", "freeform-second"])
def test_boolean_on_a_loft_and_a_body_names_the_remaining_gap(k, op,
                                                              order) -> None:
    """A smooth loft now converts to its exact patch skin at the boolean
    dispatch (LoftSolid.to_patches — the K7 flagship), so the refusal a
    loft × planar-Body boolean gets names the gap that actually remains:
    the OTHER operand's missing patch conversion, not the loft's."""
    loft, box = _loft(k), k.box(4, 4, 40)
    a, b = (loft, box) if order == "freeform-first" else (box, loft)
    err = _refusal(lambda: k.boolean(op, a, b))
    assert err.signature.diagnostic == "NotYetImplemented"
    assert err.stage is not None and "K7" in err.stage
    assert "no attribute" not in str(err)   # the leaked AttributeError text
    assert err.predicate == "mixed_patchsolid_boolean_unbuilt"
    assert err.remedy                        # says what would unblock it


@pytest.mark.parametrize("make", [_tube, _spline_prism],
                         ids=["TubeSolid", "SplinePrism"])
def test_boolean_on_other_freeform_reps_refuses_at_k7(k, make) -> None:
    ff = make(k)
    err = _refusal(lambda: k.boolean("cut", ff, k.box(4, 4, 40)))
    assert err.signature.diagnostic == "NotYetImplemented"
    assert err.stage is not None and "K7" in err.stage
    assert type(ff).__name__ in str(err)
    assert "no attribute" not in str(err)


def test_freeform_vs_quadric_names_k7_not_the_quadric_gap(k) -> None:
    """A loft cut by a cylinder is missing because FREEFORM booleans are
    missing (K7), not because quadric booleans are (K2.2) — the old label
    sent an agent to the wrong backlog item."""
    err = _refusal(lambda: k.boolean("cut", _loft(k), k.cylinder(2, 40)))
    assert err.stage is not None and "K7" in err.stage
    assert "K2.2" not in str(err)


def test_the_freeform_refusal_serialises_for_an_agent(k) -> None:
    err = _refusal(lambda: k.boolean("cut", _loft(k), k.box(4, 4, 40)))
    d = err.as_dict()
    import json

    json.dumps(d)
    assert d["stage"] and "K7" in d["stage"]


# --- provenance: "exact" vs "certified ± e" through the seam (ADR-0019) ------

def test_mass_props_of_exact_representations_says_exact(k) -> None:
    for shape in (k.box(2, 3, 4), _loft(k), _spline_prism(k),
                  k.cylinder(3, 5), k.sphere(4)):
        mp = k.mass_props(shape)
        assert mp["provenance"] == "exact", type(shape).__name__


def test_mass_props_of_a_certified_solid_says_so_and_carries_its_bracket(k) -> None:
    """The TubeSolid volume is a CInterval (π enters); its midpoint is only
    honest next to the half-width that brackets the truth, and ``provenance``
    is what stops a consumer reading it as exact."""
    mp = k.mass_props(_tube(k))
    assert mp["provenance"] == "certified"
    assert "volume_halfwidth" in mp
    assert mp["volume_halfwidth"] >= 0.0


def test_the_empty_solid_is_still_exact(k) -> None:
    box = k.box(2, 2, 2)
    mp = k.mass_props(k.boolean("cut", box, k.box(2, 2, 2)))
    assert mp["empty"] is True
    assert mp["provenance"] == "exact"      # zero is the exact answer


def test_validate_carries_provenance(k) -> None:
    for shape, want in ((k.box(2, 3, 4), "exact"),
                        (_loft(k), "exact"),
                        (_spline_prism(k), "exact"),
                        (k.cylinder(3, 5), "exact"),
                        (_tube(k), "certified")):
        report = k.validate(shape)
        assert report.checks.get("provenance") == want, type(shape).__name__
