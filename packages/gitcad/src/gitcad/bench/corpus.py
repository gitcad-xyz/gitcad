"""The kernel benchmark corpus — deterministic documents per operator
class (ADR-0018 W0).

Each entry builds a Document tagged with the operator classes it
exercises. This corpus is simultaneously: the differential-test input
(ref vs occt), the benchmark workload (timed per backend), and the
future acceptance suite for kernel cutover. Torture entries encode the
configurations that break kernels — tangencies, coincidences, slivers
— where beating OCCT must become measurable.
"""

from __future__ import annotations

from typing import Callable

from gitcad.document import Document, Feature


def plate_with_holes() -> Document:
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 60, "dy": 40, "dz": 4}))
    prev = base
    for i in range(4):
        prev = d.add(Feature(op="hole", params={
            "x": 10 + 13 * i, "y": 20, "top_z": 4, "depth": 4,
            "diameter": 5}, inputs=[prev]))
    return d


def quadric_boss() -> Document:
    d = Document()
    base = d.add(Feature(op="cylinder", params={"radius": 20, "height": 8}))
    boss = d.add(Feature(op="cone", params={"r1": 10, "r2": 6, "height": 12}))
    bm = d.add(Feature(op="move", params={"translate": [0, 0, 8]}, inputs=[boss]))
    u = d.add(Feature(op="boolean", params={"kind": "union"}, inputs=[base, bm]))
    s = d.add(Feature(op="sphere", params={"radius": 5}))
    sm = d.add(Feature(op="move", params={"translate": [0, 0, 22]}, inputs=[s]))
    d.add(Feature(op="boolean", params={"kind": "union"}, inputs=[u, sm]))
    return d


def revolve_profile() -> Document:
    d = Document()
    profile = {"start": [5, 0], "segments": [
        {"kind": "line", "to": [15, 0]}, {"kind": "line", "to": [15, 4]},
        {"kind": "line", "to": [8, 8]}, {"kind": "line", "to": [8, 20]},
        {"kind": "line", "to": [5, 20]}, {"kind": "line", "to": [5, 0]}]}
    d.add(Feature(op="revolve", params={"profile": profile, "angle_deg": 360.0}))
    return d


def extrude_L() -> Document:
    d = Document()
    profile = {"start": [0, 0], "segments": [
        {"kind": "line", "to": [30, 0]}, {"kind": "line", "to": [30, 8]},
        {"kind": "line", "to": [8, 8]}, {"kind": "line", "to": [8, 25]},
        {"kind": "line", "to": [0, 25]}, {"kind": "line", "to": [0, 0]}]}
    d.add(Feature(op="extrude", params={"profile": profile, "height": 12}))
    return d


def filleted_block() -> Document:
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 30, "dy": 20, "dz": 10}))
    d.add(Feature(op="fillet", params={"radius": 2.5}, inputs=[b]))
    return d


def chamfered_block() -> Document:
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 30, "dy": 20, "dz": 10}))
    d.add(Feature(op="chamfer", params={"distance": 2.0}, inputs=[b]))
    return d


def shelled_box() -> Document:
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 40, "dy": 30, "dz": 20}))
    d.add(Feature(op="shell", params={"faces": [], "thickness": 2.0},
                  inputs=[b]))
    return d


def drafted_block() -> Document:
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 30, "dy": 30, "dz": 15}))
    d.add(Feature(op="draft", params={"faces": [], "angle_deg": 3.0},
                  inputs=[b]))
    return d


def spring() -> Document:
    d = Document()
    d.add(Feature(op="spring", params={"radius": 8, "pitch": 4, "turns": 6,
                                       "wire_diameter": 1.5}))
    return d


def swept_channel() -> Document:
    d = Document()
    profile = {"start": [-2, -2], "segments": [
        {"kind": "line", "to": [2, -2]}, {"kind": "line", "to": [2, 2]},
        {"kind": "line", "to": [-2, 2]}, {"kind": "line", "to": [-2, -2]}]}
    d.add(Feature(op="sweep", params={"profile": profile,
                                      "path": [[0, 0, 0], [0, 0, 20],
                                               [15, 0, 35], [40, 0, 35]]}))
    return d


