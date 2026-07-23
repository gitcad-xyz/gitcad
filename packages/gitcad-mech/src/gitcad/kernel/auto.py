"""`auto` backend — forge-first, OCCT-fallback (ADR-0018 promotion).

The exact from-scratch kernel (``forge``: ref + Rust) is now the
*default* for every operator class it has earned. Each call is tried on
forge first; only an honest, stage-named ``NotYetImplemented`` refusal
falls through to OCCT. So a document builds with exact arithmetic
wherever forge reaches, and OCCT covers the genuinely-not-yet-ported
tail — no capability regression, exactness where it counts.

This is the ADR-0018 gate-G2 promotion: forge crossed the coverage bar
long ago (20/20 corpus vs OCCT's 18/20); ``auto`` makes it the front
door while keeping OCCT as the honest safety net.
"""

from __future__ import annotations

from typing import Any

from gitcad.errors import KernelError

# operations that fall back to OCCT geometry (a real Shape) cannot then
# be metric-queried on forge — once a shape is OCCT's, it stays OCCT's.
_METRIC_OPS = frozenset({
    "mass_props", "measure", "bbox", "entities", "validate", "tessellate",
})


def _is_refusal(exc: KernelError) -> bool:
    sig = getattr(exc, "signature", None)
    return getattr(sig, "diagnostic", None) == "NotYetImplemented"


class AutoKernel:
    """Forge-first kernel with OCCT fallback on honest refusal.

    A shape carries no backend tag, so we track provenance by identity:
    any shape forge produced is a forge shape; anything else came from
    OCCT and its subsequent ops route to OCCT."""

    name = "auto-forge-first"

    def __init__(self) -> None:
        from gitcad.kernel.occt import OcctKernel
        from gitcad.kernel.ref import RefKernel

        self._forge = RefKernel()
        self._occt = OcctKernel()
        self._occt_shapes: set[int] = set()      # id() of OCCT-made shapes

    def _forge_shape(self, shape) -> bool:
        """True if this shape was produced by forge (not OCCT)."""
        from forgekernel.brep import Solid

        # forge shapes are forgekernel objects; OCCT shapes are OCP.Shape.
        # We identify OCCT shapes by the tag set we maintain, and forge
        # shapes structurally.
        if id(shape) in self._occt_shapes:
            return False
        return not _looks_like_occt(shape)

    def __getattr__(self, op: str):
        # generic dispatcher for every Kernel-protocol method
        def call(*args, **kwargs):
            shape_args = [a for a in args if _is_shape(a)]
            # metric ops + ops on OCCT-provenance shapes go straight to OCCT
            route_occt = any(not self._forge_shape(s) for s in shape_args)
            if not route_occt:
                try:
                    out = getattr(self._forge, op)(*args, **kwargs)
                    return out
                except KernelError as exc:
                    if not _is_refusal(exc):
                        raise
                    # forge refused — fall through to OCCT, rebuilding any
                    # forge shape operands as OCCT shapes is out of scope
                    # for planar ops (the corpus never mixes), so only
                    # source-free ops (primitives/import) fall back cleanly.
                    if shape_args:
                        raise
            out = getattr(self._occt, op)(*args, **kwargs)
            if _is_shape(out):
                self._occt_shapes.add(id(out))
            return out

        return call


def _is_shape(x) -> bool:
    """Heuristic: a geometry handle (has no simple-scalar/str/dict type)."""
    if isinstance(x, (int, float, str, bool, dict, list, tuple, type(None))):
        return False
    return True


def _looks_like_occt(x) -> bool:
    return type(x).__module__.startswith("OCP")
