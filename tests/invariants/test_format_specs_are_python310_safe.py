"""`f"{x:g}"` on a Fraction raises on Python 3.10 and 3.11.

`Fraction.__format__` only began accepting a format spec in 3.12. Before that,
`f"{Fraction(1,3):g}"` raises TypeError. Our declared floor is 3.10, and the
development machine runs 3.12 — so this class of bug is invisible locally and
only appears for users on older Pythons.

It had already shipped: `weldment.rect_tube`, `angle`, `channel` and `flat_bar`
built their profile names that way, so every weldment call crashed on 3.10.
Nothing caught it, because the CI job that would have was broken (see
test_null_kernel_suite_is_real.py — the whole of CI had gone quiet).

The rule is narrow on purpose: `float()` the value before formatting it. That
is correct wherever the formatted result is DISPLAY — a name, a message, a
report line — which is every site this lint covers. It says nothing about
arithmetic, and ADR-0019 is untouched: no float decides anything here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# a numeric format spec applied to some expression
SPEC = re.compile(r"\{([^{}:]+?):(g|\.\d+f|,\.\d+f|[<>^]?\d*\.\d+f)\}")

# expressions that are already numeric by construction
SAFE_PREFIX = ("float(", "len(", "abs(float", "sum(float", "round(")


def _sources() -> list[Path]:
    return [p for p in (ROOT / "packages").rglob("*.py")
            if "src" in p.parts and "__pycache__" not in p.parts]


@pytest.mark.invariant
def test_no_format_spec_is_applied_to_a_possibly_exact_value() -> None:
    bad: list[str] = []
    for path in _sources():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in SPEC.finditer(line):
                expr = m.group(1).strip()
                if expr.startswith(SAFE_PREFIX) or expr.isdigit():
                    continue
                bad.append(
                    f"{path.relative_to(ROOT)}:{i}: {m.group(0)} — wrap in "
                    f"float(): {{float({expr}):{m.group(2)}}}")
    assert bad == [], (
        "a format spec on a value that may be a Fraction raises TypeError on "
        "Python 3.10/3.11 (Fraction.__format__ gained spec support in 3.12), "
        "and this repo supports 3.10:\n  " + "\n  ".join(bad[:25]))


@pytest.mark.invariant
def test_the_lint_would_have_caught_the_bug_that_motivated_it(tmp_path) -> None:
    """A checker nobody has seen fail is a checker nobody trusts."""
    src = tmp_path / "weldment_like.py"
    src.write_text('name = f"RT{w:g}x{h:g}"\n', encoding="utf-8")
    hits = [m.group(0) for line in src.read_text(encoding="utf-8").splitlines()
            for m in SPEC.finditer(line)]
    assert hits == ["{w:g}", "{h:g}"]

    src.write_text('name = f"RT{float(w):g}x{float(h):g}"\n', encoding="utf-8")
    clean = [m.group(1).strip() for line in src.read_text(encoding="utf-8").splitlines()
             for m in SPEC.finditer(line)]
    assert all(e.startswith("float(") for e in clean), "the fixed form is clean"


def test_the_failure_is_real_on_this_interpreter_or_documented() -> None:
    """Pin WHY the rule exists to the actual language behaviour, so that when
    3.10 and 3.11 are eventually dropped this test says plainly that the lint
    can go rather than leaving a rule nobody remembers the reason for."""
    import sys
    from fractions import Fraction

    if sys.version_info < (3, 12):
        with pytest.raises(TypeError):
            format(Fraction(1, 3), "g")
    else:
        assert format(Fraction(1, 3), "g") == "0.333333", (
            "3.12+ formats Fractions fine — the lint exists for 3.10/3.11, "
            "which pyproject still declares. Drop both when the floor rises.")
