"""GOLDEN: atomic components — footprint <-> registry part round-trip."""

from __future__ import annotations

import pytest

from gitcad.ecad import Footprint, Pad, footprint_from_part, footprint_to_part
from gitcad.part import PartManifest, check_release


def _qfn() -> Footprint:
    return Footprint("QFN8-REP", pads=[
        Pad("1", -3.0, 1.0, 1.2, 0.8), Pad("2", -3.0, -1.0, 1.2, 0.8),
        Pad("3", 3.0, 1.0, 1.2, 0.8), Pad("4", 3.0, -1.0, 1.2, 0.8)], courtyard=(8, 5))


def test_round_trip_preserves_the_footprint() -> None:
    part = footprint_to_part(_qfn(), "prt_00000000000000f1", "0.1.0")
    assert part.domain == "ecad.component"
    assert set(part.interface.ports) == {"pad_1", "pad_2", "pad_3", "pad_4"}
    assert part.interface.ports["pad_1"].type == "elec.pin"
    assert part.interface.envelope["dx"] == 8
    back = footprint_from_part(PartManifest.loads(part.dumps()))
    assert back == _qfn()


def test_moved_pad_requires_major() -> None:
    """The ADR-0010 promise: a pad move can never ship as a patch."""
    old = footprint_to_part(_qfn(), "prt_00000000000000f1", "1.0.0")
    fp2 = _qfn()
    fp2.pads[0] = Pad("1", -3.2, 1.0, 1.2, 0.8)   # pad moved 0.2mm
    new = footprint_to_part(fp2, "prt_00000000000000f1", "1.0.1")
    violations = check_release("1.0.0", "1.0.1", old.interface, new.interface)
    assert violations and "MAJOR" in violations[0]


def test_through_hole_drill_survives() -> None:
    hdr = Footprint("HDR-2P-2.54", pads=[
        Pad("1", 0, -1.27, 1.7, 1.7, "circle", 1.0), Pad("2", 0, 1.27, 1.7, 1.7, "circle", 1.0)])
    part = footprint_to_part(hdr, "prt_00000000000000f2")
    assert part.interface.ports["pad_1"].spec["drill"] == 1.0
    assert footprint_from_part(part).pads[0].drill == 1.0
