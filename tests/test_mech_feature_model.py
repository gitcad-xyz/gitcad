"""Mechanical feature-model completeness: spline profiles, table-driven
patterns, feature suppression, drilled-solid placement."""

import pytest

pytest.importorskip("forgekernel")

from gitcad.document import Document, Feature  # noqa: E402
from gitcad.kernel.ref import RefKernel  # noqa: E402
from gitcad.sketch import Profile  # noqa: E402


def _box_pattern(op, params):
    k = RefKernel()
    d = Document()
    s = d.add(Feature(op="box", params={"dx": 5, "dy": 5, "dz": 5}))
    d.add(Feature(op=op, params=params, inputs=[s]))
    return k.mass_props(d.build(k).final(d))["volume"]


def test_spline_profile_authoring_extrudes_exact() -> None:
    prof = Profile((0, 0)).line_to(10, 0).spline_to(0, 0, ctrl=[[12, 7], [-2, 7]])
    d = Document()
    d.add(Feature(op="extrude", params={"profile": prof.to_params(),
                                        "height": 5}))
    # survives a canonical-text round-trip and builds exact
    doc = Document.loads(d.dumps())
    k = RefKernel()
    assert doc.build(k).final(doc).volume() == 231


def test_pattern_table_matches_pattern_linear() -> None:
    vt = _box_pattern("pattern_table", {"placements": [
        {"translate": [10, 0, 0]}, {"translate": [20, 0, 0]}]})
    vl = _box_pattern("pattern_linear", {"count": 3, "step": [10, 0, 0]})
    assert vt == vl == 375                     # 3 disjoint 125-boxes


def test_pattern_table_supports_rotation() -> None:
    v = _box_pattern("pattern_table",
                     {"placements": [{"translate": [10, 0, 0],
                                      "rotate_deg": 90.0}]})
    assert v == 250                            # 2 disjoint boxes


def test_feature_suppression() -> None:
    k = RefKernel()
    d = Document()
    s = d.add(Feature(op="box", params={"dx": 5, "dy": 5, "dz": 5}))
    d.add(Feature(op="pattern_linear",
                  params={"count": 3, "step": [10, 0, 0]}, inputs=[s]))
    assert k.mass_props(d.build(k).final(d))["volume"] == 375
    d.features[-1].params["suppressed"] = True
    assert k.mass_props(d.build(k).final(d))["volume"] == 125   # back to seed


def test_cannot_suppress_a_base_feature() -> None:
    from gitcad.errors import GitcadError

    k = RefKernel()
    d = Document()
    d.add(Feature(op="box", params={"dx": 5, "dy": 5, "dz": 5,
                                    "suppressed": True}))
    with pytest.raises(GitcadError, match="orphan"):
        d.build(k)


def test_drilled_solid_translates_preserving_volume() -> None:
    import math

    k = RefKernel()
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 10}))
    h = d.add(Feature(op="hole", params={"x": 10, "y": 10, "top_z": 10,
                                         "depth": 10, "diameter": 4}, inputs=[b]))
    d.add(Feature(op="move", params={"translate": [5, 5, 0]}, inputs=[h]))
    v = k.mass_props(d.build(k).final(d))["volume"]
    assert abs(v - (20 * 20 * 10 - math.pi * 4 * 10)) < 1e-6
