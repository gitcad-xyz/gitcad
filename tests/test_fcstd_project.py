"""Golden: fcstd_to_project — one command, a whole gitcad project.

Oracles: every body becomes .model + .part with a content-addressed
asset; the .gitcad root instances all bodies; the committed models use
project-RELATIVE asset paths (portable) and the viewer resolves them
against the model's directory, so the converted project renders.
"""

import zipfile
from pathlib import Path

import pytest


def _fcstd(tmp_path) -> Path:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    a = tmp_path / "a.brep"
    b = tmp_path / "b.brep"
    k.export_brep(k.box(10, 10, 10), str(a))
    k.export_brep(k.transform(k.box(5, 5, 5), translate=(20, 0, 0)), str(b))
    f = tmp_path / "two.FCStd"
    with zipfile.ZipFile(f, "w") as zf:
        zf.write(a, "Lid.Shape.brp")
        zf.write(b, "Base.Shape.brp")
        zf.writestr("Document.xml", "<Document/>")
    return f


@pytest.mark.occt
def test_convert_produces_a_complete_project(tmp_path):
    from gitcad.importers.fcstd import fcstd_to_project
    from gitcad.kernel.occt import OcctKernel
    from gitcad.part import PartManifest

    out = tmp_path / "proj"
    r = fcstd_to_project(str(_fcstd(tmp_path)), str(out), OcctKernel(),
                         name="widget")
    assert r["bodies"] == ["Base", "Lid"]
    for stem in ("Base", "Lid"):
        assert (out / f"{stem}.model").is_file()
        part = PartManifest.loads((out / f"{stem}.part").read_text(encoding="utf-8"))
        assert part.body["model"] == f"{stem}.model"
    root = PartManifest.loads((out / "widget.gitcad").read_text(encoding="utf-8"))
    assert set(root.body["instances"]) == {"Base", "Lid"}
    # committed model references are project-relative (portable)
    model_text = (out / "Base.model").read_text(encoding="utf-8")
    assert '"assets/Base-' in model_text
    assert str(out).replace("\\", "/") not in model_text.replace("\\", "/")


@pytest.mark.occt
def test_converted_project_renders_through_the_viewer(tmp_path):
    from gitcad.importers.fcstd import fcstd_to_project
    from gitcad.kernel.occt import OcctKernel
    from gitcad.viewer.server import assembly_mesh_payload

    k = OcctKernel()
    out = tmp_path / "proj"
    fcstd_to_project(str(_fcstd(tmp_path)), str(out), k, name="widget")
    payload = assembly_mesh_payload(out / "widget.gitcad", k)
    assert payload["stats"]["instances"] == 2
    assert payload["stats"]["triangles"] > 0        # relative assets resolved


@pytest.mark.occt
def test_reconvert_is_content_stable(tmp_path):
    from gitcad.importers.fcstd import fcstd_to_project
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    src = _fcstd(tmp_path)
    out = tmp_path / "proj"
    fcstd_to_project(str(src), str(out), k, name="widget")
    first = (out / "Base.model").read_text(encoding="utf-8")
    out2 = tmp_path / "proj2"
    fcstd_to_project(str(src), str(out2), k, name="widget")
    second = (out2 / "Base.model").read_text(encoding="utf-8")
    assert first == second                          # content-addressed assets