# gitcad-core

Core of [**gitcad**](https://gitcad.xyz) — the agent-first, headless, git-native
CAD substrate. This package is the dependency-free foundation the mechanical and
electrical domains build on:

- **Canonical text** — every model serializes to byte-stable, diff-friendly
  source; geometry is a build artifact, never committed.
- **Stable identity** — entity and feature ids derive from construction lineage
  and geometric fingerprint, never from ordinal position.
- **The Part standard** — one manifest/interface/semver/lockfile model that lets
  mechanical parts, boards, and assemblies compose across domains.
- **Report pipeline** — the verification/render loop that turns a build into a
  reviewable artifact.

Pure Python, no third-party runtime dependencies. Install the full system with
`pip install gitcad`.

Apache-2.0 · https://github.com/gitcad-xyz/gitcad
