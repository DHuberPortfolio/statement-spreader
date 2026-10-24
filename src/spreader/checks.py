"""Derived lines, accounting checks and ratios, all computed by code from the spread.

A check compares two formulas for one period. Its tolerance is the rounding the statement
itself allows: each printed number can be off by half a unit of the printed scale, so a check
combining n numbers in millions may differ by up to n x 0.5 million without anything being wrong.
Passing a check does not prove the inputs right (two offsetting mistakes pass); it only proves
they are consistent. That is why low-confidence mappings go to review even when checks pass.
"""

from __future__ import annotations

from decimal import Decimal

from . import formulas
from .contracts import (
    CheckResult,
    CheckStatus,
    Period,
    ProvenanceStep,
    RatioResult,
    SpreadValue,
    StatementType,
    ValueStatus,
)
from .profile import Profile


class Env:
    """Looks up spread values for one column, joining statements by period end date."""

    def __init__(self, values: list[SpreadValue], periods: list[Period], profile: Profile) -> None:
        self.by_key: dict[tuple[str, str], SpreadValue] = {(v.line, v.period): v for v in values}
        self.periods = periods
        self.profile = profile
        self.period_by_key = {p.key: p for p in periods}

    def _key_for(self, line: str, period: Period) -> str | None:
        stmt = self.profile.line_statement.get(line)
        if stmt is StatementType.BALANCE:
            return f"{period.end}/I"
        if period.months is not None:
            return period.key
        # A balance-sheet column asking for a flow line: the year ending on that date.
        same_end = [p for p in self.periods if p.end == period.end and p.months is not None]
        if not same_end:
            return None
        return max(same_end, key=lambda p: p.months or 0).key

    def get(self, line: str, period: Period) -> Decimal | None:
        key = self._key_for(line, period)
        if key is None:
            return None
        v = self.by_key.get((line, key))
        return v.value if v else None

    def prior(self, period: Period) -> Period | None:
        earlier = [p for p in self.periods if p.months == period.months and p.end < period.end]
        return max(earlier, key=lambda p: p.end) if earlier else None

    def evaluate(self, expr: str, period: Period) -> tuple[Decimal | None, list[str], str | None]:
        prev = self.prior(period)

        def get_prior(name: str) -> Decimal | None:
            return self.get(name, prev) if prev else None

        days = Decimal(period.months * 365) / Decimal(12) if period.months else None
        return formulas.evaluate(expr, lambda n: self.get(n, period), get_prior, days)


def statement_periods(periods: list[Period], statement: StatementType, keys: set[str]) -> list[Period]:
    return [p for p in periods if p.key in keys and ((p.months is None) == (statement is StatementType.BALANCE))]


def add_derived(values: list[SpreadValue], periods: list[Period], profile: Profile,
                period_keys: dict[StatementType, set[str]]) -> tuple[list[SpreadValue], set[tuple[str, str]]]:
    """Compute template lines the statement did not print. Returns new values and checks to skip."""
    env = Env(values, periods, profile)
    added: list[SpreadValue] = []
    skip: set[tuple[str, str]] = set()
    for d in profile.derived:
        stmt = profile.line_statement[d.line]
        for p in statement_periods(periods, stmt, period_keys.get(stmt, set())):
            if env.get(d.line, p) is not None:
                continue
            if any(env.get(r, p) is None for r in d.requires):
                continue
            value, missing, _ = env.evaluate(d.expr, p)
            if value is None:
                continue
            inputs = sorted(formulas.names(d.expr))
            refs = [r for n in inputs if (sv := env.by_key.get((n, env._key_for(n, p) or ""))) for r in sv.refs]
            sv = SpreadValue(line=d.line, period=p.key, value=value, status=ValueStatus.CALCULATED,
                             confidence=min([env.by_key[(n, env._key_for(n, p) or "")].confidence
                                             for n in inputs if (n, env._key_for(n, p) or "") in env.by_key] or [1.0]),
                             refs=refs,
                             steps=[ProvenanceStep(kind="calculate",
                                                   detail=f"Not printed; calculated as {d.expr} = {value:,}")])
            added.append(sv)
            env.by_key[(d.line, p.key)] = sv
            if d.skip_check:
                skip.add((d.skip_check, p.key))
    return added, skip


def run_checks(values: list[SpreadValue], periods: list[Period], profile: Profile,
               period_keys: dict[StatementType, set[str]], scales: dict[StatementType, int],
               skip: set[tuple[str, str]]) -> list[CheckResult]:
    env = Env(values, periods, profile)
    results: list[CheckResult] = []
    for c in profile.checks:
        for p in statement_periods(periods, c.statement, period_keys.get(c.statement, set())):
            lines = sorted(formulas.names(c.lhs) | formulas.names(c.rhs))
            if (c.id, p.key) in skip:
                results.append(CheckResult(id=c.id, title=c.title, period=p.key, status=CheckStatus.SKIPPED, lines=lines,
                                           explanation="Not independent here: one side was calculated from the other."))
                continue
            lhs, miss_l, why_l = env.evaluate(c.lhs, p)
            rhs, miss_r, why_r = env.evaluate(c.rhs, p)
            if lhs is None or rhs is None:
                missing = sorted(set(miss_l + miss_r))
                reason = why_l or why_r or "missing"
                results.append(CheckResult(id=c.id, title=c.title, period=p.key, status=CheckStatus.SKIPPED, lines=lines,
                                           explanation=f"Not checked: {', '.join(missing) or reason} {'not in the spread' if missing else ''}".strip()))
                continue
            involved = {profile.line_statement[n] for n in lines}
            scale = max(scales.get(s, 1) for s in involved)
            terms = formulas.term_count(c.lhs) + formulas.term_count(c.rhs)
            tol = Decimal(terms) * Decimal("0.5") * Decimal(scale)
            if c.relative_tolerance:
                tol = max(tol, abs(rhs) * Decimal(str(c.relative_tolerance)))
            diff = lhs - rhs
            ok = abs(diff) <= tol
            expl = "" if ok else (
                f"{c.lhs} = {lhs:,} but {c.rhs} = {rhs:,}; they differ by {diff:,} (allowed {tol:,})."
                + (f" {c.note}" if c.note else "")
            )
            results.append(CheckResult(id=c.id, title=c.title, period=p.key,
                                       status=CheckStatus.PASS if ok else CheckStatus.FAIL,
                                       lhs=lhs, rhs=rhs, difference=diff, tolerance=tol, lines=lines, explanation=expl))
    return results


def run_ratios(values: list[SpreadValue], periods: list[Period], profile: Profile) -> list[RatioResult]:
    env = Env(values, periods, profile)
    flow_periods = [p for p in periods if p.months is not None]
    columns = flow_periods or periods
    out: list[RatioResult] = []
    for r in profile.ratios:
        for p in columns:
            value, missing, why = env.evaluate(r.expr, p)
            inputs = {n: env.get(n, p) for n in sorted(formulas.names(r.expr))}
            reason = None
            if value is None:
                reason = f"Not computable: {', '.join(missing)} missing" if missing else f"Not computable: {why}"
            out.append(RatioResult(id=r.id, label=r.label, period=p.key, value=value, format=r.format, formula=r.expr,
                                   inputs=inputs, reason=reason, note=r.note))
    return out
