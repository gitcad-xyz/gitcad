"""#10 — the capability headline is a PAIR, single-op · composed.

The single-op grid probes every seam operation against a fresh solid; it
cannot see whether the RESULT of an operation is still usable, which is
where real modelling sessions fail (a rotated lathe that can no longer be
a boolean operand or a STEP export). The composed grid probes exactly
those chains, and ``headline()`` refuses to let either number travel
without the other. Kernel-independent structure checks run on the null
backend; the honest numbers themselves are pinned by the kernel-marked
seam invariants.
"""

from __future__ import annotations

from gitcad.bench import capability as C
from gitcad.kernel import get_kernel


def _null():
    return get_kernel(require="null")


def test_composed_probe_covers_every_representation() -> None:
    r = C.probe_composed(_null())
    assert set(r["grid"]) == set(C.representations(_null()))


def test_composed_ops_are_chains_not_single_ops() -> None:
    single = set(C.operations(_null(), "."))
    composed = set(C.composed_operations(_null(), "."))
    assert composed, "composed grid must not be empty"
    assert not (composed & single), (
        "a composed column duplicating a single-op column would double-count "
        "it in the pair")


def test_headline_carries_both_numbers() -> None:
    r = C.probe(_null())
    rc = C.probe_composed(_null())
    h = C.headline(r, rc)
    assert h.startswith("single-op ")
    assert " · composed " in h
    assert C.summary(r) in h and C.summary(rc) in h


def test_composed_boundary_entries_all_name_real_cells() -> None:
    # a boundary entry for a cell that no longer exists would silently
    # reclassify nothing — the proof text must stay attached to a live cell
    shapes = set(C.representations(_null()))
    ops = set(C.composed_operations(_null(), "."))
    for sname, oname in C._EXACT_FIELD_BOUNDARY_COMPOSED:
        assert sname in shapes and oname in ops


def test_composed_boundary_is_the_minority_of_the_grid() -> None:
    # the permanent-wall list must never quietly absorb the gap list —
    # that would be gaming the number the issue was filed about
    n_cells = (len(C.representations(_null()))
               * len(C.composed_operations(_null(), ".")))
    assert len(C._EXACT_FIELD_BOUNDARY_COMPOSED) < n_cells * 0.10
