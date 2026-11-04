"""Each open review item in plain words, with the numbers behind it and what could fix it (D63).

A review item's message says what happened in the engine's terms. A reviewer needs more: what is wrong, why it stops
approval or asks for a look, which values it touches, and what would fix it. All of that is worked out here from the
spread itself, at read time, and nothing here changes a value or decides anything: a suggestion is only ever applied by
a person, who says why.

A suggestion that says a person looked ("I compared these with the filing") never carries a written reason: that
sentence has to be theirs. One that follows from the numbers ("this row equals the gap") does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Any

from rapidfuzz import fuzz

from .contracts import CheckResult, CheckStatus, ReviewItem, ReviewKind, RowMapping, Severity, Spread, SpreadValue, StatementRow
from .echo import is_catch_all
from .formulas import names
from .profile import CheckDef, Profile

MIN_LINE_SIMILARITY = 75
MAX_COMBINATION = 3  # rows that together close a gap: more than this is coincidence
MAX_ROWS_SEARCHED = 14
# Wording no alias covers, for a suggestion only: mapping itself never reads this.
HINTS = {"intangibles": re.compile(r"trademark|brand|patent|licen[cs]e|franchise|customer relationship", re.I),
         "other_nonoperating": re.compile(r"\b(income|gain|gains|equity in)\b", re.I)}

BLOCKS = "Approval is locked until this is fixed, or a person accepts it with a reason."
WARNS = "This does not lock approval, but a person should look before relying on these numbers."

TITLES = {
    ReviewKind.UNMAPPED_ROW: "A printed row has no place in the spread",
    ReviewKind.LOW_CONFIDENCE: "The engine is unsure where this row belongs",
    ReviewKind.FAILED_CHECK: "The numbers do not add up",
    ReviewKind.FOOTING: "A printed total does not match the rows above it",
    ReviewKind.ASSUMED_SCALE: "The unit had to be assumed",
    ReviewKind.ASSUMED_PERIOD: "The period had to be assumed",
    ReviewKind.MISSING_STATEMENT: "A statement or a year is missing",
    ReviewKind.CONFLICT: "The document gives conflicting information",
    ReviewKind.SUSPICIOUS: "This number looks wrong",
    ReviewKind.UNREADABLE: "A number could not be read reliably",
    ReviewKind.PRIOR_PERIOD: "This differs from the approved spread",
    ReviewKind.SECOND_READER: "Two readings of this number disagree",
    ReviewKind.CURRENCY: "The currency needs a look",
    ReviewKind.UNCONFIRMED: "These values were not confirmed twice",
}

RISK = {
    ReviewKind.UNMAPPED_ROW: "Its amount is left out of the spread, so a total or ratio built on it could be wrong.",
    ReviewKind.LOW_CONFIDENCE: "If the row is on the wrong line, every ratio using that line is wrong even though the "
                               "number was read correctly.",
    ReviewKind.FAILED_CHECK: "A credit decision would rest on figures that do not agree with each other.",
    ReviewKind.FOOTING: "Either a number was misread or the document's own subtotal is off.",
    ReviewKind.ASSUMED_SCALE: "A unit read wrong makes every number on the statement wrong by 1,000 times or more.",
    ReviewKind.ASSUMED_PERIOD: "Values dated to the wrong period would be compared with the wrong year.",
    ReviewKind.MISSING_STATEMENT: "Without it, the spread is incomplete and some checks cannot run.",
    ReviewKind.CONFLICT: "The engine cannot tell which information to trust, so a person has to decide.",
    ReviewKind.SUSPICIOUS: "A scale, sign or column mix-up often looks like this.",
    ReviewKind.UNREADABLE: "A misread digit would pass into the spread unnoticed.",
    ReviewKind.PRIOR_PERIOD: "It is either a restatement by the company or a misread now.",
    ReviewKind.SECOND_READER: "One of the two readings is wrong.",
    ReviewKind.CURRENCY: "Amounts in another currency are not comparable with this template's.",
    ReviewKind.UNCONFIRMED: "One check can hold while a value in it is wrong, so a value goes out alone only when two "
                            "separate confirmations agree with it.",
}

MODES = {
    ReviewKind.UNMAPPED_ROW: ["move", "exclude", "accept"],
    ReviewKind.LOW_CONFIDENCE: ["accept", "move", "exclude"],
    ReviewKind.FAILED_CHECK: ["move", "value", "accept"],
    ReviewKind.FOOTING: ["value", "move", "accept"],
    ReviewKind.SUSPICIOUS: ["value", "move", "accept"],
    ReviewKind.UNREADABLE: ["value", "accept"],
    ReviewKind.PRIOR_PERIOD: ["value", "accept"],
    ReviewKind.SECOND_READER: ["value", "accept"],
    ReviewKind.UNCONFIRMED: ["accept", "value", "move"],
}


def _label(row: StatementRow) -> str:
    """The row's label; a dash the filing's encoding lost shows as a dash, not a replacement character."""
    return row.label.replace("�", "-")


def _period_value(row: StatementRow, period: str) -> Decimal | None:
    pv = row.values.get(period) or row.values.get(period.split("/")[0] + "/I")
    return pv.displayed if pv is not None and pv.displayed not in (None, Decimal(0)) else None


def _find(values: Iterable[SpreadValue], line: str, period: str) -> SpreadValue | None:
    keys = {period, period.split("/")[0] + "/I"}
    return next((v for v in values if v.line == line and v.period in keys), None)


def best_line(row: StatementRow, mapping: RowMapping | None, profile: Profile, lines: list[str]) -> str | None:
    """The likeliest line among `lines` for a row: what the mapper considered, then the wording, then a catch-all.
    Never a total or a result: a printed detail row does not belong on either."""
    lines = [ln for ln in lines if not ln.startswith("total_") and profile.lines[ln].kind != "result"]
    for ln, pattern in HINTS.items():
        if ln in lines and pattern.search(row.label_clean):
            return ln
    if mapping is not None:
        for cand, _ in mapping.candidates:
            if cand in lines:
                return cand
    best, score = None, 0.0
    for ln in lines:
        words = [profile.lines[ln].label, *(a.replace("*", " ").strip() for a in profile.lines[ln].aliases)]
        s = max(fuzz.token_sort_ratio(row.label_clean, w.lower()) for w in words if w)
        if s > score:
            best, score = ln, s
    if best is not None and score >= MIN_LINE_SIMILARITY:
        return best
    return next((ln for ln in lines if is_catch_all(ln)), None)


def _row_entry(statement: str, row: StatementRow, mapping: RowMapping | None, period: str, mult: Decimal,
               profile: Profile) -> dict[str, Any]:
    amount = _period_value(row, period)
    line = mapping.canonical if mapping is not None else None
    return {"statement": statement, "row": row.index, "label": _label(row), "section": row.section,
            "amount": str(amount * mult) if amount is not None else None, "line": line,
            "line_label": profile.lines[line].label if line else None,
            "excluded": bool(mapping.excluded) if mapping is not None else False}


def _value_entry(line: str, period: str, spread: Spread, profile: Profile, confirmed_by: list[str] | None = None,
                 ) -> dict[str, Any]:
    v = _find(spread.values, line, period)
    return {"line": line, "label": profile.lines[line].label, "period": v.period if v else period,
            "value": str(v.value) if v is not None and v.value is not None else None,
            "status": v.status.value if v is not None else "missing", "rows": list(v.source_rows) if v is not None else [],
            "confirmed_by": confirmed_by or []}


def _sum_lines(cdef: CheckDef, c: CheckResult, profile: Profile) -> list[str]:
    totals = names(cdef.lhs)
    return [ln for ln in c.lines if ln not in totals and not ln.startswith("total_")
            and profile.line_statement.get(ln) == cdef.statement]


def _failed_check(item: ReviewItem, spread: Spread, profile: Profile) -> dict[str, Any]:
    cid, period = item.id.split(":", 2)[1:]
    c = next((x for x in spread.checks if x.id == cid and x.period == period), None)
    cdef = next((x for x in profile.checks if x.id == cid), None)
    if c is None or cdef is None:
        return {}
    res = spread.statements.get(cdef.statement.value)
    gap = abs(c.difference) if c.difference is not None else None
    tol = c.tolerance or Decimal(0)
    out: dict[str, Any] = {
        "what": f"{c.title}, but they do not for this period.",
        "compare": {"left_label": _side_label(cdef.lhs, profile), "left": str(c.lhs), "right_label": _side_label(cdef.rhs, profile),
                    "right": str(c.rhs), "gap": str(gap)} if gap is not None else None,
        "suggestions": [], "rows": []}
    if res is None or gap is None:
        return out
    mult = Decimal(res.table.scale.multiplier)
    statement = cdef.statement.value
    maps = {m.row_index: m for m in res.mappings}
    targets = _sum_lines(cdef, c, profile) or [ln for ln, st in profile.line_statement.items() if st == cdef.statement]
    unplaced: list[tuple[StatementRow, Decimal]] = []
    set_aside: list[tuple[StatementRow, Decimal]] = []
    placed_elsewhere: list[tuple[StatementRow, Decimal]] = []
    for r in res.table.rows:
        m = maps.get(r.index)
        amount = _period_value(r, period)
        if m is None or amount is None:
            continue
        full = amount * mult
        if m.excluded:
            set_aside.append((r, full))
        elif m.canonical is None:
            unplaced.append((r, full))
        elif m.canonical not in c.lines:
            placed_elsewhere.append((r, full))
    out["rows"] = [_row_entry(statement, r, maps.get(r.index), period, mult, profile) for r, _ in unplaced]

    def move(r: StatementRow, why: str, strength: str, reason: str) -> None:
        line = best_line(r, maps.get(r.index), profile, targets)
        out["suggestions"].append({
            "strength": strength,
            "title": f"Place '{_label(r)}' on {profile.lines[line].label}" if line else f"Place '{_label(r)}' on a line",
            "detail": why, "fix": {"mode": "move", "statement": statement, "row": r.index, "line": line}, "reason": reason})

    exact = [(r, a) for r, a in unplaced if abs(abs(a) - gap) <= tol]
    for r, a in exact:
        move(r, f"This row is left out of the spread and its amount ({a:,.0f}) equals the gap exactly.", "strong",
             f"'{_label(r)}' was left unplaced and equals the gap in this check.")
    if not exact:
        pool = sorted(unplaced, key=lambda x: -abs(x[1]))[:MAX_ROWS_SEARCHED]
        found = next((combo for k in range(2, MAX_COMBINATION + 1) for combo in combinations(pool, k)
                      if abs(abs(sum((a for _, a in combo), Decimal(0))) - gap) <= tol), None)
        for r, _ in found or ():
            others = " and ".join(f"'{_label(o)}'" for o, _ in found if o is not r)  # type: ignore[union-attr]
            move(r, f"Together with {others}, this row's amount equals the gap exactly. Place each of them.", "strong",
                 f"'{_label(r)}' was left unplaced; with {others} it equals the gap in this check.")
        if found is None:
            for r, a in unplaced[:4]:
                move(r, f"This row ({a:,.0f}) is left out of the spread and may belong in this sum, but it does not close "
                        "the gap alone.", "possible", f"'{_label(r)}' was left unplaced and belongs in this sum.")
    for r, a in placed_elsewhere:
        if abs(abs(a) - gap) <= tol:
            line = best_line(r, maps.get(r.index), profile, targets)
            holder = profile.lines[maps[r.index].canonical].label  # type: ignore[index]
            out["suggestions"].append({
                "strength": "possible", "title": f"Move '{_label(r)}' off {holder}",
                "detail": f"It sits on {holder}, outside this sum, and its amount equals the gap.",
                "fix": {"mode": "move", "statement": statement, "row": r.index, "line": line},
                "reason": f"'{_label(r)}' was on {holder}, but its amount equals the gap in this check."})
    for r, a in set_aside:
        if abs(abs(a) - gap) <= tol:
            out["suggestions"].append({
                "strength": "possible", "title": f"Use the printed subtotal '{_label(r)}'",
                "detail": "It was set aside so its rows are not counted twice, and its amount equals the gap.",
                "fix": {"mode": "move", "statement": statement, "row": r.index, "line": None},
                "reason": f"The printed subtotal '{_label(r)}' equals the gap in this check."})
    out["suggestions"].append({
        "strength": "manual", "title": "The figures are right as printed",
        "detail": "Use this when you have compared them with the document and the sum simply does not apply to this "
                  "company, for example a line the template has no place for.", "fix": {"mode": "accept"}, "reason": ""})
    return out


def _side_label(formula: str, profile: Profile) -> str:
    """One line's name, or a plain name for a sum."""
    return profile.lines[formula].label if formula in profile.lines else "Calculated from the lines"


