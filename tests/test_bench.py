"""ADR-0018 W0: the kernel benchmark harness — corpus integrity and
scorecard comparison logic (kernel-free; the OCCT runs live in bench/)."""

from __future__ import annotations

from gitcad.bench.corpus import CORPUS
from gitcad.bench.scorecard import compare


def test_corpus_entries_build_documents_and_are_unique() -> None:
    names = [n for n, _, _ in CORPUS]
    assert len(names) == len(set(names))
    assert sum(1 for _, cls, _ in CORPUS if "torture" in cls) >= 4
    for name, _classes, build in CORPUS:
        doc = build()
        assert len(doc) > 0, name
        assert doc.dumps() == build().dumps(), f"{name} not deterministic"


def test_compare_flags_disagreements() -> None:
    a = {"backend": "occt", "models": {"m": {"ok": True, "volume": 100.0,
                                             "faces": 6}}}
    b = {"backend": "ref", "models": {"m": {"ok": True, "volume": 100.1,
                                            "faces": 7}}}
    c = compare(a, b)
    assert any("volume" in d for d in c["disagreements"])
    assert c["models"]["m"]["faces_diff"] == (6, 7)
    b["models"]["m"]["volume"] = 100.0 + 1e-8
    b["models"]["m"]["faces"] = 6
    assert compare(a, b)["disagreements"] == []
