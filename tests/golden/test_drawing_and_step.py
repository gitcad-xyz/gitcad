"""GOLDEN: mechanical manufacturing outputs — STEP export and drawings.

Forge-native. STEP export of a curved/drilled solid and non-planar fillets are
forge_gap (K3.7 / K5.2); STL, HLR, and the drawing render forge-native.
"""

from __future__ import annotations

import math

import pytest



@pytest.fixture(scope="module")
def part():
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    plate = k.box(60, 40, 8)
    hole = k.transform(k.cylinder(3.2, 8), translate=(15, 20, 0))
    return k, k.boolean("cut", plate, hole)


def test_boolean_volume_is_exact(part) -> None:
    k, shape = part
    expected = 60 * 40 * 8 - math.pi * 3.2**2 * 8
    assert k.measure(shape)["volume"] == pytest.approx(expected, rel=1e-6)


def test_step_export_is_valid_iso10303(part, tmp_path) -> None:
    k, shape = part
    path = str(tmp_path / "part.step")
    k.export_step(shape, path)
    text = open(path).read()
    assert text.startswith("ISO-10303-21;")
    assert "END-ISO-10303-21;" in text


def test_stl_export_writes_mesh(part, tmp_path) -> None:
    k, shape = part
    path = str(tmp_path / "part.stl")
    k.export_stl(shape, path)
    assert (tmp_path / "part.stl").stat().st_size > 1000


def test_hlr_projections_are_dimensionally_correct(part) -> None:
    from gitcad.drawing.hlr import bounds, project

    k, shape = part
    for view, (w, h) in {"front": (60, 8), "top": (60, 40), "right": (40, 8)}.items():
        b = bounds(project(k, shape, view)["visible"])
        assert b[2] - b[0] == pytest.approx(w, abs=1e-3), view
        assert b[3] - b[1] == pytest.approx(h, abs=1e-3), view


def test_drawing_renders_svg_and_pdf(part) -> None:
    from gitcad.drawing import make_drawing

    _, shape = part
    d = make_drawing(shape, title="test part")
    svg = d.to_svg()
    assert svg.startswith("<svg") and "polyline" in svg and "test part" in svg
    pdf = d.to_pdf()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert len(d.views) == 4
    # 3 overall dims + 2 position dims and a Ø-callout for the hole.
    assert len(d.dims) == 5 and len(d.callouts) == 1


@pytest.mark.forge_gap
def test_fillet_reduces_volume_and_stays_valid(part) -> None:
    k, shape = part
    filleted = k.fillet(shape, None, 1.0)
    assert k.validate(filleted).ok
    assert k.measure(filleted)["volume"] < k.measure(shape)["volume"]


# --- one writer, one manifold convention (review round 8) --------------------

def _step_edge_uses(text, fold_same_sense: bool):
    """Effective traversal of every EDGE_CURVE, per using face.

    ``fold_same_sense`` selects the reading: an ADVANCED_FACE's flag is exactly
    what relates the loop's direction in the SURFACE's parameter space to the
    face's own outward orientation, so composing it is the correct one — and
    the two writers this project used to carry disagreed about it.
    """
    import re
    from collections import defaultdict

    oriented = {i: (r, s) for i, r, s in re.findall(
        r"#(\d+) = ORIENTED_EDGE\(.*?#(\d+),(\.[TF]\.)\)", text)}
    loops = {i: re.findall(r"#(\d+)", a) for i, a in re.findall(
        r"#(\d+) = EDGE_LOOP\(.*?\((.*?)\)\)", text)}
    bounds = {i: m for i, m in re.findall(
        r"#(\d+) = FACE_(?:OUTER_)?BOUND\(.*?#(\d+),", text)}
    uses = defaultdict(list)
    for bl, flag in re.findall(
            r"#\d+ = ADVANCED_FACE\(.*?\((.*?)\),#\d+,(\.[TF]\.)\)", text):
        for b in re.findall(r"#(\d+)", bl):
            for o in loops[bounds[b]]:
                ref, sense = oriented[o]
                fwd = sense == ".T."
                uses[ref].append(fwd == (flag == ".T.") if fold_same_sense
                                 else fwd)
    return uses


STEP_SHAPES = [
    ("box", lambda k: k.box(20, 20, 10)),
    ("L-prism", lambda k: k.extrude(
        {"start": [0, 0], "segments": [{"kind": "line", "to": [30, 0]},
                                       {"kind": "line", "to": [30, 10]},
                                       {"kind": "line", "to": [10, 10]},
                                       {"kind": "line", "to": [10, 30]},
                                       {"kind": "line", "to": [0, 30]},
                                       {"kind": "line", "to": [0, 0]}]}, 8)),
    # THE one that shipped broken: a Solid with an interior void, which the
    # planar writer sent out as a MANIFOLD_SOLID_BREP over a shell whose 16 of
    # 56 edges were used by exactly ONE face — dangling on either convention
    ("shelled box", lambda k: k.shell(k.box(20, 20, 20), [], 2)),
    ("drilled plate", lambda k: k.boolean(
        "cut", k.box(40, 20, 5),
        k.transform(k.cylinder(4, 5), translate=(20, 10, 0)))),
    ("blind bore", lambda k: k.boolean(
        "cut", k.box(30, 30, 10),
        k.transform(k.cylinder(3, 6), translate=(15, 15, 4)))),
    ("counterbore", lambda k: k.boolean(
        "cut", k.boolean("cut", k.box(30, 30, 10),
                         k.transform(k.cylinder(2, 10), translate=(15, 15, 0))),
        k.transform(k.cylinder(4, 3), translate=(15, 15, 7)))),
    ("bare cylinder", lambda k: k.cylinder(5, 12)),
]


@pytest.mark.parametrize("label,build", STEP_SHAPES,
                         ids=[s[0] for s in STEP_SHAPES])
def test_every_exported_shell_is_closed(label, build, tmp_path) -> None:
    """One writer for every representation, and it audits itself before
    emitting. A MANIFOLD_SOLID_BREP over an open shell is the worst outcome
    available: the file opens, and then will not boolean, will not mesh for
    CAM, and imports as a surface soup — nothing downstream reports it."""
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    path = tmp_path / f"{label.replace(' ', '_')}.step"
    k.export_step(build(k), str(path))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("ISO-10303-21;")
    uses = _step_edge_uses(text, fold_same_sense=True)
    open_edges = [e for e, us in uses.items() if sorted(us) != [False, True]]
    assert open_edges == [], (
        f"{len(open_edges)} of {len(uses)} edges are not traversed once each "
        "way — the shell is open")
