# ADR-0004: Text is source, geometry is a build artifact

**Status:** accepted

## Context

Git fails for CAD today for one reason: files are opaque binary blobs — no diff,
no blame, no meaningful merge. We want git as the genuine backbone (versioning,
branching, PRs, rollback), not a blob store.

## Decision

- The **model is text**: a feature tree serialized canonically (deterministic
  JSON today; a friendlier surface syntax may layer on later). It diffs, blames,
  branches, and merges like code. `Document.dumps()` is byte-stable for equal
  documents — a hard requirement, enforced by an invariant test.
- **Geometry is a build artifact**: `.brep`, STEP, glTF, PDF, DXF are *generated*
  by building the model against a kernel. They are content-addressed via
  `Storage.put_artifact`, cached, and **never committed as source**.
- Because we own the format we get **semantic diff for free**: mass/volume delta,
  added/removed features, before/after renders in a PR.

## Consequences

- Model migrations are **codemods** over text — only possible because source is
  text. Kernel swaps use shadow-run: build old vs new behind the seam, diff the
  resulting geometry, cut over when divergence is acceptable.
- **Geometric semver**: a change that alters geometry output is *breaking* even if
  the API signature is unchanged; detected by hashing corpus geometry in CI.
- `.gitignore` excludes generated geometry; CI produces and caches it.
