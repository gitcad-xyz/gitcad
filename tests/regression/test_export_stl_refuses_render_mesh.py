"""``export_stl`` never ships a mesh that its own mesher called a render.

Found by the certified-tier cost audit (2026-07-28). A K7 boolean returns a
``TrimmedShell``; ``tessellate`` meshes it with
``forgekernel.tess.trimmed_shell_mesh``, whose docstring is explicit — *"NOT
watertight by design (the honest K7 caveat rendered visible); a render
artifact, never a measure"* — and which reports the uncertainty band as
``gaps`` quads and stamps ``provenance: "render"``.

``export_stl`` read ``mesh["triangles"]`` and wrote them out. Measured on the
pillow ∩ box cap: **992 facets, edge-use histogram {1: 144, 2: 1416}** — 144
boundary edges — under the header ``solid forge`` with no gap, provenance or
uncertainty marker anywhere in the file. Every sibling consumer is honest
about a certified result (``mass_props``/``validate``/``tessellate`` carry the
bracket; ``bbox``/``measure``/``export_step`` and the whole drawing path
refuse). STL was the one path that silently dropped it — and it is the path a
manufacturer consumes.

Root cause: the mesh dict's ``provenance`` and ``gaps`` channels existed and
nothing read them. Violated invariant: a geometry artifact that leaves the
seam is either correct or a refusal, never a plausible-looking wrong file
(CLAUDE.md rule 7; ADR-0019's "the refusal is the answer"). The comment above
``export_stl`` already records this exact failure mode being fixed once for
deflection — it was not fixed for gaps.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md); this needs
# real geometry.
pytest.importorskip("forgekernel")

from forgekernel.bsolid import PatchSolid, box_patches
from forgekernel.nurbs import bezier_surface

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

# the stage-1 dome closed into the pillow, cut by a box — the K7 fixture
DOME = bezier_surface([[(0, 0, 0), (0, 2, 0), (0, 4, 0)],
                       [(2, 0, 0), (2, 2, 6), (2, 4, 0)],
                       [(4, 0, 0), (4, 2, 0), (4, 4, 0)]])
BOT = bezier_surface([[(0, 0, 0), (4, 0, 0)], [(0, 4, 0), (4, 4, 0)]])
PILLOW = PatchSolid([DOME, BOT])
BOX = PatchSolid(box_patches(4, 4, 2, origin=(0, 0, 1)))


def _cap():
    return RefKernel().boolean("intersect", PILLOW, BOX)


def test_certified_shell_stl_refuses_instead_of_shipping_gaps(tmp_path):
    """The exact file the audit measured: 144 boundary edges, no marker."""
    k = RefKernel()
    shell = _cap()
    out = tmp_path / "cap.stl"

    with pytest.raises(KernelError) as exc:
        k.export_stl(shell, str(out))

    err = exc.value
    assert "export_stl" in str(err)
    # the refusal must carry the numbers, not just say no (ADR-0019 / #114)
    assert err.measured is not None
    assert err.measured.get("gap_quads") == 152
    assert err.measured.get("open_edges") == 144
    assert err.predicate == "render_mesh_not_watertight"
    assert err.remedy  # names what to do instead

    # and NOTHING is written — a half-file on disk is the same lie
    assert not out.exists()


def test_the_mesh_itself_still_renders(tmp_path):
    """The refusal is scoped to EXPORT. The viewer path is untouched —
    an honest picture of a freeform boolean is the whole point of the
    gap quads, and this must not take it away."""
    mesh = RefKernel().tessellate(_cap())
    assert mesh["provenance"] == "render"
    assert len(mesh["gaps"]) == 152
    assert len(mesh["triangles"]) == 992


def test_a_watertight_solid_still_exports(tmp_path):
    """Control: the guard must not fire on an ordinary solid, or it would
    close the STL path for everyone."""
    k = RefKernel()
    out = tmp_path / "box.stl"
    k.export_stl(k.box(10, 10, 10), str(out))

    text = out.read_text()
    assert text.startswith("solid forge")
    assert text.rstrip().endswith("endsolid forge")
    # a box is 12 triangles; every edge used exactly twice
    assert text.count("facet normal") == 12
