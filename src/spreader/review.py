"""What a person must look at, and which spread values each item touches.

A value with no review item on it is "auto-accepted". The evaluator's silent error rate is the
share of auto-accepted values that are wrong, so every reason to doubt a value must end up here.
"""

from __future__ import annotations

from decimal import Decimal

from .contracts import (
    CheckResult,
    CheckStatus,
    RatioResult,
    ReviewItem,
    ReviewKind,
    RowMapping,
    RowRole,
    Severity,
    SpreadValue,
    StatementResult,
    StatementType,
)
from .mapping import CONFIDENCE_REVIEW, CONFIDENCE_REVIEW_CRITICAL
from .profile import Profile

JUMP_FACTOR = Decimal(10)  # a line changing more than 10x between adjacent periods is suspicious


def build_review(statements: dict[str, StatementResult], values: list[SpreadValue], checks: list[CheckResult],
                 profile: Profile, ratios: list[RatioResult] | None = None) -> list[ReviewItem]:
    items: list[ReviewItem] = []

    for stype in profile.statements:
        if stype.value not in statements:
            items.append(ReviewItem(id=f"missing:{stype.value}", kind=ReviewKind.MISSING_STATEMENT, severity=Severity.WARNING,
                                    statement=stype,
                                    message=f"No {profile.statements[stype].title.lower()} was found in this document."))

    for skey, res in statements.items():
        t = res.table
        stype = StatementType(skey)
        if t.scale.assumed:
            items.append(ReviewItem(id=f"scale:{skey}", kind=ReviewKind.ASSUMED_SCALE, severity=Severity.BLOCKER, statement=stype,
                                    message=f"{t.scale.evidence} Values were taken as printed (units). Confirm the unit before approving.",
                                    lines=[m.canonical for m in res.mappings if m.canonical],
                                    periods=[p.key for p in t.periods]))
        for p in t.periods:
            if p.assumed:
                items.append(ReviewItem(id=f"period:{skey}:{p.key}", kind=ReviewKind.ASSUMED_PERIOD, severity=Severity.WARNING,
                                        statement=stype, message=f"Column '{p.label}': " + " ".join(p.assumed),
                                        lines=[m.canonical for m in res.mappings if m.canonical], periods=[p.key]))
        for w in t.warnings:
            if w.startswith("DUPLICATE_PERIOD:"):
                pk = w.split(":")[1]
                items.append(ReviewItem(id=f"dup_period:{skey}:{pk}", kind=ReviewKind.CONFLICT, severity=Severity.BLOCKER,
                                        statement=stype, periods=[pk],
                                        lines=[m.canonical for m in res.mappings if m.canonical],
                                        message=w.split(":", 2)[2].strip().capitalize()))
            if w.startswith("COMPETING_TABLE:"):
                items.append(ReviewItem(id=f"competing:{skey}", kind=ReviewKind.CONFLICT, severity=Severity.WARNING,
                                        statement=stype, message=w.split(":", 1)[1].strip()))
        by_index = {r.index: r for r in t.rows}
        mapping_of = {m.row_index: m for m in res.mappings}
        for row in t.rows:
            bad = [(k, v) for k, v in row.values.items() if v.note and v.displayed is None]
            for k, v in bad:
                items.append(ReviewItem(id=f"unreadable:{skey}:{row.index}:{k}", kind=ReviewKind.UNREADABLE,
                                        severity=Severity.WARNING, statement=stype, rows=[row.index], periods=[k],
                                        lines=[mapping_of[row.index].canonical] if mapping_of.get(row.index) and mapping_of[row.index].canonical else [],
                                        message=f"Row '{row.label}': {v.note}."))
            looks_total = row.label_clean.startswith("total") and row.unit.value == "money"
            # A "total" with no detail rows of its own above it (the only revenue line, labelled
            # "Total revenue") has nothing to foot against.
            pos = t.rows.index(row)
            prev = next((r for r in reversed(t.rows[:pos]) if r.role is RowRole.HEADER or r.role is RowRole.TOTAL
                         or r.values), None)
            standalone = prev is None or prev.role is not RowRole.DETAIL
            if looks_total and not standalone and row.role is not RowRole.TOTAL and row.values:
                m = mapping_of.get(row.index)
                items.append(ReviewItem(
                    id=f"footing:{skey}:{row.index}", kind=ReviewKind.FOOTING, severity=Severity.WARNING, statement=stype,
                    rows=[row.index], lines=[m.canonical] if m and m.canonical else [], periods=list(row.values),
                    message=(f"'{row.label}' does not equal the sum of the rows directly above it. Either a number was "
                             "misread or the document's own subtotal does not add up; compare it with the source.")))
        # Mapping problems on rows whose numbers reach the spread.
        components = {c for r in t.rows if r.role is RowRole.TOTAL and mapping_of.get(r.index) and mapping_of[r.index].canonical
                      for c in r.children if mapping_of.get(c) and mapping_of[c].canonical == mapping_of[r.index].canonical}
        for m in res.mappings:
            row = by_index[m.row_index]
            has_values = any(v.displayed is not None and v.displayed != 0 for v in row.values.values())
            if not has_values or m.excluded:
                continue
            if m.canonical is None:
                inside_total = any(m.row_index in r.children for r in t.rows if r.role is RowRole.TOTAL
                                   and mapping_of.get(r.index) and mapping_of[r.index].canonical)
                sev = Severity.INFO if inside_total else Severity.WARNING
                cand = ", ".join(f"{profile.lines[c].label} ({s:.0%})" for c, s in m.candidates[:3] if c in profile.lines)
                items.append(ReviewItem(
                    id=f"unmapped:{skey}:{row.index}", kind=ReviewKind.UNMAPPED_ROW, severity=sev, statement=stype,
                    rows=[row.index], periods=list(row.values),
                    message=(f"Row '{row.label}' was not placed on any template line" +
                             (" (it is inside a total that was placed, so the total already counts it)." if inside_total
                              else ". Its amount is not in the spread.") + (f" Closest: {cand}." if cand else ""))))
                continue
            if m.row_index in components:
                continue
            critical = profile.lines[m.canonical].critical
            threshold = CONFIDENCE_REVIEW_CRITICAL if critical else CONFIDENCE_REVIEW
            if m.confidence < threshold:
                items.append(ReviewItem(
                    id=f"confidence:{skey}:{row.index}", kind=ReviewKind.LOW_CONFIDENCE,
                    severity=Severity.WARNING, statement=stype, rows=[row.index], lines=[m.canonical],
                    periods=list(row.values),
                    message=(f"'{row.label}' was placed on {profile.lines[m.canonical].label} with {m.confidence:.0%} "
                             f"confidence ({m.method.value}): {m.reason}")))

    for c in checks:
        if c.status is not CheckStatus.FAIL:
            continue
        cdef = next(cd for cd in profile.checks if cd.id == c.id)
        sev = Severity.BLOCKER if cdef.severity == "blocker" else Severity.WARNING
        hint = _likely_causes(c, statements, profile)
        items.append(ReviewItem(id=f"check:{c.id}:{c.period}", kind=ReviewKind.FAILED_CHECK, severity=sev,
                                statement=cdef.statement, lines=c.lines, periods=[c.period],
                                message=f"{c.title}: failed. {c.explanation}{(' ' + hint) if hint else ''}"))

    # Covenant and policy limits on ratios.
    for r in ratios or []:
        rdef = next((d for d in profile.ratios if d.id == r.id), None)
        if rdef is None or (rdef.min is None and rdef.max is None):
            continue
        limit = " and ".join(x for x in [f"at least {rdef.min}" if rdef.min is not None else "",
                                          f"at most {rdef.max}" if rdef.max is not None else ""] if x)
        lines = sorted(r.inputs)
        if r.value is None:
            items.append(ReviewItem(id=f"covenant:{r.id}:{r.period}", kind=ReviewKind.SUSPICIOUS, severity=Severity.WARNING,
                                    lines=lines, periods=[r.period],
                                    message=f"{r.label} must be {limit}, but it cannot be computed ({r.reason})."))
        elif (rdef.min is not None and r.value < Decimal(str(rdef.min))) or (rdef.max is not None and r.value > Decimal(str(rdef.max))):
            items.append(ReviewItem(id=f"covenant:{r.id}:{r.period}", kind=ReviewKind.SUSPICIOUS, severity=Severity.BLOCKER,
                                    lines=lines, periods=[r.period],
                                    message=f"{r.label} is {r.value:.2f}; the limit is {limit}. Confirm the inputs, then "
                                            "record the breach (resolving this item needs a note)."))

    # Suspicious values that pass every check.
    by_line: dict[str, list[SpreadValue]] = {}
    for v in values:
        by_line.setdefault(v.line, []).append(v)
    for line, vals in by_line.items():
        ldef = profile.lines[line]
        for v in vals:
            if v.value is not None and v.value < 0 and ldef.kind in {"income", "asset"} and line in {
                    "revenue", "total_assets", "total_current_assets", "cash"}:
                items.append(ReviewItem(id=f"suspicious:neg:{line}:{v.period}", kind=ReviewKind.SUSPICIOUS,
                                        severity=Severity.BLOCKER, lines=[line], periods=[v.period],
                                        message=f"{ldef.label} is negative ({v.value:,}); check the sign and the column."))
        same_len: dict[str, list[SpreadValue]] = {}
        for v in vals:
            suffix = v.period.split("/")[-1]
            same_len.setdefault(suffix, []).append(v)
        for group in same_len.values():
            group.sort(key=lambda v: v.period)
            for a, b in zip(group, group[1:], strict=False):
                if a.value and b.value and a.value != 0 and b.value != 0:
                    ratio = abs(b.value / a.value)
                    if ratio > JUMP_FACTOR or ratio < 1 / JUMP_FACTOR:
                        if abs(a.value) < 1000 and abs(b.value) < 1000:
                            continue
                        items.append(ReviewItem(
                            id=f"suspicious:jump:{line}:{a.period}:{b.period}", kind=ReviewKind.SUSPICIOUS,
                            severity=Severity.WARNING, lines=[line], periods=[a.period, b.period],
                            message=(f"{ldef.label} changes {ratio:.1f}x between {a.period} ({a.value:,}) and "
                                     f"{b.period} ({b.value:,}). Real, or a scale or column mix-up?")))
    return items


