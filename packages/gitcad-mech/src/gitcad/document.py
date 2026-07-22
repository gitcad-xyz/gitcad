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
import math
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


def _resolve_entity_indices(entity_ids: list[str], input_feature: str,
                            result: BuildResult, kind: str = "edge") -> list[int]:
    """Map stored entity ids to the input shape's current enumeration indices
    — the moment ADR-0003 pays off: the reference survives upstream edits
    because identity re-binds by fingerprint, not position."""
    identity = result.identity
    assert identity is not None
    indexed = result.entities.get(input_feature, {}).get(kind, [])
    descriptors = [d for _, d in indexed]
    by_current_id = {eid: i for i, (eid, _) in enumerate(indexed)}
    indices: list[int] = []
    for eid in entity_ids:
        if eid in by_current_id:            # exact id still present
            indices.append(by_current_id[eid])
            continue
        resolved = identity.resolve(eid, descriptors)   # re-bind by fingerprint
        if resolved is None:
            raise IdentityError(
                f"{kind} {eid!r} no longer exists on feature {input_feature!r}",
                entity=eid,
            )
        indices.append(descriptors.index(resolved))
    return indices


# Ops that act on prior geometry MUST name it — a subtractive op with no
# inputs silently building a disconnected feature was a dogfood finding.
_REQUIRED_INPUTS = {"boolean": 2, "fillet": 1, "chamfer": 1, "shell": 1,
                    "move": 1, "hole": 1, "boss": 1, "mirror": 1,
                    "pattern_linear": 1, "pattern_circular": 1}

_AXIS_ROTATION = {"z": None, "y": ((1, 0, 0), -90.0), "x": ((0, 1, 0), 90.0)}


def _dispatch(kernel: Kernel, f: Feature, ins: list[Shape], result: BuildResult) -> Shape:
    """Map an intent op to a kernel call. Unknown ops fail loud so an agent
    gets an actionable error, not silence."""
    p = f.params
    need = _REQUIRED_INPUTS.get(f.op, 0)
    if len(ins) < need:
        raise GitcadError(
            f"op {f.op!r} requires inputs=[{need} feature id(s)] naming the "
            f"geometry it acts on — got {len(ins)} (feature {f.id})")
    if f.op == "box":
        return kernel.box(p["dx"], p["dy"], p["dz"])
    if f.op == "cylinder":
        shape = kernel.cylinder(p["radius"], p["height"])
        rot = _AXIS_ROTATION.get(p.get("axis", "z"), "bad")
        if rot == "bad":
            raise GitcadError(f"cylinder axis must be x|y|z, got {p.get('axis')!r}")
        if rot is not None:
            shape = kernel.transform(shape, rotate_axis=rot[0], rotate_deg=rot[1])
        return shape
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
    if f.op == "extrude":
        return kernel.extrude(p["profile"], p["height"])
    if f.op == "revolve":
        return kernel.revolve(p["profile"], p.get("angle_deg", 360.0))
    if f.op == "loft":
        # Sections: [{"profile": <sketch profile>, "z": height}, ...] bottom-up.
        sections = [(s["profile"], s["z"]) for s in p["sections"]]
        return kernel.loft(sections, ruled=bool(p.get("ruled", False)))
    if f.op == "sweep":
        return kernel.sweep(p["profile"], [tuple(pt) for pt in p["path"]])
    if f.op == "mirror":
        mirrored = kernel.mirror(ins[0], p["plane"])
        if p.get("fuse", False):
            return kernel.boolean("union", ins[0], mirrored)
        return mirrored
    if f.op == "boolean":
        return kernel.boolean(p["kind"], ins[0], ins[1])
    if f.op == "fillet":
        edge_ids = p.get("edges", [])
        indices = _resolve_entity_indices(edge_ids, f.inputs[0], result) if edge_ids else None
        return kernel.fillet(ins[0], indices, p["radius"])
    if f.op == "chamfer":
        edge_ids = p.get("edges", [])
        indices = _resolve_entity_indices(edge_ids, f.inputs[0], result) if edge_ids else None
        return kernel.chamfer(ins[0], indices, p["distance"])
    if f.op == "shell":
        face_indices = _resolve_entity_indices(p.get("faces", []), f.inputs[0], result, kind="face")
        return kernel.shell(ins[0], face_indices, p["thickness"])
    if f.op == "pattern_linear":
        # Composition, not a kernel primitive: union of translated copies.
        out = ins[0]
        step = p.get("step", [0.0, 0.0, 0.0])
        for i in range(1, int(p["count"])):
            copy = kernel.transform(ins[0], translate=(step[0] * i, step[1] * i, step[2] * i))
            out = kernel.boolean("union", out, copy)
        return out
    if f.op == "pattern_circular":
        out = ins[0]
        count = int(p["count"])
        for i in range(1, count):
            copy = kernel.transform(ins[0], rotate_axis=(0, 0, 1),
                                    rotate_deg=360.0 * i / count)
            out = kernel.boolean("union", out, copy)
        return out
    if f.op == "boss":
        # Mounting boss: cylinder unioned onto a body from base_z upward, with
        # an optional pilot hole from its top — the standoff the dogfood's
        # housing had ports for but no geometry under (friction finding).
        x, y, base_z = p["x"], p["y"], p["base_z"]
        height, dia = p["height"], p["diameter"]
        post = kernel.transform(kernel.cylinder(dia / 2, height),
                                translate=(x, y, base_z))
        out = kernel.boolean("union", ins[0], post)
        if p.get("pilot_diameter"):
            pilot_depth = p.get("pilot_depth", height)
            pilot = kernel.transform(
                kernel.cylinder(p["pilot_diameter"] / 2, pilot_depth),
                translate=(x, y, base_z + height - pilot_depth))
            out = kernel.boolean("cut", out, pilot)
        return out
    if f.op == "hole":
        # Drilled from top_z downward; optional counterbore. A composed cut —
        # the workhorse mech feature as one intent-level op.
        x, y, top_z = p["x"], p["y"], p["top_z"]
        depth, dia = p["depth"], p["diameter"]
        tool = kernel.transform(kernel.cylinder(dia / 2, depth),
                                translate=(x, y, top_z - depth))
        if p.get("cbore_diameter"):
            cb = kernel.transform(
                kernel.cylinder(p["cbore_diameter"] / 2, p["cbore_depth"]),
                translate=(x, y, top_z - p["cbore_depth"]))
            tool = kernel.boolean("union", tool, cb)
        if p.get("csink_diameter"):
            # Countersink: cone from hole diameter up to csink diameter at the
            # surface; included angle defaults to the 90-deg standard.
            angle = p.get("csink_angle_deg", 90.0)
            csink_depth = ((p["csink_diameter"] - dia) / 2
                           / math.tan(math.radians(angle / 2)))
            cs = kernel.transform(
                kernel.cone(dia / 2, p["csink_diameter"] / 2, csink_depth),
                translate=(x, y, top_z - csink_depth))
            tool = kernel.boolean("union", tool, cs)
        return kernel.boolean("cut", ins[0], tool)
    raise GitcadError(f"unknown operation {f.op!r} (feature {f.id})")
