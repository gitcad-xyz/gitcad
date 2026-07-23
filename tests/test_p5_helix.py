"""SW-map P5: helix + pipe kernel ops, the spring feature, and thread
specs as data on holes (surfaced in drawing callouts)."""

from __future__ import annotations

import math

import pytest

from gitcad.document import Document, Feature
from gitcad.kernel.null import NullKernel


def test_spring_builds_under_null_kernel() -> None:
    d = Document()
    d.add(Feature(op="spring", params={"radius": 6, "pitch": 3, "turns": 5,
                                       "wire_diameter": 1.2}))
    result = d.build(NullKernel())
    assert d.features[-1].id in result.shapes


def test_hole_thread_spec_is_data_and_roundtrips() -> None:
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 5}))
    d.add(Feature(op="hole", params={"x": 10, "y": 10, "top_z": 5, "depth": 5,
                                     "diameter": 2.5, "thread": "M3x0.5-6H"},
                  inputs=[base]))
    d2 = Document.loads(d.dumps())
    assert d2.features[-1].params["thread"] == "M3x0.5-6H"
    d2.build(NullKernel())                        # spec is data, build unaffected


@pytest.mark.occt
def test_spring_volume_matches_wire_length() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    r, pitch, turns, wd = 6.0, 3.0, 5.0, 1.2
    d = Document()
    d.add(Feature(op="spring", params={"radius": r, "pitch": pitch,
                                       "turns": turns, "wire_diameter": wd}))
    vol = k.mass_props(d.build(k).final(d))["volume"]
    helix_len = turns * math.hypot(2 * math.pi * r, pitch)
    expected = math.pi * (wd / 2) ** 2 * helix_len
    assert vol == pytest.approx(expected, rel=0.02)


@pytest.mark.occt
def test_thread_spec_appears_in_drawing_callout(tmp_path) -> None:
    from gitcad.mcp.server import REGISTRY

    model = REGISTRY["model_new"]()["model"]
    model = REGISTRY["feature_add"](model=model, op="box",
                                    params={"dx": 20, "dy": 20, "dz": 5})["model"]
    import json
    base_id = json.loads(model)["features"][0]["id"]
    model = REGISTRY["feature_add"](
        model=model, op="hole",
        params={"x": 10, "y": 10, "top_z": 5, "depth": 5, "diameter": 2.5,
                "thread": "M3x0.5-6H"},
        inputs=[base_id])["model"]
    out = tmp_path / "part.svg"
    REGISTRY["model_drawing"](model=model, path=str(out))
    svg = out.read_text()
    assert "M3x0.5-6H" in svg
