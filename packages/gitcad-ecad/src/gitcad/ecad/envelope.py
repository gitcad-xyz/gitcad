"""Electrical envelope checking — the hardware type system, v1 (ADR-0015).

ERC's role matrix asks "may these pin *kinds* share a net?"; this module
asks "does the *physics* fit?" — net voltage vs. each pin's absolute
maximum and operating minimum, and rail current draw vs. source capacity.

Net voltages derive from the design deterministically: an explicit
``Schematic.net_specs`` entry wins; otherwise the power-net NAME is parsed
(``+3V3`` -> 3.3, ``5V_PUMP`` -> 5.0, ``GND`` -> 0) — engineers already
encode volts in rail names; a name that parses is a contract.

Coverage is reported, never assumed: a part without ``pin_specs`` produces
no violations and no false confidence — ``pins_with_specs`` in the checks
says how much was actually verified (the null-kernel honesty rule).
"""

from __future__ import annotations

import re

from gitcad.ecad.schematic import Schematic
from gitcad.errors import GitcadError, ValidationReport

_GROUND = {"GND", "AGND", "DGND", "GNDA", "GNDD", "VSS", "0V"}
# +3V3 / 3V3_IN / +5V_PUMP / 12V / +12V0 ...
_VOLT_NAME = re.compile(r"^\+?(\d+)V(\d+)?(?:[_-].*)?$")


def net_voltage(name: str, net_specs: dict | None = None) -> float | None:
    """The net's nominal voltage, or None when the design doesn't say."""
    spec = (net_specs or {}).get(name)
    if spec is not None and "v" in spec:
        return float(spec["v"])
    u = name.upper()
    if u in _GROUND:
        return 0.0
    m = _VOLT_NAME.match(u)
    if m:
        whole, frac = m.group(1), m.group(2)
        return float(f"{whole}.{frac or 0}")
    return None


def check_envelopes(sch: Schematic) -> ValidationReport:
    """Overvoltage / underpowered / rail-overload — code:detail violations."""
    violations: list[str] = []
    pins_with_specs = 0
    nets_with_voltage = 0
    rails: dict[str, dict] = {}

    spec_of = {c.ref: c.attrs.get("pin_specs", {}) for c in sch.components}

    for net, pin_refs in sorted(sch.nets.items()):
        v = net_voltage(net, sch.net_specs)
        if v is not None:
            nets_with_voltage += 1
        draws: list[tuple[str, float]] = []
        sources: list[tuple[str, float]] = []
        for pr in sorted(pin_refs):
            ref, num = pr.split(".", 1)
            spec = spec_of.get(ref, {}).get(num)
            if not isinstance(spec, dict):
                continue
            pins_with_specs += 1
            if v is not None:
                vmax = spec.get("v_abs_max")
                if vmax is not None and v > float(vmax) + 1e-9:
                    violations.append(f"pin-overvoltage:{net}:{pr}:{v:g}>{float(vmax):g}")
                vopmin = spec.get("v_op_min")
                if vopmin is not None and v < float(vopmin) - 1e-9:
                    violations.append(f"pin-underpowered:{net}:{pr}:{v:g}<{float(vopmin):g}")
            if "i_draw_ma" in spec:
                draws.append((pr, float(spec["i_draw_ma"])))
            if "i_source_ma" in spec:
                sources.append((pr, float(spec["i_source_ma"])))
        if sources or draws:
            draw = sum(d for _, d in draws)
            cap = min((c for _, c in sources), default=None)
            rails[net] = {"draw_ma": round(draw, 3),
                          "cap_ma": cap if cap is None else round(cap, 3),
                          "sources": [p for p, _ in sources],
                          "loads": [p for p, _ in draws]}
            if cap is not None:
                rails[net]["utilization"] = round(draw / cap, 3) if cap else None
                if draw > cap + 1e-9:
                    violations.append(
                        f"rail-overload:{net}:draw={draw:g}ma>cap={cap:g}ma")

    return ValidationReport(
        ok=not violations,
        checks={"envelope": "electrical-v1 (ADR-0015)",
                "pins_with_specs": pins_with_specs,
                "nets_with_voltage": nets_with_voltage,
                "rails": {k: f"{r['draw_ma']}/{r['cap_ma']}ma"
                          for k, r in sorted(rails.items())}},
        violations=violations)


def power_budget(sch: Schematic) -> dict[str, dict]:
    """Per-rail draw vs. capacity roll-up — the budget view of the same data.
    Rails are nets that have at least one spec'd source or load."""
    report = check_envelopes(sch)
    out: dict[str, dict] = {}
    for net, pin_refs in sorted(sch.nets.items()):
        v = net_voltage(net, sch.net_specs)
        draws, sources = [], []
        for pr in sorted(pin_refs):
            ref, num = pr.split(".", 1)
            comp = next((c for c in sch.components if c.ref == ref), None)
            spec = (comp.attrs.get("pin_specs", {}) if comp else {}).get(num, {})
            if "i_draw_ma" in spec:
                draws.append((pr, float(spec["i_draw_ma"])))
            if "i_source_ma" in spec:
                sources.append((pr, float(spec["i_source_ma"])))
        if not (draws or sources):
            continue
        draw = sum(d for _, d in draws)
        cap = min((c for _, c in sources), default=None)
        out[net] = {"voltage": v, "draw_ma": round(draw, 3),
                    "cap_ma": cap, "loads": dict(draws), "sources": dict(sources),
                    "utilization": (round(draw / cap, 3) if cap else None),
                    "ok": cap is None or draw <= cap + 1e-9}
    if not out and not report.checks["pins_with_specs"]:
        raise GitcadError(
            "no pin has electrical specs (attrs.pin_specs) — a power budget "
            "over zero data would be a lie; add i_draw_ma/i_source_ma first")
    return out
