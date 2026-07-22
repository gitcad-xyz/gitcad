"""Demo: a drilled mounting plate, end to end — model → verify → STEP + drawing.

Run:  python examples/bracket.py [outdir]
Needs the OCCT kernel:  pip install "gitcad[occt]"
"""

import sys
from pathlib import Path

from gitcad.mcp.server import REGISTRY as tools

out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
out.mkdir(exist_ok=True)

# Build: 60x40x8 plate with two Ø6.4 mounting holes.
m = tools["model_new"]()["model"]
r = tools["feature_add"](model=m, op="box", params={"dx": 60, "dy": 40, "dz": 8})
m, plate = r["model"], r["feature_id"]

holes = []
for x, y in ((12, 12), (48, 28)):
    r = tools["feature_add"](model=m, op="cylinder", params={"radius": 3.2, "height": 8})
    m, cyl = r["model"], r["feature_id"]
    r = tools["feature_add"](model=m, op="move", params={"translate": [x, y, 0]}, inputs=[cyl])
    m, moved = r["model"], r["feature_id"]
    holes.append(moved)

body = plate
for hole in holes:
    r = tools["feature_add"](model=m, op="boolean", params={"kind": "cut"}, inputs=[body, hole])
    m, body = r["model"], r["feature_id"]

# Verify — never ship unchecked geometry.
validation = tools["model_validate"](model=m)
assert all(v["ok"] for v in validation["results"].values()), validation
measures = tools["model_measure"](model=m)
print(f"kernel={measures['kernel']}  volume={measures['measures'][body]['volume']:.1f} mm^3")

# Manufacturing outputs.
print(tools["model_export"](model=m, path=str(out / "bracket.step"), fmt="step"))
print(tools["model_export"](model=m, path=str(out / "bracket.stl"), fmt="stl"))
print(tools["model_drawing"](model=m, path=str(out / "bracket.pdf"), title="bracket 60x40x8"))
print(tools["model_drawing"](model=m, path=str(out / "bracket.svg"), title="bracket 60x40x8"))
(out / "bracket.gitcad.json").write_text(m, newline="\n")
print(f"model source saved: {out / 'bracket.gitcad.json'}")
