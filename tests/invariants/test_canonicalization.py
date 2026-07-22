"""INVARIANTS: the canonicalization policy (ADR-0004, hardened 2026-07-22).

Each test here pins a hole that was VERIFIED live in the early review:
NaN serialization, -0.0 identity splits, int-vs-float hash divergence,
ordinal twin ids, and silent duplicate-id collapse. These are the properties
"semantically equal ⇒ byte-identical" actually requires.
"""

from __future__ import annotations

import pytest

from gitcad.canonical import canonical_json, canonicalize
from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.identity import IdentityService

pytestmark = pytest.mark.invariant


# -- the number policy --------------------------------------------------------

def test_non_finite_numbers_are_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(GitcadError):
            canonical_json({"dx": bad})


def test_negative_zero_is_normalized() -> None:
    assert canonical_json({"x": -0.0}) == canonical_json({"x": 0.0})


def test_int_and_float_serialize_identically() -> None:
    assert canonical_json({"dx": 1}) == canonical_json({"dx": 1.0})


def test_bools_are_not_coerced_to_floats() -> None:
    assert canonicalize({"flag": True}) == {"flag": True}


def test_document_hash_ignores_int_float_distinction() -> None:
    a, b = Document(), Document()
    a.add(Feature(op="box", params={"dx": 10, "dy": 20, "dz": 5}))
    b.add(Feature(op="box", params={"dx": 10.0, "dy": 20.0, "dz": 5.0}))
    assert a.content_hash() == b.content_hash()
    assert a.features[0].id == b.features[0].id


# -- identity: value-based ids, order-independence ----------------------------

def test_different_constructions_never_share_an_id_regardless_of_order() -> None:
    """The verified P0 bug: box(1) after box(9) must NOT become box(1)_1."""
    a = Document()
    small_alone = a.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))

    b = Document()
    b.add(Feature(op="box", params={"dx": 9, "dy": 9, "dz": 9}))
    small_after = b.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))

    assert small_alone == small_after  # same construction -> same id, any order


def test_identity_noise_across_zero_does_not_split() -> None:
    svc = IdentityService()
    id_a = svc.assign({"area": 1.0, "centroid": [1e-9, 0.0, 0.0]}, ("f", "face"))
    id_b = svc.assign({"area": 1.0, "centroid": [-1e-9, 0.0, 0.0]}, ("f", "face"))
    assert id_a == id_b


# -- duplicate ids: the git-merge failure mode --------------------------------

def test_loads_rejects_duplicate_feature_ids() -> None:
    d = Document()
    d.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
    text = d.dumps()
    # Simulate a bad merge: the same feature block twice.
    corrupted = text.replace(
        '"features": [', '"features": [' + text.split('"features": [')[1].rsplit("]", 1)[0] + ",", 1)
    with pytest.raises(GitcadError):
        Document.loads(corrupted)


# -- identity registry persistence (ADR-0003) ---------------------------------

def test_identity_registry_roundtrips_and_resolves() -> None:
    svc = IdentityService()
    eid = svc.assign({"curve": "line", "length": 8.0}, ("f_1", "edge"))
    restored = IdentityService.loads(svc.dumps())
    match = restored.resolve(eid, [{"curve": "line", "length": 8.0},
                                   {"curve": "circle", "length": 3.0}])
    assert match == {"curve": "line", "length": 8.0}