def loft_transition() -> Document:
    d = Document()
    sq = {"start": [-10, -10], "segments": [
        {"kind": "line", "to": [10, -10]}, {"kind": "line", "to": [10, 10]},
        {"kind": "line", "to": [-10, 10]}, {"kind": "line", "to": [-10, -10]}]}
    sm = {"start": [-4, -4], "segments": [
        {"kind": "line", "to": [4, -4]}, {"kind": "line", "to": [4, 4]},
        {"kind": "line", "to": [-4, 4]}, {"kind": "line", "to": [-4, -4]}]}
    d.add(Feature(op="loft", params={"sections": [
        {"profile": sq, "z": 0.0}, {"profile": sm, "z": 25.0}]}))
    return d


def sheetmetal_folded() -> Document:
    from gitcad.sheetmetal import Flange, SheetMetal

    sm = SheetMetal(name="bench-bracket", width=40, height=50, thickness=2,
                    k_factor=0.44, bend_radius=2,
                    flanges=[Flange(edge="n", length=20),
                             Flange(edge="e", length=12, direction="down")])
    return sm.to_document()


# -- torture: the configurations that break kernels ---------------------------

def torture_tangent_cylinders() -> Document:
    d = Document()
    a = d.add(Feature(op="cylinder", params={"radius": 10, "height": 10}))
    b = d.add(Feature(op="cylinder", params={"radius": 10, "height": 10}))
    bm = d.add(Feature(op="move", params={"translate": [20, 0, 0]}, inputs=[b]))
    d.add(Feature(op="boolean", params={"kind": "union"}, inputs=[a, bm]))
    return d


def torture_coincident_faces() -> Document:
    d = Document()
    a = d.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 10}))
    b = d.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 10}))
    bm = d.add(Feature(op="move", params={"translate": [20, 0, 0]}, inputs=[b]))
    d.add(Feature(op="boolean", params={"kind": "union"}, inputs=[a, bm]))
    return d


def torture_sliver_cut() -> Document:
    d = Document()
    a = d.add(Feature(op="box", params={"dx": 30, "dy": 30, "dz": 10}))
    b = d.add(Feature(op="box", params={"dx": 30, "dy": 30, "dz": 10}))
    bm = d.add(Feature(op="move", params={"translate": [29.999, 0, 0]},
                       inputs=[b]))
    d.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[a, bm]))
    return d


def torture_tangent_sphere_plane() -> Document:
    d = Document()
    a = d.add(Feature(op="box", params={"dx": 30, "dy": 30, "dz": 10}))
    s = d.add(Feature(op="sphere", params={"radius": 5}))
    sm = d.add(Feature(op="move", params={"translate": [15, 15, 15]},
                       inputs=[s]))
    d.add(Feature(op="boolean", params={"kind": "union"}, inputs=[a, sm]))
    return d


CORPUS: list[tuple[str, tuple[str, ...], Callable[[], Document]]] = [
    ("plate_with_holes", ("planar", "boolean", "hole"), plate_with_holes),
    ("quadric_boss", ("quadric", "boolean"), quadric_boss),
    ("revolve_profile", ("quadric", "revolve"), revolve_profile),
    ("extrude_L", ("planar", "extrude"), extrude_L),
    ("filleted_block", ("blend",), filleted_block),
    ("chamfered_block", ("planar", "blend"), chamfered_block),
    ("shelled_box", ("offset",), shelled_box),
    ("drafted_block", ("draft",), drafted_block),
    ("spring", ("sweep", "freeform"), spring),
    ("swept_channel", ("sweep",), swept_channel),
    ("loft_transition", ("loft", "freeform"), loft_transition),
    ("sheetmetal_folded", ("planar", "boolean"), sheetmetal_folded),
    ("torture_tangent_cylinders", ("torture", "quadric", "boolean"),
     torture_tangent_cylinders),
    ("torture_coincident_faces", ("torture", "planar", "boolean"),
     torture_coincident_faces),
    ("torture_sliver_cut", ("torture", "planar", "boolean"),
     torture_sliver_cut),
    ("torture_tangent_sphere_plane", ("torture", "quadric", "boolean"),
     torture_tangent_sphere_plane),
]
