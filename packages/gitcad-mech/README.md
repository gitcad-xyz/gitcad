# gitcad-mech

Mechanical domain for [**gitcad**](https://gitcad.xyz) — the parametric document
model and geometry kernels.

- **Document model** — feature tree with stable identity; builds to a solid and a
  reviewable report.
- **Exact kernel by default** — ships [`forgekernel`](https://pypi.org/project/forgekernel/),
  a from-scratch B-rep kernel whose topological decisions are made in exact
  rational arithmetic (ℚ), never by floating-point epsilon. OCCT
  (`cadquery-ocp`) is available as an independent oracle / fallback.
- **Sketches, extrude/revolve, loft, sweep, fillet/chamfer, shell, patterns,
  sheet metal, weldments, holes with thread specs.**
- **Associative drawings** — HLR views, section/detail views, dimensions, GD&T,
  weld & surface-finish symbols → SVG/PDF/DXF.
- **Importers** — STEP, FCStd (parametric tree), with verified feature recovery.

```bash
pip install gitcad-mech          # exact kernel + native accelerator (default where a wheel exists)
pip install gitcad-mech[occt]    # + OCCT oracle/fallback (cadquery-ocp)
```

Apache-2.0 · https://github.com/gitcad-xyz/gitcad
