# regression/ — the disposable tier

Auto-generated tests, one per reduced bug repro, land here. They are **second-class
citizens** by policy (ADR-0005):

- generated from filed bugs by the agent loop, not hand-written;
- pinned to the **public API only** (a regression test that reaches into internals
  cements those internals forever — forbidden);
- **expirable and bulk-invalidatable**: during a major architecture change this
  entire directory may be quarantined or declared obsolete without sign-off.

If a bug in here reveals a property that *should* always hold, a human promotes it
to `tests/invariants/` — where it becomes permanent and architecture-independent.
That promotion is the only path from disposable to durable.

Nothing in this directory may be treated as a specification. The spec lives in
`invariants/` and `golden/`.
