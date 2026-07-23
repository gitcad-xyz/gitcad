"""Sheet reuse — one .kicad_sch file instanced by several sheet nodes.

KiCad's instances model: each symbol carries per-instance-path references
(``(instances (project (path "/root-uuid/sheet-uuid" (reference ...))))``);
the importer resolves the ref for the instance path it entered through.
Expected netlists were validated against ``kicad-cli sch export netlist``
on this exact fixture (nets /NET_A=R1.1, /NET_B=R2.1, /ch_a/OUT=R1.2,
/ch_b/OUT=R2.2)."""

from __future__ import annotations

import pytest

from gitcad.errors import GitcadError
from gitcad.importers.kicad_sch import import_kicad_sch

_ROOT = """(kicad_sch (version 20250114) (generator "eeschema")
  (uuid "aaaaaaaa-0000-0000-0000-000000000001")
  (lib_symbols)
  (sheet (at 100 100) (size 20 10)
    (uuid "bbbbbbbb-0000-0000-0000-00000000000a")
    (property "Sheetname" "ch_a" (at 100 99 0))
    (property "Sheetfile" "channel.kicad_sch" (at 100 111 0))
    (pin "IN" input (at 100 105 180)))
  (sheet (at 140 100) (size 20 10)
    (uuid "bbbbbbbb-0000-0000-0000-00000000000b")
    (property "Sheetname" "ch_b" (at 140 99 0))
    (property "Sheetfile" "channel.kicad_sch" (at 140 111 0))
    (pin "IN" input (at 140 105 180)))
  (wire (pts (xy 95 105) (xy 100 105)))
  (label "NET_A" (at 95 105 0))
  (wire (pts (xy 135 105) (xy 140 105)))
  (label "NET_B" (at 135 105 0))
)
"""

_CHANNEL = """(kicad_sch (version 20250114) (generator "eeschema")
  (uuid "cccccccc-0000-0000-0000-000000000001")
  (lib_symbols
    (symbol "Device:R"
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "~") (number "1"))
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "~") (number "2")))))
  (symbol (lib_id "Device:R") (at 50 50 0)
    (uuid "dddddddd-0000-0000-0000-000000000001")
    (property "Reference" "R?" (at 52 49 0))
    (property "Value" "10k" (at 52 51 0))
    (instances
      (project "reuse"
        (path "/aaaaaaaa-0000-0000-0000-000000000001/bbbbbbbb-0000-0000-0000-00000000000a"
          (reference "R1") (unit 1))
        (path "/aaaaaaaa-0000-0000-0000-000000000001/bbbbbbbb-0000-0000-0000-00000000000b"
          (reference "R2") (unit 1)))))
  (wire (pts (xy 50 46.19) (xy 50 40)))
  (hierarchical_label "IN" (shape input) (at 50 40 0))
  (wire (pts (xy 50 53.81) (xy 50 58)))
  (label "OUT" (at 50 58 0))
)
"""


def _write_project(tmp_path, root=_ROOT, channel=_CHANNEL):
    (tmp_path / "reuse.kicad_sch").write_text(root, encoding="utf-8")
    (tmp_path / "channel.kicad_sch").write_text(channel, encoding="utf-8")
    return str(tmp_path / "reuse.kicad_sch")


def test_reused_sheet_resolves_per_instance_refs(tmp_path) -> None:
    sch, report = import_kicad_sch(_write_project(tmp_path))
    assert sorted(c.ref for c in sch.components) == ["R1", "R2"]
    # node-for-node the kicad-cli netlist of this fixture
    assert sorted(sch.nets["NET_A"]) == ["R1.1"]
    assert sorted(sch.nets["NET_B"]) == ["R2.1"]
    assert sorted(sch.nets["ch_a/OUT"]) == ["R1.2"]
    assert sorted(sch.nets["ch_b/OUT"]) == ["R2.2"]
    assert report.warnings == []


def test_sheet_pins_are_known_wire_targets(tmp_path) -> None:
    _, report = import_kicad_sch(_write_project(tmp_path))
    assert report.imported["wire_end_hit_pct"] == 100


def test_duplicate_sheetnames_get_distinct_scopes(tmp_path) -> None:
    root = _ROOT.replace('"Sheetname" "ch_a"', '"Sheetname" "ch"') \
                .replace('"Sheetname" "ch_b"', '"Sheetname" "ch"')
    sch, _ = import_kicad_sch(_write_project(tmp_path, root=root))
    assert sorted(n for n in sch.nets if n.endswith("/OUT")) == ["ch#2/OUT", "ch/OUT"]
    assert sorted(sch.nets["ch/OUT"] + sch.nets["ch#2/OUT"]) == ["R1.2", "R2.2"]


def test_reuse_without_instances_still_fails_loud(tmp_path) -> None:
    # both instances would import the property ref "R9" — a genuine collision
    channel = _CHANNEL.replace('"Reference" "R?"', '"Reference" "R9"')
    start = channel.index("(instances")
    depth, i = 0, start
    while True:
        if channel[i] == "(":
            depth += 1
        elif channel[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    channel = channel[:start] + channel[i + 1:]
    with pytest.raises(GitcadError, match="duplicate ref"):
        import_kicad_sch(_write_project(tmp_path, channel=channel))


def test_root_level_instances_override_property_ref(tmp_path) -> None:
    # the real-project format: root symbols carry (path "/root-uuid" (reference ..))
    root = _ROOT.replace(
        "  (wire (pts (xy 95 105) (xy 100 105)))",
        """  (symbol (lib_id "Device:R") (at 60 50 0)
    (property "Reference" "R?" (at 0 0 0))
    (property "Value" "1k" (at 0 0 0))
    (instances (project "reuse"
      (path "/aaaaaaaa-0000-0000-0000-000000000001"
        (reference "R100") (unit 1)))))
  (wire (pts (xy 95 105) (xy 100 105)))""").replace(
        "(lib_symbols)", _CHANNEL[_CHANNEL.index("(lib_symbols"):
                                  _CHANNEL.index("(symbol (lib_id")].rstrip())
    sch, _ = import_kicad_sch(_write_project(tmp_path, root=root))
    assert "R100" in {c.ref for c in sch.components}
