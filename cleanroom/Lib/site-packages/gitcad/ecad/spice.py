"""Simulation as tests, v1 (roadmap: sim-as-test) — SPICE from the schematic.

``to_spice`` exports the netlist SPICE-ready: ground nets become node 0,
R/C/L/V/I elements derive from ref + value, diodes get a default model,
and anything else must bring its own card via ``attrs["spice"]`` — parts
without one are REPORTED as unmodeled, never silently dropped (a sim over
a half-modeled circuit would be a lie wearing a plot).

``sim_check`` runs ngspice in batch and asserts node voltages against
declared ranges — "the LED node sits at 2.1±0.2 V" becomes a check that
runs on every commit, exactly like a unit test. No ngspice installed ->
a loud, actionable error (the null-kernel honesty rule, again).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from gitcad.ecad.envelope import net_voltage
from gitcad.ecad.schematic import Schematic
from gitcad.errors import GitcadError, ValidationReport

_GROUND = {"GND", "AGND", "DGND", "GNDA", "GNDD", "VSS", "0V"}

_VALUE = re.compile(r"^(\d+(?:\.\d+)?)\s*(T|G|MEG|K|M|U|N|P|F)?\s*(OHM|R|F|H|A|V)?$",
                    re.IGNORECASE)


def _spice_value(value: str) -> str | None:
    """'4.7k'/'330R'/'100nF' -> SPICE-legal value, or None if unparseable."""
    m = _VALUE.match(value.strip().replace("Ω", "ohm"))
    if not m:
        return None
    num, prefix, _unit = m.groups()
    return num + (prefix or "")


def _node(net: str) -> str:
    return "0" if net.upper() in _GROUND else re.sub(r"[^A-Za-z0-9_+-]", "_", net)


def to_spice(sch: Schematic, *, title: str | None = None) -> tuple[str, dict]:
    """(netlist text, report). Report lists modeled and unmodeled refs."""
    net_of: dict[str, str] = {}
    for net, prs in sch.nets.items():
        for pr in prs:
            net_of[pr] = net

    lines = [f"* {title or sch.name} — exported by gitcad"]
    modeled: list[str] = []
    unmodeled: list[str] = []
    need_dmodel = False

    for comp in sorted(sch.components, key=lambda c: c.ref):
        pins = [f"{comp.ref}.{p.number}" for p in comp.pins]
        nodes = [_node(net_of.get(pr, f"_nc_{pr}")) for pr in pins]
        card = comp.attrs.get("spice", {}).get("card") if isinstance(
            comp.attrs.get("spice"), dict) else None
        letter = comp.ref[0].upper()
        if card:
            # custom card: {ref} and {n1}..{nk} substitute; models via
            # attrs["spice"]["model"] appended once below
            sub = card.format(ref=comp.ref,
                              **{f"n{i+1}": n for i, n in enumerate(nodes)})
            lines.append(sub)
            modeled.append(comp.ref)
        elif letter in "RCLVI" and len(nodes) == 2:
            val = _spice_value(comp.value or "")
            if val is None:
                unmodeled.append(f"{comp.ref} (unparseable value {comp.value!r})")
                continue
            lines.append(f"{comp.ref} {nodes[0]} {nodes[1]} {val}")
            modeled.append(comp.ref)
        elif letter == "D" and len(nodes) == 2:
            lines.append(f"{comp.ref} {nodes[0]} {nodes[1]} DGEN")
            need_dmodel = True
            modeled.append(comp.ref)
        else:
            unmodeled.append(f"{comp.ref} (no spice card; kind {letter})")

    # power rails with derivable voltage become ideal sources automatically —
    # the same name-contract the envelope checker uses (ADR-0015)
    rail_idx = 0
    for net in sorted(sch.nets):
        v = net_voltage(net, sch.net_specs)
        if v and _node(net) != "0":
            rail_idx += 1
            lines.append(f"VRAIL{rail_idx} {_node(net)} 0 {v:g}")

    models = sorted({comp.attrs["spice"]["model"]
                     for comp in sch.components
                     if isinstance(comp.attrs.get("spice"), dict)
                     and comp.attrs["spice"].get("model")})
    lines.extend(models)
    if need_dmodel:
        lines.append(".model DGEN D(Is=2.52e-9 N=1.752)")
    lines.append(".end")
    report = {"modeled": sorted(modeled), "unmodeled": sorted(unmodeled),
              "auto_rails": rail_idx}
    return "\n".join(lines) + "\n", report


def _find_ngspice() -> str | None:
    import shutil

    exe = shutil.which("ngspice")
    if exe:
        return exe
    for cand in (Path("C:/Program Files/ngspice/bin/ngspice.exe"),
                 Path("C:/Program Files (x86)/ngspice/bin/ngspice.exe")):
        if cand.is_file():
            return str(cand)
    return None


def sim_check(sch: Schematic, checks: list[dict]) -> ValidationReport:
    """Operating-point simulation with assertions:
    checks = [{"node": "OUT", "min": 3.2, "max": 3.4}, ...].
    Violations follow code:detail; unmodeled parts are violations too — a
    green sim over a partial circuit must be impossible."""
    exe = _find_ngspice()
    if exe is None:
        raise GitcadError(
            "ngspice not found — install it (ngspice.sourceforge.io) or add "
            "it to PATH; sim_check refuses to pretend")
    netlist, report = to_spice(sch)
    violations = [f"sim-unmodeled:{u}" for u in report["unmodeled"]]

    want = {c["node"] for c in checks}
    control = ("\n.control\nop\n"
               + "\n".join(f"print v({_node(n)})" for n in sorted(want))
               + "\nquit\n.endc\n")
    text = netlist.replace("\n.end\n", control + ".end\n")
    with tempfile.TemporaryDirectory() as td:
        cir = Path(td) / "check.cir"
        cir.write_text(text, encoding="utf-8")
        proc = subprocess.run([exe, "-b", str(cir)], capture_output=True,
                              text=True, timeout=60)
    got: dict[str, float] = {}
    for m in re.finditer(r"v\(([\w+-]+)\)\s*=\s*([-+0-9.eE]+)", proc.stdout):
        got[m.group(1).upper()] = float(m.group(2))

    for c in checks:
        node = _node(c["node"]).upper()
        if node not in got:
            violations.append(f"sim-node-missing:{c['node']}")
            continue
        v = got[node]
        if "min" in c and v < c["min"] - 1e-12:
            violations.append(f"sim-under:{c['node']}:{v:g}<{c['min']:g}")
        if "max" in c and v > c["max"] + 1e-12:
            violations.append(f"sim-over:{c['node']}:{v:g}>{c['max']:g}")

    return ValidationReport(
        ok=not violations,
        checks={"simulator": "ngspice", "analysis": "op",
                "asserted_nodes": len(checks),
                "measured": {k: round(v, 6) for k, v in sorted(got.items())},
                "modeled": len(report["modeled"])},
        violations=violations)
