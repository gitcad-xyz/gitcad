# ADR-0009: Interface-semver and the lockfile

**Status:** accepted

## Context

Parts evolve. Consumers need to know, *mechanically*, whether an upgrade can
break them — and releases must be reproducible forever. Package managers solved
this shape (cargo/npm); parts are packages.

## Decision

**1. A dependency is two things: an intent constraint + a lock.**

```jsonc
// part.json                       // gitcad.lock (generated, committed)
"deps": { "prt_9f2c": "^1.4" }     "prt_9f2c": { "version": "1.4.2", "content": "blake2b:77ab..." }
```

The lock pins exact canonical-text content hashes → byte-reproducible builds on
any machine, forever. Upgrading is an explicit, reviewable operation
(`gitcad update`), never a surprise. Constraints: `^` (compatible), `~`
(patch-level), exact, `*`.

**2. Semver is measured on the *interface*, not the internals:**

| Bump | Meaning |
|---|---|
| **MAJOR** | interface broke: port/frame removed or moved; port type/spec changed; envelope **grew** |
| **MINOR** | interface grew compatibly: port/frame added; envelope **shrank** |
| **PATCH** | interface byte-identical: internals only |

**3. The bump is machine-enforced.** The interface block is canonical text;
`gitcad.part.interface.classify_change(old, new)` computes the *required* bump
and `check_release` rejects a version number smaller than required. CI runs it
on every part release — an agent cannot mislabel a copper move as a patch.
This is geometric semver (ADR-0004) promoted to the part level.

## Consequences

- "Patch and minor releases cannot break your assembly" is a *guarantee*, not
  a convention — the backbone of trust between teams and for the registry.
- Old boards/assemblies never mutate when a library updates (the failure both
  KiCad and Altium work around); upgrades are diffs.
- Properties (mass, notes) are informational: changing them is PATCH.
