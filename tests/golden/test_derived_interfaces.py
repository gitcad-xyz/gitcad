"""GOLDEN: domain wiring — part interfaces derived from real domain data.

The board's part.json comes from its mounting holes and outline; the mech
part's envelope comes from built geometry. Changing the domain data changes
the interface, which is what makes interface-semver bite automatically.
"""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.ecad import Board, MountingHole
from gitcad.ecad import excellon
from gitcad.kernel.null import NullKernel
from gitcad.part import Frame, Port, check_release, model_to_part


def _board() -> Board:
    b = Board(name="b", outline=[(0, 0), (30, 0), (30, 20), (0, 20)], thickness=1.6)
    b.mounting_holes += [MountingHole("mnt_1", 3, 3, 3.2, thread="M3"),
                         MountingHole("mnt_2", 27, 17, 3.2)]
    return b


def test_board_to_part_derives_envelope_and_ports() -> None:
    p = _board().to_part("prt_0000000000000001", "1.0.0")
    assert p.domain == "ecad"
    env = p.interface.envelope
    assert (env["dx"], env["dy"], env["dz"]) == (30, 20, 1.6)
    assert set(p.interface.ports) == {"mnt_1", "mnt_2"}
    port = p.interface.ports["mnt_1"]
    assert port.type == "mech.bolt" and port.spec == {"drill": 3.2, "thread": "M3"}
    assert p.interface.frames["mnt_2"].origin == (27, 17, 0.0)


def test_moving_a_hole_on_the_board_trips_the_release_gate() -> None:
    """The end-to-end property: edit the BOARD, and interface-semver reacts —
    no hand-maintained interface in between."""
    old = _board().to_part("prt_0000000000000001", "1.0.0")
    moved = _board()
    moved.mounting_holes[1] = MountingHole("mnt_2", 28.5, 17, 3.2)
    new = moved.to_part("prt_0000000000000001", "1.0.1")
    violations = check_release("1.0.0", "1.0.1", old.interface, new.interface)
    assert violations and "MAJOR" in violations[0]


def test_mounting_holes_export_as_npth_not_plated() -> None:
    b = _board()
    npth = excellon.npth_drills(b)
    plated = excellon.drills(b)
    assert "X3.000Y3.000" in npth
    assert "X3.000Y3.000" not in plated


def test_board_roundtrip_preserves_mounting_holes() -> None:
    b = _board()
    b2 = Board.loads(b.dumps())
    assert b2.dumps() == b.dumps()
    assert b2.mounting_holes == b.mounting_holes


def test_model_to_part_derives_envelope_from_geometry() -> None:
    doc = Document()
    doc.add(Feature(op="box", params={"dx": 60, "dy": 40, "dz": 8}))
    p = model_to_part(
        doc, NullKernel(), part_id="prt_0000000000000002", name="bracket",
        frames={"boss_1": Frame(origin=(13, 13, 8))},
        ports={"boss_1": Port("boss_1", "mech.boss", "boss_1")},
    )
    env = p.interface.envelope
    assert (env["dx"], env["dy"], env["dz"]) == (60, 40, 8)
    assert p.interface.properties["volume_mm3"] == pytest.approx(19200)
    assert "boss_1" in p.interface.ports


@pytest.mark.occt
def test_model_to_part_envelope_matches_occt_geometry() -> None:
    from gitcad.kernel.occt import OcctKernel

    doc = Document()
    b = doc.add(Feature(op="box", params={"dx": 60, "dy": 40, "dz": 8}))
    c = doc.add(Feature(op="cylinder", params={"radius": 3.2, "height": 8}))
    m = doc.add(Feature(op="move", params={"translate": [15, 20, 0]}, inputs=[c]))
    doc.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[b, m]))
    p = model_to_part(doc, OcctKernel(), part_id="prt_0000000000000003", name="plate")
    env = p.interface.envelope
    assert env["dx"] == pytest.approx(60, abs=1e-4)
    assert env["dy"] == pytest.approx(40, abs=1e-4)
    assert env["dz"] == pytest.approx(8, abs=1e-4)
