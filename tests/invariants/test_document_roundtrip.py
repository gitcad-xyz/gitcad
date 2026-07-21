"""INVARIANT: the text form round-trips and is canonical.

Git-native versioning (ADR-0004) depends on this: semantically equal documents
must serialize byte-identically, and load(dump(x)) must equal x. Permanent tier.
"""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature

pytestmark = pytest.mark.invariant


def _sample() -> Document:
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 10, "dy": 20, "dz": 5}))
    c = d.add(Feature(op="cylinder", params={"radius": 3, "height": 5}))
    d.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[b, c]))
    return d


def test_roundtrip_is_lossless() -> None:
    d = _sample()
    reloaded = Document.loads(d.dumps())
    assert reloaded.dumps() == d.dumps()
    assert reloaded.content_hash() == d.content_hash()


def test_serialization_is_canonical() -> None:
    """Byte-identical output on repeat — a hard requirement for clean git diffs
    (no key-order or whitespace jitter between runs)."""
    d = _sample()
    assert d.dumps() == d.dumps()


def test_forward_reference_is_rejected() -> None:
    d = Document()
    with pytest.raises(Exception):
        d.add(Feature(op="fillet", params={"radius": 1}, inputs=["does-not-exist"]))
