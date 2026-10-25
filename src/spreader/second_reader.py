"""Opt-in second reader: the inline XBRL fact tagged on each cell the spread read (DECISIONS D37).

Off by default; the printed-number reader stays the reader (D1). When on (`SPREADER_XBRL_CHECK=1`, or
`spread_document(..., tags=tagged_cells(data))`), every printed number the spread uses is compared with the fact an SEC
filer tagged on the same table cell:

- *scale*: the two are a power of ten apart (a unit read wrong by one of them);
- *value*: any other difference beyond rounding;
- *period*: the same number, tagged for another period than the column was read as.

The tag's sign is not compared: it follows the concept's convention (an expense is tagged positive), not what is
printed. A disagreement is a warning on the value's line and period, so that value goes to a person. Agreement adds
nothing to automation: using it as a basis for accepting values alone would need calibration against outcomes, and the
only outcomes available (the SEC answer keys) are built from these same tags. For the same reason this mode is never
measured against those keys; see scripts/eval_xbrl_check.py for what is measured instead.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .contracts import ReviewItem, ReviewKind, Severity, Spread, StatementType, ValueUnit


@dataclass(frozen=True)
class TagFact:
    concept: str
    magnitude: Decimal  # |value| after the tag's scale
    period: str  # period key in the spread's format ("2025-09-27/12M", "2025-09-27/I")
    decimals: int | None
    dimensional: bool


def tagged_cells(data: bytes) -> dict[str, list[TagFact]]:
    """Every numeric fact in an inline XBRL document, by the path of the table cell it is printed in. Uses the same
    parser as the answer-key builder: the reason this mode cannot be graded against those keys."""
    from .evaluation.ixbrl_truth import period_key, read_facts

    try:
        facts, _ = read_facts(data)
    except Exception:  # noqa: BLE001 - not inline XBRL (a PDF, Excel, or plain HTML): nothing to compare
        return {}
    out: dict[str, list[TagFact]] = {}
    for f in facts:
        if f.td_xpath:
            out.setdefault(f.td_xpath, []).append(TagFact(f.concept, abs(f.value), period_key(f.context), f.decimals,
                                                          f.context.dimensional))
    return out


@dataclass
class Comparison:
    items: list[ReviewItem]
    cells: int  # printed numbers that had a tag on their cell
    agree: int
    kinds: Counter[str]
    details: list[dict[str, str]]


def _power_of_ten(a: Decimal, b: Decimal) -> bool:
    if not a or not b:
        return False
    r = a / b if a > b else b / a
    return any(abs(r - Decimal(10) ** k) <= Decimal("0.01") * Decimal(10) ** k for k in range(1, 10))


def _same_period(tag: str, column: str) -> bool:
    """The tag's period matches the column. A cash-flow statement prints its opening and closing cash in a full-year
    column, and those are tagged as balances at one date: the column's end, or its start (the end of the year before,
    within ten days for 52/53-week years)."""
    if tag == column:
        return True
    t_end, _, t_kind = tag.partition("/")
    c_end, _, c_kind = column.partition("/")
    if t_kind != "I" or not c_kind.endswith("M"):
        return False
    try:
        t, c = date.fromisoformat(t_end), date.fromisoformat(c_end)
    except ValueError:
        return False
    start = c - timedelta(days=round(int(c_kind[:-1]) * 30.44))
    return t == c or abs((t - start).days) <= 10


def _close(f: TagFact, read: Decimal, unit: Decimal) -> bool:
    """Equal within the rounding of both: half a printed unit, and half the tag's stated precision."""
    rounding = unit / 2 + (Decimal(10) ** -f.decimals / 2 if f.decimals is not None else 0)
    return abs(f.magnitude - read) <= rounding


def compare(spread: Spread, tags: dict[str, list[TagFact]]) -> Comparison:
    items: list[ReviewItem] = []
    kinds: Counter[str] = Counter()
    details: list[dict[str, str]] = []
    cells = agree = 0
    for skey, res in spread.statements.items():
        mapping_of = {m.row_index: m for m in res.mappings}
        mult = Decimal(res.table.scale.multiplier)
        share_mult = Decimal(res.table.share_scale.multiplier) if res.table.share_scale else mult
        for row in res.table.rows:
            m = mapping_of.get(row.index)
            if m is None or not m.canonical or m.excluded:
                continue
            unit = Decimal(1) if row.unit in (ValueUnit.PER_SHARE, ValueUnit.PERCENT) else (
                share_mult if row.unit is ValueUnit.SHARES else mult)
            for period, pv in row.values.items():
                if pv.displayed is None or pv.ref is None or not pv.ref.xpath or pv.ref.xpath not in tags:
                    continue
                facts = tags[pv.ref.xpath]
                plain = [f for f in facts if not f.dimensional] or facts
                read = abs(pv.displayed * unit)
                cells += 1
                if any(_close(f, read, unit) and _same_period(f.period, period) for f in plain):
                    agree += 1
                    continue
                if any(_close(f, read, unit) for f in plain):
                    kind, what = "period", f"the tag gives it to {next(f.period for f in plain if _close(f, read, unit))}"
                elif any(_power_of_ten(f.magnitude, read) for f in plain):
                    kind, what = "scale", f"the tag says {plain[0].magnitude:,}, a power of ten away"
                else:
                    kind, what = "value", f"the tag says {plain[0].magnitude:,}"
                kinds[kind] += 1
                details.append({"statement": skey, "row": str(row.index), "label": row.label, "period": period,
                                "read": str(read), "tagged": str(plain[0].magnitude), "tag_period": plain[0].period,
                                "concept": plain[0].concept, "kind": kind, "xpath": pv.ref.xpath, "line": m.canonical})
                items.append(ReviewItem(
                    id=f"xbrl:{skey}:{row.index}:{period}", kind=ReviewKind.SECOND_READER, severity=Severity.WARNING,
                    statement=StatementType(skey), rows=[row.index], lines=[m.canonical], periods=[period],
                    message=(f"'{row.label}' for {period} was read as {read:,}, but {what} ({plain[0].concept}). "
                             "The two readers disagree: check the printed filing.")))
    return Comparison(items, cells, agree, kinds, details)
