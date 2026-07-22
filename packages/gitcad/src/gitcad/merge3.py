"""Semantic 3-way merge for design documents (ADR-0016).

Merge units are semantic, keyed by stable identity: features by id for
models, components by ref and connectivity by PIN for schematics. Both
sides touching different units merges cleanly; both sides changing the
same unit differently is a structured conflict — never a text marker
inside canonical JSON (that would make the file unparseable for every
tool including the resolver).

Result contract: ``{"ok": bool, "merged": text|None, "conflicts": [...]}``.
A clean merge's output is re-parsed through the document's own loader
before being returned — a merge that doesn't rebuild is a driver bug,
never shipped state.
"""

from __future__ import annotations

import json

from gitcad.canonical import canonical_json
from gitcad.release import _kind


def _cell3(base, ours, theirs):
    """Classic 3-way cell. Values are canonical strings (None = absent).
    Returns ("take", value) or ("conflict", ours, theirs)."""
    if ours == theirs:
        return ("take", ours)
    if ours == base:
        return ("take", theirs)
    if theirs == base:
        return ("take", ours)
    return ("conflict", ours, theirs)


def merge_documents(base: str, ours: str, theirs: str) -> dict:
    kind_b = _kind(base)
    if not (_kind(ours) == _kind(theirs) == kind_b):
        return {"ok": False, "merged": None, "conflicts": [
            {"unit": "document", "reason": "kind changed between branches"}]}
    if kind_b == "document":
        return _merge_model(base, ours, theirs)
    if kind_b == "schematic":
        return _merge_schematic(base, ours, theirs)
    # boards / parts: whole-document 3-way, honest coarse fallback (ADR-0016)
    verdict = _cell3(base, ours, theirs)
    if verdict[0] == "take":
        return {"ok": True, "merged": verdict[1], "conflicts": []}
    return {"ok": False, "merged": None, "conflicts": [
        {"unit": kind_b, "reason": "both branches changed this document "
         "(fine-grained merge for this kind is a later stage)"}]}


# -- models: features by stable id --------------------------------------------

def _merge_model(base: str, ours: str, theirs: str) -> dict:
    from gitcad.document import Document

    b = {f.id: f for f in Document.loads(base).features}
    o = {f.id: f for f in Document.loads(ours).features}
    t = {f.id: f for f in Document.loads(theirs).features}
    canon = lambda f: canonical_json(f.to_dict()) if f else None  # noqa: E731

    conflicts: list[dict] = []
    keep: dict[str, dict] = {}
    for fid in {**b, **o, **t}:
        verdict = _cell3(canon(b.get(fid)), canon(o.get(fid)), canon(t.get(fid)))
        if verdict[0] == "conflict":
            side = lambda v: json.loads(v) if v else None  # noqa: E731
            conflicts.append({"unit": "feature", "id": fid,
                              "op": (o.get(fid) or t.get(fid) or b.get(fid)).op,
                              "ours": side(verdict[1]), "theirs": side(verdict[2])})
        elif verdict[1] is not None:
            keep[fid] = json.loads(verdict[1])
    if conflicts:
        return {"ok": False, "merged": None, "conflicts": conflicts}

    # Order: base survivors, then ours-added, then theirs-added…
    order = [fid for fid in b if fid in keep]
    order += [fid for fid in o if fid in keep and fid not in b]
    order += [fid for fid in t if fid in keep and fid not in b and fid not in o]
    # …then a stable topological pass so inputs precede their users.
    placed: list[str] = []
    ready: set[str] = set()
    pending = list(order)
    while pending:
        progressed = False
        for fid in list(pending):
            if all(ref in ready for ref in keep[fid].get("inputs", [])):
                placed.append(fid)
                ready.add(fid)
                pending.remove(fid)
                progressed = True
        if not progressed:
            return {"ok": False, "merged": None, "conflicts": [
                {"unit": "feature", "id": pending[0],
                 "reason": "input dependency cycle or input deleted by the "
                           "other branch"}]}
    merged_text = canonical_json(
        {"schema": "gitcad/document@1",
         "features": [keep[fid] for fid in placed]}, indent=2) + "\n"
    Document.loads(merged_text)   # the rebuild gate: must parse or we crash here
    return {"ok": True, "merged": merged_text, "conflicts": []}


# -- schematics: components by ref, connectivity by pin -----------------------

