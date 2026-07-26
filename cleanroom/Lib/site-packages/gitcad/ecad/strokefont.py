"""Stroke font — moved to gitcad-core (gitcad.strokefont) so mech sketch
text/engraving shares the same glyphs as ECAD silkscreen. This shim keeps
existing imports working."""

from gitcad.strokefont import ADVANCE, text_strokes, text_width  # noqa: F401