def _likely_causes(c: CheckResult, statements: dict[str, StatementResult], profile: Profile) -> str:
    hints: list[str] = []
    # The most useful pointer: a printed row whose amount equals the difference.
    if c.difference not in (None, Decimal(0)):
        for res in statements.values():
            mult = Decimal(res.table.scale.multiplier)
            maps = {m.row_index: m for m in res.mappings}
            for r in res.table.rows:
                v = r.values.get(c.period) or r.values.get(c.period.split("/")[0] + "/I")
                if v is None or v.displayed in (None, Decimal(0)) or c.difference is None or c.tolerance is None:
                    continue
                if abs(abs(v.displayed * mult) - abs(c.difference)) <= max(c.tolerance, mult):
                    m = maps.get(r.index)
                    where = (f"placed on {profile.lines[m.canonical].label}" if m and m.canonical else "not placed")
                    hints.append(f"the difference equals '{r.label}' ({v.raw}, {where})")
            if len(hints) >= 2:
                break
        if hints:
            return "Possible cause: " + "; ".join(hints[:2]) + "."
    stmt = next((cd.statement.value for cd in profile.checks if cd.id == c.id), None)
    for skey, res in statements.items():
        if stmt and skey != stmt:
            continue
        unmapped = [r for r in res.table.rows for m in res.mappings
                    if m.row_index == r.index and m.canonical is None and not m.excluded
                    and r.values.get(c.period) is not None and r.values[c.period].displayed not in (None, Decimal(0))]
        for r in unmapped[:3]:
            hints.append(f"'{r.label}' ({r.values[c.period].raw}) is not placed")
    if hints:
        return "Possible cause: " + "; ".join(hints) + "."
    return ""


def attach_flags(values: list[SpreadValue], items: list[ReviewItem]) -> None:
    """Record on each value the open review items that concern it (same line and period)."""
    index: dict[tuple[str, str], SpreadValue] = {(v.line, v.period): v for v in values}
    for v in values:
        v.flags = []
    for it in items:
        if it.resolved or it.severity is Severity.INFO:
            continue
        for line in it.lines:
            for p in it.periods:
                v = index.get((line, p))
                if v is None and p.endswith("M"):
                    # balance-sheet lines in a flow check: match by end date
                    v = index.get((line, p.split("/")[0] + "/I"))
                if v is not None and it.id not in v.flags:
                    v.flags.append(it.id)


def is_auto_accepted(v: SpreadValue) -> bool:
    return not v.flags


def unresolved_blockers(items: list[ReviewItem]) -> list[ReviewItem]:
    return [i for i in items if i.severity is Severity.BLOCKER and not i.resolved]


def mapping_for(statements: dict[str, StatementResult], stype: str, row_index: int) -> RowMapping | None:
    res = statements.get(stype)
    if res is None:
        return None
    return next((m for m in res.mappings if m.row_index == row_index), None)
