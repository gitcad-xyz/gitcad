"""K3.7 through the seam: freeform STEP topology imports as a TrimmedShell.

The K3.6 planar importer refused every non-PLANE surface with "arrives
at K3.7". This pins the arrival's SEAM contract: a B-spline-faced STEP
solid imports as an audited :class:`forgekernel.trimshell.TrimmedShell`
whose downstream behaviour is exactly the K7 boolean-result contract —
``mass_props`` reports a certified bracket (width 0 on the exact tier),
``validate`` re-runs the three-oracle audit, ``tessellate`` returns the
certified-safe strip mesh — while ``bbox`` and ``boolean`` keep refusing
by name (import does NOT unlock re-booleans on imported solids).

The #135 border holds on the freeform path too: a CLOSED_SHELL that lies
refuses with a millimetre gap report; ``heal_tolerance`` is recorded
intent, merges vertex identities only, and can never invent a face.
"""

from __future__ import annotations

import pytest

forgekernel = pytest.importorskip("forgekernel")

from gitcad.errors import KernelError            # noqa: E402
from gitcad.kernel.ref import RefKernel          # noqa: E402
from gitcad.kernel import source_form  # ADR-0022


def _sq(h):
    return [(-h, -h), (h, -h), (h, h), (-h, h)]


def _loft(k=None):
    from forgekernel.loft import LoftSolid
    # terminating control data: the STEP decimals are lossless, so the
    # reimported volume can EQUAL the loft's exact rational volume
    return LoftSolid([(_sq(1), 0), (_sq(2), 3), (_sq(1), 6)])


def _loft_step_path(tmp_path) -> str:
    from forgekernel.stepio import write_step_patch_solid
    p = tmp_path / "skin.step"
    p.write_text(write_step_patch_solid(_loft().to_patches(),
                                        name="loft_skin"), newline="\n")
    return str(p)


def test_freeform_step_imports_as_audited_trimmed_shell(tmp_path) -> None:
    from forgekernel.trimshell import TrimmedShell

    k = RefKernel()
    s = k.import_step(_loft_step_path(tmp_path))
    assert isinstance(s, TrimmedShell)

    mp = k.mass_props(s)
    assert mp["provenance"] == "certified"
    assert mp["volume"] == pytest.approx(float(_loft().volume()))
    assert mp["volume_halfwidth"] == 0.0        # exact tier: width-0 bracket

    v = k.validate(s)
    assert v.ok
    assert v.checks["method"] == "certified-shell-audit"

    mesh = k.tessellate(s)
    assert len(mesh["vertices"]) > 0
    assert len(mesh["triangles"]) > 0


def test_imported_shell_bbox_and_boolean_keep_refusing_by_name(
        tmp_path) -> None:
    k = RefKernel()
    s = k.import_step(_loft_step_path(tmp_path))
    with pytest.raises(KernelError) as exc:
        k.bbox(s)
    assert exc.value.predicate == "trimmed_shell_extent_unbuilt"
    with pytest.raises(KernelError) as exc2:
        k.boolean("union", s, k.box(1, 1, 1))
    assert exc2.value.predicate == "trimmed_shell_reboolean_unbuilt"


def test_freeform_missing_face_refuses_with_gap_report(tmp_path) -> None:
    import re

    from forgekernel.stepio import write_step_patch_solid

    step = write_step_patch_solid(_loft().to_patches())
    m = re.search(r"CLOSED_SHELL\('[^']*',\((#\d+),", step)
    step = step.replace(m.group(0),
                        m.group(0).replace(m.group(1) + ",", "", 1))
    p = tmp_path / "torn.step"
    p.write_text(step, newline="\n")
    k = RefKernel()
    with pytest.raises(KernelError) as exc:
        k.import_step(str(p))
    assert exc.value.predicate == "shell_closure"
    assert exc.value.measured["open_edges"] > 0
    assert "mm" in str(exc.value)


def test_freeform_document_import_indexes_faces(tmp_path) -> None:
    """The user-facing route: import_step_file builds a document whose
    import feature holds the TrimmedShell, with faces indexed for
    identity (ADR-0003) and the sha256 pin intact."""
    from forgekernel.trimshell import TrimmedShell
    from gitcad.importers.step import import_step_file

    k = RefKernel()
    doc, report = import_step_file(_loft_step_path(tmp_path), k)
    assert report.imported["solids_or_bodies"] == 1
    assert report.imported["faces"] == 10          # 8 walls + 2 caps
    shape = doc.build(k).final(doc)
    assert isinstance(shape, TrimmedShell)
    mp = k.mass_props(shape)
    assert mp["volume"] == pytest.approx(float(_loft().volume()))
    assert mp["volume_halfwidth"] == 0.0


def test_freeform_heal_certificate_reaches_the_report(tmp_path) -> None:
    """A torn freeform export heals under recorded intent, and the
    certificate (vertices merged, max move) lands in the import report."""
    import re

    from forgekernel.stepio import write_step_patch_solid
    from gitcad.importers.step import import_step_file

    step = write_step_patch_solid(_loft().to_patches())
    m = re.search(r"#(\d+) = EDGE_CURVE\('',#(\d+),", step)
    vid = int(m.group(2))
    vm = re.search(rf"#{vid} = VERTEX_POINT\('',#(\d+)\)", step)
    pm = re.search(rf"#{vm.group(1)} = CARTESIAN_POINT\('',\(([^)]*)\)\)",
                   step)
    x, rest = pm.group(1).split(",", 1)
    dup = (f"#9901 = CARTESIAN_POINT('',({float(x) + 1e-7},{rest}));\n"
           f"#9902 = VERTEX_POINT('',#9901);")
    step = step.replace(m.group(0), m.group(0).replace(f"#{vid},", "#9902,"))
    step = step.replace("ENDSEC;\nEND-ISO", dup + "\nENDSEC;\nEND-ISO")
    p = tmp_path / "torn.step"
    p.write_text(step, newline="\n")

    k = RefKernel()
    with pytest.raises(KernelError) as exc:        # without recorded intent
        k.import_step(str(p))
    assert exc.value.predicate == "shell_closure"

    doc, report = import_step_file(str(p), k, heal_tolerance="1e-6")
    assert report.imported["vertices_healed"] >= 1
    assert any("merged" in w for w in report.warnings)
    shape = doc.build(k).final(doc)
    assert k.mass_props(shape)["volume"] == pytest.approx(
        float(_loft().volume()))


def test_planar_step_still_imports_as_solid(tmp_path) -> None:
    from forgekernel.brep import Solid

    k = RefKernel()
    box = k.box(2, 3, 4)
    path = str(tmp_path / "box.step")
    k.export_step(box, path)
    s = k.import_step(path)
    assert isinstance(source_form(s), Solid)
    assert k.mass_props(s)["volume"] == pytest.approx(24.0)
