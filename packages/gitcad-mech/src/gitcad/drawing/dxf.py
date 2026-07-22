"""Minimal DXF R12 writer — profiles and polylines for laser/waterjet/plasma.

DXF R12 is the lingua franca every cutting shop and CAM package ingests.
Zero dependencies, deterministic output. Lines and arcs only — exactly what a
cut path is.
"""

from __future__ import annotations

import math

from gitcad.sketch import Profile


def _entity_lines(profile: Profile) -> list[str]:
    out: list[str] = []
    prev = tuple(profile.start)
    for seg in profile.segments:
        to = tuple(seg["to"])
        if seg["kind"] == "line":
            out += ["0", "LINE", "8", "CUT",
                    "10", f"{prev[0]:.6f}", "20", f"{prev[1]:.6f}",
                    "11", f"{to[0]:.6f}", "21", f"{to[1]:.6f}"]
        else:  # three-point arc -> center/radius/angles
            cx, cy, r, a1, a2, ccw = _arc_params(prev, tuple(seg["via"]), to)
            if not ccw:
                a1, a2 = a2, a1   # DXF arcs are always CCW start->end
            out += ["0", "ARC", "8", "CUT",
                    "10", f"{cx:.6f}", "20", f"{cy:.6f}", "40", f"{r:.6f}",
                    "50", f"{math.degrees(a1):.6f}", "51", f"{math.degrees(a2):.6f}"]
        prev = to
    return out


def _arc_params(p1, via, p2):
    """Circle through three points -> (cx, cy, r, angle1, angle2, is_ccw)."""
    ax, ay = p1
    bx, by = via
    cx_, cy_ = p2
    d = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
    if abs(d) < 1e-12:
        raise ValueError("arc points are collinear")
    ux = ((ax**2 + ay**2) * (by - cy_) + (bx**2 + by**2) * (cy_ - ay)
          + (cx_**2 + cy_**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx_ - bx) + (bx**2 + by**2) * (ax - cx_)
          + (cx_**2 + cy_**2) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a1 = math.atan2(ay - uy, ax - ux)
    a2 = math.atan2(cy_ - uy, cx_ - ux)
    cross = (bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax)
    return ux, uy, r, a1, a2, cross > 0


def profile_to_dxf(profile: Profile) -> str:
    """One closed profile as a DXF R12 document (layer CUT)."""
    profile.validate()
    lines = ["0", "SECTION", "2", "HEADER",
             "9", "$ACADVER", "1", "AC1009",
             "0", "ENDSEC",
             "0", "SECTION", "2", "ENTITIES"]
    lines += _entity_lines(profile)
    lines += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(lines) + "\n"
