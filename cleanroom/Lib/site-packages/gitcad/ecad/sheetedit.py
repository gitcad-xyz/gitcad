"""Sheet authoring — agents draw schematics the way KiCad users do.

``SheetEditor`` places symbols on the sheet, draws wires between pin
positions, and adds labels and power flags. ``finish()`` derives the
netlist FROM the drawn geometry through the same engine that imports
KiCad sheets (ecad/netderive.py) — so an authored sheet and an imported
sheet mean their drawings in exactly the same way, ``sheet_parity`` is
green by construction, and the result renders through the fidelity
renderer (``sheet_to_svg``) in KiCad's visual language.

Built-in symbols follow KiCad library conventions (y-up frame, 2.54 mm
grid): resistor, capacitor, led, diode, ic (pins left/right), header.
"""

from __future__ import annotations

from gitcad.ecad.netderive import derive_nets, derive_nets_ex, hier_merge, pin_abs
from gitcad.ecad.schematic import PIN_TYPES, Pin, SchComponent, Schematic
from gitcad.errors import GitcadError

Point = tuple[float, float]


def _remap_refs(sch: Schematic, ref_map: dict[str, str]) -> Schematic:
    """Copy a child schematic with refs renamed — the authoring-side mirror
    of KiCad's per-instance references, used when one child is instanced
    more than once."""
    import copy

    out = copy.deepcopy(sch)
    for comp in out.components:
        comp.ref = ref_map.get(comp.ref, comp.ref)

    def m(refpin: str) -> str:
        r, p = refpin.split(".", 1)
        return f"{ref_map.get(r, r)}.{p}"

    out.nets = {n: sorted(m(rp) for rp in refs) for n, refs in out.nets.items()}
    g = getattr(out, "graphics", None)
    if g and "symbols" in g:
        g["symbols"] = {ref_map.get(k, k): v for k, v in g["symbols"].items()}
    return out


def _two_pin(kind: str) -> dict:
    """Vertical two-pin symbol: pin 1 top (0, 3.81), pin 2 bottom (0, -3.81)."""
    pins = [{"number": "1", "x": 0.0, "y": 3.81, "angle": 270.0, "len": 1.27},
            {"number": "2", "x": 0.0, "y": -3.81, "angle": 90.0, "len": 1.27}]
    if kind == "resistor":
        shapes = [{"kind": "rect", "pts": [[-1.016, -2.54], [1.016, 2.54]]}]
    elif kind == "capacitor":
        shapes = [{"kind": "poly", "pts": [[-1.905, 0.762], [1.905, 0.762]]},
                  {"kind": "poly", "pts": [[-1.905, -0.762], [1.905, -0.762]]}]
        pins[0]["len"] = 3.048
        pins[1]["len"] = 3.048
    elif kind in ("led", "diode"):
        shapes = [{"kind": "poly",
                   "pts": [[-1.27, 1.27], [1.27, 1.27], [0.0, -1.27], [-1.27, 1.27]]},
                  {"kind": "poly", "pts": [[-1.27, -1.27], [1.27, -1.27]]}]
        if kind == "led":
            shapes += [{"kind": "poly", "pts": [[1.6, 0.8], [2.6, 1.8]]},
                       {"kind": "poly", "pts": [[2.2, 0.4], [3.2, 1.4]]}]
        pins[0]["len"] = 2.54
        pins[1]["len"] = 2.54
    else:
        raise GitcadError(f"unknown two-pin symbol kind {kind!r}")
    return {"pins": pins, "shapes": shapes}


def _ic(left: int, right: int) -> dict:
    """Box IC: pins 1..left down the left side, then left+1.. up the right."""
    rows = max(left, right)
    h = rows * 2.54 + 2.54
    half = h / 2
    shapes = [{"kind": "rect", "pts": [[-5.08, -half], [5.08, half]]}]
    pins = []
    for i in range(left):
        pins.append({"number": str(i + 1), "x": -7.62,
                     "y": half - 2.54 * (i + 1), "angle": 0.0, "len": 2.54})
    for i in range(right):
        pins.append({"number": str(left + i + 1), "x": 7.62,
                     "y": -half + 2.54 * (i + 1), "angle": 180.0, "len": 2.54})
    return {"pins": pins, "shapes": shapes}


def _header(n: int) -> dict:
    h = n * 2.54
    shapes = [{"kind": "rect", "pts": [[-1.27, -h / 2], [1.27, h / 2]]}]
    pins = [{"number": str(i + 1), "x": -5.08,
             "y": h / 2 - 1.27 - 2.54 * i, "angle": 0.0, "len": 3.81}
            for i in range(n)]
    return {"pins": pins, "shapes": shapes}


