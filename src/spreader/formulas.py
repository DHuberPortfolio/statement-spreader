"""A small, safe formula language for checks, derived lines and ratios.

Formulas come from the profile (config), which a deployment edits, so they are parsed into a
syntax tree and walked here; Python's eval() is never used. Allowed:

    names         canonical line ids; "x_or_zero" reads x and uses 0 when it is missing
    + - * /       on Decimals; division by zero makes the result not computable
    sum_present(a, b, ...)   sum of the arguments that are present; missing if none are
    coalesce(a, b, ...)      the first argument that is present
    prior(x)                 x in the previous period of the same length
    days()                   days in the period (months x 365 / 12)
    numbers       literal constants

A formula whose inputs are missing returns None plus the names that were missing, so a check
or ratio can say "not computable: interest_expense missing" instead of silently using zero.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from decimal import Decimal, DivisionByZero, InvalidOperation
from functools import lru_cache

FUNCTIONS = {"sum_present", "coalesce", "prior", "days"}
OR_ZERO = "_or_zero"


class FormulaError(ValueError):
    pass


@lru_cache(maxsize=512)
def parse(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Cannot parse formula '{expr}': {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Expression | ast.Load | ast.operator | ast.unaryop | ast.Name):
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
            continue
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise FormulaError(f"Formula '{expr}' calls something that is not allowed")
            if node.func.id == "prior" and (len(node.args) != 1 or not isinstance(node.args[0], ast.Name)):
                raise FormulaError(f"prior() takes one line name in '{expr}'")
            continue
        raise FormulaError(f"Formula '{expr}' uses '{type(node).__name__}', which is not allowed")
    return tree


def names(expr: str) -> set[str]:
    """Line ids a formula reads (with any _or_zero suffix removed)."""
    out: set[str] = set()
    for node in ast.walk(parse(expr)):
        if isinstance(node, ast.Name) and node.id not in FUNCTIONS:
            n = node.id
            out.add(n[: -len(OR_ZERO)] if n.endswith(OR_ZERO) else n)
    return out


def term_count(expr: str) -> int:
    """How many values a formula combines (used to size rounding tolerance)."""
    return sum(1 for node in ast.walk(parse(expr)) if isinstance(node, ast.Name) and node.id not in FUNCTIONS)


Getter = Callable[[str], Decimal | None]


class Missing(Exception):
    def __init__(self, names: list[str], reason: str = "missing") -> None:
        super().__init__(", ".join(names))
        self.names = names
        self.reason = reason


def evaluate(expr: str, get: Getter, get_prior: Getter | None = None, days: Decimal | None = None
             ) -> tuple[Decimal | None, list[str], str | None]:
    """Evaluate a formula. Returns (value, missing names, reason when not computable)."""
    tree = parse(expr)

    def ev(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            n = node.id
            if n.endswith(OR_ZERO):
                v = get(n[: -len(OR_ZERO)])
                return v if v is not None else Decimal(0)
            v = get(n)
            if v is None:
                raise Missing([n])
            return v
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if b == 0:
                raise Missing([], "division by zero")
            try:
                return a / b
            except (DivisionByZero, InvalidOperation) as exc:  # pragma: no cover
                raise Missing([], "division by zero") from exc
        if isinstance(node, ast.Call):
            fn = node.func.id  # type: ignore[attr-defined]
            if fn == "days":
                if days is None:
                    raise Missing([], "the period length is unknown")
                return days
            if fn == "prior":
                name = node.args[0].id  # type: ignore[attr-defined]
                if get_prior is None:
                    raise Missing([f"prior({name})"], "no earlier period")
                v = get_prior(name)
                if v is None:
                    raise Missing([f"prior({name})"], "no earlier period")
                return v
            vals: list[Decimal] = []
            missing: list[str] = []
            for arg in node.args:
                try:
                    vals.append(ev(arg))
                except Missing as m:
                    if m.reason != "missing":
                        raise
                    missing.extend(m.names)
                    if fn == "coalesce":
                        continue
            if fn == "coalesce":
                if not vals:
                    raise Missing(missing)
                return vals[0]
            if not vals:  # sum_present with nothing present
                raise Missing(missing)
            return sum(vals, Decimal(0))
        raise FormulaError(f"Unsupported node {type(node).__name__}")  # pragma: no cover - parse() rejects it

    try:
        return ev(tree), [], None
    except Missing as m:
        return None, m.names, m.reason
