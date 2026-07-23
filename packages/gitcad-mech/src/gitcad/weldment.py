"""Weldments — structural members along a 3D sketch, with a cut list.

A weldment is DECLARED as structure: a 3D sketch (named vertices + a set
of segments) plus a structural-member profile per segment. From that the
kernel produces the swept solid; but the manufacturing deliverable is the
**cut list** — grouped member lengths a fabricator cuts stock to — which
is pure geometry, kernel-free.

Structural-profile cross-sections are EXACT rationals (they are
polygon/annulus areas), so member mass is exact given a density. Member
lengths are Euclidean and generally irrational; Pythagorean segments are
exact, others are reported to μm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from gitcad.errors import GitcadError

F = Fraction


# -- structural profile library (exact rational cross-section area) ----------

@dataclass(frozen=True)
class StructuralProfile:
    name: str
    area: Fraction            # cross-section area (mm²), exact
    kind: str = "rect_tube"

    @staticmethod
    def rect_tube(w, h, t) -> "StructuralProfile":
        w, h, t = F(w), F(h), F(t)
        if 2 * t >= min(w, h):
            raise GitcadError("rect_tube wall too thick")
        return StructuralProfile(f"RT{w:g}x{h:g}x{t:g}",
                                 w * h - (w - 2 * t) * (h - 2 * t), "rect_tube")

    @staticmethod
    def l_angle(a, b, t) -> "StructuralProfile":
        a, b, t = F(a), F(b), F(t)
        return StructuralProfile(f"L{a:g}x{b:g}x{t:g}",
                                 a * t + (b - t) * t, "l_angle")

    @staticmethod
    def c_channel(w, h, t) -> "StructuralProfile":
        w, h, t = F(w), F(h), F(t)
        return StructuralProfile(f"C{w:g}x{h:g}x{t:g}",
                                 w * h - (w - t) * (h - 2 * t), "c_channel")

    @staticmethod
    def flat_bar(w, t) -> "StructuralProfile":
        return StructuralProfile(f"FB{F(w):g}x{F(t):g}", F(w) * F(t), "flat_bar")


@dataclass
class Sketch3D:
    """Named 3D vertices and the segments joining them (a wire frame)."""
    vertices: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    segments: list[tuple[str, str]] = field(default_factory=list)

    def vertex(self, name, x, y, z) -> "Sketch3D":
        self.vertices[name] = (x, y, z)
        return self

    def segment(self, a, b) -> "Sketch3D":
        if a not in self.vertices or b not in self.vertices:
            raise GitcadError(f"segment {a}-{b}: unknown vertex")
        self.segments.append((a, b))
        return self

    def length(self, a, b) -> float:
        va, vb = self.vertices[a], self.vertices[b]
        return math.dist(va, vb)


@dataclass
class Member:
    seg: tuple[str, str]
    profile: StructuralProfile


class Weldment:
    """A frame: structural members (one per segment) on a 3D sketch."""

    def __init__(self, sketch: Sketch3D, default_profile: StructuralProfile) -> None:
        self.sketch = sketch
        self.members = [Member(seg, default_profile) for seg in sketch.segments]

    def set_profile(self, a, b, profile: StructuralProfile) -> "Weldment":
        for m in self.members:
            if set(m.seg) == {a, b}:
                m.profile = profile
        return self

    def cut_list(self, *, round_mm: int = 3) -> list[dict[str, Any]]:
        """Grouped cut list: (profile, length) → quantity, longest-first.
        The fabricator's stock schedule."""
        groups: dict[tuple[str, float], int] = {}
        for m in self.members:
            L = round(self.sketch.length(*m.seg), round_mm)
            groups[(m.profile.name, L)] = groups.get((m.profile.name, L), 0) + 1
        rows = [{"profile": p, "length": L, "qty": n}
                for (p, L), n in groups.items()]
        rows.sort(key=lambda r: (r["profile"], -r["length"]))
        return rows

    def total_length(self) -> float:
        return sum(self.sketch.length(*m.seg) for m in self.members)

    def mass(self, density_kg_per_mm3: float) -> float:
        """Total mass — exact-area cross-sections × lengths × density."""
        return sum(float(m.profile.area) * self.sketch.length(*m.seg)
                   for m in self.members) * density_kg_per_mm3

    def stock_summary(self) -> dict[str, float]:
        """Total cut length per profile (stock ordering)."""
        out: dict[str, float] = {}
        for m in self.members:
            out[m.profile.name] = out.get(m.profile.name, 0.0) \
                + self.sketch.length(*m.seg)
        return {k: round(v, 3) for k, v in out.items()}
