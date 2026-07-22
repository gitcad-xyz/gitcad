# ADR-0008: The Part standard — one unit across all domains

**Status:** accepted — interchange contract; most change-resistant thing we own

## Context

gitcad is mechanical + electrical with **equal weight**, and real products are
heterogeneous assemblies: enclosures containing boards containing sub-assemblies.
An interchange contract must be committed *before* two implementations exist,
not extracted afterward — this is the one place where "let the core emerge"
does not apply.

## Decision

**1. The Part is the universal unit — and an Assembly is just a Part.**

> A **Part** = a manifest (domain-neutral) + a body (domain-specific) + an
> interface (domain-neutral). An **Assembly** is a Part whose body is
> *composition* instead of geometry or netlist.

Recursion falls out: assemblies contain parts of any domain, including other
assemblies, with no special cases.

**2. The manifest (`part.json`)** is owned by core:

```jsonc
{
  "id": "prt_9f2c...",        // stable forever; assigned at creation, never derived from path/name
  "name": "main-board",
  "domain": "ecad",            // mech | ecad | assembly | (open set)
  "version": "1.4.2",          // interface-semver, ADR-0009
  "interface": { ... },        // see below
  "deps": { "prt_...": "^1.4" },
  "body": { ... }              // domain-specific; core never parses foreign bodies
}
```

**3. The interface** is the domain-neutral projection of any part. Assemblies
depend on interfaces, never internals:

- **envelope** — bounding geometry. v1: axis-aligned box `{origin, dx, dy, dz}`
  (machine-checkable fit tests with no kernel); an optional content-addressed
  exact-geometry artifact can accompany it.
- **frames** — named coordinate frames (origin + z/x axes): datums, mounting
  points, connector locations.
- **ports** — typed connection points bound to frames, with an open namespaced
  type vocabulary (`mech.bolt`, `elec.pin`, `elec.connector`, later `therm.*`).
  Core standardizes the *structure*; domains extend the vocabulary.
- **properties** — informational data (mass, part number). Never load-bearing.

**4. Assemblies** place instances by explicit rigid transform and declare
**mates** between ports. v1 deliberately has *no constraint solver*: mates are
**checks** (type compatibility + positional coincidence after transforms), not
solvers. Assembly validation = interface checking; a solver can come later
behind the same data model.

**5. Stable identity extends upward** (ADR-0003): the part `id` and port/frame
*names* are the durable references. An assembly mates `prt_9f2c…#mnt_1`, never
"hole 3".

## Consequences

- Cross-domain co-design is structural: the enclosure mates the PCB's
  `mech.bolt` ports without understanding schematics.
- The manifest schema is CODEOWNERS-protected; every schema change needs a
  migration story.
- Multi-board systems (Altium's separate project type) are just assemblies.
