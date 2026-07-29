"""Kernel backends — implementations of the :class:`gitcad.seams.Kernel` seam.

- :mod:`gitcad.kernel.ref` — the exact-arithmetic forge kernel (``forgekernel``).
  Real geometry with no floating-point tolerance; refuses ops it cannot yet do
  with an honest, stage-named ``NotYetImplemented``.
- :mod:`gitcad.kernel.null` — pure-Python, no geometry; exercises the document
  model, identity, and reduction. Its ``validate()`` reports
  ``geometry_checked: False`` — it never claims to have checked geometry.

``get_kernel()`` returns the exact forge kernel (ADR-0020: forge is the sole
geometry kernel — OCCT is no longer bundled). ``forgekernel`` is a default
dependency, so a plain ``pip install gitcad`` gets real exact geometry out of
the box; only when it somehow can't be imported does the null backend answer,
and it never pretends to have checked geometry.
"""

from __future__ import annotations

from gitcad.seams import Kernel


def source_form(shape):
    """The special form a ``Body`` was built from (ADR-0022 B), or the shape.

    The seam returns a canonical ``Body`` and nothing else (ADR-0022 A), so
    code that needs the exact closed form of the construction — an inertia
    tensor that exists for a planar ``Solid``, a bench probe classifying
    boolean operands — asks for it here instead of `isinstance`-checking a
    kernel output. That check is what ADR-0022 exists to remove: it made a
    capability depend on how a shape was BUILT rather than on the shape, so a
    plate with a hole supported different operations depending on its history.

    **A caller may use this to go FASTER or to reach an exact term. It may
    never use it to give a different answer** — that is ADR-0022 B, and it is
    checkable: strip the hints and the corpus must produce identical geometry.
    """
    try:
        from forgekernel import body as _B
    except ImportError:                              # null backend, no forge
        return shape
    if isinstance(shape, _B.Body) and shape.repr_hint is not None:
        return shape.repr_hint
    return shape


def get_kernel(require: str | None = None) -> Kernel:
    """Return a geometry kernel. ``require="forge"`` or ``"null"`` pin a backend;
    the default returns forge, falling back to null only if forge is unimportable."""
    if require == "null":
        from gitcad.kernel.null import NullKernel

        return NullKernel()
    if require in (None, "forge"):
        try:
            from gitcad.kernel.ref import RefKernel

            return RefKernel()
        except Exception as exc:         # noqa: BLE001
            if require == "forge":
                raise ImportError(
                    "the forge kernel was required but is unavailable "
                    f"({exc!r}) — install with: pip install forgekernel"
                ) from exc
            from gitcad.kernel.null import NullKernel

            return NullKernel()
    raise ValueError(
        f"unknown kernel {require!r} (want 'forge' or 'null'; OCCT was removed "
        "in ADR-0020 — forge is the sole geometry kernel)"
    )