def _unconfirmed(item: ReviewItem, spread: Spread, profile: Profile) -> dict[str, Any]:
    period = item.periods[0]
    keys = {period, period.split("/")[0] + "/I"}
    entries = []
    for ln in item.lines:
        by = [c.title for c in spread.checks if c.status is CheckStatus.PASS and ln in c.lines and c.period in keys]
        by += ["Same number printed elsewhere" for e in spread.echoes if e.line == ln and e.period in keys]
        by += [c.detail for c in spread.confirmations if c.line == ln and c.period in keys]
        entries.append(_value_entry(ln, period, spread, profile, list(dict.fromkeys(by))))
    n = len(entries)
    return {
        "what": f"{n} value{'s' if n != 1 else ''} for this period {'are' if n != 1 else 'is'} probably fine: nothing "
                "doubts them. But fewer than two separate confirmations back them, so they wait for a person.",
        "values": entries,
        "suggestions": [{"strength": "manual", "title": "Compare them with the document",
                         "detail": "Open each value's source row. If they match what is printed, accept them.",
                         "fix": {"mode": "accept"}, "reason": ""}]}


def _unmapped(item: ReviewItem, spread: Spread, profile: Profile) -> dict[str, Any]:
    if item.statement is None or not item.rows:
        return {}
    res = spread.statements.get(item.statement.value)
    if res is None:
        return {}
    statement = item.statement.value
    maps = {m.row_index: m for m in res.mappings}
    mult = Decimal(res.table.scale.multiplier)
    rows = [r for r in res.table.rows if r.index in item.rows]
    lines = [ln for ln, st in profile.line_statement.items() if st == item.statement]
    period = item.periods[0] if item.periods else (res.table.periods[0].key if res.table.periods else "")
    out: dict[str, Any] = {"rows": [_row_entry(statement, r, maps.get(r.index), period, mult, profile) for r in rows],
                           "suggestions": []}
    if item.kind is ReviewKind.LOW_CONFIDENCE and rows and maps.get(rows[0].index) and maps[rows[0].index].canonical:
        m = maps[rows[0].index]
        out["what"] = (f"'{_label(rows[0])}' was placed on {profile.lines[m.canonical].label}"  # type: ignore[index]
                       f" by its wording. Matches of this kind were measured below the bar for going out without a look.")
    for r in rows[:3]:
        m = maps.get(r.index)
        chosen = best_line(r, m, profile, [ln for ln in lines if ln != (m.canonical if m else None)])
        current = profile.lines[m.canonical].label if m and m.canonical else None
        if item.kind is ReviewKind.LOW_CONFIDENCE and current:
            out["suggestions"].append({
                "strength": "strong", "title": f"Keep '{_label(r)}' on {current}",
                "detail": f"Use this if '{_label(r)}' really is {current}.",
                "fix": {"mode": "accept"}, "reason": ""})
        if chosen:
            out["suggestions"].append({
                "strength": "possible", "title": f"Place '{_label(r)}' on {profile.lines[chosen].label}",
                "detail": "The closest line by its wording.",
                "fix": {"mode": "move", "statement": statement, "row": r.index, "line": chosen},
                "reason": f"'{_label(r)}' belongs on {profile.lines[chosen].label}."})
    out["suggestions"].append({
        "strength": "manual", "title": "Leave it off the spread",
        "detail": "Use this when the row is a subtotal or a memo line whose amount is already counted.",
        "fix": {"mode": "exclude", "statement": statement, "row": rows[0].index if rows else None}, "reason": ""})
    return out


