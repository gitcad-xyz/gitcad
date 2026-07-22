"""Kernel backends — implementations of the :class:`gitcad.seams.Kernel` seam.

- :mod:`gitcad.kernel.null` — pure-Python, no dependencies. Exercises the
  document model, identity, and reduction in tests without the OCCT wheel.
  Its ``validate()`` reports ``geometry_checked: False`` — it cannot lie about
  having verified geometry it never built.
- :mod:`gitcad.kernel.occt` — the real b-rep kernel via ``cadquery-ocp``.

``get_kernel()`` prefers OCCT and falls back to null; ``get_kernel(require=
"occt")`` raises instead of silently degrading — callers that *need* real
geometry must not receive a backend that can't check it (reviewed 2026-07-22).
"""

from __future__ import annotations

from gitcad.seams import Kernel


def get_kernel(require: str | None = None) -> Kernel:
    try:
        from gitcad.kernel.occt import OcctKernel

        return OcctKernel()
    except Exception as exc:
        if require == "occt":
            raise ImportError(
                "the OCCT kernel was explicitly required but is unavailable "
                f"({exc!r}) — install with: pip install 'gitcad[occt]'"
            ) from exc
    from gitcad.kernel.null import NullKernel

    return NullKernel()
