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


# --- the export path IS the seam mesher (round-9 docket W5 + W10) -------------
#
# `export_stl` used to try forge's `io.to_stl(shape)` first, which calls
# `shape.tessellate()` with NO argument. Every representation carrying a
# `.tessellate` attribute therefore took a deflection-blind path: a cylinder
# shipped 48 facets whether the caller asked for 0.2 or 0.001 (0.17 mm of wall
# sag against a requested 0.001), and an AxisStack shipped a chorded mesh 21.6%
# light that the seam's own `tessellate` honestly refuses. The invariant: the
# STL a manufacturer consumes is the SAME mesh `tessellate` answers with, at
# the SAME deflection — and where `tessellate` refuses, `export_stl` refuses
# too, rather than shipping the one artifact nobody downstream can check.

def _stl_facets(path):
    """Parse an ASCII STL into a list of 3-vertex tuples."""
    tris, cur = [], []
    for line in open(path).read().splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            cur.append(tuple(float(x) for x in line.split()[1:]))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    return tris


def _stl_volume(tris):
    """Enclosed volume by the divergence theorem — independent of the kernel."""
    return abs(sum(
        (a[0] * (b[1] * c[2] - b[2] * c[1])
         - a[1] * (b[0] * c[2] - b[2] * c[0])
         + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        for a, b, c in tris))


def test_stl_export_honours_deflection(tmp_path) -> None:
    """W5: finer deflection must yield a finer mesh, and the facet count must
    match what the seam's own `tessellate` produces at that deflection."""
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    counts = {}
    for defl in (0.2, 0.001):
        path = str(tmp_path / f"cyl_{defl}.stl")
        k.export_stl(k.cylinder(5, 12), path, deflection=defl)
        counts[defl] = len(_stl_facets(path))
        assert counts[defl] == len(
            k.tessellate(k.cylinder(5, 12), deflection=defl)["triangles"])
    assert counts[0.001] > counts[0.2], (
        "deflection is discarded: the same mesh ships at every tolerance")


def test_stl_export_volume_converges_to_truth(tmp_path) -> None:
    """W5, the number that matters: at deflection 0.001 the shipped cylinder
    must enclose 300π to well under the 4.5% the 48-facet mesh was off by.
    300π is a closed form, not a kernel output."""
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    path = str(tmp_path / "cyl_fine.stl")
    k.export_stl(k.cylinder(5, 12), path, deflection=0.001)
    true = 300 * math.pi
    assert _stl_volume(_stl_facets(path)) == pytest.approx(true, rel=5e-3)


def test_stl_export_refuses_what_tessellate_refuses(tmp_path) -> None:
    """W10: a cylinder-sphere AxisStack has no honest mesh yet — `tessellate`
    refuses it (K3.7). `export_stl` must refuse the SAME shape, not silently
    write a chorded lathe enclosing 644 where the exact volume is 784π/3 =
    821.003. A structured refusal is the finished answer; a wrong watertight
    file is the defect."""
    from gitcad.errors import KernelError
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    ax = k.boolean("union", k.cylinder(4, 10),
                   k.transform(k.sphere(5), translate=(0, 0, 10)))
    with pytest.raises(KernelError):
        k.tessellate(ax, deflection=0.01)     # the seam already refuses this
    path = tmp_path / "axstack.stl"
    with pytest.raises(KernelError):
        k.export_stl(ax, str(path))
    assert not path.exists(), "refusal must not leave a partial file behind"


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
