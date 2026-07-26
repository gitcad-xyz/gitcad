"""The import honesty contract: every importer reports what happened."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportReport:
    """What an import actually did — machine-readable, never silent.

    ``imported`` counts what came through; ``warnings`` are approximations the
    user should verify (e.g. "outline approximated by bounding box");
    ``dropped`` is data that did NOT survive the import. An import with drops
    still succeeds — refusing entirely helps nobody — but the caller (and the
    agent driving it) can see exactly what to check.
    """

    source: str
    format: str
    imported: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    def count(self, kind: str, n: int = 1) -> None:
        self.imported[kind] = self.imported.get(kind, 0) + n

    def to_dict(self) -> dict:
        return {"source": self.source, "format": self.format,
                "imported": dict(sorted(self.imported.items())),
                "warnings": self.warnings, "dropped": self.dropped}
