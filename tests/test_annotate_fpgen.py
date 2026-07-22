"""Golden: schematic annotation + footprint generators (KiCad-map P4/P5).

Kernel-free. Annotation oracles: placeholders get the lowest free numbers
in reading order, existing refs never move, nets referencing placeholders
refuse. Generator oracles: exact pad counts, pin-1 position conventions,
symmetric geometry, courtyards present.
"""

import pytest

from gitcad.ecad.annotate import annotate
from gitcad.ecad.fpgen import chip, generate, header, qfn, soic
from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError


def _c(ref, x=None, y=None):
    attrs = {"at": [x, y]} if x is not None else {}
    return SchComponent(ref=ref, pins=[Pin("1", "1")], attrs=attrs)


def test_annotation_fills_gaps_in_reading_order():
    sch = Schematic(name="a")
    sch.components = [_c("R2"), _c("R?", 50, 10), _c("R?", 10, 10),
                      _c("C?", 30, 30), _c("R5")]
    renames = annotate(sch)
    refs = [c.ref for c in sch.components]
    # reading order: y then x -> the R? at (10,10) gets R1, at (50,10) gets R3
    assert refs == ["R2", "R3", "R1", "C1", "R5"]
    assert renames == {"R?@0": "R3", "R?@1": "R1", "C?@0": "C1"}


def test_existing_numbers_never_move():
    sch = Schematic(name="a")
    sch.components = [_c("U1"), _c("U?", 0, 0)]
    annotate(sch)
    assert [c.ref for c in sch.components] == ["U1", "U2"]


def test_nets_referencing_placeholders_refuse():
    sch = Schematic(name="a")
    sch.components = [_c("R?", 0, 0)]
    sch.connect("N", "R?.1")
    with pytest.raises(GitcadError, match="placeholder"):
        annotate(sch)


def test_chip_footprint_dimensions():
    fp = chip("0603")
    assert fp.name == "CHIP-0603" and len(fp.pads) == 2
    assert fp.pads[0].x == -fp.pads[1].x            # symmetric
    assert fp.courtyard is not None
    with pytest.raises(GitcadError, match="unknown chip size"):
        chip("9999")


def test_soic_pin_one_top_left_counter_clockwise():
    fp = soic(8)
    assert len(fp.pads) == 8
    p1, p4, p5, p8 = fp.pads[0], fp.pads[3], fp.pads[4], fp.pads[7]
    assert p1.x < 0 and p1.y > 0                     # pin 1 top-left
    assert p4.x < 0 and p4.y < 0                     # down the left side
    assert p5.x > 0 and p5.y < 0                     # cross to bottom-right
    assert p8.x > 0 and p8.y > 0                     # up the right side
    with pytest.raises(GitcadError):
        soic(7)


def test_qfn_four_sides_and_exposed_pad():
    fp = qfn(16, ep=2.1)
    assert len(fp.pads) == 17
    assert fp.pads[-1].name == "EP" and fp.pads[-1].w == 2.1
    xs = {round(p.x, 3) for p in fp.pads[:16]}
    ys = {round(p.y, 3) for p in fp.pads[:16]}
    assert min(xs) == -max(xs) and min(ys) == -max(ys)   # symmetric square
    with pytest.raises(GitcadError):
        qfn(10)


def test_header_through_hole():
    fp = header(6, rows=2)
    assert fp.name == "HDR-2x3" and len(fp.pads) == 6
    assert all(p.drill for p in fp.pads)             # PTH
    assert fp.pads[0].shape == "circle"


def test_generate_dispatch():
    assert generate("chip", size="0402").name == "CHIP-0402"
    with pytest.raises(GitcadError, match="unknown footprint family"):
        generate("dip")
