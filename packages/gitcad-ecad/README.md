# gitcad-ecad

Electrical domain for [**gitcad**](https://gitcad.xyz) — schematic through
fabrication, one git-native substrate.

- **Schematic capture** — netlist-level and sheet-level, with ERC and typed
  electrical-envelope checks (voltage/current specs on interfaces).
- **Board** — multi-layer stackup, tracks/zones/vias (incl. blind/buried),
  net classes, keepouts, DRC with rule packs, connectivity.
- **Schematic ↔ board parity** and back-annotation.
- **Fab outputs** — Gerber (RS-274X), Excellon drill, pick-and-place, IPC-2581,
  BOM.
- **KiCad import** — `.kicad_sch` / `.kicad_pcb` with real wire geometry and
  hierarchical sheet instances.

Pure Python, no third-party runtime dependencies. Install the full system with
`pip install gitcad`.

Apache-2.0 · https://github.com/gitcad-xyz/gitcad
