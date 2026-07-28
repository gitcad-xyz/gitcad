"""Issue #52: `final()` is `features[-1]`, so a document holding several
unconsumed bodies reports one of them as "the part" with no warning.

Measured while designing a 90 mm impeller: a refused keyseat cut left its
3.68 x 4.04 x 22 tool behind, and `model_mass` answered 327.078 mm^3 /
2.5676 g for a Ø11.96 x 55 steel shaft that weighs ~48 g. Nothing said the
document had two loose bodies.

The tools still answer for `features[-1]` — this pins that they say so.
"""
from gitcad.document import Document, Feature
from gitcad.mcp.server import REGISTRY

EMPTY = '{"features": [], "schema": "gitcad/document@1"}'


def _doc(*features):
    d = Document()
    for op, params, inputs in features:
        d.add(Feature(op=op, params=params, inputs=list(inputs)))
    return d


def test_unconsumed_bodies_is_document_order_minus_the_consumed():
    d = _doc(("box", {"dx": 10, "dy": 10, "dz": 10}, []),
             ("box", {"dx": 2, "dy": 2, "dz": 30}, []))
    a, b = (f.id for f in d.features)
    assert [f.id for f in d.unconsumed_bodies()] == [a, b]

    d.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[a, b]))
    assert [f.op for f in d.unconsumed_bodies()] == ["boolean"]


def test_one_body_reports_the_count_without_a_warning():
    out = REGISTRY["model_mass"](
        model=_doc(("box", {"dx": 10, "dy": 10, "dz": 10}, [])).dumps())
    assert out["bodies"] == 1
    assert out["final_feature"]["op"] == "box"
    assert "warning" not in out
    assert "loose_bodies" not in out


def test_a_scaffold_left_by_a_refused_cut_is_named_in_model_mass():
    """The shaft-keyseat shape: tool built, cut refused, tool left behind."""
    d = _doc(("box", {"dx": 10, "dy": 10, "dz": 10}, []),
             ("box", {"dx": 2, "dy": 2, "dz": 30}, []))
    out = REGISTRY["model_mass"](model=d.dumps())
    assert out["bodies"] == 2
    # it still answers for the LAST feature -- the contract is unchanged
    assert out["final_feature"]["id"] == d.features[-1].id
    assert out["volume"] == 2 * 2 * 30
    assert [b["op"] for b in out["loose_bodies"]] == ["box", "box"]
    assert "2 unconsumed bodies" in out["warning"]


def test_model_export_and_drawing_carry_the_same_report(tmp_path):
    d = _doc(("box", {"dx": 10, "dy": 10, "dz": 10}, []),
             ("box", {"dx": 2, "dy": 2, "dz": 30}, []))
    step = REGISTRY["model_export"](model=d.dumps(),
                                    path=str(tmp_path / "p.step"))
    assert step["bodies"] == 2 and "warning" in step
    svg = REGISTRY["model_drawing"](model=d.dumps(),
                                    path=str(tmp_path / "p.svg"), bom=False)
    assert svg["bodies"] == 2 and "warning" in svg


def test_feature_add_reports_the_count_as_the_tree_grows():
    a = REGISTRY["feature_add"](model=EMPTY, op="box",
                                params={"dx": 10, "dy": 10, "dz": 10})
    assert a["bodies"] == 1
    b = REGISTRY["feature_add"](model=a["model"], op="box",
                                params={"dx": 2, "dy": 2, "dz": 30})
    assert b["bodies"] == 2
    assert [x["op"] for x in b["loose_bodies"]] == ["box", "box"]
    c = REGISTRY["feature_add"](model=b["model"], op="boolean",
                                params={"kind": "cut"},
                                inputs=[f.id for f in
                                        Document.loads(b["model"]).features])
    assert c["bodies"] == 1 and "warning" not in c


def test_a_refusal_reports_the_leftovers_it_is_leaving_behind():
    a = REGISTRY["feature_add"](model=EMPTY, op="box",
                                params={"dx": 10, "dy": 10, "dz": 10})
    b = REGISTRY["feature_add"](model=a["model"], op="box",
                                params={"dx": 2, "dy": 2, "dz": 30})
    bad = REGISTRY["feature_add"](model=b["model"], op="boolean",
                                  params={"kind": "nonsense"},
                                  inputs=[f.id for f in
                                          Document.loads(b["model"]).features])
    assert bad["buildable"] is False
    # the refused feature is NOT counted -- it was not added
    assert bad["bodies"] == 2
    assert bad["final_feature"]["op"] == "box"
    assert "2 unconsumed bodies" in bad["warning"]
