"""Safe arithmetic expressions — the engine behind named parameters.

A tiny, auditable evaluator over Python's ast: numbers, + - * / // % **,
unary +/-, parentheses, parameter names, and a whitelist of math
functions. No attribute access, no subscripts, no comprehensions, no
eval — an expression can compute a dimension and nothing else.

Convention (spreadsheet-style, used across gitcad): a string value
beginning with ``=`` is an expression; anything else is a literal.
"""

from __future__ import annotations

import ast
import math
from typing import Any, Mapping

from gitcad.errors import GitcadError


class ExprError(GitcadError):
    pass


class UndefinedNameError(ExprError):
    def __init__(self, name: str) -> None:
        super().__init__(f"undefined name {name!r} in expression")
        self.name = name


_FUNCS: dict[str, Any] = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "sqrt": math.sqrt,
    "abs": abs,
    "min": min,
    "max": max,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
}
_CONSTS = {"pi": math.pi}

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}


def eval_expr(expr: str, env: Mapping[str, float]) -> float:
    """Evaluate ``expr`` with parameter values from ``env``. Angles for
    trig are DEGREES (the CAD convention). Raises UndefinedNameError for
    unknown names, ExprError for anything outside the whitelist."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"bad expression {expr!r}: {e.msg}") from None

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            raise ExprError(f"non-numeric constant {node.value!r} in {expr!r}")
        if isinstance(node, ast.Name):
            if node.id in env:
                return float(env[node.id])
            if node.id in _CONSTS:
                return _CONSTS[node.id]
            raise UndefinedNameError(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Name) and node.func.id in _FUNCS
                    and not node.keywords):
                return float(_FUNCS[node.func.id](*[ev(a) for a in node.args]))
            raise ExprError(f"function not allowed in {expr!r}")
        raise ExprError(f"construct {type(node).__name__} not allowed in {expr!r}")

    return ev(tree)


def is_expression(value: Any) -> bool:
    """The gitcad convention: strings starting with '=' are expressions."""
    return isinstance(value, str) and value.startswith("=")


def resolve_value(value: Any, env: Mapping[str, float]) -> Any:
    """Resolve one value: '=expr' strings evaluate; lists/dicts recurse;
    everything else passes through untouched (enums, paths, ids)."""
    if is_expression(value):
        return eval_expr(value[1:], env)
    if isinstance(value, list):
        return [resolve_value(v, env) for v in value]
    if isinstance(value, tuple):
        return tuple(resolve_value(v, env) for v in value)
    if isinstance(value, dict):
        return {k: resolve_value(v, env) for k, v in value.items()}
    return value


def resolve_table(parameters: Mapping[str, Any]) -> dict[str, float]:
    """Resolve a parameter table where values may reference each other
    ('=W*2'). Deterministic, cycle-detecting, fail-loud."""
    env: dict[str, float] = {}
    pending = dict(parameters)
    progress = True
    while pending and progress:
        progress = False
        for name in sorted(pending):
            v = pending[name]
            if not is_expression(v):
                try:
                    env[name] = float(v)
                except (TypeError, ValueError):
                    raise ExprError(
                        f"parameter {name!r}: value {v!r} is neither a number "
                        f"nor an '=' expression") from None
                del pending[name]
                progress = True
                continue
            try:
                env[name] = eval_expr(v[1:], env)
            except UndefinedNameError as e:
                if e.name not in pending:
                    raise ExprError(
                        f"parameter {name!r} references undefined {e.name!r}") from None
                continue                      # dependency not resolved yet
            del pending[name]
            progress = True
    if pending:
        raise ExprError(
            f"parameter cycle: {sorted(pending)} reference each other")
    return env
