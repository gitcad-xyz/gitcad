"""Sketch constraint solver — authoring-time only (ADR-0013).

Draw roughly, constrain, solve, and get an exact :class:`gitcad.sketch.Profile`
out. The drawn coordinates are the Newton initial guess, which is what pins
the intended solution branch; what lands in the document is the solved
profile — the build never sees a constraint (determinism, ADR-0004).

Stdlib only: numeric Jacobian by central differences, Gauss-Newton step via
normal equations with partial-pivot elimination. Sketches are small (tens of
points); clarity beats sparsity here.

Failures are authoring errors with per-constraint residuals, plus a
degrees-of-freedom count so "under-constrained by 2" is a visible number,
never a coincidentally-right solution silently trusted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gitcad.errors import GitcadError
from gitcad.sketch import Profile

_TOL = 1e-10          # convergence: max |residual|
_RANK_TOL = 1e-7      # Jacobian rank estimation
_MAX_ITER = 100
_FD = 1e-6            # finite-difference step


@dataclass
class SolveResult:
    points: dict[str, tuple[float, float]]
    iterations: int
    residuals: dict[str, float]      # constraint label -> |residual| after solve
    dof: int                         # remaining degrees of freedom

    @property
    def converged(self) -> bool:
        return all(r < 1e-8 for r in self.residuals.values())


@dataclass
class ConstraintSketch:
    """Points + constraints; ``solve()`` then ``profile()`` for the document."""

    _pts: dict[str, list[float]] = field(default_factory=dict)
    _cons: list[tuple[str, callable]] = field(default_factory=list)

    # -- authoring -------------------------------------------------------------

    def point(self, name: str, x: float, y: float) -> str:
        if name in self._pts:
            raise GitcadError(f"duplicate point {name!r}")
        self._pts[name] = [float(x), float(y)]
        return name

    def _p(self, name: str) -> list[float]:
        if name not in self._pts:
            raise GitcadError(f"unknown point {name!r}")
        return self._pts[name]

    def _add(self, label: str, *residual_fns) -> None:
        for i, fn in enumerate(residual_fns):
            self._cons.append((f"{label}[{i}]" if len(residual_fns) > 1 else label, fn))

    def fix(self, p: str, x: float, y: float) -> None:
        pp = self._p(p)
        self._add(f"fix:{p}", lambda: pp[0] - x, lambda: pp[1] - y)

    def coincident(self, p: str, q: str) -> None:
        pp, qq = self._p(p), self._p(q)
        self._add(f"coincident:{p}:{q}",
                  lambda: pp[0] - qq[0], lambda: pp[1] - qq[1])

    def horizontal(self, p: str, q: str) -> None:
        pp, qq = self._p(p), self._p(q)
        self._add(f"horizontal:{p}:{q}", lambda: pp[1] - qq[1])

    def vertical(self, p: str, q: str) -> None:
        pp, qq = self._p(p), self._p(q)
        self._add(f"vertical:{p}:{q}", lambda: pp[0] - qq[0])

    def distance(self, p: str, q: str, d: float) -> None:
        pp, qq = self._p(p), self._p(q)
        self._add(f"distance:{p}:{q}",
                  lambda: math.hypot(pp[0] - qq[0], pp[1] - qq[1]) - d)

    def angle(self, p: str, q: str, deg: float) -> None:
        """Direction of p->q (residual via cross product with the target dir,
        smooth everywhere unlike atan2)."""
        pp, qq = self._p(p), self._p(q)
        tx, ty = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        self._add(f"angle:{p}:{q}",
                  lambda: (qq[0] - pp[0]) * ty - (qq[1] - pp[1]) * tx)

    def parallel(self, a: tuple[str, str], b: tuple[str, str]) -> None:
        p1, p2, p3, p4 = self._p(a[0]), self._p(a[1]), self._p(b[0]), self._p(b[1])
        self._add(f"parallel:{a[0]}{a[1]}:{b[0]}{b[1]}",
                  lambda: (p2[0] - p1[0]) * (p4[1] - p3[1])
                  - (p2[1] - p1[1]) * (p4[0] - p3[0]))

    def perpendicular(self, a: tuple[str, str], b: tuple[str, str]) -> None:
        p1, p2, p3, p4 = self._p(a[0]), self._p(a[1]), self._p(b[0]), self._p(b[1])
        self._add(f"perpendicular:{a[0]}{a[1]}:{b[0]}{b[1]}",
                  lambda: (p2[0] - p1[0]) * (p4[0] - p3[0])
                  + (p2[1] - p1[1]) * (p4[1] - p3[1]))

    def equal_length(self, a: tuple[str, str], b: tuple[str, str]) -> None:
        p1, p2, p3, p4 = self._p(a[0]), self._p(a[1]), self._p(b[0]), self._p(b[1])
        self._add(f"equal:{a[0]}{a[1]}:{b[0]}{b[1]}",
                  lambda: math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                  - math.hypot(p4[0] - p3[0], p4[1] - p3[1]))

    # -- solving ---------------------------------------------------------------

    def _residuals(self) -> list[float]:
        return [fn() for _, fn in self._cons]

    def _jacobian(self) -> list[list[float]]:
        flat = [v for pt in self._pts.values() for v in (0, 1)]  # index map
        vars_ = [(pt, i) for pt in self._pts.values() for i in (0, 1)]
        del flat
        J = []
        base = self._residuals()
        for k in range(len(base)):
            J.append([0.0] * len(vars_))
        for col, (pt, i) in enumerate(vars_):
            orig = pt[i]
            pt[i] = orig + _FD
            plus = self._residuals()
            pt[i] = orig - _FD
            minus = self._residuals()
            pt[i] = orig
            for row in range(len(plus)):
                J[row][col] = (plus[row] - minus[row]) / (2 * _FD)
        return J

    def solve(self) -> SolveResult:
        n_vars = 2 * len(self._pts)
        for it in range(1, _MAX_ITER + 1):
            r = self._residuals()
            if max((abs(v) for v in r), default=0.0) < _TOL:
                return self._result(it)
            J = self._jacobian()
            dx = _gauss_newton_step(J, r)
            if dx is None:
                break   # singular normal equations — report as-is below
            vars_ = [(pt, i) for pt in self._pts.values() for i in (0, 1)]
            for (pt, i), d in zip(vars_, dx):
                pt[i] += d
            if max((abs(d) for d in dx), default=0.0) < _TOL:
                return self._result(it)
        result = self._result(_MAX_ITER)
        if not result.converged:
            worst = max(result.residuals.items(), key=lambda kv: kv[1])
            raise GitcadError(
                f"sketch did not converge: worst constraint {worst[0]} "
                f"residual {worst[1]:.3e} (conflicting constraints?) — "
                f"dof={result.dof}, {len(self._cons)} constraints, {n_vars} vars")
        return result

    def _result(self, iterations: int) -> SolveResult:
        residuals = {label: abs(fn()) for label, fn in self._cons}
        rank = _rank(self._jacobian())
        return SolveResult(
            points={k: (round(v[0], 9), round(v[1], 9)) for k, v in self._pts.items()},
            iterations=iterations, residuals=residuals,
            dof=2 * len(self._pts) - rank)

    def profile(self, *point_names: str) -> Profile:
        """Closed polygon Profile through solved points, in the given order."""
        if len(point_names) < 3:
            raise GitcadError("profile needs at least 3 points")
        pts = [self._p(n) for n in point_names]
        prof = Profile((round(pts[0][0], 9), round(pts[0][1], 9)))
        for p in pts[1:]:
            prof.line_to(round(p[0], 9), round(p[1], 9))
        return prof.close()


def _gauss_newton_step(J: list[list[float]], r: list[float]) -> list[float] | None:
    """Solve (J^T J + λI) dx = -J^T r; tiny Tikhonov λ keeps under-constrained
    sketches solvable (minimum-norm step) without disturbing exact solutions."""
    m, n = len(J), len(J[0]) if J else 0
    A = [[sum(J[k][i] * J[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    for i in range(n):
        A[i][i] += 1e-12
    b = [-sum(J[k][i] * r[k] for k in range(m)) for i in range(n)]
    return _solve_linear(A, b)


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float] | None:
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda rr: abs(M[rr][col]))
        if abs(M[piv][col]) < 1e-300:
            return None
        M[col], M[piv] = M[piv], M[col]
        for rr in range(col + 1, n):
            f = M[rr][col] / M[col][col]
            for cc in range(col, n + 1):
                M[rr][cc] -= f * M[col][cc]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def _rank(J: list[list[float]]) -> int:
    """Row-echelon rank with a scale-aware tolerance."""
    M = [row[:] for row in J]
    if not M:
        return 0
    n_rows, n_cols = len(M), len(M[0])
    rank, col = 0, 0
    while rank < n_rows and col < n_cols:
        piv = max(range(rank, n_rows), key=lambda rr: abs(M[rr][col]))
        if abs(M[piv][col]) < _RANK_TOL:
            col += 1
            continue
        M[rank], M[piv] = M[piv], M[rank]
        for rr in range(rank + 1, n_rows):
            f = M[rr][col] / M[rank][col]
            for cc in range(col, n_cols):
                M[rr][cc] -= f * M[rank][cc]
        rank += 1
        col += 1
    return rank
