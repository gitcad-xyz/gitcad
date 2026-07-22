# 0015. A type system for hardware: interfaces carry envelopes, connections type-check

Date: 2026-07-23
Status: Accepted

## Context

Incumbent tools check *roles* (an output driving an output) but not
*envelopes* (5V driving a 3.6V-max pin), because their part libraries are
drawings with strings attached. gitcad's parts are MPN-atomic with
machine-readable properties (ADR-0010), its ports are typed (ADR-0008), and
its checks run headless in CI. That combination makes the missing check
possible: **connecting two interfaces is a typed operation, and a connection
outside either side's envelope is a design-time error** — the class of bug
that today survives until bring-up smoke.

## Decision

Interfaces gain machine-checkable **envelopes**; checks compare envelopes
across every connection. Staged by domain:

### v1 (this ADR, implemented now): electrical envelopes

Pin-level specs ride in the component's free-form ``attrs`` under a
documented key — no schema change, additive and optional:

```
attrs["pin_specs"] = {
  "<pin number>": {
    "v_abs_max": 3.6,      # absolute maximum voltage on this pin
    "v_op_min": 2.7,       # minimum operating voltage (power pins)
    "i_draw_ma": 12,       # current this pin draws from its rail
    "i_source_ma": 150,    # current this pin can source (regulator outputs)
  }, ...
}
```

Net voltages derive from the design itself, deterministically:

1. explicit ``net_specs`` (optional, additive field on the schematic:
   ``{"VBAT": {"v": 3.7}}``) always wins;
2. else the power-net **name** is parsed — engineers already encode volts
   there: ``+3V3`` → 3.3, ``+5V_PUMP`` → 5.0, ``12V`` → 12.0, ``GND``/
   ``AGND``/``VSS`` → 0. A name that parses is a contract, not a comment.

Checks (``ecad/envelope.py``, code:detail violations, transmit-safe):

- **pin-overvoltage** — net voltage exceeds a connected pin's ``v_abs_max``
- **pin-underpowered** — a power pin's ``v_op_min`` exceeds its rail
- **rail-overload** — Σ ``i_draw_ma`` on a rail exceeds the minimum
  ``i_source_ma`` among its sources; utilization reported per rail even
  when green (a 96%-loaded rail is information)

Specs are optional everywhere: a part without specs produces no violations
and no false confidence — coverage is REPORTED (pins-with-specs count) so
"all green" cannot be confused with "nothing checked" (same honesty rule as
the null kernel's ``geometry_checked: False``).

### v2 (designed, later): mechanical fits

The same pattern on mech ports: thread class + engagement length, press-fit
interference class vs. material, torque spec vs. boss. Envelope keys on
``Port.spec``; the interference engine already computes the geometry.

### Budgets (with v1): roll-ups as checks

``power_budget(schematic)`` returns per-rail draw vs. capacity. Mass and
cost roll-ups follow the same shape on the mech/BOM side (already have
``model_mass`` and ``assembly_bom``); requirements-as-code (a future ADR)
will bind these to named limits.

## Consequences

- Registry parts become more valuable as they gain specs — a datasheet
  fact transcribed once protects every design that ever places the part.
  Trust tiers (ADR-0010) apply: spec'd + reviewed parts outrank bare ones.
- Net names become load-bearing where they already were by convention.
  ``net_specs`` exists precisely for the exceptions (VBAT, mid-rails).
- No schema break: ``pin_specs``/``net_specs`` are additive and optional;
  documents without them are unchanged byte-for-byte.
- ERC's role matrix and the envelope check stay separate reports — roles
  are topology, envelopes are physics; a design can pass one and fail the
  other, and the violation names say which.
