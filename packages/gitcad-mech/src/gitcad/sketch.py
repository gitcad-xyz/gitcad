"""2D sketch profiles — the source geometry of extrude/revolve (feature-map A2).

A profile is an ordered list of segments (lines and arcs) forming one closed
loop, defined in the XY plane of its own local frame. Profiles are pure data
(canonical text like everything else); the kernel turns them into wires/faces
at build time. v1 has no constraint solver — coordinates are explicit, which
is exactly what agents author well; the constraint layer (ADR-0002's intent
API) arrives on top of this representation, not instead of it.

Segment forms:
    {"kind": "line", "to": [x, y]}
    {"kind": "arc",  "to": [x, y], "via": [mx, my]}   # three-point arc

The loop starts at ``start`` and each segment continues from the previous
endpoint; the final segment must return to ``start`` (validated).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gitcad.errors import GitcadError

_CLOSE_TOL = 1e-9


@dataclass
class Profile:
    start: tuple[float, float]
    segments: list[dict] = field(default_factory=list)

    def line_to(self, x: float, y: float) -> "Profile":
        self.segments.append({"kind": "line", "to": [x, y]})
        return self

    def arc_to(self, x: float, y: float, *, via: tuple[float, float]) -> "Profile":
        self.segments.append({"kind": "arc", "to": [x, y], "via": [via[0], via[1]]})
        return self

    def spline_to(self, x: float, y: float, *, ctrl: list) -> "Profile":
        """A polynomial-Bézier segment to (x, y) with intermediate control
        points ``ctrl`` (one → quadratic, two → cubic, …). Its enclosed area
        is exact in ℚ (Green's theorem), so an extrude of it is exact."""
        self.segments.append({"kind": "spline", "to": [x, y],
                              "ctrl": [list(c) for c in ctrl]})
        return self

    def close(self) -> "Profile":
        """Close the loop back to ``start`` with a line (if not already there)."""
        if self.segments and self._end() != tuple(self.start):
            self.line_to(*self.start)
        return self

    def _end(self) -> tuple[float, float]:
        if not self.segments:
            return tuple(self.start)
        return tuple(self.segments[-1]["to"])

    def validate(self) -> None:
        if len(self.segments) < 2:
            raise GitcadError("profile needs at least 2 segments")
        prev = tuple(self.start)
        for i, seg in enumerate(self.segments):
            if seg["kind"] not in ("line", "arc", "spline"):
                raise GitcadError(f"segment {i}: unknown kind {seg['kind']!r}")
            if seg["kind"] == "spline" and "ctrl" not in seg:
                raise GitcadError(f"segment {i}: spline needs 'ctrl' points")
            to = tuple(seg["to"])
            if to == prev and seg["kind"] == "line":
                raise GitcadError(f"segment {i}: zero-length line")
            prev = to
        if math.dist(prev, self.start) > _CLOSE_TOL:
            raise GitcadError(
                f"profile is not closed: ends at {prev}, started at {tuple(self.start)} "
                "(call .close() or end at the start point)"
            )

    def to_params(self) -> dict:
        """The document-param form of this profile (canonical-text friendly)."""
        self.validate()
        return {"start": list(self.start), "segments": self.segments}

    @classmethod
    def from_params(cls, p: dict) -> "Profile":
        prof = cls(start=tuple(p["start"]), segments=[dict(s) for s in p["segments"]])
        prof.validate()
        return prof

    # -- conveniences ---------------------------------------------------------

    @classmethod
    def rectangle(cls, w: float, h: float) -> "Profile":
        return cls((0, 0)).line_to(w, 0).line_to(w, h).line_to(0, h).close()

    @classmethod
    def l_shape(cls, w: float, h: float, thickness: float) -> "Profile":
        t = thickness
        return (cls((0, 0)).line_to(w, 0).line_to(w, t).line_to(t, t)
                .line_to(t, h).line_to(0, h).close())
