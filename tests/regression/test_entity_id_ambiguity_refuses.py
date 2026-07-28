"""One entity id must never resolve to two different entities.

Found by the certified-tier audit (2026-07-28). ``_resolve_entity_indices``
has two branches and they disagreed whenever an id was ambiguous:

* the fast path builds ``{eid: i for i, (eid, _) in enumerate(indexed)}`` —
  a dict, so a repeated key keeps the **last** index;
* the re-bind path ends in ``descriptors.index(resolved)`` — which returns
  the **first** match.

Same document, same id, different face depending on which branch ran. A
selector that silently points at a different face than the one the author
picked is the topological-naming failure ADR-0003 exists to prevent, and it
is silent-wrong rather than a refusal.

Measured blast radius before fixing (probe over the corpus: box, cylinder,
sphere, cone, drilled, chamfered, filleted, shelled, a plate with two
identical holes, a plate with four congruent corner holes — faces and edges,
20 shape/kind combinations): **zero ambiguous ids**. Ordinary descriptors
carry enough geometry that even four congruent bores stay distinct. The one
producer of geometry-free descriptors is a certified ``TrimmedShell``, whose
face descriptor is ``{"surface": "trimmed-bspline", "sense": 1, "loops": 1}``
— identical for every face, so N faces collapse to one id.

So this test pins the CONTRACT rather than a representation: whatever mints
the ids, an ambiguous reference is refused, never guessed. Enriching the
trimmed-shell descriptor so its faces are distinguishable is the separate,
larger fix — it changes identity semantics and wants human sign-off
(CLAUDE.md rule 1).
"""

from __future__ import annotations

import pytest

from gitcad.document import BuildResult, _resolve_entity_indices
from gitcad.errors import IdentityError
from gitcad.identity import IdentityService


def _result_with(descriptors: list[dict]) -> tuple[BuildResult, list[str]]:
    """Index `descriptors` under one feature exactly as a build would."""
    identity = IdentityService()
    indexed = [(identity.assign(d, lineage=("f1", "face")), d)
               for d in descriptors]
    res = BuildResult(entities={"f1": {"face": indexed}}, identity=identity)
    return res, [eid for eid, _ in indexed]


# a certified shell's faces: same descriptor, no geometry to tell them apart
GEOMETRY_FREE = {"surface": "trimmed-bspline", "sense": 1, "loops": 1}


def test_two_entities_sharing_one_id_refuses_instead_of_picking_one():
    res, ids = _result_with([dict(GEOMETRY_FREE), dict(GEOMETRY_FREE)])
    # the premise of the bug: both faces really do mint the same id
    assert ids[0] == ids[1]

    with pytest.raises(IdentityError) as exc:
        _resolve_entity_indices([ids[0]], "f1", res, kind="face")

    msg = str(exc.value)
    assert "ambiguous" in msg.lower()
    assert "2" in msg  # says how many entities claim it


def test_the_two_branches_no_longer_disagree():
    """The specific defect. Before: the fast path answered 1 (dict keeps
    last) and the re-bind path answered 0 (`.index` finds first). Neither
    branch may quietly win — both must refuse the same way."""
    res, ids = _result_with([dict(GEOMETRY_FREE), dict(GEOMETRY_FREE)])
    eid = ids[0]

    with pytest.raises(IdentityError):          # fast path: id is present
        _resolve_entity_indices([eid], "f1", res, kind="face")

    # force the re-bind path by making the stored id absent from the
    # current enumeration, while the descriptors stay ambiguous
    res.entities["f1"]["face"] = [("e_gone_1", dict(GEOMETRY_FREE)),
                                  ("e_gone_2", dict(GEOMETRY_FREE))]
    with pytest.raises(IdentityError):
        _resolve_entity_indices([eid], "f1", res, kind="face")


def test_distinct_descriptors_still_resolve_exactly():
    """Control — the ordinary case must be untouched. This is what the
    corpus probe found everywhere: descriptors that differ, ids that differ,
    indices that are exact."""
    res, ids = _result_with([
        {"surface": "plane", "normal": [0.0, 0.0, 1.0], "area": 400.0},
        {"surface": "plane", "normal": [0.0, 0.0, -1.0], "area": 400.0},
        {"surface": "cylinder", "radius": 3.0, "area": 120.0},
    ])
    assert len(set(ids)) == 3
    assert _resolve_entity_indices(ids, "f1", res, kind="face") == [0, 1, 2]
    assert _resolve_entity_indices([ids[2]], "f1", res, kind="face") == [2]


def test_a_missing_id_still_says_it_no_longer_exists():
    """The pre-existing refusal must not be swallowed by the new one —
    'gone' and 'ambiguous' are different answers."""
    res, _ = _result_with([{"surface": "plane", "normal": [0.0, 0.0, 1.0],
                            "area": 400.0}])
    with pytest.raises(IdentityError) as exc:
        _resolve_entity_indices(["e_never_existed"], "f1", res, kind="face")
    assert "no longer exists" in str(exc.value)
