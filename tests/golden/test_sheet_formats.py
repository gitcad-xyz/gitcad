"""Standard sheet formats + git-derived title-block fields — no kernel.

The pure-data half of task #139 (the geometry half lives in
``test_title_blocks.py``): ISO 5457 / ANSI Y14.1 paper sizes, the standard
scale series, the auto sheet pick, the projection symbol, and the
git-derived ISO 7200 fields. Runs in the null-kernel job.
"""

from __future__ import annotations

import re
import subprocess

from gitcad.drawing.formats import FORMATS, STANDARD_SCALES, pick_sheet, scale_text
from gitcad.drawing.sheet import Drawing
from gitcad.drawing.titleblock import resolve_title_block


# -- paper sizes ---------------------------------------------------------------

def test_iso_sheets_have_standard_trimmed_sizes() -> None:
    assert (FORMATS["A4"].width, FORMATS["A4"].height) == (210.0, 297.0)  # portrait
    assert (FORMATS["A3"].width, FORMATS["A3"].height) == (420.0, 297.0)
    assert (FORMATS["A2"].width, FORMATS["A2"].height) == (594.0, 420.0)
    assert (FORMATS["A1"].width, FORMATS["A1"].height) == (841.0, 594.0)
    assert (FORMATS["A0"].width, FORMATS["A0"].height) == (1189.0, 841.0)
    # ISO 5457 untrimmed sizes ride along as data
    assert FORMATS["A3"].untrimmed == (450.0, 330.0)
    assert FORMATS["A4"].untrimmed == (240.0, 330.0)


def test_ansi_sheets_have_standard_sizes() -> None:
    assert (FORMATS["ANSI A"].width, FORMATS["ANSI A"].height) == (279.4, 215.9)
    assert (FORMATS["ANSI B"].width, FORMATS["ANSI B"].height) == (431.8, 279.4)
    assert (FORMATS["ANSI D"].width, FORMATS["ANSI D"].height) == (863.6, 558.8)


def test_iso_frame_margins_follow_iso_5457() -> None:
    # 20 mm filing margin left, 10 mm elsewhere: A3 frame is 390x277
    x0, y0, x1, y1 = FORMATS["A3"].frame
    assert (x1 - x0, y1 - y0) == (390.0, 277.0)
    x0, y0, x1, y1 = FORMATS["A4"].frame
    assert (x1 - x0, y1 - y0) == (180.0, 277.0)


def test_scale_text_shows_true_standard_ratios() -> None:
    assert scale_text(1.0) == "1:1"
    assert scale_text(2.0) == "2:1"
    assert scale_text(0.5) == "1:2"
    assert scale_text(0.02) == "1:50"


def test_auto_pick_prefers_smallest_sheet_at_full_size() -> None:
    assert pick_sheet(40.0, 30.0, "iso")[0] == "A4"
    big = pick_sheet(900.0, 500.0, "iso")[0]
    assert big in ("A1", "A0")
    assert pick_sheet(40.0, 30.0, "ansi")[0].startswith("ANSI")
    assert all(pick_sheet(w, w, "iso")[1] in STANDARD_SCALES
               for w in (10.0, 100.0, 1000.0, 10000.0))


def test_projection_symbol_third_vs_first_differ() -> None:
    from gitcad.drawing.frame import projection_symbol

    third = projection_symbol(0.0, 0.0, 5.0, "third")
    first = projection_symbol(0.0, 0.0, 5.0, "first")
    assert third["lines"] != first["lines"]      # the trapezoid flips
    assert len(third["circles"]) == 2 and len(first["circles"]) == 2


# -- git-derived fields --------------------------------------------------------

def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=True).stdout.strip()


def test_git_fields_derive_from_the_part_file(tmp_path) -> None:
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.name", "Test Author"], tmp_path)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    part = tmp_path / "widget.gitcad.json"
    part.write_text("{}\n", encoding="utf-8")
    _git(["add", "widget.gitcad.json"], tmp_path)
    _git(["commit", "-q", "-m", "add widget"], tmp_path)
    sha = _git(["log", "-1", "--format=%h", "--", "widget.gitcad.json"], tmp_path)
    date = _git(["log", "-1", "--format=%ad", "--date=format:%Y-%m-%d"], tmp_path)

    block = resolve_title_block(title="widget", scale="1:1", sheet_name="A4",
                                settings={"source_path": str(part)})
    assert block.author == "Test Author"
    assert block.revision == sha
    assert block.date == date
    assert block.revisions[0][0] == sha
    assert "add widget" in block.revisions[0][2]
    assert block.drawing_number == "WIDGET"       # from the part name


def test_uncommitted_file_gets_blank_fields_never_a_lie(tmp_path) -> None:
    _git(["init", "-q"], tmp_path)
    part = tmp_path / "untracked.gitcad.json"
    part.write_text("{}\n", encoding="utf-8")
    block = resolve_title_block(title="untracked", scale="1:1", sheet_name="A4",
                                settings={"source_path": str(part)})
    assert block.revision == "" and block.date == "" and block.revisions == []


def test_dirty_tracked_file_is_flagged_not_hidden(tmp_path) -> None:
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.name", "T"], tmp_path)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    part = tmp_path / "p.gitcad.json"
    part.write_text("{}\n", encoding="utf-8")
    _git(["add", "p.gitcad.json"], tmp_path)
    _git(["commit", "-q", "-m", "v1"], tmp_path)
    part.write_text('{"changed": true}\n', encoding="utf-8")
    block = resolve_title_block(title="p", scale="1:1", sheet_name="A4",
                                settings={"source_path": str(part)})
    assert block.revision.endswith("*")           # modified since last commit


def test_outside_a_repo_everything_is_blank(tmp_path) -> None:
    part = tmp_path / "loose.gitcad.json"
    part.write_text("{}\n", encoding="utf-8")
    block = resolve_title_block(title="loose", scale="1:1", sheet_name="A4",
                                settings={"source_path": str(part)})
    assert block.revision == "" and block.date == "" and block.revisions == []


def test_explicit_overrides_beat_git(tmp_path) -> None:
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.name", "From Git"], tmp_path)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    part = tmp_path / "q.gitcad.json"
    part.write_text("{}\n", encoding="utf-8")
    _git(["add", "q.gitcad.json"], tmp_path)
    _git(["commit", "-q", "-m", "v1"], tmp_path)
    block = resolve_title_block(title="q", scale="1:1", sheet_name="A4",
                                settings={"source_path": str(part),
                                          "author": "Handed Down", "revision": "C"})
    assert block.author == "Handed Down" and block.revision == "C"


# -- back-compat: hand-built Drawings keep the plain border --------------------

def test_custom_size_drawing_keeps_legacy_border() -> None:
    d = Drawing(sheet="A4", width=120, height=90, scale=1.0, title="t")
    svg = d.to_svg()
    assert "<svg" in svg and 'class="ref"' not in svg
    assert re.search(r'<rect x="5[."]', svg)      # the old 5 mm border survives
