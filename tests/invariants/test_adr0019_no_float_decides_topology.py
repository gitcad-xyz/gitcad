"""ADR-0019, enforced instead of remembered: no float may decide topology.

The charter's central rule was held up by discipline and review alone, and
review is exactly what kept missing it. Two defects shipped this way:

  * the pocket containment guard took a cap's ring through ``float()`` and
    compared against it, so at coordinates near 2**53 the cap's own corner
    rounded and a mouth a full millimetre OUTSIDE the flat was accepted;
  * ``_disc_misses_solid`` squared with ``** 2``, which ``SurdVal`` does not
    implement, turning an honest refusal into a raw ``TypeError`` out of the
    seam for every exactly-rotated solid.

WHAT THIS CHECKS, and why it is this and not "no floats anywhere". Floats are
LEGAL and necessary — for display, meshing, bounds, reporting, and certified
numerics. ADR-0019 forbids something narrower: a float may not decide a
PREDICATE whose answer changes the geometry that gets built. So the rule here
is *a float-valued expression inside a comparison*. Scanning for float use at
all flags 439 sites, which is a lint nobody runs; scanning comparisons flags a
handful, each of which is a real question.

HOW TO SILENCE ONE. Say why in the enclosing function's docstring, citing
ADR-0019 — the codebase already does this wherever floats are deliberate
("Floats are legal here — this is meshing (ADR-0019)"). That makes the
exemption reviewable in the place a reader is already looking, rather than in a
config file nobody opens.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Expressions that yield a float.
FLOAT_CALLS = {"float", "round"}
FLOAT_MATH = {"sqrt", "cos", "sin", "tan", "atan2", "hypot", "isclose", "acos",
              "asin", "atan", "degrees", "radians", "log", "exp"}

# Modules whose WHOLE JOB is certified numerics or display. ADR-0019 allows
# floats there by construction; the exactness they owe is stated in their own
# terms (an enclosure that brackets the true answer, not an exact predicate).
NUMERIC_BY_DESIGN = {
    "ssi.py",            # K3.3 certified marching — floats bracketed by intervals
    "ssi_curves.py",
    "nurbs.py",          # K3.2 evaluation; the exact/certified split is internal
    "interval.py",       # the interval type itself
    "hlr.py",            # a drawing projection is a picture
    "tess.py", "mesh2d.py",
    "stepio.py",         # AP214 is a decimal interchange format
    "surfacing.py", "trim.py", "loft.py", "profile2d.py", "curve.py",
    "bsolid.py", "stepbody_fixed.py",
}


def _targets() -> list[Path]:
    forge = Path(__file__).resolve().parents[2].parent / "forge" / "src" / "forgekernel"
    seam = (Path(__file__).resolve().parents[2] / "packages" / "gitcad-mech"
            / "src" / "gitcad" / "kernel" / "ref.py")
    out = [p for p in sorted(forge.glob("*.py"))
           if p.name not in NUMERIC_BY_DESIGN]
    if seam.is_file():
        out.append(seam)
    return out


def _float_reason(node: ast.AST) -> str | None:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in FLOAT_CALLS:
                return f"{f.id}()"
            if isinstance(f, ast.Attribute) and f.attr in FLOAT_MATH \
                    and getattr(f.value, "id", "") in ("math", "m", "_m"):
                return f"math.{f.attr}()"
        if isinstance(n, ast.Constant) and isinstance(n.value, float):
            return f"the literal {n.value!r}"
    return None


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if "ADR-0019" in (ast.get_docstring(tree) or ""):
        return []                       # the module declares itself a float zone
    exempt: list[tuple[int, int]] = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and "ADR-0019" in (ast.get_docstring(n) or ""):
            exempt.append((n.lineno, getattr(n, "end_lineno", n.lineno)))

    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Compare):
            continue
        if any(a <= n.lineno <= b for a, b in exempt):
            continue
        for side in [n.left, *n.comparators]:
            why = _float_reason(side)
            if why:
                out.append(f"{path.name}:{n.lineno}: {why} decides "
                           f"`{lines[n.lineno - 1].strip()[:70]}`")
                break
    return out


@pytest.mark.parametrize("path", _targets(), ids=lambda p: p.name)
def test_no_float_appears_in_an_exact_predicate(path: Path) -> None:
    bad = _offenders(path)
    assert bad == [], (
        "ADR-0019: a float decides a predicate here. Make the test exact, or "
        "say in the enclosing function's docstring why floats are right and "
        "cite ADR-0019.\n  " + "\n  ".join(bad))


def test_the_lint_would_catch_the_defects_that_motivated_it(tmp_path) -> None:
    """A checker nobody has seen fail is a checker nobody trusts."""
    src = tmp_path / "guard.py"
    src.write_text(
        "def contains(ring, q):\n"
        "    '''No exemption claimed.'''\n"
        "    return float(ring[0]) < q\n", encoding="utf-8")
    assert _offenders(src), "the float-ring guard must be flagged"

    src.write_text(
        "def near(a, b):\n"
        "    '''No exemption claimed.'''\n"
        "    return abs(a - b) < 1e-9\n", encoding="utf-8")
    assert _offenders(src), "an epsilon comparison must be flagged"


def test_an_explicit_exemption_silences_it(tmp_path) -> None:
    src = tmp_path / "mesh.py"
    src.write_text(
        "def sample(a, b):\n"
        "    '''Floats are legal here — this is meshing (ADR-0019).'''\n"
        "    return float(a) < b\n", encoding="utf-8")
    assert _offenders(src) == []


def test_exact_comparisons_are_not_flagged(tmp_path) -> None:
    """The lint must not push people toward pointless rewrites."""
    src = tmp_path / "exact.py"
    src.write_text(
        "from fractions import Fraction\n"
        "def inside(x, lo, hi):\n"
        "    '''No exemption claimed, and none needed.'''\n"
        "    return lo < x < hi and x != 0 and (x - lo) * (x - hi) <= 0\n",
        encoding="utf-8")
    assert _offenders(src) == []


def test_the_exact_field_boundary_is_marked_permanent_not_backlog() -> None:
    """Two cells are outside ANY exact field and always will be. Under
    ADR-0019 the refusal IS the finished answer there, so counting them as gaps
    makes the matrix read as 345 achievable cells when it is 343.

    Naming them costs nothing and stops a future reader — human or agent —
    spending a day trying to close a hole that is a wall.
    """
    from gitcad.bench.capability import _EXACT_FIELD_BOUNDARY, probe

    grid = probe()["grid"]
    for (shape, op), why in _EXACT_FIELD_BOUNDARY.items():
        assert grid[shape][op] == "exact-field", (
            f"{shape}/{op} is no longer classified as a permanent boundary — "
            "either it was fixed (delete the entry) or the probe regressed")
        assert why, "a boundary entry must say WHICH number it would need"
    counts = {}
    for row in grid.values():
        for v in row.values():
            counts[v] = counts.get(v, 0) + 1
    assert counts.get("CRASH", 0) == 0, "a raw exception through the seam"
    assert counts["exact-field"] == len(_EXACT_FIELD_BOUNDARY)
