# 0016. Branch-and-merge design exploration: semantic 3-way merge

Date: 2026-07-23
Status: Accepted

## Context

Incumbent CAD cannot branch. Files are binary, identity is ordinal, so two
people (or two agents) cannot edit the same design in parallel and combine
the results — the industry's answer is file locking and PLM check-out. That
forecloses the most powerful design workflow git ever enabled: spawn N
variants, evaluate all of them against the same gates, merge the winners.

gitcad already has the two prerequisites nobody else has:

1. **Canonical text** (ADR-0004) — designs diff line-by-line, but more
   importantly they parse, so we can merge *meaning* instead of lines.
2. **Stable identity** (ADR-0003) — features and entities keep their ids
   across edits, so "both branches touched the same feature" is decidable,
   which is exactly the question a 3-way merge must answer.

## Decision

**Merge at the semantic unit, never the text line.** A git merge driver
(`gitcad-merge`, wired via ``.gitattributes``) performs classic 3-way merge
(base/ours/theirs) where the units are:

- **Models**: features, keyed by stable feature id. Compare canonical JSON
  per feature against base. One side changed → take it; both changed
  identically → take it; both changed differently → **conflict naming the
  feature id and op**; modify vs delete → conflict; add/add with the same
  id but different content → conflict. Merged feature order: base order,
  then ours-added, then theirs-added, then a stable topological pass so
  every feature's inputs precede it (build-order validity is restored
  mechanically, not hoped for).
- **Schematics**: components keyed by ref (same 3-way rule on canonical
  content), and connectivity keyed by **pin** — each pin's net assignment
  is a 3-way cell, so a net rename (all pins move together) merges cleanly
  and only "the same pin moved to two different nets" conflicts.
  ``net_specs`` merge per key.
- Boards and parts: v1 falls back to whole-document 3-way (identical-side
  shortcuts, conflict when both sides changed) — honest, not silently
  line-merged. Component/track-level board merge is a later stage.

**Conflicts are structured data, not markers.** On conflict the driver
leaves "ours" in the worktree, writes a ``<file>.gitcad-conflict.json``
report naming every conflicted unit with both candidate values, and exits
nonzero — git marks the path unmerged. An agent (or human) resolves by
editing the document and ``git add``, exactly like code. Text-level
conflict markers inside canonical JSON would be worse than useless: they
make the document unparseable for every tool including the resolver.

**A merge must rebuild.** The driver reloads its own output through the
document's parser before writing (a merge that doesn't parse is a bug in
the driver, never shipped state). Geometry/ERC consequences of a clean
merge are ``gitcad-review``'s job on the merge commit — merging and
verifying stay separate, per the writer/checker rule.

**Exploration is the same machinery pointed sideways.** N branches, one
base: run the review/check suite per branch (existing ``review_range``)
and tabulate. No new engine — the merge driver makes the branches
combinable, the checks make them comparable.

## Consequences

- Two agents can work the same model concurrently and merge, conflicting
  only when they touched the same feature — the file-lock era ends here.
- The identity service becomes even more load-bearing: changing id
  semantics now also invalidates merge history reasoning (already flagged
  human-sign-off territory in ADR-0003; doubly so now).
- Order restoration via topological sort means a clean merge can reorder
  features relative to either parent; ids (lineage-based) do not change,
  and the rebuild gate catches any dependency the sort cannot satisfy.
- Boards conflict coarsely for now; that is a scope statement, not a
  limitation of the approach.
