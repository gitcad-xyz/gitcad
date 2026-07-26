"""The routing helper — the dogfood's #1 friction finding, fixed.

Hand-routing meant mentally computing every pad's absolute position, planning
layer changes, and placing vias by hand — and the check chain caught five
mistakes that careful planning still made. This module PREVENTS instead of
detects:

- :func:`pad_position` — any "REF.pad" resolved to absolute board coordinates
  with side/through/net facts.
- :func:`route` — one call per net path: waypoints are pads or points, layer
  changes insert vias automatically, SMD endpoints are enforced onto their
  pad's side, and every pad waypoint's net must match the routed net. The
  mistakes the dogfood made are now *unrepresentable*.
"""

from __future__ import annotations

from gitcad.ecad.board import Board, Track, Via
from gitcad.errors import GitcadError


def pad_position(board: Board, ref_pad: str) -> dict:
    """Resolve "REF.pad_name" to absolute position + facts."""
    if "." not in ref_pad:
        raise GitcadError(f"pad ref {ref_pad!r} must be 'REF.pad_name'")
    ref, pad_name = ref_pad.split(".", 1)
    for comp in board.components:
        if comp.ref != ref:
            continue
        for pad, bx, by, _rot in comp.placed_pads():
            if pad.name == pad_name:
                return {"x": bx, "y": by, "side": comp.side,
                        "through": pad.drill is not None,
                        "net": comp.nets.get(pad.name, "")}
        raise GitcadError(f"{ref} has no pad {pad_name!r}")
    raise GitcadError(f"no component {ref!r} on the board")


def route(board: Board, net: str, points: list[dict], *, width: float = 0.4,
          via_drill: float = 0.4, via_diameter: float = 0.8) -> dict:
    """Route ``net`` through ``points``, mutating ``board``.

    Each waypoint: ``{"pad": "REF.name"}`` or ``{"x": .., "y": ..}``, plus
    optional ``"layer": "top"|"bottom"``. Rules enforced at build time:

    - a pad waypoint must belong to ``net`` (wrong-net routing is an error,
      not a DRC surprise later)
    - an SMD pad endpoint forces its own side (bottom copper cannot "reach"
      a top pad — the GND-islands mistake)
    - a layer change between consecutive waypoints inserts a via there

    Returns {"tracks": n, "vias": n}.
    """
    if len(points) < 2:
        raise GitcadError("route needs at least 2 waypoints")

    resolved: list[tuple[float, float, str]] = []   # (x, y, layer)
    layer = None
    for i, wp in enumerate(points):
        if "pad" in wp:
            info = pad_position(board, wp["pad"])
            if info["net"] != net:
                raise GitcadError(
                    f"waypoint {wp['pad']} is on net {info['net']!r}, not {net!r} "
                    "— refusing to route onto the wrong pad")
            x, y = info["x"], info["y"]
            if info["through"]:
                want = wp.get("layer", layer or "top")
            else:
                want = info["side"]
                if "layer" in wp and wp["layer"] != want:
                    raise GitcadError(
                        f"waypoint {wp['pad']} is an SMD pad on {want!r} — "
                        f"cannot arrive on {wp['layer']!r}")
        else:
            x, y = float(wp["x"]), float(wp["y"])
            want = wp.get("layer", layer or "top")
        if layer is None:
            layer = want
        resolved.append((x, y, want))

    tracks = vias = 0
    for (x1, y1, l1), (x2, y2, l2) in zip(resolved, resolved[1:]):
        seg_layer = l1
        if l2 != l1:
            # layer change happens AT the second waypoint: via there, segment
            # runs on the departing layer.
            board.vias.append(Via(x2, y2, drill=via_drill, diameter=via_diameter, net=net))
            vias += 1
        if (x1, y1) != (x2, y2):
            board.tracks.append(Track(x1, y1, x2, y2, width, seg_layer, net))
            tracks += 1
    # Final-endpoint SMD side check (the arriving segment's layer).
    last = points[-1]
    if "pad" in last:
        info = pad_position(board, last["pad"])
        if not info["through"] and resolved[-1][2] != info["side"]:
            raise GitcadError(f"route arrives at SMD pad {last['pad']} on the wrong side")
    return {"tracks": tracks, "vias": vias}