def _pin_map(sch) -> dict[str, str]:
    return {pr: net for net, prs in sch.nets.items() for pr in prs}


def _merge_schematic(base: str, ours: str, theirs: str) -> dict:
    from gitcad.ecad.schematic import Schematic

    sb, so, st = (Schematic.loads(x) for x in (base, ours, theirs))
    canon = lambda c: canonical_json(  # noqa: E731
        {"ref": c.ref, "value": c.value, "footprint": c.footprint,
         "pins": [p.__dict__ for p in c.pins], "attrs": c.attrs}) if c else None

    conflicts: list[dict] = []
    comps: dict[str, dict] = {}
    cb = {c.ref: c for c in sb.components}
    co = {c.ref: c for c in so.components}
    ct = {c.ref: c for c in st.components}
    for ref in {**cb, **co, **ct}:
        verdict = _cell3(canon(cb.get(ref)), canon(co.get(ref)), canon(ct.get(ref)))
        if verdict[0] == "conflict":
            side = lambda v: json.loads(v) if v else None  # noqa: E731
            conflicts.append({"unit": "component", "ref": ref,
                              "ours": side(verdict[1]), "theirs": side(verdict[2])})
        elif verdict[1] is not None:
            comps[ref] = json.loads(verdict[1])

    pb, po, pt = _pin_map(sb), _pin_map(so), _pin_map(st)
    pins: dict[str, str] = {}
    for pr in {**pb, **po, **pt}:
        verdict = _cell3(pb.get(pr), po.get(pr), pt.get(pr))
        if verdict[0] == "conflict":
            conflicts.append({"unit": "pin", "pin": pr,
                              "ours": verdict[1], "theirs": verdict[2]})
        elif verdict[1] is not None and pr.split(".", 1)[0] in comps:
            pins[pr] = verdict[1]

    specs: dict[str, dict] = {}
    for key in {**sb.net_specs, **so.net_specs, **st.net_specs}:
        cj = lambda d: canonical_json(d) if d is not None else None  # noqa: E731
        verdict = _cell3(cj(sb.net_specs.get(key)), cj(so.net_specs.get(key)),
                         cj(st.net_specs.get(key)))
        if verdict[0] == "conflict":
            conflicts.append({"unit": "net_spec", "net": key,
                              "ours": verdict[1], "theirs": verdict[2]})
        elif verdict[1] is not None:
            specs[key] = json.loads(verdict[1])

    if conflicts:
        return {"ok": False, "merged": None, "conflicts": conflicts}

    name3 = _cell3(sb.name, so.name, st.name)
    merged = Schematic(name=name3[1] if name3[0] == "take" else so.name)
    from gitcad.ecad.schematic import Pin, SchComponent

    for ref in sorted(comps):
        c = comps[ref]
        merged.components.append(SchComponent(
            ref=c["ref"], value=c["value"], footprint=c["footprint"],
            pins=[Pin(**p) for p in c["pins"]], attrs=c["attrs"]))
    for pr, net in pins.items():
        merged.connect(net, pr)
    merged.net_specs = specs
    text = merged.dumps()
    Schematic.loads(text)   # the rebuild gate
    return {"ok": True, "merged": text, "conflicts": []}


def main() -> None:  # pragma: no cover - git merge driver entrypoint
    """git merge driver: gitcad-merge %O %A %B — result written to %A.

    .gitattributes:  *.gitcad.json merge=gitcad
    .git/config:     [merge "gitcad"]
                       name = gitcad semantic merge
                       driver = gitcad-merge %O %A %B
    """
    import sys
    from pathlib import Path

    base_p, ours_p, theirs_p = (Path(p) for p in sys.argv[1:4])
    result = merge_documents(base_p.read_text(encoding="utf-8"),
                             ours_p.read_text(encoding="utf-8"),
                             theirs_p.read_text(encoding="utf-8"))
    if result["ok"]:
        ours_p.write_text(result["merged"], encoding="utf-8")
        sys.exit(0)
    report = ours_p.with_suffix(ours_p.suffix + ".gitcad-conflict.json")
    report.write_text(canonical_json({"conflicts": result["conflicts"]},
                                     indent=2) + "\n", encoding="utf-8")
    print(f"gitcad-merge: {len(result['conflicts'])} semantic conflict(s) — "
          f"see {report.name}", file=sys.stderr)
    sys.exit(1)
