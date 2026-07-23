"""IPC-2581C export — the modern fab/assembly exchange format.

Structure mirrors what KiCad 10 emits for the same data (our conformance
oracle: ``kicad-cli pcb export ipc2581`` on the same board, compared
element-for-element on refdes/net/layer/component sets): IPC-2581 rev C,
namespace ``http://webstds.ipc.org/2581`` — Content dictionaries,
LogisticHeader, HistoryRecord, Bom, Ecad (CadHeader, Layer definitions,
Stackup, a BOARD Step carrying Profile, Packages, Components,
LogicalNets, and per-copper-layer features), Avl.

Deterministic by construction: everything sorted, and the origination
timestamp is a PARAMETER (default epoch) — same board text, byte-identical
XML, per ADR-0004. Pass a real date when a customer needs one.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from gitcad._version import __version__ as _V
from gitcad.ecad.board import Board

_NS = "http://webstds.ipc.org/2581"


def _pad_primitive(pad_key: tuple, idx: int) -> str:
    shape, w, h = pad_key
    if shape == "circle":
        return (f'<EntryStandard id="PRIM_{idx}">'
                f'<Circle diameter="{max(w, h):.6f}"/></EntryStandard>')
    if shape == "obround":
        return (f'<EntryStandard id="PRIM_{idx}">'
                f'<Oval width="{w:.6f}" height="{h:.6f}"/></EntryStandard>')
    return (f'<EntryStandard id="PRIM_{idx}">'
            f'<RectCenter width="{w:.6f}" height="{h:.6f}"/></EntryStandard>')


def to_ipc2581(board: Board, *, origination: str = "1970-01-01T00:00:00") -> str:
    copper = board.copper_layers()
    n = len(copper)

    def side_of(layer: str) -> str:
        return ("TOP" if layer == "top"
                else "BOTTOM" if layer == "bottom" else "INTERNAL")

    # -- dictionaries: pad primitives + line widths ---------------------------
    pad_keys: dict[tuple, int] = {}
    for comp in board.components:
        for pad in comp.footprint.pads:
            pad_keys.setdefault((pad.shape, pad.w, pad.h), len(pad_keys) + 1)
    for via in board.vias:
        pad_keys.setdefault(("circle", via.diameter, via.diameter),
                            len(pad_keys) + 1)
    widths = sorted({t.width for t in board.tracks})
    line_ids = {w: i + 1 for i, w in enumerate(widths)}

    # -- nets ------------------------------------------------------------------
    nets: dict[str, list[str]] = {}
    for comp in board.components:
        for pad_name, net in sorted(comp.nets.items()):
            if net:
                nets.setdefault(net, []).append(f"{comp.ref}.{pad_name}")

    x: list[str] = []
    x.append('<?xml version="1.0" encoding="UTF-8"?>')
    x.append(f'<IPC-2581 revision="C" xmlns="{_NS}">')

    # Content
    x.append('<Content roleRef="Owner">')
    x.append('<FunctionMode mode="ASSEMBLY"/>')
    x.append(f'<StepRef name="{escape(board.name)}"/>')
    for layer in copper:
        x.append(f'<LayerRef name="{escape(layer)}"/>')
    x.append(f'<BomRef name="{escape(board.name)}_bom"/>')
    x.append('<DictionaryLineDesc units="MILLIMETER">')
    for w, i in sorted(line_ids.items(), key=lambda kv: kv[1]):
        x.append(f'<EntryLineDesc id="LINE_{i}">'
                 f'<LineDesc lineEnd="ROUND" lineWidth="{w:.6f}"/></EntryLineDesc>')
    x.append('</DictionaryLineDesc>')
    x.append('<DictionaryStandard units="MILLIMETER">')
    for key, idx in sorted(pad_keys.items(), key=lambda kv: kv[1]):
        x.append(_pad_primitive(key, idx))
    x.append('</DictionaryStandard>')
    x.append('</Content>')

    # LogisticHeader + HistoryRecord
    x.append('<LogisticHeader>'
             '<Role id="Owner" roleFunction="SENDER"/>'
             '<Enterprise id="UNKNOWN" code="NONE"/>'
             '<Person name="UNKNOWN" enterpriseRef="UNKNOWN" roleRef="Owner"/>'
             '</LogisticHeader>')
    x.append(f'<HistoryRecord number="1" origination="{origination}" '
             f'software="gitcad {_V}" lastChange="{origination}">'
             '<FileRevision fileRevisionId="1" comment="" label="">'
             f'<SoftwarePackage name="gitcad" revision="{_V}" vendor="gitcad">'
             '<Certification certificationStatus="SELFTEST"/>'
             '</SoftwarePackage></FileRevision></HistoryRecord>')

    # Bom
    x.append(f'<Bom name="{escape(board.name)}_bom">')
    x.append(f'<BomHeader revision="1" assembly="{escape(board.name)}">'
             f'<StepRef name="{escape(board.name)}"/></BomHeader>')
    by_item: dict[tuple, list] = {}
    for comp in sorted(board.components, key=lambda c: c.ref):
        by_item.setdefault((comp.footprint.name, comp.value), []).append(comp)
    for (fp_name, value), comps in sorted(by_item.items()):
        x.append(f'<BomItem OEMDesignNumberRef="{escape(fp_name)}" '
                 f'quantity="{len(comps)}" '
                 f'pinCount="{len(comps[0].footprint.pads)}" category="ELECTRICAL">')
        for comp in comps:
            x.append(f'<RefDes name="{escape(comp.ref)}" '
                     f'packageRef="{escape(fp_name)}" populate="true" '
                     f'layerRef="{escape(comp.side)}"/>')
        x.append('</BomItem>')
    x.append('</Bom>')

    # Ecad
    x.append('<Ecad name="Design"><CadHeader units="MILLIMETER"/><CadData>')
    for layer in copper:
        x.append(f'<Layer name="{escape(layer)}" layerFunction="CONDUCTOR" '
                 f'side="{side_of(layer)}" polarity="POSITIVE"/>')
    x.append(f'<Layer name="drill" layerFunction="DRILL" side="ALL" '
             f'polarity="POSITIVE"/>')
    # Stackup: copper foils + equal dielectrics summing to board thickness
    x.append(f'<Stackup name="Primary_Stackup" '
             f'overallThickness="{board.thickness:.4f}" tolPlus="0" tolMinus="0" '
             f'whereMeasured="METAL">')
    x.append('<StackupGroup name="Primary_Stackup_Group" '
             f'thickness="{board.thickness:.4f}" tolPlus="0" tolMinus="0">')
    copper_t = 0.035
    dielectric = (board.thickness - n * copper_t) / (n - 1)
    seq = 1
    for i, layer in enumerate(copper):
        x.append(f'<StackupLayer layerOrGroupRef="{escape(layer)}" '
                 f'thickness="{copper_t:.4f}" tolPlus="0" tolMinus="0" '
                 f'sequence="{seq}"/>')
        seq += 1
        if i < n - 1:
            x.append(f'<StackupLayer layerOrGroupRef="dielectric_{i + 1}" '
                     f'thickness="{dielectric:.4f}" tolPlus="0" tolMinus="0" '
                     f'sequence="{seq}"/>')
            seq += 1
    x.append('</StackupGroup></Stackup>')

    # Step
    x.append(f'<Step name="{escape(board.name)}" type="BOARD">')
    pts = list(board.outline)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    x.append('<Profile><Polygon>')
    x.append(f'<PolyBegin x="{pts[0][0]:.6f}" y="{pts[0][1]:.6f}"/>')
    for px, py in pts[1:]:
        x.append(f'<PolyStepSegment x="{px:.6f}" y="{py:.6f}"/>')
    x.append('</Polygon></Profile>')

    # Packages
    for fp_name in sorted({c.footprint.name for c in board.components}):
        fp = next(c.footprint for c in board.components
                  if c.footprint.name == fp_name)
        x.append(f'<Package name="{escape(fp_name)}" type="OTHER" '
                 f'pinOne="1" pinOneOrientation="OTHER">')
        for pad in fp.pads:
            x.append(f'<Pin number="{escape(pad.name)}" type="SURFACE" '
                     f'electricalType="ELECTRICAL">'
                     f'<Location x="{pad.x:.6f}" y="{pad.y:.6f}"/></Pin>')
        x.append('</Package>')

    # Components
    for comp in sorted(board.components, key=lambda c: c.ref):
        x.append(f'<Component refDes="{escape(comp.ref)}" '
                 f'packageRef="{escape(comp.footprint.name)}" '
                 f'layerRef="{escape(comp.side)}" part="{escape(comp.value)}">'
                 f'<Xform rotation="{comp.rot:.1f}"/>'
                 f'<Location x="{comp.x:.6f}" y="{comp.y:.6f}"/></Component>')

    # LogicalNets
    for net, prs in sorted(nets.items()):
        x.append(f'<LogicalNet name="{escape(net)}">')
        for pr in sorted(prs):
            ref, pin = pr.split(".", 1)
            x.append(f'<PinRef pin="{escape(pin)}" componentRef="{escape(ref)}"/>')
        x.append('</LogicalNet>')

    # Per-copper-layer features
    for layer in copper:
        x.append(f'<LayerFeature layerRef="{escape(layer)}">')
        outer = layer in ("top", "bottom")
        for comp in sorted(board.components, key=lambda c: c.ref):
            for pad, bx, by, rot in comp.placed_pads():
                if not (pad.drill is not None or (outer and comp.side == layer)):
                    continue
                key = (pad.shape, pad.w, pad.h)
                net = comp.nets.get(pad.name, "")
                x.append(f'<Set net="{escape(net)}"><Pad>'
                         f'<Location x="{bx:.6f}" y="{by:.6f}"/>'
                         f'<StandardPrimitiveRef id="PRIM_{pad_keys[key]}"/>'
                         f'</Pad></Set>')
        for via in board.vias:
            key = ("circle", via.diameter, via.diameter)
            x.append(f'<Set net="{escape(via.net)}" padUsage="VIA"><Pad>'
                     f'<Location x="{via.x:.6f}" y="{via.y:.6f}"/>'
                     f'<StandardPrimitiveRef id="PRIM_{pad_keys[key]}"/>'
                     f'</Pad></Set>')
        for t in sorted((t for t in board.tracks if t.layer == layer),
                        key=lambda t: (t.x1, t.y1, t.x2, t.y2)):
            x.append(f'<Set net="{escape(t.net)}"><Features>'
                     f'<Line startX="{t.x1:.6f}" startY="{t.y1:.6f}" '
                     f'endX="{t.x2:.6f}" endY="{t.y2:.6f}">'
                     f'<LineDescRef id="LINE_{line_ids[t.width]}"/></Line>'
                     f'</Features></Set>')
        for z in board.zones:
            if z.layer != layer or z.kind != "copper":
                continue
            zpts = list(z.polygon)
            if zpts[0] != zpts[-1]:
                zpts.append(zpts[0])
            x.append(f'<Set net="{escape(z.net)}"><Features><Polygon>')
            x.append(f'<PolyBegin x="{zpts[0][0]:.6f}" y="{zpts[0][1]:.6f}"/>')
            for px, py in zpts[1:]:
                x.append(f'<PolyStepSegment x="{px:.6f}" y="{py:.6f}"/>')
            x.append('</Polygon></Features></Set>')
        x.append('</LayerFeature>')

    # drill layer
    x.append('<LayerFeature layerRef="drill">')
    for comp in sorted(board.components, key=lambda c: c.ref):
        for pad, bx, by, _rot in comp.placed_pads():
            if pad.drill is not None:
                x.append(f'<Set net="{escape(comp.nets.get(pad.name, ""))}">'
                         f'<Hole name="{escape(comp.ref)}.{escape(pad.name)}" '
                         f'diameter="{pad.drill:.6f}" platingStatus="PLATED" '
                         f'plusTol="0" minusTol="0" x="{bx:.6f}" y="{by:.6f}"/></Set>')
    for i, via in enumerate(board.vias):
        x.append(f'<Set net="{escape(via.net)}" padUsage="VIA">'
                 f'<Hole name="via{i}" diameter="{via.drill:.6f}" '
                 f'platingStatus="VIA" plusTol="0" minusTol="0" '
                 f'x="{via.x:.6f}" y="{via.y:.6f}"/></Set>')
    for mh in board.mounting_holes:
        x.append(f'<Set net=""><Hole name="{escape(mh.name)}" '
                 f'diameter="{mh.drill:.6f}" platingStatus="NONPLATED" '
                 f'plusTol="0" minusTol="0" x="{mh.x:.6f}" y="{mh.y:.6f}"/></Set>')
    x.append('</LayerFeature>')

    x.append('</Step></CadData></Ecad>')
    x.append('</IPC-2581>')
    return "\n".join(x) + "\n"
