"""Remember each company across years: its confirmed mappings and its approved spreads.

Most filers come back every year, and last year's approved spread is the strongest evidence there is about this
year's comparative column. Two uses:

- **Mappings.** The label-to-line mapping of every placed row in an approved spread is remembered for that company
  (rule `memory.company` in the mapping cascade, tried before the global reviewer memory and the rules). It is a
  calibrated method like any other (finops.core.policy): until its accuracy is measured, its rows are reviewed.
- **Approved values.** When a new document prints a period the company already has approved values for, every line
  that differs beyond rounding raises a review item that says what it most likely is, with the evidence. The approved
  spread is never changed: approvals are append-only (spreader.store), and a difference is a question for a person.

What the comparison can tell from the document alone (it never sees the notes):
- a factor of ten, a hundred, a thousand, or a flipped sign: almost always a misread unit or sign;
- the value equals another line's or another period's approved value: a misread row or column;
- lines that move by equal and opposite amounts in one period, or a statement whose columns are headed "as restated",
  "recast" or "as adjusted": a reclassification or restatement by the company;
- anything else: restatement or misread, and the item says to check the document.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal

from .contracts import ReviewItem, ReviewKind, Severity, Spread, SpreadValue, StatementType
from .profile import Profile

RESTATED = re.compile(r"\b(as\s+restated|restated|recast|as\s+adjusted|retrospectively\s+adjusted|revised)\b", re.I)


@dataclass(frozen=True)
class ApprovedValue:
    period: str  # period key, e.g. "2024-09-28/12M"
    line: str
    value: Decimal
    tolerance: Decimal  # the rounding the approved value carries (half a unit of its scale per printed number)
    run_id: int | None = None
    document: str = ""
    approved_by: str = ""
    approved_at: str = ""


@dataclass
class CompanyContext:
    company_id: str
    mappings: dict[tuple[str, str, str], str] = field(default_factory=dict)  # (statement, label, section) -> line
    approved: dict[tuple[str, str], ApprovedValue] = field(default_factory=dict)  # (period, line) -> latest approval

    @property
    def version(self) -> str:
        """Changes whenever what is remembered changes, so a run on new memory is a new run (idempotency, D19)."""
        import hashlib

        parts = sorted(f"{k}={v}" for k, v in self.mappings.items())
        parts += sorted(f"{p}|{ln}={a.value}|{a.run_id}" for (p, ln), a in self.approved.items())
        return hashlib.sha256("\n".join([self.company_id, *parts]).encode()).hexdigest()[:16]


def detect_company_id(data: bytes) -> str | None:
    """An SEC filing's CIK from its cover-page tag (dei:EntityCentralIndexKey). Identification, not a value: the
    numbers are still read only from what a person can see (D1). None when the tag is absent."""
    m = re.search(rb"name=\"dei:EntityCentralIndexKey\"[^>]*>\s*(?:<[^>]+>\s*)*0*(\d{1,10})\s*<", data[:3_000_000])
    return f"cik:{int(m.group(1))}" if m else None


def value_tolerance(v: SpreadValue, multiplier: Decimal) -> Decimal:
    """Half a unit of the printed scale for each printed number the value is built from (D4)."""
    return multiplier / 2 * max(1, len(v.refs))


def approved_from_spread(spread: Spread, run_id: int | None = None, document: str = "", by: str = "", at: str = "",
                         ) -> list[ApprovedValue]:
    scale = {StatementType(k): r.table.scale.multiplier for k, r in spread.statements.items()}
    out = []
    for v in spread.values:
        if v.value is None:
            continue
        mult = next((m for st, m in scale.items() if any(p.key == v.period for p in spread.statements[st.value].table.periods)),
                    Decimal(1))
        out.append(ApprovedValue(v.period, v.line, v.value, value_tolerance(v, Decimal(mult)), run_id, document, by, at))
    return out


def confirmed_mappings(spread: Spread, corrected_lines: set[str] | None = None) -> dict[tuple[str, str, str], str]:
    """Every placed row of an approved spread: (statement, label, section) -> line.

    Rows feeding a line whose value was corrected before approval are left out: a corrected total says the rows behind
    it were placed wrong, so approving the corrected value does not confirm them (found on the evaluation: three values
    went silent because a corrected line's rows were remembered and reused the next year)."""
    out = {}
    for skey, res in spread.statements.items():
        rows = {r.index: r for r in res.table.rows}
        for m in res.mappings:
            row = rows.get(m.row_index)
            if row is None or not m.canonical or m.excluded or m.canonical in (corrected_lines or set()):
                continue
            section = row.section.split(" > ")[-1] if row.section else ""
            out[(skey, row.label_clean, section)] = m.canonical
    return out


def _power_of_ten(new: Decimal, old: Decimal) -> int | None:
    if not new or not old:
        return None
    r = abs(float(new) / float(old))
    k = round(math.log10(r))
    return k if k != 0 and abs(r / 10 ** k - 1) < 0.01 else None


def compare_with_approved(spread: Spread, ctx: CompanyContext, profile: Profile, document_text: str = "") -> list[ReviewItem]:
    """One review item per line and period that differs from the company's approved value beyond rounding."""
    scale = {k: r.table.scale.multiplier for k, r in spread.statements.items()}
    stmt_of_period: dict[str, str] = {}
    for k, r in spread.statements.items():
        for p in r.table.periods:
            stmt_of_period.setdefault(p.key, k)
    restated_text = bool(RESTATED.search(document_text))
    diffs: dict[str, list[tuple[SpreadValue, ApprovedValue, Decimal]]] = {}
    for v in spread.values:
        a = ctx.approved.get((v.period, v.line))
        if a is None or v.value is None:
            continue
        mult = scale.get(stmt_of_period.get(v.period, ""), Decimal(1))
        tol = value_tolerance(v, Decimal(mult)) + a.tolerance
        if abs(v.value - a.value) > tol:
            diffs.setdefault(v.period, []).append((v, a, tol))
    other_values = {(a.period, a.line): a.value for a in ctx.approved.values()}
    items = []
    for period, found in diffs.items():
        for v, a, tol in found:
            delta = v.value - a.value  # type: ignore[operator]
            reasons, verdict = [], "restatement or misread"
            power = _power_of_ten(v.value, a.value)  # type: ignore[arg-type]
            if power is not None:
                verdict, reasons = "likely a misread", [f"the new value is 10^{power} times the approved one (a unit read wrong)"]
            elif v.value == -a.value:
                verdict, reasons = "likely a misread", ["the sign is flipped"]
            else:
                same_line_other_period = [p for (p, ln), val in other_values.items() if ln == v.line and p != period
                                          and abs(val - v.value) <= tol]  # type: ignore[operator]
                other_line = [ln for (p, ln), val in other_values.items() if p == period and ln != v.line
                              and abs(val - v.value) <= tol and val != 0]  # type: ignore[operator]
                offset = [w.line for w, b, t in found if w.line != v.line and abs((w.value - b.value) + delta) <= tol + t]  # type: ignore[operator]
                if same_line_other_period:
                    verdict, reasons = "likely a misread", [f"it equals the approved value for {same_line_other_period[0]} "
                                                            "(a column read for the wrong period)"]
                elif other_line:
                    names = ", ".join(profile.lines[ln].label for ln in other_line[:2] if ln in profile.lines)
                    verdict, reasons = "likely a misread", [f"it equals the approved value of {names} (a row placed on the wrong line)"]
                elif offset:
                    names = ", ".join(profile.lines[ln].label for ln in offset[:2] if ln in profile.lines)
                    verdict, reasons = "likely a reclassification by the company", [
                        f"{names} moved by the same amount the other way, so the total is unchanged"]
                elif restated_text:
                    verdict, reasons = "likely a restatement by the company", [
                        "the statement says its figures were restated, recast or adjusted"]
            label = profile.lines[v.line].label if v.line in profile.lines else v.line
            when = f"{a.approved_by}, {a.approved_at[:10]}" if a.approved_by else "an earlier approval"
            msg = (f"{label} for {period} is {v.value:,} here, but the company's approved spread says {a.value:,} ({when}). "
                   f"{verdict[0].upper() + verdict[1:]}" + (f": {'; '.join(reasons)}." if reasons else
                                                            ": check the document for a restatement note.")
                   + " The approved spread is not changed.")
            items.append(ReviewItem(id=f"prior:{v.line}:{period}", kind=ReviewKind.PRIOR_PERIOD, severity=Severity.WARNING,
                                    statement=StatementType(stmt_of_period[period]) if period in stmt_of_period else None,
                                    message=msg, lines=[v.line], periods=[period]))
    return items


def verdict_of(item: ReviewItem) -> str:
    """The comparison's classification, from an item's message (for evaluation)."""
    m = item.message
    if "likely a misread" in m.lower():
        return "misread"
    if "reclassification" in m or "restatement by the company" in m:
        return "restatement"
    return "unclear"
