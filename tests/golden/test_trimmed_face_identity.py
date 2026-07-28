"""A certified shell's faces are individually nameable (#87).

Every face of a ``TrimmedShell`` used to report the same geometry-free
descriptor — ``{"surface": "trimmed-bspline", "sense": 1, "loops": 1}`` — so
``IdentityService.assign`` minted ONE id for all of them and no selector could
name a single face. ADR-0003 requires ids to be *collision-resistant* and
derived from *lineage + a geometric fingerprint*; that descriptor had no
fingerprint.

The fingerprint is built from the exact control net and the exact trim-loop
(u, v) coordinates — Fractions, hashed as (numerator, denominator) pairs. No
float enters it, so it is stable across processes and machines without any
tolerance (ADR-0019). The certified area is deliberately NOT part of it: an
area is a *bracket*, and rounding a bracket endpoint to hash it would put a
float back in charge of identity.

Signed off by the repo owner 2026-07-28 as an identity-semantics change
(CLAUDE.md rule 1).
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from forgekernel.bsolid import PatchSolid, box_patches
from forgekernel.nurbs import bezier_surface

from gitcad.identity import IdentityService
from gitcad.kernel.ref import RefKernel

DOME = bezier_surface([[(0, 0, 0), (0, 2, 0), (0, 4, 0)],
                       [(2, 0, 0), (2, 2, 6), (2, 4, 0)],
                       [(4, 0, 0), (4, 2, 0), (4, 4, 0)]])
BOT = bezier_surface([[(0, 0, 0), (4, 0, 0)], [(0, 4, 0), (4, 4, 0)]])


def _cap():
    """pillow ∩ box — the K7 fixture, two faces off one boolean."""
    k = RefKernel()
    return k, k.boolean("intersect", PatchSolid([DOME, BOT]),
                        PatchSolid(box_patches(4, 4, 2, origin=(0, 0, 1))))


def _ids(k, shell):
    ident = IdentityService()
    return [ident.assign(d, lineage=("f1", "face"))
            for d in k.entities(shell, "face")]


def test_each_face_of_a_certified_shell_gets_its_own_id():
    k, shell = _cap()
    ids = _ids(k, shell)
    assert len(ids) == len(shell.faces) == 2
    assert len(set(ids)) == 2, "faces collapsed to one id again"


def test_the_descriptor_actually_carries_geometry():
    k, shell = _cap()
    for d in k.entities(shell, "face"):
        assert d["surface"] == "trimmed-bspline"
        assert isinstance(d["fingerprint"], str) and len(d["fingerprint"]) == 32
        assert d["trim_vertices"] > 0
        assert len(d["net"]) == 2


def test_ids_are_stable_across_a_rebuild():
    """Identity is worthless if it is per-process. The trim (u, v) live in a
    dict keyed by ``id(face)``, so a naive hash would leak object addresses —
    this is the test that catches that."""
    k1, s1 = _cap()
    k2, s2 = _cap()
    assert _ids(k1, s1) == _ids(k2, s2)


def test_the_fingerprint_contains_no_float():
    """ADR-0019: a float may never decide identity. Rebuilding the same shell
    must give byte-identical fingerprints — a float-derived hash would too,
    so the real check is that the descriptor exposes no float field at all."""
    k, shell = _cap()
    for d in k.entities(shell, "face"):
        for key, value in d.items():
            assert not isinstance(value, float), f"{key} is a float"
            if isinstance(value, list):
                assert not any(isinstance(x, float) for x in value), key


def test_two_fragments_of_the_same_surface_stay_distinct():
    """The case a control-net hash alone would collide: a boolean can leave
    two faces sharing one surface, differing only in their trim loops. The
    (u, v) of the loops are in the hash precisely for this."""
    k, shell = _cap()
    descriptors = k.entities(shell, "face")
    by_net: dict[tuple, list[str]] = {}
    for d in descriptors:
        by_net.setdefault(tuple(d["net"]), []).append(d["fingerprint"])
    for net, prints in by_net.items():
        assert len(set(prints)) == len(prints), \
            f"faces sharing net {net} share a fingerprint"


def test_selectors_resolve_to_one_face_each():
    """End to end: the ambiguity refusal added with #87's sibling fix must no
    longer fire on a certified shell, because the ids are now distinct."""
    from gitcad.document import BuildResult, _resolve_entity_indices

    k, shell = _cap()
    ident = IdentityService()
    indexed = [(ident.assign(d, lineage=("f1", "face")), d)
               for d in k.entities(shell, "face")]
    res = BuildResult(entities={"f1": {"face": indexed}}, identity=ident)

    ids = [eid for eid, _ in indexed]
    assert _resolve_entity_indices(ids, "f1", res, kind="face") == [0, 1]
