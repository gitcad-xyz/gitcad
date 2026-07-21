"""Kernel backends — implementations of the :class:`gitcad.seams.Kernel` seam.

- :mod:`gitcad.kernel.null` — pure-Python, no dependencies. Enough to exercise
  the document model, identity, and reduction in tests without the ~hundreds-of-MB
  OCCT wheel. Booleans/fillets are tracked symbolically (provenance only).
- :mod:`gitcad.kernel.occt` — the real b-rep kernel via ``cadquery-ocp``.

``get_kernel()`` returns the best available backend, preferring OCCT.
"""

from __future__ import annotations

from gitcad.seams import Kernel


def get_kernel(prefer: str = "occt") -> Kernel:
    if prefer == "occt":
        try:
            from gitcad.kernel.occt import OcctKernel

            return OcctKernel()
        except Exception:
            pass
    from gitcad.kernel.null import NullKernel

    return NullKernel()