def symbol(kind: str, **kw) -> dict:
    if kind in ("resistor", "capacitor", "led", "diode"):
        return _two_pin(kind)
    if kind == "ic":
        return _ic(int(kw.get("left", 4)), int(kw.get("right", 4)))
    if kind == "header":
        return _header(int(kw.get("n", 4)))
    raise GitcadError(
        f"unknown symbol kind {kind!r} (want resistor|capacitor|led|diode|ic|header)")


class SheetEditor:
    """Author a drawn schematic sheet; geometry is the netlist source."""

    def __init__(self, name: str) -> None:
        self.sch = Schematic(name=name)
        self._gfx: dict = {"wires": [], "powers": [], "labels": [],
                           "symbols": {}, "junctions": []}
        self._pins: list[tuple[Point, str, str]] = []
        self._net_names: dict[Point, str] = {}
        self._subsheets: list[dict] = []
        self._children: list[Schematic] = []

    # -- placement -------------------------------------------------------------

    def place(self, ref: str, kind: str, x: float, y: float, *,
              value: str = "", rot: float = 0.0, footprint: str = "",
              pin_types: dict[str, str] | None = None, **kw) -> "SheetEditor":
        if any(c.ref == ref for c in self.sch.components):
            raise GitcadError(f"duplicate ref {ref!r}")
        sym = symbol(kind, **kw)
        types = pin_types or {}
        for t in types.values():
            if t not in PIN_TYPES:
                raise GitcadError(f"unknown pin type {t!r}")

        comp_pins, pin_xy, shapes_abs = [], {}, []
        import math
        for p in sym["pins"]:
            pt = pin_abs(p["x"], p["y"], x, y, rot)
            ptype = types.get(p["number"], "passive")
            comp_pins.append(Pin(p["number"], p["number"], ptype))
            pin_xy[p["number"]] = [pt[0], pt[1]]
            self._pins.append((pt, f"{ref}.{p['number']}", ptype))
            rad = math.radians(p["angle"])
            bx = p["x"] + p["len"] * math.cos(rad)
            by = p["y"] + p["len"] * math.sin(rad)
            shapes_abs.append({"kind": "pin",
                               "pts": [list(pt), list(pin_abs(bx, by, x, y, rot))]})
        for shp in sym["shapes"]:
            baked = {"kind": shp["kind"],
                     "pts": [list(pin_abs(px, py, x, y, rot)) for px, py in shp["pts"]]}
            if "r" in shp:
                baked["r"] = shp["r"]
            shapes_abs.append(baked)

        attrs = {"at": [x, y], "lib_id": f"gitcad:{kind}", "pin_xy": pin_xy}
        if rot:
            attrs["rot"] = rot
        self.sch.components.append(SchComponent(
            ref=ref, value=value, footprint=footprint,
            pins=comp_pins, attrs=attrs))
        self._gfx["symbols"][ref] = {"shapes": shapes_abs, "at": [x, y],
                                     "value": value}
        return self

    def pin_pos(self, ref: str, number: str) -> Point:
        for c in self.sch.components:
            if c.ref == ref:
                if number not in c.attrs["pin_xy"]:
                    raise GitcadError(f"{ref}: no pin {number!r}")
                return tuple(c.attrs["pin_xy"][number])
        raise GitcadError(f"unknown ref {ref!r}")

    # -- wiring ----------------------------------------------------------------

    def wire(self, *points: Point) -> "SheetEditor":
        """Polyline through the given points (each consecutive pair a segment)."""
        if len(points) < 2:
            raise GitcadError("wire needs at least 2 points")
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            self._gfx["wires"].append([float(x1), float(y1), float(x2), float(y2)])
        return self

    def connect(self, a: tuple[str, str], b: tuple[str, str],
                *via: Point) -> "SheetEditor":
        """Wire pin a to pin b, optionally through waypoints — the common case."""
        self.wire(self.pin_pos(*a), *via, self.pin_pos(*b))
        return self

    def junction(self, x: float, y: float) -> "SheetEditor":
        self._gfx["junctions"].append([float(x), float(y)])
        return self

    def bus(self, *points: Point) -> "SheetEditor":
        """A bus polyline — VISUAL grouping only (KiCad semantics): member
        connectivity comes from same-named labels on the tapped wires, which
        the netlist engine unifies by name. Draw the bus, tap wires off it,
        label each tap; the labels are the electrical truth."""
        if len(points) < 2:
            raise GitcadError("bus needs at least 2 points")
        self._gfx.setdefault("buses", [])
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            self._gfx["buses"].append([float(x1), float(y1), float(x2), float(y2)])
        return self

    def note(self, text: str, x: float, y: float, *,
             size: float = 1.6) -> "SheetEditor":
        """Free text annotation on the sheet — documentation, not netlist."""
        self._gfx.setdefault("notes", []).append(
            {"text": str(text), "x": float(x), "y": float(y), "size": size})
        return self

    def label(self, name: str, x: float, y: float) -> "SheetEditor":
        self._gfx["labels"].append({"name": name, "x": float(x), "y": float(y),
                                    "kind": "label", "rot": 0.0})
        self._net_names[(float(x), float(y))] = name
        return self

    def power(self, name: str, x: float, y: float, *, rot: float = 0.0) -> "SheetEditor":
        self._gfx["powers"].append({"name": name, "x": float(x), "y": float(y),
                                    "rot": rot})
        self._net_names[(float(x), float(y))] = name
        return self

    def global_label(self, name: str, x: float, y: float) -> "SheetEditor":
        """Design-wide net name — same name is the same net on EVERY sheet
        of the hierarchy (KiCad global-label semantics)."""
        self._gfx["labels"].append({"name": name, "x": float(x), "y": float(y),
                                    "kind": "global_label", "rot": 0.0})
        self._net_names[(float(x), float(y))] = name
        return self

    def hier_label(self, name: str, x: float, y: float) -> "SheetEditor":
        """Hierarchical label — the child-side attachment point a parent
        sheet pin of the same name bridges to."""
        self._gfx["labels"].append({"name": name, "x": float(x), "y": float(y),
                                    "kind": "hierarchical_label", "rot": 0.0})
        self._net_names[(float(x), float(y))] = name
        return self

    # -- hierarchy -------------------------------------------------------------

    def sheet(self, name: str, child: "Schematic | SheetEditor",
              x: float, y: float, w: float, h: float, *,
              pins: dict[str, Point],
              ref_map: dict[str, str] | None = None) -> "SheetEditor":
        """Place a subsheet instance. ``child`` is a finished Schematic (or a
        SheetEditor, finished here); ``pins`` maps sheet-pin names to points
        on THIS sheet — each must match a hierarchical label in the child,
        and parent wires touching that point bridge into the child's net.

        REUSE: place the same child twice with distinct ``ref_map``s (the
        authoring mirror of KiCad's per-instance references); colliding refs
        fail loud in the merge."""
        if any(ss["name"] == name for ss in self._subsheets):
            raise GitcadError(f"duplicate sheet name {name!r}")
        csch = child.finish() if isinstance(child, SheetEditor) else child
        if ref_map:
            csch = _remap_refs(csch, ref_map)
        spins = [{"name": pn, "x": float(px), "y": float(py)}
                 for pn, (px, py) in sorted(pins.items())]
        child_hier = {lb["name"]
                      for lb in (getattr(csch, "graphics", None) or {}).get("labels", [])
                      if lb.get("kind") == "hierarchical_label"}
        for sp in spins:
            if sp["name"] not in child_hier:
                raise GitcadError(
                    f"sheet {name!r}: pin {sp['name']!r} has no hierarchical "
                    f"label in child {csch.name!r}")
        self._subsheets.append({"name": name, "file": f"{csch.name}.sch",
                                "x": float(x), "y": float(y),
                                "w": float(w), "h": float(h), "pins": spins})
        self._children.append(csch)
        return self

    # -- result ----------------------------------------------------------------

    def finish(self) -> Schematic:
        """Derive the netlist from the drawing (geometry is the source) and
        return the schematic with its sheet graphics attached. With subsheets
        placed, the hierarchy flattens through the SAME hier_merge engine as
        the KiCad importer — authored and imported hierarchies mean exactly
        the same thing. ERC and sheet_parity are the caller's gates."""
        wires = [((w[0], w[1]), (w[2], w[3])) for w in self._gfx["wires"]]
        junctions = [tuple(j) for j in self._gfx["junctions"]]
        self.sch.nets = {}
        self.warnings: list[str] = []
        if not self._subsheets:
            nets = derive_nets(self._pins, wires, junctions, self._net_names)
            for name, refs in nets.items():
                self.sch.connect(name, *refs)
        else:
            query_pts = tuple((sp["x"], sp["y"])
                              for ss in self._subsheets for sp in ss["pins"])
            parent_nets, query_net = derive_nets_ex(
                self._pins, wires, junctions, self._net_names,
                frozenset(), query_pts)
            hier_merge(self.sch, parent_nets, self._subsheets, self._children,
                       query_net, self._gfx["labels"], self._gfx["powers"],
                       self.warnings)
            self._gfx["sheets"] = self._subsheets
        self.sch.graphics = dict(self._gfx)  # type: ignore[attr-defined]
        return self.sch
