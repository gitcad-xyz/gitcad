"""Kernel backends — implementations of the :class:`gitcad.seams.Kernel` seam.

- :mod:`gitcad.kernel.ref` — the exact-arithmetic forge kernel (``forgekernel``).
  Real geometry with no floating-point tolerance; refuses ops it cannot yet do.
- :mod:`gitcad.kernel.auto` — forge-first with OCCT fallback (needs both).
- :mod:`gitcad.kernel.occt` — the b-rep kernel via ``cadquery-ocp``.
- :mod:`gitcad.kernel.null` — pure-Python, no geometry; exercises the document
  model, identity, and reduction. Its ``validate()`` reports
  ``geometry_checked: False`` — it never claims to have checked geometry.

``get_kernel()`` selects **forge-first** (ADR-0018): the exact kernel with OCCT
fallback when both are installed, else forge alone, else OCCT alone, and only
the null backend when no geometry engine is available at all. As of the 0.8
line ``forgekernel`` is a default dependency, so a plain ``pip install gitcad``
gets real exact geometry out of the box — not the null backend (reviewed
2026-07-24, from dogfood feedback). ``get_kernel(require="occt")`` still raises
rather than silently degrade for callers that specifically need OCCT.
"""

from __future__ import annotations

from gitcad.seams import Kernel


def get_kernel(require: str | None = None) -> Kernel:
    if require == "occt":
        try:
            from gitcad.kernel.occt import OcctKernel

            return OcctKernel()
        except Exception as exc:  # noqa: BLE001 - report, don't degrade
            raise ImportError(
                "the OCCT kernel was explicitly required but is unavailable "
                f"({exc!r}) — install with: pip install 'gitcad[occt]'"
            ) from exc
    if require == "forge":
        from gitcad.kernel.ref import RefKernel

        return RefKernel()
    if require == "null":
        from gitcad.kernel.null import NullKernel

        return NullKernel()

    # Default, forge-first (ADR-0018): AutoKernel (forge + OCCT fallback) when
    # both are present, else the exact forge kernel alone, else OCCT alone,
    # else — only if no geometry engine exists — the null backend.
    for factory in (_try_auto, _try_ref, _try_occt):
        kernel = factory()
        if kernel is not None:
            return kernel
    from gitcad.kernel.null import NullKernel

    return NullKernel()


def _try_auto() -> Kernel | None:
    try:
        from gitcad.kernel.auto import AutoKernel

        return AutoKernel()          # needs both forge and OCCT installed
    except Exception:                # noqa: BLE001
        return None


def _try_ref() -> Kernel | None:
    try:
        from gitcad.kernel.ref import RefKernel

        return RefKernel()           # forge only — exact, refuses what it can't do
    except Exception:                # noqa: BLE001
        return None


def _try_occt() -> Kernel | None:
    try:
        from gitcad.kernel.occt import OcctKernel

        return OcctKernel()
    except Exception:                # noqa: BLE001
        return None
