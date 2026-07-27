"""GOLDEN: imported geometry that does not close (#135).

The contract at the STEP border: a file whose CLOSED_SHELL lies is refused
with a structured gap report in user millimetres — never silently imported,
never handed a confident volume/centroid (both are origin-dependent, i.e.
meaningless, on an open shell). The one sanctioned repair is an exact,
opt-in vertex merge recorded as intent on the import feature, certified by
a volume-change bound — and it can never invent a face.

The flagship broken file is an AUTHORED test asset
(tests/golden/fixtures/box_missing_face.step): a 10x20x30 box whose bottom
face was removed from the CLOSED_SHELL by hand. It is committed, not
generated — no correct exporter can produce it, which is exactly why it
exists (ADR-0004 bans generated artifacts; this is authored source for the
import contract). Variants (a 3 um tear) are authored in-test from
forgekernel's own writer output.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gitcad.errors import KernelError

FIXTURE = Path(__file__).parent / "fixtures" / "box_missing_face.step"


def _kernel():
    from gitcad.kernel.ref import RefKernel
    return RefKernel()


def _torn_step(tmp_path) -> str:
    """A 10x20x30 box with one face's corner torn 3 um off the shared vertex
    (10,0,0) -> (10.003,0,0), authored from forge's own writer output."""
    from forgekernel.brep import Solid
    from forgekernel.stepio import write_step_planar_solid

    text = write_step_planar_solid(Solid.box(10, 20, 30))
    cp = re.search(r"#(\d+) = CARTESIAN_POINT\('',\(10\.,0\.,0\.\)\)", text).group(1)
    vp = re.search(r"#(\d+) = VERTEX_POINT\('',#" + cp + r"\)", text).group(1)
    ec = re.search(r"#(\d+) = EDGE_CURVE\('',#" + vp + r",#(\d+),#(\d+),\.T\.\)", text)
    maxid = max(int(x) for x in re.findall(r"#(\d+) =", text))
    add = (f"#{maxid + 1} = CARTESIAN_POINT('',(10.003,0.,0.));\n"
           f"#{maxid + 2} = VERTEX_POINT('',#{maxid + 1});\n"
           f"#{maxid + 3} = EDGE_CURVE('',#{maxid + 2},#{ec.group(2)},#{ec.group(3)},.T.);\n")
    oe = re.search(r"#(\d+) = ORIENTED_EDGE\('',\*,\*,#" + ec.group(1) + r",\.T\.\)",
                   text).group(0)
    text = text.replace(oe, oe.replace(f"#{ec.group(1)}", f"#{maxid + 3}"), 1)
    text = text.replace("ENDSEC;\nEND-ISO-10303-21;",
                        add + "ENDSEC;\nEND-ISO-10303-21;")
    p = tmp_path / "torn.step"
    p.write_text(text, newline="\n")
    return str(p)


def test_fixture_is_the_authored_broken_shell():
    text = FIXTURE.read_text()
    assert "AUTHORED BROKEN FIXTURE" in text          # provenance, in the file
    assert "CLOSED_SHELL" in text                     # the lie being tested


def test_nonclosed_step_refuses_with_gap_report_not_a_confident_volume():
    from gitcad.importers.step import import_step_file

    k = _kernel()
    with pytest.raises(KernelError) as ei:
        import_step_file(str(FIXTURE), k)
    e = ei.value
    assert e.signature.diagnostic == "NonClosedShell"
    assert e.predicate == "shell_closure"
    # the gap report speaks user millimetres
    assert e.measured["open_edges"] == 4
    assert e.measured["open_perimeter_mm"] == pytest.approx(60.0)
    # the remedy names both sanctioned outs and the bet that rules out a third
    assert "heal_tolerance" in e.remedy
    assert "invent" in e.remedy
    # and never leaks raw carrier-line parameterizations
    assert "line-dir" not in str(e)


def test_nonclosed_refusal_happens_at_build_so_measure_is_unreachable():
    """The pre-fix behaviour — measure() confidently answering 6000.0 for an
    open shell — is the bug this contract kills: the refusal fires at the
    import border, so no non-closed shell ever reaches measure/mass_props."""
    import hashlib

    from gitcad.document import Document, Feature

    k = _kernel()
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    doc = Document()
    doc.add(Feature(op="import", params={"format": "step", "file": str(FIXTURE),
                                         "sha256": digest}))
    with pytest.raises(KernelError) as ei:
        doc.build(k)
    assert ei.value.signature.diagnostic == "NonClosedShell"


def test_heal_is_recorded_intent_and_certified(tmp_path):
    from gitcad.importers.step import import_step_file

    k = _kernel()
    path = _torn_step(tmp_path)
    # without heal: a refusal naming the crack
    with pytest.raises(KernelError) as ei:
        import_step_file(path, k)
    assert ei.value.signature.diagnostic == "NonClosedShell"
    assert ei.value.measured["open_perimeter_mm"] > 0

    # with heal: recorded intent on the feature, exact merge, certificate
    doc, report = import_step_file(path, k, heal_tolerance="0.01")
    feat = doc.features[0]
    assert feat.params["heal_tolerance"] == "0.01"    # ADR-0022: intent, replayable
    shape = doc.build(k).final(doc)
    assert k.measure(shape)["volume"] == 6000.0       # exactly closed, exactly 6000
    assert report.imported.get("vertices_healed") == 1
    assert any("heal" in w and "bound" in w for w in report.warnings)

    # the recorded intent REPLAYS: a fresh build from the document text alone
    from gitcad.document import Document
    doc2 = Document.loads(doc.dumps())
    shape2 = doc2.build(k).final(doc2)
    assert k.measure(shape2)["volume"] == 6000.0


def test_heal_never_invents_a_missing_face():
    from gitcad.importers.step import import_step_file

    k = _kernel()
    with pytest.raises(KernelError) as ei:
        import_step_file(str(FIXTURE), k, heal_tolerance="0.01")
    assert ei.value.signature.diagnostic == "NonClosedShell"


def test_import_brep_border_is_audited_too(tmp_path):
    from forgekernel import io
    from forgekernel.brep import Solid

    k = _kernel()
    open_solid = Solid(Solid.box(10, 20, 30).polys[1:])
    p = tmp_path / "open.brep"
    p.write_text(io.dumps(open_solid), newline="\n")
    with pytest.raises(KernelError) as ei:
        k.import_brep(str(p))
    assert ei.value.signature.diagnostic == "NonClosedShell"


def test_null_kernel_takes_the_heal_param_and_still_refuses_cleanly():
    from gitcad.kernel.null import NullKernel

    with pytest.raises(NotImplementedError):
        NullKernel().import_step("x.step", heal_tolerance="0.01")
