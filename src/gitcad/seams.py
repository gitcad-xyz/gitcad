"""The six seams — the only load-bearing interfaces in gitcad.

Rule (see ADR-0002): everything swappable lives behind one of these Protocols.
Agents work *inside* a seam, never across one. A "major architecture change"
should mean writing a new backend for one seam, not a rewrite. Keeping the seam
count small and the interfaces narrow is what preserves that property, so adding
a seam or widening one is a human-sign-off change (see ``CODEOWNERS``).

These are :class:`typing.Protocol` classes: backends satisfy them structurally,
so a backend package need not import gitcad-core to implement one.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from gitcad.errors import ValidationReport

# A Shape is an opaque, backend-owned handle to geometry. Core code never
# inspects its internals — it only passes it back to the same Kernel. This is
# what lets OCCT, a mesh kernel, or a future Rust kernel all satisfy `Kernel`.
Shape = Any


@runtime_checkable
class Kernel(Protocol):
    """Geometry backend. The one seam that talks b-rep math.

    Intent-level, not control-point level: callers express *what must be true*
    (through these points, tangent to that face, curvature-continuous) and the
    kernel solves the geometry. See ADR-0002 for why the API is intent-based.
    """

    name: str
    """Backend identity for fingerprints, e.g. ``"occt-7.8.1"`` or ``"null"``."""

    def box(self, dx: float, dy: float, dz: float) -> Shape: ...

    def cylinder(self, radius: float, height: float) -> Shape: ...

    def sphere(self, radius: float) -> Shape: ...

    def cone(self, r1: float, r2: float, height: float) -> Shape: ...

    def boolean(self, op: str, a: Shape, b: Shape) -> Shape:
        """``op`` in {"union", "cut", "intersect"}."""
        ...

    def fillet(self, shape: Shape, edges: list[int] | None, radius: float) -> Shape:
        """Fillet by enumeration index into ``entities(shape, "edge")`` order
        (``None`` = all edges). Index resolution from stable entity ids happens
        one level up, in the document build (ADR-0003) — the kernel never sees
        identity, only concrete indices valid for this exact shape."""
        ...

    def entities(self, shape: Shape, kind: str) -> list[dict[str, Any]]:
        """Enumerate topological entities (``kind`` in {"face","edge","vertex"})
        with a stable, order-independent semantic descriptor each. This is the
        raw material the :class:`IdentityService` turns into durable IDs."""
        ...

    def transform(self, shape: Shape, *, translate: tuple[float, float, float] = (0, 0, 0),
                  rotate_axis: tuple[float, float, float] = (0, 0, 1), rotate_deg: float = 0.0) -> Shape:
        """Rigid placement: rotate about an axis through the origin, then
        translate. The primitive every positioned feature builds on."""
        ...

    def validate(self, shape: Shape) -> ValidationReport:
        """Machine-readable geometric checks (watertight, self-intersection,
        continuity). The core of the agent verification loop."""
        ...

    def measure(self, shape: Shape) -> dict[str, float]:
        """Mass properties: volume, area, centroid — deterministic oracle used
        by golden tests and by geometric-diff in PRs."""
        ...

    def bbox(self, shape: Shape) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Axis-aligned bounding box ((minx,miny,minz),(maxx,maxy,maxz)) —
        the source of a derived part envelope (ADR-0008)."""
        ...

    def export_step(self, shape: Shape, path: str) -> None:
        """Write ISO 10303-21 STEP — the mechanical interchange deliverable."""
        ...

    def export_stl(self, shape: Shape, path: str, *, deflection: float = 0.1) -> None:
        """Tessellate and write STL for 3D printing."""
        ...

    def import_step(self, path: str) -> Shape:
        """Read STEP — the onboarding path for existing mechanical work."""
        ...

    def import_brep(self, path: str) -> Shape:
        """Read OCCT-native .brep (what .FCStd embeds per object)."""
        ...

    def export_brep(self, shape: Shape, path: str) -> None:
        """Write OCCT-native .brep — the content-addressed import artifact."""
        ...

    def compound(self, shapes: list[Shape]) -> Shape:
        """Combine shapes into one compound (multi-body import container)."""
        ...

    def hlr_project(self, shape: Shape, direction: tuple[float, float, float],
                    xdir: tuple[float, float, float], *,
                    deflection: float = 0.05) -> dict[str, list[list[tuple[float, float]]]]:
        """Hidden-line-removal projection to 2D polylines (visible/hidden) —
        the geometry backend of the DrawingEngine (ADR-0002)."""
        ...


@runtime_checkable
class IdentityService(Protocol):
    """Assigns stable IDs to topological entities (the topological-naming fix).

    An ID must survive upstream edits, reordering, and rebuilds. Identity is
    derived from *construction lineage + geometric fingerprint*, never from an
    ordinal index. See ADR-0003 — this is the decision that makes git workflows
    (merge, rebase) survivable for CAD.
    """

    def assign(self, descriptor: dict[str, Any], lineage: tuple[str, ...]) -> str: ...

    def resolve(self, entity_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Re-bind a stored ID to the best-matching current entity after a
        rebuild, or ``None`` if it genuinely no longer exists."""
        ...


@runtime_checkable
class DocumentModel(Protocol):
    """The feature tree and its canonical text (de)serialization.

    Source of truth is text (ADR-0004): this seam owns the mapping between the
    editable, git-diffable text form and the in-memory feature graph.
    """

    def dumps(self) -> str: ...

    @classmethod
    def loads(cls, text: str) -> "DocumentModel": ...

    def content_hash(self) -> str: ...


@runtime_checkable
class Renderer(Protocol):
    """Headless tessellation → images / glTF. The agent's eyes (stub for now)."""

    def render(self, shape: Shape, *, views: list[str], overlay: str | None = None) -> dict[str, bytes]: ...

    def to_gltf(self, shape: Shape) -> bytes: ...


@runtime_checkable
class DrawingEngine(Protocol):
    """3D → 2D drafting: HLR projection, associative dimensions, GD&T, sheets.

    The mechanical-engineering deliverable. Projection is delegated to the
    Kernel's HLR; this seam owns the 2D document model on top. Stub for now.
    """

    def project(self, shape: Shape, direction: str) -> dict[str, Any]:
        """Return 2D edges tagged visible/hidden for one orthographic view."""
        ...

    def export(self, sheet: dict[str, Any], fmt: str) -> bytes:
        """``fmt`` in {"svg", "pdf", "dxf"}."""
        ...


@runtime_checkable
class Storage(Protocol):
    """Git-backed store: text models are source, geometry is a build artifact.

    ADR-0004. Models are committed as text; ``.brep``/STEP/PDF are generated,
    content-addressed artifacts — never source. Stub for now.
    """

    def read_model(self, ref: str, path: str) -> str: ...

    def write_model(self, path: str, text: str, message: str) -> str:
        """Commit a model revision; return the commit id."""
        ...

    def put_artifact(self, data: bytes) -> str:
        """Store a build artifact content-addressed; return its digest."""
        ...
