# gitcad-core

Core package of gitcad, a headless, git-native B-rep CAD system.

Provides:

- Canonical text serialization of models.
- Entity and feature identity derived from construction lineage and geometric
  fingerprint.
- The Part standard: manifest, interface, semantic version, and lockfile,
  shared by the mechanical and electrical packages.
- The report pipeline used to verify and render a build.

Pure Python, no third-party runtime dependencies.

Install the full system with `pip install gitcad`.

License: Apache-2.0. Source: https://github.com/gitcad-xyz/gitcad
