"""The document model — a feature tree that is *text first*.

Source of truth is text (ADR-0004). A model is a linear list of features, each
an intent-level operation with named inputs referring to earlier features by
stable id. The canonical text form is deterministic (via
:mod:`gitcad.canonical`) so it diffs cleanly in git and hashes identically
across machines.

Geometry is never stored here. Building a document against a :class:`Kernel`
produces shapes on demand; those are *build artifacts*, not source. Building
also assigns stable entity ids (ADR-0003) so features can reference faces and
edges durably — see :meth:`Document.build`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError, IdentityError
from gitcad.identity import IdentityService
from gitcad.seams import Kernel, Shape


@dataclass
class Feature:
    """One intent-level operation in the tree.

    ``id`` is stable and order-independent: derived from the operation, its
    parameter *values*, and its input ids — so an unrelated insertion never
    renumbers a downstream feature (ADR-0003). Two *identical* constructions
    (structural twins) are disambiguated by occurrence order at add-time and
    keep their minted id verbatim in the text form thereafter.
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


@dataclass
class BuildResult:
    """Everything a build produces: shapes per feature, plus the stable entity
    ids assigned to each feature's topology (ADR-0003).

    ``entities[feature_id][kind]`` is an ordered list of ``(entity_id,
    descriptor)`` pairs; the list index is the kernel's enumeration index for
    the same shape, which is how selectors resolve back to concrete topology.
    """

    shapes: dict[str, Shape] = field(default_factory=dict)
    entities: dict[str, dict[str, list[tuple[str, dict[str, Any]]]]] = field(default_factory=dict)
    identity: IdentityService | None = None

    def final(self, doc: "Document") -> Shape:
        return self.shapes[doc.features[-1].id]


class Document:
    """An ordered feature tree with canonical text (de)serialization."""

    SCHEMA = "gitcad/document@1"

    def __init__(self) -> None:
        self._features: list[Feature] = []
        self._by_id: dict[str, Feature] = {}

    # -- construction ---------------------------------------------------------

    def add(self, feature: Feature) -> str:
        """Append a feature, minting a stable id from its full construction:
        op + canonical param values + input ids. Never a running index."""
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
        # Full construction identity: op + canonical param VALUES + inputs.
        # (Param values matter: box(1,1,1) after box(9,9,9) must not collide —
        # ids survive reordering, not revaluing. Reviewed 2026-07-22.)
        basis = canonical_json({
            "op": feature.op,
            "params": feature.params,
            "inputs": list(feature.inputs),
        })
        base = "f_" + hashlib.blake2b(basis.encode(), digest_size=8).hexdigest()
        # Exact structural twins (identical op+params+inputs) are disambiguated
        # by occurrence order; the suffix is persisted in text and never
        # re-derived, so it is stable for existing documents.
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
        doc = {"schema": self.SCHEMA, "features": [f.to_dict() for f in self._features]}
        return canonical_json(doc, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Document":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported document schema {doc.get('schema')!r}")
        out = cls()
        for fd in doc["features"]:
            f = Feature.from_dict(fd)
            if not f.id:
                raise GitcadError("stored feature is missing its id")
            if f.id in out._by_id:
                # The state a git merge of two branches can produce — refuse
                # loudly instead of silently collapsing (reviewed 2026-07-22).
                raise GitcadError(f"duplicate feature id in document: {f.id!r}")
            for ref in f.inputs:
                if ref not in out._by_id:
                    raise GitcadError(f"feature {f.id} references unknown input {ref}")
            out._features.append(f)
            out._by_id[f.id] = f
        return out

    def content_hash(self) -> str:
        return hashlib.blake2b(self.dumps().encode(), digest_size=16).hexdigest()

    # -- build (produces artifacts, not source) -------------------------------

    def build(self, kernel: Kernel, identity: IdentityService | None = None) -> BuildResult:
        """Evaluate the tree against a kernel.

        Assigns stable entity ids to every feature's faces/edges via
        ``identity`` (ADR-0003): id = hash(lineage + rounded geometric
        fingerprint). Entity-referencing params (e.g. fillet ``edges``) are
        resolved against these ids during the build. Persist the registry with
        ``result.identity.dumps()`` alongside the model so stored references
        resolve in future processes.
        """
        identity = identity or IdentityService()
        result = BuildResult(identity=identity)
        for f in self._features:
            ins = [result.shapes[i] for i in f.inputs]
            shape = _dispatch(kernel, f, ins, result)
            result.shapes[f.id] = shape
            result.entities[f.id] = _index_entities(kernel, shape, f.id, identity)
        return result


def _index_entities(kernel: Kernel, shape: Shape, feature_id: str,
                    identity: IdentityService) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    out: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for kind in ("face", "edge"):
        try:
            descriptors = kernel.entities(shape, kind)
        except NotImplementedError:
            descriptors = []
        out[kind] = [(identity.assign(d, lineage=(feature_id, kind)), d) for d in descriptors]
    return out


def _resolve_edge_indices(edge_ids: list[str], input_feature: str,
                          result: BuildResult) -> list[int]:
    """Map stored entity ids to the input shape's current edge enumeration
    indices — the moment ADR-0003 pays off: the reference survives upstream
    edits because identity re-binds by fingerprint, not position."""
    identity = result.identity
    assert identity is not None
    indexed = result.entities.get(input_feature, {}).get("edge", [])
    descriptors = [d for _, d in indexed]
    by_current_id = {eid: i for i, (eid, _) in enumerate(indexed)}
    indices: list[int] = []
    for eid in edge_ids:
        if eid in by_current_id:            # exact id still present
            indices.append(by_current_id[eid])
            continue
        resolved = identity.resolve(eid, descriptors)   # re-bind by fingerprint
        if resolved is None:
            raise IdentityError(
                f"edge {eid!r} no longer exists on feature {input_feature!r}",
                entity=eid,
            )
        indices.append(descriptors.index(resolved))
    return indices


def _dispatch(kernel: Kernel, f: Feature, ins: list[Shape], result: BuildResult) -> Shape:
    """Map an intent op to a kernel call. Unknown ops fail loud so an agent
    gets an actionable error, not silence."""
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
    if f.op == "import":
        # Imported geometry is the one case where a binary artifact IS source
        # (the user's existing work). The document pins its sha256 so a build
        # can never silently use a swapped or corrupted file (ADR-0004 spirit:
        # the text names exactly one artifact, verifiably).
        path, fmt = p["file"], p.get("format", "step")
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if p.get("sha256") and digest != p["sha256"]:
            raise GitcadError(
                f"import integrity failure: {path!r} hashes {digest[:12]}..., "
                f"document pins {p['sha256'][:12]}..."
            )
        if fmt == "step":
            return kernel.import_step(path)
        if fmt == "brep":
            return kernel.import_brep(path)
        raise GitcadError(f"unknown import format {fmt!r} (want step|brep)")
    if f.op == "boolean":
        return kernel.boolean(p["kind"], ins[0], ins[1])
    if f.op == "fillet":
        edge_ids = p.get("edges", [])
        indices = _resolve_edge_indices(edge_ids, f.inputs[0], result) if edge_ids else None
        return kernel.fillet(ins[0], indices, p["radius"])
    raise GitcadError(f"unknown operation {f.op!r} (feature {f.id})")
