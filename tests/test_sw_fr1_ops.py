"""Golden: SW-manual FR1 ops — loft, sweep, mirror, countersink, mass props.

Each op is verified against an analytic volume oracle, not against itself:
a ruled square-to-square loft is a frustum (V = h/3*(A1+A2+sqrt(A1*A2))),
a straight sweep is a prism, a fused mirror doubles volume exactly, and a
90-degree countersink removes a computable cone ring.

OCCT-backed tests carry the ``occt`` marker (lazy kernel import — the base
suite collects this file with no OCCT wheel installed); the null-kernel
symbolic test runs everywhere.
"""

import math

import pytest

from gitcad.document import Document, Feature
from gitcad.sketch import Profile


def _square(side: float) -> dict:
    h = side / 2
    return (Profile((-h, -h)).line_to(h, -h).line_to(h, h)
            .line_to(-h, h).close().to_params())


@pytest.fixture(scope="module")
def kern():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def _build(kern, *features):
    doc = Document()
    for f in features:
        doc.add(f)
    return doc, doc.build(kern).final(doc)


@pytest.mark.occt
def test_ruled_loft_is_a_frustum(kern):
    _, shape = _build(kern, Feature(op="loft", params={
        "sections": [{"profile": _square(10), "z": 0.0},
                     {"profile": _square(5), "z": 12.0}],
        "ruled": True}))
    a1, a2, h = 100.0, 25.0, 12.0
    expected = h / 3 * (a1 + a2 + math.sqrt(a1 * a2))
    assert kern.measure(shape)["volume"] == pytest.approx(expected, rel=1e-6)


@pytest.mark.occt
def test_loft_needs_two_sections(kern):
    from gitcad.errors import KernelError

    with pytest.raises(KernelError, match="at least 2"):
        kern.loft([(_square(10), 0.0)])


@pytest.mark.occt
def test_straight_sweep_is_a_prism(kern):
    _, shape = _build(kern, Feature(op="sweep", params={
        "profile": _square(2), "path": [[0, 0, 0], [0, 0, 20]]}))
    assert kern.measure(shape)["volume"] == pytest.approx(80.0, rel=1e-6)


@pytest.mark.occt
def test_sweep_refuses_offset_path(kern):
    from gitcad.errors import KernelError

    with pytest.raises(KernelError, match="start at"):
        kern.sweep(_square(2), [(5.0, 0.0, 0.0), (5.0, 0.0, 20.0)])


@pytest.mark.occt
def test_mirror_fuse_doubles_a_half_body(kern):
    doc = Document()
    bid = doc.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 5}))
    doc.add(Feature(op="mirror", params={"plane": "xy", "fuse": True}, inputs=[bid]))
    shape = doc.build(kern).final(doc)
    # box occupies z in [0,5]; mirror across xy adds [-5,0] -> volume doubles
    assert kern.measure(shape)["volume"] == pytest.approx(1000.0, rel=1e-6)
    lo, _hi = kern.bbox(shape)
    assert lo[2] == pytest.approx(-5.0, abs=1e-6)


@pytest.mark.occt
def test_countersink_hole_removes_cone_ring(kern):
    doc = Document()
    bid = doc.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 10}))
    doc.add(Feature(op="hole", params={
        "x": 10, "y": 10, "top_z": 10, "depth": 10, "diameter": 4,
        "csink_diameter": 8, "csink_angle_deg": 90}, inputs=[bid]))
    shape = doc.build(kern).final(doc)
    # 90-deg csink from r2 to r4: depth (8-4)/2 = 2. Removed = through hole
    # + (cone frustum r2->r4 h2  minus its cylindrical core already drilled).
    hole = math.pi * 2 ** 2 * 10
    frustum = math.pi * 2 / 3 * (4 ** 2 + 4 * 2 + 2 ** 2)
    core = math.pi * 2 ** 2 * 2
    expected = 20 * 20 * 10 - hole - (frustum - core)
    assert kern.measure(shape)["volume"] == pytest.approx(expected, rel=1e-6)


@pytest.mark.occt
def test_mass_props_of_a_box(kern):
    p = kern.mass_props(kern.box(10, 20, 30))
    assert p["volume"] == pytest.approx(6000.0, rel=1e-9)
    assert (p["cx"], p["cy"], p["cz"]) == pytest.approx((5.0, 10.0, 15.0))
    # Inertia about the center of mass, unit density: Ixx = m/12*(dy^2+dz^2)
    m = 6000.0
    assert p["ixx"] == pytest.approx(m / 12 * (20 ** 2 + 30 ** 2), rel=1e-9)


def test_null_kernel_tracks_new_ops_symbolically():
    from gitcad.kernel.null import NullKernel

    nk = NullKernel()
    lofted = nk.loft([(_square(10), 0.0), (_square(5), 10.0)])
    assert lofted.kind == "loft"
    mirrored = nk.mirror(nk.box(2, 2, 2), "xy")
    assert nk.mass_props(mirrored)["volume"] == pytest.approx(8.0)
    with pytest.raises(ValueError):
        nk.mirror(nk.box(1, 1, 1), "diagonal")
