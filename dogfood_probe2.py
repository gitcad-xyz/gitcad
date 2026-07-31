"""Isolate the quadric-boolean boundary and test allow_sampled rescue."""
from __future__ import annotations
import math, time
from gitcad.kernel.ref import RefKernel
from gitcad.document import Document, Feature
from gitcad.part import check_interference
from gitcad.errors import KernelError

k = RefKernel()
def try_(label, fn):
    t0=time.perf_counter()
    try:
        r=fn(); dt=time.perf_counter()-t0
        extra=""
        try: extra=f" vol={k.measure(r).get('volume'):.2f}"
        except Exception: pass
        print(f"[ok    {dt*1e3:7.1f}ms] {label}{extra}")
        return r
    except KernelError as e:
        dt=time.perf_counter()-t0
        stage=getattr(e,'stage','')
        print(f"[REFUSE{dt*1e3:7.1f}ms] {label}  stage={stage!r}: {e}")
    except Exception as e:
        dt=time.perf_counter()-t0
        print(f"[CRASH {dt*1e3:7.1f}ms] {label}  {type(e).__name__}: {e}")

GT=12.0
print("### boundary: cutting an off-axis cylinder from various solids ###")
# plain cylinder minus off-axis cylinder (Cyl x Cyl)
cyl = k.cylinder(18, GT)
try_("plain cyl - off-axis cyl (Cyl x Cyl cut)",
     lambda: k.boolean("cut", cyl, k.transform(k.cylinder(2,GT), translate=(11,0,0))))
# box minus off-axis cylinder (baseline that works)
try_("box - off-axis cyl (Box x Cyl cut)",
     lambda: k.boolean("cut", k.box(40,40,GT), k.transform(k.cylinder(2,GT), translate=(11,0,0))))
# bored cyl (coaxial) then off-axis cut
bored = k.boolean("cut", cyl, k.cylinder(5,GT))  # coaxial bore
try_("bored cyl - off-axis cyl (Revolve x Cyl cut)",
     lambda: k.boolean("cut", bored, k.transform(k.cylinder(2,GT), translate=(11,0,0))))
# bored cyl - off-axis BOX (keyway)
try_("bored cyl - off-axis box (Revolve x Box cut, keyway)",
     lambda: k.boolean("cut", bored, k.transform(k.box(3,3,GT), translate=(9,-1.5,0))))
# annulus (internal ring) minus bolt hole
ring = k.boolean("cut", k.cylinder(60,GT), k.cylinder(52,GT))
try_("ring annulus - off-axis bolt hole (Revolve x Cyl cut)",
     lambda: k.boolean("cut", ring, k.transform(k.cylinder(1.7,GT), translate=(57,0,0))))

print("\n### does allow_sampled rescue these? ###")
k.allow_sampled=True
try_("[sampled] bored cyl - off-axis cyl",
     lambda: k.boolean("cut", bored, k.transform(k.cylinder(2,GT), translate=(11,0,0))))
try_("[sampled] ring - bolt hole",
     lambda: k.boolean("cut", ring, k.transform(k.cylinder(1.7,GT), translate=(57,0,0))))
k.allow_sampled=False

print("\n### interference: quadric vs quadric with/without allow_sampled ###")
# two overlapping cylinders (planet into sun)
sun = k.cylinder(22, GT)
planet = k.cylinder(18, GT)
shapes = {"sun":(sun,(0,0,0),0.0), "planet":(planet,(33,0,0),0.0)}  # 22+18=40>33 -> overlap
r=check_interference(k, shapes)
print(f"  exact: ok={r.ok} overlaps={r.checks.get('overlaps_mm3')} undet={r.checks.get('undetermined')}")
k.allow_sampled=True
r2=check_interference(k, shapes)
print(f"  sampled: ok={r2.ok} overlaps={r2.checks.get('overlaps_mm3')} undet={r2.checks.get('undetermined')}")
k.allow_sampled=False

print("\n### tangent cylinders (pitch contact) — does it read as clear or undetermined? ###")
shapes_t = {"sun":(sun,(0,0,0),0.0), "planet":(planet,(40,0,0),0.0)}  # 22+18=40 exactly tangent
rt=check_interference(k, shapes_t)
print(f"  exact tangent: ok={rt.ok} pairs={rt.checks.get('pairs_intersected')} undet={rt.checks.get('undetermined')} overlaps={rt.checks.get('overlaps_mm3')}")
