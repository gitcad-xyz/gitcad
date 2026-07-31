"""DOGFOOD: a planetary gear set — sun, 3 planets (circular pattern), carrier
with pins + bolt circle, internal ring gear, housing. Push assembly + patterns
+ whole-assembly interference. Track timings, outcomes, allow_sampled use.

USER code only — no edits to packages/ or src/.
"""
from __future__ import annotations
import math, time, tempfile, os, traceback

from gitcad.kernel.ref import RefKernel
from gitcad.document import Document, Feature
from gitcad.part import Assembly, PartManifest, check_interference
from gitcad.part.interface import Interface, Frame, Port
from gitcad.errors import KernelError, GitcadError

k = RefKernel()
LOG = []
def op(label, fn, note=""):
    t0 = time.perf_counter()
    try:
        r = fn()
        dt = time.perf_counter() - t0
        LOG.append((label, "ok", dt, note))
        print(f"[ok    {dt*1000:8.1f}ms] {label}  {note}")
        return r
    except KernelError as e:
        dt = time.perf_counter() - t0
        stage = getattr(e, "stage", "") or getattr(getattr(e, "signature", None), "diagnostic", "")
        msg = f"REFUSED stage={stage!r}: {e}"
        LOG.append((label, "refused", dt, msg))
        print(f"[REFUSE{dt*1000:8.1f}ms] {label}  {msg}")
        return None
    except Exception as e:
        dt = time.perf_counter() - t0
        msg = f"{type(e).__name__}: {e}"
        LOG.append((label, "CRASH", dt, msg))
        print(f"[CRASH {dt*1000:8.1f}ms] {label}  {msg}")
        traceback.print_exc()
        return None

def summ(shape, label):
    """measure + validate + watertight for a built part."""
    m = op(f"measure({label})", lambda: k.measure(shape))
    v = op(f"validate({label})", lambda: k.validate(shape))
    if m: print(f"        vol={m.get('volume'):.4f}")
    if v is not None:
        print(f"        validate.ok={v.ok}  watertight={getattr(v,'checks',{})}")
    return m, v

# ---- gear geometry (module design) -----------------------------------------
M = 2.0
Zs, Zp = 20, 16
Zr = Zs + 2*Zp                 # 52
rs, rp, rr = M*Zs/2, M*Zp/2, M*Zr/2   # 20, 16, 52 pitch radii
center_dist = rs + rp          # 36 -> planet orbit radius
print(f"design: Zs={Zs} Zp={Zp} Zr={Zr}  rs={rs} rp={rp} rr={rr} orbit={center_dist}")
add = M  # addendum
sun_out, planet_out = rs+add, rp+add    # 22, 18 blank outer radii
GEAR_T = 12.0  # gear face width / thickness

print("\n=== PART 1: SUN GEAR (blank + bore + keyway + lightening holes) ===")
def build_sun():
    doc = Document()
    blank = doc.add(Feature(op="cylinder", params={"radius": sun_out, "height": GEAR_T}))
    # bore
    doc.add(Feature(op="hole", params={"x":0,"y":0,"top_z":GEAR_T,"diameter":10,"depth":GEAR_T}, inputs=[blank]))
    return doc
sun_doc = build_sun()
sun = op("sun.build", lambda: sun_doc.build(k).final(sun_doc))
if sun: summ(sun, "sun")

# keyway: cut a small rect slot from the bore wall
print("\n-- sun keyway (rect cut) --")
def build_sun_keyway():
    doc = build_sun()
    feats = doc.features
    base = feats[-1].id
    # keyway box tool 3x3 placed at bore wall
    slot = doc.add(Feature(op="box", params={"dx":3,"dy":3,"dz":GEAR_T}))
    slotm = doc.add(Feature(op="move", params={"translate":[-1.5,4,0]}, inputs=[slot]))
    doc.add(Feature(op="boolean", params={"op":"cut"}, inputs=[base, slotm]))
    return doc
sk_doc = build_sun_keyway()
sun_k = op("sun.keyway.build", lambda: sk_doc.build(k).final(sk_doc))
if sun_k: summ(sun_k, "sun+keyway")

print("\n=== PART 2: PLANET GEAR (blank + bore) ===")
def build_planet():
    doc = Document()
    blank = doc.add(Feature(op="cylinder", params={"radius": planet_out, "height": GEAR_T}))
    doc.add(Feature(op="hole", params={"x":0,"y":0,"top_z":GEAR_T,"diameter":6,"depth":GEAR_T}, inputs=[blank]))
    return doc
pl_doc = build_planet()
planet = op("planet.build", lambda: pl_doc.build(k).final(pl_doc))
if planet: summ(planet, "planet")

