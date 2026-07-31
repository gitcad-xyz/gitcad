"""DOGFOOD: a 3-part ball-and-socket joint (complexity 8).

Part A: ball stud  -- sphere(8) + cylindrical shank, multi-axis flats, cross bore
Part B: socket     -- block with a spherical cavity (sphere subtracted)
Part C: retaining cap -- ring with a stepped (counterbore) retaining bore
Assemble, run interference/clearance checks, export STEP.

I am a USER. Everything below only touches the public seam API.
"""
from __future__ import annotations
import math, tempfile, os, traceback

from gitcad.kernel import get_kernel

k = get_kernel()
print("kernel:", getattr(k, "name", type(k).__name__))

LOG = []

def op(label, fn, want_provenance=False, allow_sampled=False):
    """Run one op, record outcome verbatim."""
    prev = getattr(k, "allow_sampled", False)
    if allow_sampled:
        k.allow_sampled = True
    try:
        res = fn()
        entry = {"op": label, "outcome": "ok"}
        LOG.append(entry)
        print(f"\n[OK] {label}")
        return res
    except Exception as exc:  # noqa: BLE001
        stage = getattr(exc, "stage", "") or getattr(getattr(exc, "signature", None), "diagnostic", "")
        msg = str(exc)
        LOG.append({"op": label, "outcome": type(exc).__name__,
                    "stage": stage, "msg": msg})
        print(f"\n[{type(exc).__name__}] {label}\n   stage={stage!r}\n   msg={msg!r}")
        return None
    finally:
        if allow_sampled:
            k.allow_sampled = prev

def report(label, shape):
    """measure + mass_props(provenance) + validate(watertight)."""
    if shape is None:
        print(f"   -- {label}: no shape")
        return
    try:
        m = k.measure(shape)
        print(f"   measure: {m}")
    except Exception as e:
        print(f"   measure CRASH: {type(e).__name__}: {e}")
        m = {}
    try:
        mp = k.mass_props(shape)
        print(f"   mass_props: volume={mp.get('volume')} provenance={mp.get('provenance')!r} "
              f"centroid={mp.get('centroid')}")
    except Exception as e:
        print(f"   mass_props CRASH: {type(e).__name__}: {e}")
        mp = {}
    try:
        v = k.validate(shape)
        print(f"   validate.ok={v.ok} checks={v.checks} violations={v.violations}")
    except Exception as e:
        print(f"   validate CRASH: {type(e).__name__}: {e}")
    return m, mp

print("="*70, "\nPART A — BALL STUD\n", "="*70)

R_BALL = 8.0
ball = op("A.ball = sphere(8)", lambda: k.sphere(R_BALL))
report("ball", ball)

# closed form sphere
print(f"   [xcheck] sphere V = 4/3 pi R^3 = {4/3*math.pi*R_BALL**3:.4f}")

# shank up the +z axis
shank = op("A.shank = cylinder(4,24)", lambda: k.cylinder(4.0, 24.0))
stud = op("A.stud = union(ball, shank)", lambda: k.boolean("union", ball, shank))
report("stud(ball+shank)", stud)

# ---- multi-axis flats (ADR-0023 sphere cap on any axis) ----
def half_space(axis, cut, keep_low):
    # big box, one live wall at `cut` on `axis`
    lo = [-40.0, -40.0, -40.0]; hi = [40.0, 40.0, 40.0]
    if keep_low: lo[axis] = cut
    else:        hi[axis] = cut
    box = k.box(hi[0]-lo[0], hi[1]-lo[1], hi[2]-lo[2])
    return k.transform(box, translate=tuple(lo))

flatx = op("A.flat +x (cut x>6) [sphere cap on X]",
           lambda: k.boolean("cut", stud, half_space(0, 6.0, keep_low=True)))
report("stud+flatX", flatx)
# spherical cap closed form: h = R-6 = 2
h = R_BALL - 6.0
print(f"   [xcheck] cap removed V = pi h^2 (3R-h)/3 = {math.pi*h*h*(3*R_BALL-h)/3:.4f}")

