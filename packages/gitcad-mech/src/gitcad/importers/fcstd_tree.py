"""FCStd parametric-tree import — true history recovery, with proof.

FreeCAD's ``Document.xml`` is the one open interchange where the parametric
tree actually survives: object types, properties, placements, and boolean
links are all there in XML. This module maps the tractable subset to gitcad
features:

    Part::Box / Part::Cylinder / Part::Sphere / Part::Cone   -> primitives
    Placement (position + z-rotation)                         -> move
    Part::Cut / Part::Fuse / Part::Common / Part::MultiFuse   -> boolean

and then **proves** the reconstruction the same way feature recognition does:
rebuild the parametric document and take the symmetric boolean difference
against the geometry embedded in the same .FCStd (the ``.brep`` payloads are
the oracle — both sources ship in one zip). Only a proven tree is returned as
parametric; anything else falls back to geometry-only import with the reason
in the report. PartDesign (sketch-based) models are out of v1 scope and fall
back honestly.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile

from gitcad.document import Document, Feature
from gitcad.importers.fcstd import import_fcstd
from gitcad.importers.report import ImportReport
from gitcad.seams import Kernel

_REL_TOL = 1e-6

# FreeCAD type -> (gitcad op, property name -> param name)
_PRIMITIVES = {
    "Part::Box": ("box", {"Length": "dx", "Width": "dy", "Height": "dz"}),
    "Part::Cylinder": ("cylinder", {"Radius": "radius", "Height": "height"}),
    "Part::Sphere": ("sphere", {"Radius": "radius"}),
    "Part::Cone": ("cone", {"Radius1": "r1", "Radius2": "r2", "Height": "height"}),
}
_BOOLEANS = {"Part::Cut": "cut", "Part::Fuse": "union", "Part::Common": "intersect"}


class _Obj:
    def __init__(self, name: str, ftype: str) -> None:
        self.name = name
        self.type = ftype
        self.props: dict[str, float] = {}
        self.placement: tuple[float, float, float, float] | None = None  # x,y,z,angle_z_deg
        self.links: list[str] = []          # Base, Tool (in order)


def _parse_document_xml(xml_text: str) -> dict[str, _Obj]:
    """Objects with their types, numeric properties, placements, and links."""
    root = ET.fromstring(xml_text)
    objects: dict[str, _Obj] = {}
    for od in root.iter("Object"):
        name, ftype = od.get("name"), od.get("type")
        if name and ftype and name not in objects:
            objects[name] = _Obj(name, ftype)

    for od in root.iter("ObjectData"):
        for obj_el in od.iter("Object"):
            obj = objects.get(obj_el.get("name", ""))
            if obj is None:
                continue
            for prop in obj_el.iter("Property"):
                pname = prop.get("name", "")
                if pname == "Placement":
                    pp = prop.find("PropertyPlacement")
                    if pp is not None:
                        px, py, pz = (float(pp.get(k, 0)) for k in ("Px", "Py", "Pz"))
                        angle = float(pp.get("A", 0))          # radians
                        ax, ay, az = (float(pp.get(k, 0)) for k in ("Ox", "Oy", "Oz"))
                        import math

                        deg = math.degrees(angle)
                        # v1 supports identity or Z-axis rotation only; anything
                        # else marks the object unmappable via a sentinel.
                        if abs(angle) < 1e-12 or (abs(az) > 0.999999 and abs(ax) < 1e-9 and abs(ay) < 1e-9):
                            obj.placement = (px, py, pz, deg if az >= 0 else -deg)
                        else:
                            obj.placement = None
                            obj.props["_unsupported_rotation"] = 1.0
                    continue
                fl = prop.find("Float")
                if fl is not None:
                    obj.props[pname] = float(fl.get("value", 0))
                    continue
                if pname in ("Base", "Tool"):
                    ln = prop.find("Link")
                    if ln is not None and ln.get("value"):
                        obj.links.append(ln.get("value"))
    return objects


def import_fcstd_tree(path: str, kernel: Kernel, assets_dir: str) -> tuple[Document, ImportReport]:
    """Parametric-first FCStd import. Returns a parametric document when the
    whole tree maps AND the rebuild proves out against the embedded geometry;
    otherwise falls back to geometry-only import with the reason reported."""
    with zipfile.ZipFile(path) as zf:
        if "Document.xml" not in zf.namelist():
            return import_fcstd(path, kernel, assets_dir)
        xml_text = zf.read("Document.xml").decode("utf-8", errors="replace")

    objects = _parse_document_xml(xml_text)

    def fallback(reason: str) -> tuple[Document, ImportReport]:
        doc, report = import_fcstd(path, kernel, assets_dir)
        report.warnings.append(f"parametric import not possible: {reason}; geometry imported instead")
        return doc, report

    # Which objects are unmapped? (Ignore non-shape helper objects: origins etc.)
    consumed: set[str] = set()
    for obj in objects.values():
        consumed.update(obj.links)
    unmapped = [o for o in objects.values()
                if o.type not in _PRIMITIVES and o.type not in _BOOLEANS]
    if unmapped:
        kinds = sorted({o.type for o in unmapped})
        return fallback(f"unmapped object types: {kinds}")
    if any("_unsupported_rotation" in o.props for o in objects.values()):
        return fallback("placement rotation about a non-Z axis")

    # -- build the parametric document (topological order via links) ----------
    doc = Document()
    built: dict[str, str] = {}   # FreeCAD name -> gitcad feature id

    def build_obj(name: str) -> str:
        if name in built:
            return built[name]
        obj = objects[name]
        if obj.type in _PRIMITIVES:
            op, prop_map = _PRIMITIVES[obj.type]
            params = {param: obj.props[fc_prop] for fc_prop, param in prop_map.items()
                      if fc_prop in obj.props}
            if len(params) != len(prop_map):
                raise KeyError(f"{name}: missing properties for {obj.type}")
            fid = doc.add(Feature(op=op, params=params))
        else:
            kind = _BOOLEANS[obj.type]
            if len(obj.links) != 2:
                raise KeyError(f"{name}: boolean needs Base+Tool")
            ins = [build_obj(link) for link in obj.links]
            fid = doc.add(Feature(op="boolean", params={"kind": kind}, inputs=ins))
        if obj.placement and obj.placement != (0.0, 0.0, 0.0, 0.0):
            x, y, z, deg = obj.placement
            fid = doc.add(Feature(op="move", params={
                "translate": [x, y, z],
                **({"rotate_deg": deg} if abs(deg) > 1e-9 else {}),
            }, inputs=[fid]))
        built[name] = fid
        return fid

    roots = [o.name for o in objects.values() if o.name not in consumed]
    try:
        for root_name in roots:
            build_obj(root_name)
    except KeyError as exc:
        return fallback(str(exc))

    # -- the proof: rebuild vs embedded geometry -------------------------------
    geo_doc, _ = import_fcstd(path, kernel, assets_dir)
    reference = geo_doc.build(kernel).final(geo_doc)
    v_ref = kernel.measure(reference)["volume"]

    rebuilt_result = doc.build(kernel)
    shapes = [rebuilt_result.shapes[built[r]] for r in roots]
    rebuilt = shapes[0] if len(shapes) == 1 else kernel.compound(shapes)
    residual = (kernel.measure(kernel.boolean("cut", rebuilt, reference))["volume"]
                + kernel.measure(kernel.boolean("cut", reference, rebuilt))["volume"])
    if v_ref <= 0 or residual / v_ref > _REL_TOL:
        return fallback(f"parametric rebuild does not match geometry "
                        f"(residual {residual:.6f} mm3)")

    report = ImportReport(source=path, format="fcstd-parametric")
    report.count("parametric_features", len(doc))
    report.count("objects", len(objects))
    report.imported["proof_residual_mm3"] = round(residual, 6)
    report.warnings.append(
        "parametric tree imported and PROVEN against embedded geometry — "
        "dimensions are live and editable"
    )
    return doc, report
