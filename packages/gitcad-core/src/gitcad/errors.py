"""Structured errors.

Errors here are not just for humans — a kernel/validation failure carries enough
structure to become a *bug-repro payload* (see :mod:`gitcad.report`). Every
failure exposes a stable ``fingerprint_key`` so 10,000 users hitting one kernel
bug produce one deduplicated issue, not 10,000.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class GitcadError(Exception):
    """Base class for all gitcad errors."""


@dataclass
class FailureSignature:
    """The deduplication key for a failure.

    Deliberately excludes user coordinates and model contents — it is derived
    only from *what went wrong* (the operation and the kernel's own diagnostic),
    so it is safe to transmit and stable across unrelated models.
    """

    op: str
    """The intent-level operation that failed, e.g. ``"fillet"``."""

    diagnostic: str
    """The kernel/validator's own message class, e.g. ``"BRepCheck:BadOrientation"``."""

    kernel: str = "unknown"
    """Backend + version, e.g. ``"occt-7.8.1"``."""

    def key(self) -> str:
        return f"{self.kernel}|{self.op}|{self.diagnostic}"


class KernelError(GitcadError):
    """A geometry-kernel operation failed.

    Carries a :class:`FailureSignature` so the failure can be fingerprinted and
    the model auto-reduced to a minimal, synthetic repro before anything leaves
    the user's machine.
    """

    def __init__(self, message: str, signature: FailureSignature) -> None:
        super().__init__(message)
        self.signature = signature


class GeometryInvalidError(KernelError):
    """A produced shape violated a geometric invariant (e.g. not watertight)."""


class IdentityError(GitcadError):
    """A stable-identity operation failed (e.g. dangling entity reference)."""

    def __init__(self, message: str, *, entity: str | None = None) -> None:
        super().__init__(message)
        self.entity = entity


@dataclass
class ValidationReport:
    """Result of validating a shape or document. Machine-readable by design so
    an agent can act on it instead of parsing prose."""

    ok: bool
    checks: dict[str, Any] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)

    def raise_if_invalid(self, op: str, kernel: str = "unknown") -> None:
        if not self.ok:
            # Fingerprints must carry only the closed-vocabulary violation
            # CODES, never the per-instance detail after the first colon —
            # detail embeds designators/dimensions (unsafe to transmit, per
            # the FailureSignature contract) and varies per model (destroying
            # dedup). Reviewed 2026-07-22. Violation format: "code:detail".
            codes = sorted({v.split(":", 1)[0] for v in self.violations})
            sig = FailureSignature(op=op, diagnostic=";".join(codes), kernel=kernel)
            raise GeometryInvalidError(f"{op} produced invalid geometry: {self.violations}", sig)