flaty = op("A.flat -y (cut y<-6) [sphere cap on Y]",
           lambda: k.boolean("cut", flatx, half_space(1, -6.0, keep_low=False)))
report("stud+flatX+flatY", flaty)

# ---- cross bore through the ball (curved boolean: sphere minus cylinder) ----
def x_cylinder(radius, length):
    c = k.cylinder(radius, length)                 # along +z, z in [0,length]
    c = k.transform(c, rotate_axis=(0,1,0), rotate_deg=90)  # now along x
    return c
xb = x_cylinder(1.5, 60.0)
print("   [dbg] cross-bore tool bbox:", op("dbg bbox xbore", lambda: k.bbox(xb)))
# center it on origin along x
xb = op("A.crossbore tool centered", lambda: k.transform(x_cylinder(1.5, 60.0), translate=(-30.0,0.0,0.0)))
print("   [dbg] centered tool bbox:", None if xb is None else k.bbox(xb))
stud_bored = op("A.stud through-bored (cut cylinder r1.5 along X)",
                lambda: k.boolean("cut", flaty, xb))
report("PART A final (ball stud)", stud_bored)
# napkin-ring closed form for a full central cylinder
a = 1.5
removed = 4/3*math.pi*(R_BALL**3 - (R_BALL**2 - a**2)**1.5)
print(f"   [xcheck] full central drill removed V = 4/3 pi (R^3-(R^2-a^2)^1.5) = {removed:.4f} "
      f"(approx; real bore also crosses the flats)")

PART_A = stud_bored if stud_bored is not None else flaty

print("="*70, "\nPART B — SOCKET (spherical cavity)\n", "="*70)

block = op("B.block = box(30,30,24)", lambda: k.box(30,30,24))
R_CAV = 8.2   # 0.2mm radial clearance vs ball
cav_tool = op("B.cavity tool = sphere(8.2) @ (15,15,24)",
              lambda: k.transform(k.sphere(R_CAV), translate=(15,15,24)))
socket = op("B.socket = block CUT sphere-cavity [sphere-minus-sphere-region]",
            lambda: k.boolean("cut", block, cav_tool))
report("PART B (socket)", socket)
# cavity is a hemisphere bowl (center on top face): removed = half sphere
print(f"   [xcheck] cavity removed ~ half sphere = 2/3 pi R^3 = {2/3*math.pi*R_CAV**3:.4f}")
print(f"   [xcheck] block V = {30*30*24}, socket V should ~ {30*30*24 - 2/3*math.pi*R_CAV**3:.4f}")
PART_B = socket

print("="*70, "\nPART C — RETAINING CAP (stepped bore ring)\n", "="*70)

cap_body = op("C.body = cylinder(14,8)", lambda: k.cylinder(14, 8))
# lower counterbore r8.2 z[0,4] ; upper retaining bore r7 z[4,9]
cbore = op("C.counterbore r8.2 z[0,4]",
           lambda: k.boolean("cut", cap_body, k.cylinder(8.2, 4)))
cap = op("C.retaining bore r7 z[4,9]",
         lambda: k.boolean("cut", cbore, k.transform(k.cylinder(7, 5), translate=(0,0,4))))
report("PART C (cap)", cap)
PART_C = cap

print("="*70, "\nASSEMBLE — compound + placement\n", "="*70)

# placement transforms in the assembly frame
# socket at origin; ball center at (15,15,24); shank up; cap on socket top.
PLACE = {
    "socket": ((0.0, 0.0, 0.0), 0.0),
    "ball":   ((15.0, 15.0, 24.0), 0.0),
    "cap":    ((15.0, 15.0, 24.0), 0.0),
}
def placed(shape, tr):
    (t, rz) = tr
    return k.transform(shape, translate=t, rotate_axis=(0,0,1), rotate_deg=rz)

pieces = {}
if PART_A: pieces["ball"] = placed(PART_A, PLACE["ball"])
if PART_B: pieces["socket"] = placed(PART_B, PLACE["socket"])
if PART_C: pieces["cap"] = placed(PART_C, PLACE["cap"])

comp = op("compound(ball, socket, cap)", lambda: k.compound(list(pieces.values())))
report("assembly compound", comp)