# planet with lightening holes via circular pattern
print("\n-- planet lightening holes (pattern_circular of a hole tool?) --")
def build_planet_light():
    doc = Document()
    blank = doc.add(Feature(op="cylinder", params={"radius": planet_out, "height": GEAR_T}))
    bored = doc.add(Feature(op="hole", params={"x":0,"y":0,"top_z":GEAR_T,"diameter":6,"depth":GEAR_T}, inputs=[blank]))
    # one lightening hole then pattern_circular
    lh = doc.add(Feature(op="hole", params={"x":11,"y":0,"top_z":GEAR_T,"diameter":4,"depth":GEAR_T}, inputs=[bored]))
    doc.add(Feature(op="pattern_circular", params={"count":6}, inputs=[lh]))
    return doc
pll_doc = build_planet_light()
planet_l = op("planet.lightening.build", lambda: pll_doc.build(k).final(pll_doc))
if planet_l: summ(planet_l, "planet+lightening")

print("\n=== PART 3: CARRIER PLATE (disk + pins + bolt circle via patterns) ===")
CARRIER_T = 5.0
PIN_H = GEAR_T + 4
def build_carrier():
    doc = Document()
    disk = doc.add(Feature(op="cylinder", params={"radius": center_dist+planet_out+3, "height": CARRIER_T}))
    bored = doc.add(Feature(op="hole", params={"x":0,"y":0,"top_z":CARRIER_T,"diameter":10,"depth":CARRIER_T}, inputs=[disk]))
    # one pin (boss) at planet orbit, then circular pattern x3
    pin = doc.add(Feature(op="boss", params={"x":center_dist,"y":0,"base_z":CARRIER_T,"height":PIN_H,"diameter":6}, inputs=[bored]))
    pins = doc.add(Feature(op="pattern_circular", params={"count":3}, inputs=[pin]))
    # bolt circle: one thru hole then pattern x8
    bolt = doc.add(Feature(op="hole", params={"x":center_dist+planet_out+1,"y":0,"top_z":CARRIER_T,"diameter":3.4,"depth":CARRIER_T}, inputs=[pins]))
    doc.add(Feature(op="pattern_circular", params={"count":8}, inputs=[bolt]))
    return doc
ca_doc = build_carrier()
carrier = op("carrier.build", lambda: ca_doc.build(k).final(ca_doc))
if carrier: summ(carrier, "carrier")

print("\n=== PART 4: RING GEAR (internal — annulus, bore houses planets) ===")
RING_OUT = rr + 8   # 60
def build_ring():
    doc = Document()
    blank = doc.add(Feature(op="cylinder", params={"radius": RING_OUT, "height": GEAR_T}))
    # internal bore = ring pitch (planets tangent to it)
    doc.add(Feature(op="hole", params={"x":0,"y":0,"top_z":GEAR_T,"diameter":2*rr,"depth":GEAR_T}, inputs=[blank]))
    return doc
ri_doc = build_ring()
ring = op("ring.build", lambda: ri_doc.build(k).final(ri_doc))
if ring: summ(ring, "ring")

# ring with bolt-circle fastener holes (pattern)
def build_ring_bolts():
    doc = build_ring()
    base = doc.features[-1].id
    bolt = doc.add(Feature(op="hole", params={"x":RING_OUT-3,"y":0,"top_z":GEAR_T,"diameter":3.4,"depth":GEAR_T}, inputs=[base]))
    doc.add(Feature(op="pattern_circular", params={"count":8}, inputs=[bolt]))
    return doc
rib_doc = build_ring_bolts()
ring_b = op("ring.bolts.build", lambda: rib_doc.build(k).final(rib_doc))
if ring_b: summ(ring_b, "ring+bolts")

print("\n=== PART 5: HOUSING (base plate + wall + bolt bosses) ===")
def build_housing():
    doc = Document()
    base = doc.add(Feature(op="cylinder", params={"radius": RING_OUT+5, "height": 6}))
    bored = doc.add(Feature(op="hole", params={"x":0,"y":0,"top_z":6,"diameter":24,"depth":6}, inputs=[base]))
    boss = doc.add(Feature(op="boss", params={"x":RING_OUT,"y":0,"base_z":6,"height":GEAR_T,"diameter":8,"pilot_diameter":3.4}, inputs=[bored]))
    doc.add(Feature(op="pattern_circular", params={"count":8}, inputs=[boss]))
    return doc
ho_doc = build_housing()
housing = op("housing.build", lambda: ho_doc.build(k).final(ho_doc))
if housing: summ(housing, "housing")

# ---------------------------------------------------------------------------
print("\n=== ASSEMBLY: place everything concentric + pattern the planets ===")

def mkpart(pid_suffix, name, out_r, dz, oz=0.0):
    env = {"origin":[-out_r,-out_r,oz], "dx":2*out_r, "dy":2*out_r, "dz":dz}
    return PartManifest(id=f"prt_000000000000{pid_suffix}", name=name, domain="mech",
                        version="1.0.0", interface=Interface(envelope=env))

