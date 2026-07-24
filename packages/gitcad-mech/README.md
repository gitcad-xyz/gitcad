# gitcad-mech

Mechanical package of gitcad.

Provides:

- A parametric document model with a feature tree and stable identity.
- An exact-arithmetic B-rep geometry kernel; geometric decisions use rational
  arithmetic.
- Sketches; extrude, revolve, loft, sweep; fillet, chamfer, shell; patterns;
  sheet metal; weldments; holes with thread specs.
- Associative drawings: projected and section/detail views, dimensions, GD&T,
  weld and surface-finish symbols; SVG, PDF, and DXF output.
- Importers for STEP and parametric part files.

## Install

```
pip install gitcad-mech           # includes the geometry kernel
pip install gitcad-mech[occt]     # add the optional alternative kernel backend
```

The native (compiled) build of the kernel is installed by default on common
platforms; elsewhere the pure-Python build is used.

License: Apache-2.0. Source: https://github.com/gitcad-xyz/gitcad
