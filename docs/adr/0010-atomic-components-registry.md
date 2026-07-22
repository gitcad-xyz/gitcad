# ADR-0010: Atomic components and the parts registry

**Status:** accepted (registry implementation staged after core Part machinery)

## Context

ECAD lives and dies on its parts library. KiCad decouples symbols from
footprints and makes the *user* bind them at placement — the binding step is
where the errors live. Altium's unified/atomic component model eliminates that
error class; its weakness is copy-bloat and a subscription wall around library
governance.

## Decision

**1. Atomic at the reference layer, normalized at the storage layer.**
An ECAD component is a Part (`domain: "ecad.component"`) whose body binds
symbol + footprint + 3D model + pin-map + parameters as **one versioned,
locked entity** — but the assets are shared, content-addressed objects, so 400
resistors reference one 0402 footprint rather than embedding 400 copies.

**2. The component's 3D model IS its mech-facing interface** (the `envelope` +
mounting frames of ADR-0008). The atomic model is the hinge of co-design, not a
bolted-on courtesy.

**3. Interface-semver applies:** pins/pads/courtyard are the interface.
Silkscreen tweak = PATCH; added alternate MPN = MINOR; moved copper or changed
pin map = MAJOR. Machine-enforced per ADR-0009.

**4. The registry** is a package registry for parts:
- **Machine gates before human review**: pin-map completeness vs symbol and
  footprint; IPC-7351 land-pattern math; 3D model within courtyard; datasheet
  cross-check (agent re-derives pin table from the PDF); canonical-form lint.
- **Trust tiers on the artifact**: `draft` (machine-checks pass) → `verified`
  (independent agent re-derived from datasheet and matched) → `reviewed`
  (human eyeballed vs datasheet drawing) → `proven` (attested used on a
  manufactured board). Because boards lock components by hash, "this exact
  footprint revision fabbed N times" is a queryable fact.
- **Part data is CC0.** The tool stays Apache-2.0; the library data is a
  separate, maximally reusable corpus. The value we keep is the registry, the
  trust graph, and the verification machinery.
- **Volatile supply data stays out of versioned artifacts.** MPNs and
  lifecycle states are parameters (slow-moving); live stock/pricing is a
  runtime lookup keyed by MPN, never committed.

## Consequences

- Contribution scales through agents (datasheet → draft component) with humans
  promoted to reviewers; the KiCad volunteer-review bottleneck is bypassed.
- Fab capability profiles and rule packs are themselves versioned parts.
- Registry protocol work is staged behind the core Part machinery (ADR-0008/9).
