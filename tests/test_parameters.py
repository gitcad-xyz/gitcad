"""SW-map P1: named parameters + equations — a part becomes a function.

The design invariant under test: feature ids are minted from expression
TEXT ('=W/2'), parameter VALUES live in the document table — so re-valuing
a parameter rebuilds different geometry (an ADR-0006 breaking change)
while every feature id, entity lineage, and downstream reference survives
untouched. That is the property no click-driven CAD gives you."""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.expr import ExprError, eval_expr, resolve_table, resolve_value
from gitcad.kernel.null import NullKernel


class _RecordingKernel(NullKernel):
    """NullKernel that records primitive calls so tests can see the numbers
    the build actually used."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def box(self, dx, dy, dz):
        self.calls.append(("box", dx, dy, dz))
        return super().box(dx, dy, dz)

    def cylinder(self, radius, height):
        self.calls.append(("cylinder", radius, height))
        return super().cylinder(radius, height)


# -- expression engine ---------------------------------------------------------

def test_eval_expr_arithmetic_names_and_functions() -> None:
    assert eval_expr("2 + 3*4", {}) == 14
    assert eval_expr("W/2 + 1", {"W": 10}) == 6
    assert eval_expr("min(W, H) - 2*wall", {"W": 30, "H": 20, "wall": 2.5}) == 15
    assert eval_expr("cos(60)", {}) == pytest.approx(0.5)
    assert eval_expr("pi", {}) == pytest.approx(3.14159265)


def test_eval_expr_rejects_everything_else() -> None:
    for bad in ("__import__('os')", "W.x", "[1,2]", "lambda: 1", "'abc'",
                "open('x')", "W if 1 else 2"):
        with pytest.raises(ExprError):
            eval_expr(bad, {"W": 1})


def test_resolve_table_chains_and_detects_cycles() -> None:
    env = resolve_table({"W": 30, "H": "=W/2", "area": "=W*H"})
    assert env == {"W": 30.0, "H": 15.0, "area": 450.0}
    with pytest.raises(ExprError, match="cycle"):
        resolve_table({"a": "=b", "b": "=a"})
    with pytest.raises(ExprError, match="undefined"):
        resolve_table({"a": "=nope"})


def test_resolve_value_recurses_and_leaves_literals_alone() -> None:
    env = {"W": 10.0}
    out = resolve_value({"dx": "=W", "axis": "z",
                         "pts": [["=W/2", 0], [3, "=W"]]}, env)
    assert out == {"dx": 10.0, "axis": "z", "pts": [[5.0, 0], [3, 10.0]]}


# -- document integration ------------------------------------------------------

def test_build_resolves_parameters_into_kernel_calls() -> None:
    doc = Document()
    doc.set_parameter("W", 30)
    doc.set_parameter("H", "=W/3")
    doc.add(Feature(op="box", params={"dx": "=W", "dy": "=W/2", "dz": "=H"}))
    k = _RecordingKernel()
    doc.build(k)
    assert k.calls == [("box", 30.0, 15.0, 10.0)]


def test_revaluing_a_parameter_never_reidentifies_features() -> None:
    def make(width: float) -> Document:
        d = Document()
        d.set_parameter("W", width)
        d.add(Feature(op="box", params={"dx": "=W", "dy": 5, "dz": 2}))
        d.add(Feature(op="cylinder", params={"radius": "=W/10", "height": 4},
                      inputs=[]))
        return d

    a, b = make(30), make(50)
    assert [f.id for f in a.features] == [f.id for f in b.features]
    # and the geometry genuinely differs
    ka, kb = _RecordingKernel(), _RecordingKernel()
    a.build(ka); b.build(kb)
    assert ka.calls != kb.calls


def test_parameter_free_documents_stay_byte_identical() -> None:
    d = Document()
    d.add(Feature(op="box", params={"dx": 1, "dy": 2, "dz": 3}))
    assert "parameters" not in d.dumps()
    # and with parameters, the table round-trips canonically
    d.set_parameter("W", 30)
    d2 = Document.loads(d.dumps())
    assert d2.parameters == {"W": 30}
    assert d2.dumps() == d.dumps()


def test_undefined_reference_fails_loud_with_feature_context() -> None:
    d = Document()
    d.add(Feature(op="box", params={"dx": "=missing", "dy": 1, "dz": 1}))
    with pytest.raises(GitcadError, match="box"):
        d.build(NullKernel())


def test_bad_parameter_name_rejected() -> None:
    d = Document()
    with pytest.raises(GitcadError, match="identifier"):
        d.set_parameter("2bad", 1)


def test_mcp_model_parameters_tool() -> None:
    from gitcad.mcp.server import REGISTRY

    model = REGISTRY["model_new"]()["model"]
    r = REGISTRY["model_parameters"](model=model, set={"W": 30, "H": "=W/2"})
    assert r["resolved"] == {"W": 30.0, "H": 15.0}
    r2 = REGISTRY["feature_add"](model=r["model"], op="box",
                                 params={"dx": "=W", "dy": "=H", "dz": 2})
    assert "feature_id" in r2


# -- configurations (SW-map P2) ------------------------------------------------

def _family() -> Document:
    d = Document()
    d.set_parameter("L", 8)
    d.set_parameter("d", 3)
    d.set_parameter("head", "=d*1.8")
    d.add(Feature(op="cylinder", params={"radius": "=d/2", "height": "=L"}))
    d.set_configuration("M3x8", {"L": 8})
    d.set_configuration("M3x10", {"L": 10})
    d.set_configuration("M4x10", {"L": 10, "d": 4})
    return d


def test_configurations_resolve_with_dependent_expressions() -> None:
    d = _family()
    assert d.resolved_parameters("M3x10") == {"L": 10.0, "d": 3.0, "head": 5.4}
    assert d.resolved_parameters("M4x10")["head"] == pytest.approx(7.2)


def test_variant_builds_share_feature_ids() -> None:
    d = _family()
    ka, kb = _RecordingKernel(), _RecordingKernel()
    ra = d.build(ka, config="M3x8")
    rb = d.build(kb, config="M4x10")
    assert ka.calls == [("cylinder", 1.5, 8.0)]
    assert kb.calls == [("cylinder", 2.0, 10.0)]
    assert set(ra.shapes) == set(rb.shapes)          # same ids, every variant


def test_configuration_roundtrips_and_fails_loud() -> None:
    d = _family()
    d2 = Document.loads(d.dumps())
    assert d2.configurations == d.configurations
    assert d2.dumps() == d.dumps()
    with pytest.raises(GitcadError, match="undefined parameter"):
        d2.set_configuration("bad", {"nope": 1})
    with pytest.raises(GitcadError, match="unknown configuration"):
        d2.resolved_parameters("ghost")
    plain = Document()
    plain.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
    assert "configurations" not in plain.dumps()


def test_mcp_model_configurations_tool() -> None:
    from gitcad.mcp.server import REGISTRY

    model = REGISTRY["model_new"]()["model"]
    model = REGISTRY["model_parameters"](model=model, set={"L": 8, "d": 3})["model"]
    r = REGISTRY["model_configurations"](
        model=model, set={"M3x8": {"L": 8}, "M3x12": {"L": 12}})
    assert r["resolved"]["M3x12"] == {"L": 12.0, "d": 3.0}
