"""#11 — expensive tool results carry their cost.

A crankbait-scale loft is minutes of exact arithmetic, and nothing told the
agent so; it cannot decide "this loft is too dense, coarsen it" without a
cost model. The contract here is the minimal honest one: every tool result
(success OR structured refusal) whose handler ran longer than
``SLOW_TOOL_S`` carries ``elapsed_s``, wall-clock seconds, attached by the
one wrapper every tool already goes through. Fast results stay clean — the
signal marks expense, so its absence is information too.
"""

from __future__ import annotations

from gitcad.mcp import server as S

BOX = {"dx": 10, "dy": 10, "dz": 10}


def test_fast_results_do_not_carry_elapsed() -> None:
    r = S.REGISTRY["model_new"]()
    assert "elapsed_s" not in r


def test_slow_success_carries_elapsed(monkeypatch) -> None:
    monkeypatch.setattr(S, "SLOW_TOOL_S", 0.0)
    m = S.REGISTRY["model_new"]()["model"]
    r = S.REGISTRY["feature_add"](model=m, op="box", params=BOX)
    assert r.get("ok", True) is not False
    assert isinstance(r["elapsed_s"], float) and r["elapsed_s"] >= 0.0


def test_slow_refusal_carries_elapsed(monkeypatch) -> None:
    monkeypatch.setattr(S, "SLOW_TOOL_S", 0.0)
    m = S.REGISTRY["model_new"]()["model"]
    r = S.REGISTRY["feature_add"](model=m, op="bogus_op")
    assert r["ok"] is False
    assert isinstance(r["elapsed_s"], float) and r["elapsed_s"] >= 0.0


def test_threshold_default_is_a_positive_number() -> None:
    # the signal must mark EXPENSE — a zero default would stamp every result
    # and turn the signal into noise
    assert S.SLOW_TOOL_S > 0