def _prior(item: ReviewItem, spread: Spread, profile: Profile) -> dict[str, Any]:
    out: dict[str, Any] = {"suggestions": []}
    m = re.search(r"approved spread says ([-\d,.]+)", item.message)
    line = item.lines[0] if item.lines else None
    period = item.periods[0] if item.periods else None
    if m and line and period:
        try:
            value = Decimal(m.group(1).rstrip(".").replace(",", ""))
        except InvalidOperation:
            value = None
        if value is not None:
            out["suggestions"].append({
                "strength": "possible", "title": f"Use the approved value, {value:,}",
                "detail": "If this year's number was misread, the approved one is right.",
                "fix": {"mode": "value", "line": line, "period": period, "value": str(value)},
                "reason": "Misread: the document shows the approved figure."})
    out["suggestions"].append({
        "strength": "manual", "title": "Keep this year's number", "detail": "Use this when the company restated the figure: "
        "look for a restatement note, and say where it is.", "fix": {"mode": "accept"}, "reason": ""})
    return out


def _accept_only(item: ReviewItem) -> dict[str, Any]:
    if item.kind is ReviewKind.ASSUMED_SCALE:
        return {"suggestions": [{"strength": "manual", "title": "Confirm the unit", "detail": "Find where the document "
                "states it. The note must contain the word 'confirm', as in: Confirm: in thousands, page 3.",
                "fix": {"mode": "accept"}, "reason": ""}]}
    return {"suggestions": [{"strength": "manual", "title": "Compare it with the document",
                             "detail": "If it is fine, accept it and say what you checked.", "fix": {"mode": "accept"},
                             "reason": ""}]}


