# An exact B-rep kernel: forge vs the 30-year float kernel

*A technical note on gitcad's from-scratch geometry kernel. Every number
below corresponds to a committed oracle test; see `bench/RUST-vs-OCCT.md`
and `forge/tests/` for the reproductions.*

## Thesis

Every mainstream CAD kernel — OpenCASCADE, Parasolid, ACIS — makes
topological decisions in floating point. "Is this point on that face?"
"Do these surfaces intersect?" are answered by comparing doubles against
a tolerance. That is the root cause of the entire genre of CAD
robustness failures: booleans that leak, fillets that fail to build,
imports that self-intersect.

**forge makes no topological decision in floating point.** Numbers live
in exact fields, and a decision is taken only when its sign is *proven*
— by exact field arithmetic, or by an interval that provably excludes
zero. The bet was that this is not merely more correct but, with the
right filters, *faster*. Both halves held.

## The number tower

| field | represents | used for |
|---|---|---|
| ℚ (`Fraction`) | rationals | planar solids, polynomial curves/surfaces, freeform volume & inertia |
| ℚ[π] (`PiVal` = a+bπ) | π-linear reals | cylinders, spheres, drilled/revolved solids, fillets |
| ℚ[√d] (`SurdVal`) | quadratic surds | mitered sweep lengths |
| certified interval (`CInterval`) | anything transcendental | helix/spring, mean curvature, NURBS with irrational weights |

The charter (ADR-0019): a topological sign is legitimate iff it comes
from exact field arithmetic **or** from a `CInterval` that strictly
excludes zero. An interval straddling zero is tightened, then refused —
never guessed. Anything the current fields cannot represent earns an
honest, **stage-named** refusal (`"arrives at K3"`), never a silent
float.

## Five measured axes where forge beats OCCT

Same corpus, same seam, best-of-4 wall time.

1. **Capability — 20/20 vs 18/20.** forge builds the entire corpus;
   OCCT's float pipe rejects both sharp-cornered mitered sweeps.
2. **Speed — 4–5.5× aggregate.** 15 of 16 shared models run 2.7–306×
   faster, at identical (exact) volumes. A Shewchuk-style float filter
   decides the common case in `f64` and falls back to exact BigRational
   only near zero — the sign is *always* the exact one; the filter only
   skips slow work. A move-not-clone BSP and cached-float coordinates
   compound it.
3. **Curved-boolean accuracy.** Two r=5 spheres 6 apart: forge returns
   the union as exactly `896/3·π`; OCCT carries 1.4×10⁻⁹ relative error
   from its surface tolerance — and takes 84× longer to do it.
4. **Transcendental accuracy.** The coil spring's volume is `πρ²L`,
   `L = 6√(256π²+16)` — outside every algebraic field. forge brackets
   it to a certified interval of width ~10⁻⁵⁰; OCCT's swept-B-rep
   integration lands 4.4×10⁻⁷ away, at **306×** the cost.
5. **SSI branch-completeness.** `z=(u−½)²` is tangent to `z=0` along a
   line. OCCT's `GeomAPI_IntSS` returns **zero** intersection lines —
   it misses the branch. forge's subdivision SSI finds it, with 128
   points certified by exact rational residual. Its empty answers are
   *proofs* (bounding-box disjointness), not failures to find.

## Exactness reaches surprisingly far

- **NURBS evaluation is exact.** de Boor is only convex combinations, so
  a rational-control-point curve/surface at a rational parameter returns
  a point in ℚ³. Matches OCCT to machine epsilon; forge holds the exact
  Fraction.
- **STEP import is exact by construction.** STEP writes reals as decimal
  text, and decimal→`Fraction` is lossless. `0.1` imports as the true
  1/10, where a float kernel rounds to 53 bits. forge also *writes*
  valid AP214 that OCCT reads back exactly — round-trip with no OCCT in
  the loop.
- **Freeform volume & inertia are exactly rational.** By the divergence
  theorem, `V = ⅓∮ S·(S_u×S_v)` and the integrand is a *polynomial*, so
  a Bézier-patch-bounded solid has a ℚ volume and a ℚ inertia tensor
  (off-diagonals exactly zero on a box). OCCT can only Gauss-quadrature
  the same flux.
- **Gaussian curvature is exactly rational.** The `|n|` factors cancel
  in `K = (LN−M²)/(EG−F²)²`, so K is a Fraction — and a developable
  surface's curvature is *exactly zero*, a statement no float kernel can
  make. G1 and G2 continuity are certified by **polynomial identity**:
  zero at more samples than the degree bound is a proof, not a
  tolerance.

## Architecture

Three oracles keep it honest (ADR-0018): a Python **ref** kernel is the
executable specification (exact rationals, readable); it is
differentially checked against **OCCT**, the 30-year independent oracle;
and a Rust **forge** production port is proven bit-identical to ref.
Hot loops — BSP booleans, NURBS evaluation, SSI subdivision — live in
Rust (15× on the deep SSI loop) but every result is oracle-locked to the
spec. Nothing is trusted because it looks right; it is trusted because a
second, independent implementation agrees exactly.

## Honest boundaries

The kernel refuses by name rather than approximating past its charter.
`chamfered_block` is the one model where forge is slower (~2× — a deep
sequential-cut chain, a known targetable frontier). Full freeform
solid **booleans** (trimmed-patch classification) are the remaining
hard frontier; the volume, inertia, SSI, and STEP pieces they need are
already exact and shipped. Two features (smooth loft, variable-radius
fillet) are exact *for forge's documented smoothing law* and differ
from OCCT's different law by ~10⁻⁴ — a modeling choice, disclosed, not
a bug.

## Why it matters

A kernel that cannot make a wrong topological decision is a different
kind of foundation. It makes booleans that never leak, imports that are
byte-faithful, and mass properties you can put in a certificate. That is
the substrate gitcad is built on — and, uniquely, it is one an agent can
extend safely, because every extension either proves itself against the
oracle chain or refuses out loud.
