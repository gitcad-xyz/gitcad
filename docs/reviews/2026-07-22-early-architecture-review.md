# Early architecture & code review — 2026-07-22

Two independent passes: a fresh-eyes review agent (which **executed** suspected
bugs against the installed OCCT kernel to verify them) and the maintainer-side
architectural pass. Findings merged, deduplicated, corrected, and ranked.
"Verified" = reproduced, not just read.

Corrections to the agent pass: the working tree *is* a git repo with a
`.gitignore` (agent error), and the docs sync workflow exists in the site repo
(outside the reviewed tree); only its footer wording ("every push" vs 6-hourly
cron) needs adjusting.

## P0 — schema/identity correctness (every serialized document is a migration liability)

1. **Feature ids are ordinal for structural twins** (`document.py:_mint_id`,
   verified). Ids hash `(op, param_keys, inputs)` — not values — so
   `box(1,1,1)` after `box(9,9,9)` gets `_1` by occurrence order; inserting an
   unrelated twin perturbs downstream ids. Violates ADR-0003's own hard rule;
   the existing invariant test only covers the different-op case.
   *Fix:* include param values in the basis (identity survives reordering, not
   revaluing) **or** explicit creation nonces persisted in text. Add a
   twin-reordering invariant test.
2. **`Document.loads` accepts duplicate ids silently; `build()` collapses
   them** (verified) — exactly the state a git merge of two branches produces.
   *Fix:* raise on duplicate id at load. Two lines now; data corruption later.
3. **Canonicalization holes** (all verified): NaN/Infinity serialize as
   non-JSON; `round(-1e-9,6)` → `-0.0` ≠ `0.0` splits identities despite the
   rounding meant to prevent it; `1` vs `1.0` gives equal feature ids but
   different content hashes. *Fix:* one shared canonicalization function
   (reject non-finite, normalize −0.0, floats-always policy) used by
   document/board/manifest, plus invariant tests for each hole.

## P1 — the flagship claims that aren't wired yet

4. **Identity machinery is unwired and unpersisted** — `build()` accepts an
   `IdentityService` and never calls it; `_registry` is in-memory, so any id
   in committed text is a dead reference next process. ADR-0003 says this is
   the un-retrofittable one. *Fix before any document stores an entity ref:*
   persist fingerprint payloads in document text; wire assignment through
   build.
5. **`OcctKernel.fillet` ignores its `edges` selector** — fillets everything,
   silently producing geometry different from what was authored. *Fix now:*
   raise on non-empty selector until identity resolution lands. Silent wrong
   geometry is this project's worst failure mode.
6. **Silent kernel fallback poisons the verification loop** — any OCCT import
   failure silently yields the null kernel, whose `validate()` says `ok=True`
   for everything; MCP then reports all-green on geometry never built.
   *Fix:* explicit-preference failures raise; null validation reports
   `geometry_checked: false` at top level.

## P2 — fab-output correctness (the "never ship a bad package" gate has holes)

7. **Gerber: non-90° rotations emit wrong copper silently** (verified) — pad
   positions rotate, aperture shapes don't; silkscreen courtyards never
   rotate. *Fix:* `Board.validate()` rejects `rot % 90 != 0` in v0.1; rotate
   courtyard corners.
8. **Path traversal via `board.name`** in `export_fab` filenames, reachable
   through the MCP surface (untrusted input per ADR-0006's own threat model).
   *Fix:* name whitelist in validate + containment check on output paths.
9. **Mate/coverage honesty**: mate check is XY-only (a board floating 40mm
   above its bosses "mates"); frame orientation ignored; `pad-outside-outline`
   is a bbox test. *Fix:* check 3D coincidence; and make every
   `ValidationReport.checks` state its method/coverage so `ok=True` can't
   overstate what was checked.

## P3 — trust in the gates

10. **Envelope classifier**: a centered shrink (strictly inside the old box)
    is misclassified MAJOR because any origin motion counts as growth.
    *Fix:* containment semantics — new ⊆ old → MINOR; outside → MAJOR.
11. **`^0.0.z` deviates from the npm/cargo convention it claims** — matches
    any 0.0.x instead of exact-patch. Matters because 0.0.x parts will
    dominate early. *Fix:* exact-match for `^0.0.z`.
12. **Fingerprint hygiene**: violation strings embed designators/dimensions
    (`pad-outside-outline:R1.PAD`, `d=1.500mm`) but `FailureSignature` claims
    transmit-safety; kernel name lacks a version so fingerprints can't
    distinguish OCCT releases. *Fix:* split violations into closed-vocabulary
    `code` + local-only `detail`; fingerprint codes only; version the kernel
    name from the OCP package.

## P4 — seams, API shape, hygiene

13. **OCP imports outside the kernel seam** — `drawing/hlr.py` imports eight
    `OCP.*` modules; `_dispatch` calls `sphere`/`cone` which aren't on the
    published `Kernel` Protocol. *Fix:* add `sphere`/`cone`/`hlr_project` to
    the Protocol (with sign-off), move HLR code into `kernel/occt.py`, and add
    a 10-line invariant test asserting `OCP` is imported only there — the seam
    rule is only as real as its enforcement.
14. **MCP API shape**: every tool threads full model text in and out —
    O(n²) token growth in agent sessions as models grow. Decide the
    session/handle model *before* agents build muscle memory on the current
    signatures. Also: one error-handling decorator returning structured
    `{ok:false, error, fingerprint}` instead of raw `KeyError`s.
15. **ADR-0007 is 2/5 implemented** and the missing parts (scrub + similarity
    check) are the safety-critical ones — the reducer's current output IS a
    subset of the user's real dimensions. Mark `ReductionResult.minimal` as
    not-yet-transmit-safe until they land.
16. Hygiene: single-source `__version__` (currently 3 places); add
    ruff+mypy to CI; docs footer wording (6-hourly, not per-push); start PR
    discipline once a second contributor (human or agent) exists.

## What's genuinely solid

Seam/Protocol structure, null-kernel CI story, three-tier test taxonomy,
CODEOWNERS↔ADR mapping, deterministic Gerber/Excellon (verified byte-stable),
the dependency-free PDF writer (xref offsets and escaping verified correct),
and the ddmin reducer. The bugs cluster precisely where the ADRs say errors
are unaffordable — identity, canonical text, the semver gate — which is the
argument for fixing them this week, not next quarter.