def _headline(item: ReviewItem, spread: Spread, profile: Profile) -> str:
    """One line for the list of issues: which check, row or values this is."""
    if item.kind is ReviewKind.FAILED_CHECK:
        cid, period = item.id.split(":", 2)[1:]
        c = next((x for x in spread.checks if x.id == cid and x.period == period), None)
        if c is not None:
            return c.title
    if item.statement is not None and item.rows:
        res = spread.statements.get(item.statement.value)
        row = next((r for r in res.table.rows if r.index == item.rows[0]), None) if res else None
        if row is not None:
            return _label(row)
    if item.kind is ReviewKind.UNCONFIRMED:
        return f"{len(item.lines)} value{'s' if len(item.lines) != 1 else ''} to compare with the document"
    return TITLES.get(item.kind, "This needs a look")


def explain_item(item: ReviewItem, spread: Spread, profile: Profile) -> dict[str, Any]:
    if item.kind is ReviewKind.FAILED_CHECK:
        extra = _failed_check(item, spread, profile)
    elif item.kind is ReviewKind.UNCONFIRMED:
        extra = _unconfirmed(item, spread, profile)
    elif item.kind in (ReviewKind.UNMAPPED_ROW, ReviewKind.LOW_CONFIDENCE):
        extra = _unmapped(item, spread, profile)
    elif item.kind is ReviewKind.PRIOR_PERIOD:
        extra = _prior(item, spread, profile)
    else:
        extra = _accept_only(item)
    blocker = item.severity is Severity.BLOCKER
    values = extra.get("values")
    if values is None:
        values = [_value_entry(ln, p, spread, profile) for ln in item.lines[:24] for p in item.periods[:1]]
    return {"title": TITLES.get(item.kind, "This needs a look"), "headline": _headline(item, spread, profile), "what": extra.get("what") or item.message,
            "why": f"{BLOCKS if blocker else WARNS} {RISK.get(item.kind, '')}".strip(),
            "compare": extra.get("compare"), "values": values, "rows": extra.get("rows", []),
            "suggestions": extra.get("suggestions", []), "modes": MODES.get(item.kind, ["accept"]),
            "needs_confirm_word": item.kind is ReviewKind.ASSUMED_SCALE}


def explain(spread: Spread, profile: Profile) -> dict[str, dict[str, Any]]:
    """Open blockers and warnings, by review item id."""
    return {i.id: explain_item(i, spread, profile) for i in spread.review
            if not i.resolved and i.severity is not Severity.INFO}
