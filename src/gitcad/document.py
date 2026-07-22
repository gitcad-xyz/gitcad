"""The document model — a feature tree that is *text first*.

Source of truth is text (ADR-0004). A model is a linear list of features, each
an intent-level operation with named inputs referring to earlier features by
stable id. The canonical text form is deterministic JSON so it diffs cleanly in
git and hashes identically across machines.

Geometry is never stored here. Building a document against a :class:`Kernel`
produces shapes on demand; those are *build artifacts*, not source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from gitcad.errors import GitcadError
from gitcad.identity import IdentityService
from gitcad.seams import Kernel, Shape


@dataclass
class Feature:
    """One intent-level operation in the tree.

    ``id`` is stable and content-independent of ordering: it is derived from the
    operation and its inputs, so inserting a feature earlier does not renumber
    the ones after it (contrast ordinal indexing — the naming bug).
    """

    op: str
    params: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    id: str = ""  # assigned by Document.add if empty

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "op": self.op, "params": self.params, "inputs": self.inputs}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Feature":
        return cls(op=d["op"], params=dict(d.get("params", {})), inputs=list(d.get("inputs", [])), id=d.get("id", ""))


class Document:
    """An ordered feature tree with canonical text (de)serialization.

    Implements the :class:`gitcad.seams.DocumentModel` protocol structurally.
    """

    SCHEMA = "gitcad/document@1"

    def __init__(self) -> None:
        self._features: list[Feature] = []
        self._by_id: dict[str, Feature] = {}

    # -- construction ---------------------------------------------------------

    def add(self, feature: Feature) -> str:
        """Append a feature, minting a stable id from its op + inputs.

        The id is a hash of (op, params-shape, input-ids), NOT a running index —
        so two documents that build the same thing get the same ids, and edits
        elsewhere don't perturb it.
        """
        for ref in feature.inputs:
            if ref not in self._by_id:
                raise GitcadError(f"feature input {ref!r} does not exist yet (forward reference)")
        if not feature.id:
            feature.id = self._mint_id(feature)
        if feature.id in self._by_id:
            raise GitcadError(f"duplicate feature id {feature.id!r}")
        self._features.append(feature)
        self._by_id[feature.id] = feature
        return feature.id

    def _mint_id(self, feature: Feature) -> str:
        import hashlib

        # Params keys (not values) + inputs: identity is structural. Occurrence
        # disambiguation keeps two structurally identical siblings distinct.
        basis = {
            "op": feature.op,
            "param_keys": sorted(feature.params),
            "inputs": list(feature.inputs),
        }
        raw = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        base = "f_" + hashlib.blake2b(raw.encode(), digest_size=8).hexdigest()
        # Disambiguate structural twins deterministically by occurrence order.
        if base not in self._by_id:
            return base
        n = 1
        while f"{base}_{n}" in self._by_id:
            n += 1
        return f"{base}_{n}"

    @property
    def features(self) -> list[Feature]:
        return list(self._features)

    def __len__(self) -> int:
        return len(self._features)

    # -- text form (the git-diffable source) ----------------------------------

    def dumps(self) -> str:
        """Canonical, deterministic text. Two documents that are semantically
        equal serialize byte-identically — a hard requirement for clean diffs
        and for content hashing."""
        doc = {"schema": self.SCHEMA, "features": [f.to_dict() for f in self._features]}
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Document":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported document schema {doc.get('schema')!r}")
        out = cls()
        for fd in doc["features"]:
            f = Feature.from_dict(fd)
            # Preserve stored ids verbatim on load (round-trip fidelity).
            if not f.id:
                raise GitcadError("stored feature is missing its id")
            for ref in f.inputs:
                if ref not in out._by_id:
                    raise GitcadError(f"feature {f.id} references unknown input {ref}")
            out._features.append(f)
            out._by_id[f.id] = f
        return out

    def content_hash(self) -> str:
        import hashlib

        return hashlib.blake2b(self.dumps().encode(), digest_size=16).hexdigest()

    # -- build (produces artifacts, not source) -------------------------------

    def build(self, kernel: Kernel, identity: IdentityService | None = None) -> dict[str, Shape]:
        """Evaluate the tree against a kernel. Returns {feature_id: shape}.

        The mapping between kernel-produced entities and stable ids is what the
        drawing engine and downstream references rely on; ``identity`` is
        threaded through so entity ids are assigned during the build.
        """
        identity = identity or IdentityService()
        shapes: dict[str, Shape] = {}
        for f in self._features:
            ins = [shapes[i] for i in f.inputs]
            shapes[f.id] = _dispatch(kernel, f, ins)
        return shapes


def _dispatch(kernel: Kernel, f: Feature, ins: list[Shape]) -> Shape:
    """Map an intent op to a kernel call. Central place to add operations;
    unknown ops fail loud so an agent gets an actionable error, not silence."""
    p = f.params
    if f.op == "box":
        return kernel.box(p["dx"], p["dy"], p["dz"])
    if f.op == "cylinder":
        return kernel.cylinder(p["radius"], p["height"])
    if f.op == "sphere":
        return kernel.sphere(p["radius"])
    if f.op == "cone":
        return kernel.cone(p["r1"], p["r2"], p["height"])
    if f.op == "move":
        return kernel.transform(
            ins[0],
            translate=tuple(p.get("translate", (0, 0, 0))),
            rotate_axis=tuple(p.get("rotate_axis", (0, 0, 1))),
            rotate_deg=p.get("rotate_deg", 0.0),
        )
    if f.op == "boolean":
        return kernel.boolean(p["kind"], ins[0], ins[1])
    if f.op == "fillet":
        return kernel.fillet(ins[0], p.get("edges", []), p["radius"])
    raise GitcadError(f"unknown operation {f.op!r} (feature {f.id})")