asm = Assembly("planetary_gearset")
asm.add("sun", mkpart("0001","sun",sun_out,GEAR_T), translate=(0,0,0))
asm.add("ring", mkpart("0002","ring",RING_OUT,GEAR_T), translate=(0,0,0))
asm.add("carrier", mkpart("0003","carrier",center_dist+planet_out+3,CARRIER_T), translate=(0,0,-CARRIER_T))
asm.add("housing", mkpart("0004","housing",RING_OUT+5,6), translate=(0,0,-CARRIER_T-6))
# seed planet then circular pattern x3
planet_part = mkpart("0005","planet",planet_out,GEAR_T)
asm.add("planet", planet_part, translate=(center_dist,0,0))
made = op("asm.pattern_circular(planets x3)",
          lambda: asm.pattern_circular("planet", center=(0,0), count=3, total_angle_deg=360))
print(f"        placed planets: {[m.name for m in made] if made else made}")
print(f"        total instances: {len(asm.instances)}")
for n,i in asm.instances.items():
    print(f"          {n:12} translate={tuple(round(x,3) for x in i.translate)} rz={i.rotate_z_deg:.1f}")

vrep = op("asm.validate()", lambda: asm.validate())
if vrep is not None:
    print(f"        validate.ok={vrep.ok} checks={vrep.checks} violations={vrep.violations}")

asm_manifest = op("asm.to_manifest()", lambda: asm.to_manifest("prt_00000000000000aa"))
if asm_manifest:
    print(f"        envelope={asm_manifest.interface.envelope}")

# ---------------------------------------------------------------------------
print("\n=== WHOLE-ASSEMBLY INTERFERENCE (real geometry, pairwise boolean) ===")
# build real placed shapes matching the assembly transforms
shapes = {}
if sun: shapes["sun"] = (sun, (0,0,0), 0.0)
if ring: shapes["ring"] = (ring, (0,0,0), 0.0)
if carrier: shapes["carrier"] = (carrier, (0,0,-CARRIER_T), 0.0)
if housing: shapes["housing"] = (housing, (0,0,-CARRIER_T-6), 0.0)
if planet:
    for j,ang in enumerate((0,120,240)):
        rad = math.radians(ang)
        shapes[f"planet{j}"] = (planet, (center_dist*math.cos(rad), center_dist*math.sin(rad), 0), 0.0)
print(f"        interference over {len(shapes)} instances, {len(shapes)*(len(shapes)-1)//2} pairs")

irep = op("check_interference(full assembly)", lambda: check_interference(k, shapes))
if irep is not None:
    print(f"        ok={irep.ok}")
    print(f"        pairs_intersected={irep.checks.get('pairs_intersected')}")
    print(f"        overlaps_mm3={irep.checks.get('overlaps_mm3')}")
    print(f"        undetermined={irep.checks.get('undetermined')}")
    for viol in irep.violations:
        print(f"        VIOL: {viol}")

# deliberately-colliding variant: shove a planet inward 3mm into the sun
if planet and sun:
    bad = dict(shapes)
    bad["planet0"] = (planet, (center_dist-3, 0, 0), 0.0)
    irep2 = op("check_interference(planet crashed into sun)", lambda: check_interference(k, bad))
    if irep2 is not None:
        print(f"        ok={irep2.ok} violations={irep2.violations}")

# ---------------------------------------------------------------------------
print("\n=== COMPOUND + EXPORT STEP (whole mechanism) ===")
placed_shapes = []
if sun: placed_shapes.append(k.transform(sun, translate=(0,0,0)))
if ring: placed_shapes.append(ring)
if carrier: placed_shapes.append(k.transform(carrier, translate=(0,0,-CARRIER_T)))
if housing: placed_shapes.append(k.transform(housing, translate=(0,0,-CARRIER_T-6)))
if planet:
    for ang in (0,120,240):
        rad=math.radians(ang)
        placed_shapes.append(k.transform(planet, translate=(center_dist*math.cos(rad),center_dist*math.sin(rad),0)))
comp = op("compound(whole assembly)", lambda: k.compound(placed_shapes))
if comp:
    summ(comp, "compound")
tmp = tempfile.mkdtemp()
if comp:
    op("export_step(compound)", lambda: k.export_step(comp, os.path.join(tmp,"planetary.step")),
       note=os.path.join(tmp,"planetary.step"))
    op("export_stl(compound)", lambda: k.export_stl(comp, os.path.join(tmp,"planetary.stl")))

# ---------------------------------------------------------------------------
print("\n\n===== TIMING SUMMARY (slowest ops) =====")
for label,status,dt,note in sorted(LOG, key=lambda r:-r[2])[:15]:
    print(f"  {dt*1000:9.1f}ms  {status:8} {label}")
print("\n===== OUTCOME TALLY =====")
tally={}
for _,s,_,_ in LOG: tally[s]=tally.get(s,0)+1
print(" ", tally)