print("="*70, "\nINTERFERENCE / CLEARANCE CHECKS\n", "="*70)
from gitcad.part import check_interference

inst = {}
if PART_A: inst["ball"]   = (PART_A, PLACE["ball"][0], PLACE["ball"][1])
if PART_B: inst["socket"] = (PART_B, PLACE["socket"][0], PLACE["socket"][1])
if PART_C: inst["cap"]    = (PART_C, PLACE["cap"][0], PLACE["cap"][1])

def run_interf(label, instances, **kw):
    try:
        r = check_interference(k, instances, **kw)
        print(f"\n[interference] {label}: ok={r.ok}")
        print(f"   checks: {r.checks}")
        for v in r.violations:
            print(f"   VIOLATION: {v}")
        LOG.append({"op": f"interference:{label}", "outcome": "ok" if r.ok else "clash",
                    "violations": r.violations})
        return r
    except Exception as exc:  # noqa: BLE001
        print(f"\n[interference CRASH] {label}: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        LOG.append({"op": f"interference:{label}", "outcome": type(exc).__name__, "msg": str(exc)})
        return None

# 1) full assembly, exact tol
run_interf("full-assembly EXACT", inst)
# 2) allow sampled (sphere booleans may need it)
k.allow_sampled = True
run_interf("full-assembly EXACT (allow_sampled)", inst)
k.allow_sampled = False
# 3) ball-vs-socket only (the spherical fit)
if PART_A and PART_B:
    run_interf("ball<->socket fit", {kk: inst[kk] for kk in ("ball","socket")}, allow_sampled=True) \
        if False else run_interf("ball<->socket fit",
                                 {"ball": inst["ball"], "socket": inst["socket"]})
# 4) ball-vs-cap only (retention clearance)
if PART_A and PART_C:
    run_interf("ball<->cap retention", {"ball": inst["ball"], "cap": inst["cap"]})

# 5) DELIBERATE clash — cap with too-small retaining bore (r6 < ball 6.93 @ z=28)
print("\n--- deliberate clash variant: retaining bore r6 (should CLASH) ---")
cap_bad_body = k.cylinder(14, 8)
cap_bad = k.boolean("cut", cap_bad_body, k.cylinder(8.2, 4))
cap_bad = k.boolean("cut", cap_bad, k.transform(k.cylinder(6, 5), translate=(0,0,4)))
run_interf("ball<->cap_bad (bore r6)",
           {"ball": inst["ball"], "cap": (cap_bad, PLACE["cap"][0], PLACE["cap"][1])})

# 6) ball seated too deep into socket floor (ball down 3mm -> should CLASH socket)
if PART_A and PART_B:
    run_interf("ball sunk 3mm into socket",
               {"ball": (PART_A, (15,15,21.0), 0.0), "socket": inst["socket"]})

print("="*70, "\nEXPORT STEP\n", "="*70)
tmp = tempfile.mkdtemp()
step_path = os.path.join(tmp, "balljoint.step")
op(f"export_step(compound) -> {step_path}", lambda: k.export_step(comp, step_path))
if os.path.exists(step_path):
    print(f"   STEP size = {os.path.getsize(step_path)} bytes")
# also per-part
for nm, sh in (("ballstud", PART_A), ("socket", PART_B), ("cap", PART_C)):
    if sh is None: continue
    p = os.path.join(tmp, f"{nm}.step")
    op(f"export_step({nm})", lambda sh=sh, p=p: k.export_step(sh, p))
    if os.path.exists(p):
        print(f"   {nm}.step = {os.path.getsize(p)} bytes")

print("="*70, "\nHIGH-LEVEL Assembly API (part.Assembly / mate / exploded)\n", "="*70)
# Try the declarative assembly path too (manifest-level).
try:
    from gitcad.part.assembly import Assembly
    asm = Assembly("ball-and-socket")
    print("   Assembly created; add() needs PartManifest (not raw Shape).")
except Exception as e:
    print("   Assembly import failed:", e)

print("\n" + "="*70 + "\nSUMMARY LOG\n" + "="*70)
for e in LOG:
    print(e)
