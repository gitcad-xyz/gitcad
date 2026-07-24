# gitcad-ecad

Electrical package of gitcad.

Provides:

- Schematic capture at netlist and sheet level, with ERC and typed
  electrical-envelope checks.
- A multi-layer board model: tracks, zones, vias (including blind/buried), net
  classes, keepouts, DRC, and connectivity.
- Schematic/board parity and back-annotation.
- Fabrication outputs: Gerber, Excellon drill, pick-and-place, IPC-2581, BOM.
- Importers for common schematic and board files.

Pure Python, no third-party runtime dependencies.

Install the full system with `pip install gitcad`.

License: Apache-2.0. Source: https://github.com/gitcad-xyz/gitcad
