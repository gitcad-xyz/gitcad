"""Issue #72: a drawing dimension must say what the model says.

`_fmt` was `f"{v:.1f}".rstrip("0").rstrip(".")`, so a Ø11.96 shaft — 0.04
under the Ø12.00 bore it has to enter — was dimensioned `12` on the sheet a
shop cuts from. The error was exactly the fit.
"""
from __future__ import annotations

import re

import pytest

pytest.importorskip("forgekernel")

from gitcad.drawing.sheet import _fmt
from gitcad.mcp.server import REGISTRY

EMPTY = '{"features": [], "schema": "gitcad/document@1"}'


@pytest.mark.parametrize("value,text", [
    (11.96, "11.96"),          # the shaft that started this
    (12.0, "12"),              # a real 12 still prints as 12
    (120.0, "120"),            # the strip must not eat an integer's own zero
    (2.5, "2.5"),
    (0.05, "0.05"),            # used to round to "0.1"
    (0.04, "0.04"),            # used to vanish to "0"
    (55, "55"),
    (0.1 + 0.2, "0.3"),        # float residue never reaches the sheet
    (1 / 3, "0.3333"),         # bounded at _DIM_DECIMALS
])
def test_fmt_prints_the_value(value, text):
    assert _fmt(value) == text


def _dim_texts(svg: str) -> list[str]:
    return re.findall(r">([^<>]{1,30})</text>", svg)


def test_a_sub_millimetre_dimension_reaches_the_sheet(tmp_path):
    """A 11.96 x 55 x 3.04 block: every one of its three sizes is a number
    the old formatter destroyed."""
    m = REGISTRY["feature_add"](model=EMPTY, op="box",
                                params={"dx": 11.96, "dy": 3.04, "dz": 55.0})
    out = REGISTRY["model_drawing"](model=m["model"],
                                    path=str(tmp_path / "p.svg"),
                                    title="SHAFT", sheet="A3", bom=False)
    texts = _dim_texts((tmp_path / "p.svg").read_text(encoding="utf-8"))
    assert "11.96" in texts, texts
    assert "3.04" in texts, texts
    assert "55" in texts, texts
    assert out["views"] == ["front", "top", "right", "iso"]
    # (the sheet's frame carries grid labels "1".."8", so a negative
    # assertion on "12"/"3" would be testing the border, not the dimensions)
