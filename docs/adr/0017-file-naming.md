# 0017. File naming: .gitcad is the product, extensions are roles

Date: 2026-07-23
Status: Accepted

## Context

Design files carried ``.json`` suffixes (``enclosure.gitcad.json``,
``main.schematic.json``), which made a project directory read like a config
dump, and ``.gitcad`` named the *mechanical feature-tree document* — the
least product-like thing in the tree. User ruling: a directory listing
should explain itself, and ``.gitcad`` should mean THE project.

## Decision

Json-free, role-named extensions. Kind detection stays **content-based**
(the ``schema`` field) everywhere — extensions scope discovery and tell
humans what they're looking at; old ``*.json`` names remain accepted
forever.

| extension | role |
|-----------|------|
| ``name.gitcad`` | **THE project root**: the top-level assembly manifest whose instances are the product's parts — mechanical and electrical alike (an assembly IS a part, ADR-0008; a board-backed part is an instance like any other). One per project. |
| ``name.part`` | any other part manifest (subassemblies included) |
| ``name.model`` | a mechanical feature-tree document — how one part gets its shape, never the product. ``model_to_part`` emits ``<name>.model``. |
| ``name.sch`` | schematic (gitcad canonical; ``.kicad_sch`` stays the import format) |
| ``name.board`` | board layout |
| ``requirements.reqs`` | executable requirements (ADR: requirements-as-code) |
| ``<id>.lot`` | fab-lot provenance record |

``gitcad init`` scaffolds this shape and seeds ``<name>.gitcad`` as an
empty product assembly, so the root exists from commit one.

## Consequences

- Directory listings are self-describing: one ``.gitcad`` = the product,
  everything else names its role.
- No migration: content detection means every existing ``*.json`` document
  keeps working; new tools and generators emit the new names.
- ``.sch`` collides with legacy EAGLE/KiCad-4 schematic extensions in the
  wild; content sniffing resolves it (a non-gitcad ``.sch`` reports an
  honest per-file error in discovery, never a crash).
