# ADR-0003: Stable entity identity (the topological-naming fix)

**Status:** accepted — **foundational, get this right on day one**

## Context

Reference a face as "face 7", let an upstream edit renumber faces, and "face 7"
silently becomes a different face. Every downstream reference corrupts. This is
FreeCAD's most notorious weakness. It is *fatal* to a git workflow, where merge
and rebase reorder operations constantly. Retrofitting a fix later is effectively
impossible — the identity scheme has to be present before any feature stores a
reference.

## Decision

An entity's identity is derived from **construction lineage + a rounded geometric
fingerprint**, never from an ordinal index (`gitcad.identity.IdentityService`).

- `assign(descriptor, lineage)` mints a deterministic, collision-resistant id.
  Same construction → same id on every machine; an unrelated upstream edit does
  not perturb ids of entities it did not touch.
- `resolve(id, candidates)` re-binds a stored id to the best-matching current
  entity after a rebuild, or reports it genuinely gone.
- Geometric quantities are rounded to a tolerance so float noise cannot split an
  identity. Identity heuristics must be **auditable**, not magical.

Feature ids follow the same principle (`Document._mint_id`): a hash of
(op, param-keys, input-ids), with deterministic disambiguation of structural
twins — never a running index.

## Consequences

- Merge/rebase/branch on model text is survivable.
- Any change to identity semantics is a **human-sign-off** change (`CODEOWNERS`)
  and must be accompanied by a migration story, because stored ids are durable.
- This is arguably worth more than the choice of kernel.
