"""Rebuild the whole mechanism with allow_sampled=True. Capture error bounds,
provenance, watertight, export, and SCALE timings (many MC booleans)."""
from __future__ import annotations
import math, time, tempfile, os
from gitcad.kernel.ref import RefKernel
from gitcad.document import Document, Feature
from gitcad.part import check_interference
from gitcad.errors import KernelError

k = RefKernel()
k.allow_sampled = True   # OPT-IN sampled tier for the whole session

def T(label, fn):
    t0=time.perf_counter()
    try:
        r=fn(); dt=time.perf_counter()-t0
        print(f"[ok    {dt*1e3:8.1f}ms] {label}")
        return r,dt
    except KernelError as e:
        dt=time.perf_counter()-t0
        print(f"[REFUSE{dt*1e3:8.1f}ms] {label}  stage={getattr(e,'stage','')!r}: {e}")
        return None,dt
    except Exception as e:
        dt=time.perf_counter()-t0
        print(f"[CRASH {dt*1e3:8.1f}ms] {label}  {type(e).__name__}: {e}")
        return None,dt

GT=12.0; CARRIER_T=5.0; center_dist=36.0; planet_out=18.0; sun_out=22.0; RING_OUT=60.0

def build_planet_light():
    doc=Document()
    b=doc.add(Feature(op="cylinder",params={"radius":planet_out,"height":GT}))
    bd=doc.add(Feature(op="hole",params={"x":0,"y":0,"top_z":GT,"diameter":6,"depth":GT},inputs=[b]))
    lh=doc.add(Feature(op="hole",params={"x":11,"y":0,"top_z":GT,"diameter":4,"depth":GT},inputs=[bd]))
    doc.add(Feature(op="pattern_circular",params={"count":6},inputs=[lh]))
    return doc

def build_carrier():
    doc=Document()
    d=doc.add(Feature(op="cylinder",params={"radius":center_dist+planet_out+3,"height":CARRIER_T}))
    bd=doc.add(Feature(op="hole",params={"x":0,"y":0,"top_z":CARRIER_T,"diameter":10,"depth":CARRIER_T},inputs=[d]))
    pin=doc.add(Feature(op="boss",params={"x":center_dist,"y":0,"base_z":CARRIER_T,"height":GT+4,"diameter":6},inputs=[bd]))
    pins=doc.add(Feature(op="pattern_circular",params={"count":3},inputs=[pin]))
    bolt=doc.add(Feature(op="hole",params={"x":center_dist+planet_out+1,"y":0,"top_z":CARRIER_T,"diameter":3.4,"depth":CARRIER_T},inputs=[pins]))
    doc.add(Feature(op="pattern_circular",params={"count":8},inputs=[bolt]))
    return doc

def build_ring_bolts():
    doc=Document()
    b=doc.add(Feature(op="cylinder",params={"radius":RING_OUT,"height":GT}))
    bd=doc.add(Feature(op="hole",params={"x":0,"y":0,"top_z":GT,"diameter":104,"depth":GT},inputs=[b]))
    bolt=doc.add(Feature(op="hole",params={"x":RING_OUT-3,"y":0,"top_z":GT,"diameter":3.4,"depth":GT},inputs=[bd]))
    doc.add(Feature(op="pattern_circular",params={"count":8},inputs=[bolt]))
    return doc

def build_housing():
    doc=Document()
    b=doc.add(Feature(op="cylinder",params={"radius":RING_OUT+5,"height":6}))
    bd=doc.add(Feature(op="hole",params={"x":0,"y":0,"top_z":6,"diameter":24,"depth":6},inputs=[b]))
    boss=doc.add(Feature(op="boss",params={"x":RING_OUT,"y":0,"base_z":6,"height":GT,"diameter":8,"pilot_diameter":3.4},inputs=[bd]))
    doc.add(Feature(op="pattern_circular",params={"count":8},inputs=[boss]))
    return doc

parts={}
for name,builder in [("planet_light",build_planet_light),("carrier",build_carrier),
                     ("ring_bolts",build_ring_bolts),("housing",build_housing)]:
    doc=builder()
    print(f"\n--- {name}: {len(doc.features)} features ---")
    shp,dt=T(f"{name}.build (SAMPLED)", lambda d=doc: d.build(k).final(d))
    if shp is not None:
        parts[name]=shp
        m,_=T(f"{name}.measure", lambda s=shp: k.measure(s))
        v,_=T(f"{name}.validate", lambda s=shp: k.validate(s))
        if m: print(f"        measure -> {m}")
        if v is not None: print(f"        validate.ok={v.ok} checks={getattr(v,'checks',{})}")

print("\n### whole-assembly interference in SAMPLED mode (planetary meshing) ###")
sun=k.cylinder(sun_out,GT); planet=k.cylinder(planet_out,GT); ring=parts.get("ring_bolts")
shapes={"sun":(sun,(0,0,0),0.0)}
for j,ang in enumerate((0,120,240)):
    rad=math.radians(ang)
    shapes[f"planet{j}"]=(planet,(center_dist*math.cos(rad),center_dist*math.sin(rad),0),0.0)
if ring is not None: shapes["ring"]=(ring,(0,0,0),0.0)
r,dt=T(f"check_interference SAMPLED ({len(shapes)} inst)", lambda: check_interference(k,shapes))
if r is not None:
    print(f"        ok={r.ok} pairs={r.checks.get('pairs_intersected')}")
    print(f"        overlaps_mm3={r.checks.get('overlaps_mm3')}")
    print(f"        undetermined={r.checks.get('undetermined')}")
    for viol in r.violations: print(f"        VIOL: {viol}")

print("\n### compound + export_step of the full mechanism (SAMPLED) ###")
placed=[sun]
for j,ang in enumerate((0,120,240)):
    rad=math.radians(ang); placed.append(k.transform(planet,translate=(center_dist*math.cos(rad),center_dist*math.sin(rad),0)))
if ring is not None: placed.append(ring)
if "carrier" in parts: placed.append(k.transform(parts["carrier"],translate=(0,0,-CARRIER_T)))
if "housing" in parts: placed.append(k.transform(parts["housing"],translate=(0,0,-CARRIER_T-6)))
comp,dt=T(f"compound({len(placed)} solids)", lambda: k.compound(placed))
tmp=tempfile.mkdtemp()
if comp is not None:
    s,_=T("export_step(compound)", lambda: k.export_step(comp,os.path.join(tmp,"planetary.step")))
    p=os.path.join(tmp,"planetary.step")
    if os.path.exists(p): print(f"        wrote {os.path.getsize(p)} bytes -> {p}")
    T("export_stl(compound)", lambda: k.export_stl(comp,os.path.join(tmp,"planetary.stl")))
    T("measure(compound)", lambda: k.measure(comp))
    T("validate(compound)", lambda: k.validate(comp))

print("\n### repeated sampled measure — is the answer STABLE run-to-run? ###")
b=k.boolean("cut", k.boolean("cut",k.cylinder(18,GT),k.cylinder(6,GT)),
            k.transform(k.cylinder(2,GT),translate=(11,0,0)))
for i in range(5):
    print(f"        measure run {i}: vol={k.measure(b).get('volume'):.4f}")
