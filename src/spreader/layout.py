"""Rows of positioned tokens -> header text per column and label + values per row.

The same code serves HTML (x = grid column), Excel (x = sheet column) and PDF (x = points):

1. Value columns ("slots") are found by grouping the horizontal extents of every number in the
   table. Numbers in one column overlap; numbers in different columns do not.
2. Header rows are the rows above the first data row that put text over a value column (dates,
   "Years ended", "2025"). Their text is stacked per slot, so a spanning "Year Ended December 31,"
   over a "2025" | "2024" row becomes "Year Ended December 31, 2025" and "... 2024".
3. Each data row's label is its text left of the first value; each value goes to the slot it
   overlaps most.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .contracts import RawRow, RawTable, Token
from .numbers import clean_text, parse_amount

_YEAR = re.compile(r"^(?:fy\s*)?(19[5-9]\d|20\d\d)$", re.I)
_DATEWORD = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b|\b(19[5-9]\d|20\d\d)\b|"
    r"\b(year|years|months|weeks|quarter|ended|ending|as of|fiscal|period)\b",
    re.I,
)


@dataclass
class Slot:
    x0: float
    x1: float
    header: str = ""

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class LaidOutRow:
    row: RawRow
    label: str
    label_token: Token | None
    values: dict[int, Token] = field(default_factory=dict)  # slot index -> token
    stray: list[Token] = field(default_factory=list)  # tokens that fit no slot


@dataclass
class Layout:
    slots: list[Slot]
    header_rows: list[RawRow]
    rows: list[LaidOutRow]
    title_text: str  # non-header text above the data (statement title lines inside the table)
    warnings: list[str]
    header_label_text: str = ""  # header-row text left of the value columns ("fiscal years ended June 30")


_EUROPEAN_LIKE = re.compile(r"^\(?[$\u20ac\u00a3]?\s*-?\d{1,3}(\.\d{3})+(,\d+)?\)?$|^\(?-?\d+,\d{1,2}\)?$")


def _is_value(tok: Token) -> bool:
    amount, _ = parse_amount(tok.text)
    return amount is not None or bool(_EUROPEAN_LIKE.match(tok.text.strip()))


def _is_year(tok: Token) -> bool:
    return bool(_YEAR.match(clean_text(tok.text)))


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def find_slots(rows: list[RawRow], tolerance: float) -> list[Slot]:
    """Group the extents of value tokens into columns.

    tolerance widens each extent before testing overlap: 0 for grids (HTML/Excel), a few points
    for PDF where right-aligned numbers of different widths share only their right edge.
    """
    spans = sorted(
        (t.x0, t.x1) for r in rows for t in r.tokens if _is_value(t) and not _is_year(t)
    )
    if not spans:
        return []
    groups: list[list[float]] = []
    for x0, x1 in spans:
        if groups and x0 - tolerance < groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], x1)
            groups[-1][0] = min(groups[-1][0], x0)
        else:
            groups.append([x0, x1])
    return [Slot(g[0], g[1]) for g in groups]


def _best_slot(tok: Token, slots: list[Slot], tolerance: float) -> int | None:
    best, best_ov = None, 0.0
    for i, s in enumerate(slots):
        ov = _overlap(tok.x0 - tolerance, tok.x1 + tolerance, s.x0, s.x1)
        if ov > best_ov:
            best, best_ov = i, ov
    return best


def lay_out(table: RawTable, tolerance: float = 0.0) -> Layout:
    warnings: list[str] = []
    slots = find_slots(table.rows, tolerance)
    if not slots:
        return Layout([], [], [], "", ["no value columns found"])
    first_slot_x = min(s.x0 for s in slots)

    def label_tokens(r: RawRow) -> list[Token]:
        return [t for t in r.tokens if t.x1 <= first_slot_x + tolerance or (not _is_value(t) and t.x0 < first_slot_x)]

    def is_data_row(r: RawRow) -> bool:
        vals = [t for t in r.tokens if _is_value(t) and not _is_year(t)]
        return bool(vals) and bool(label_tokens(r) or len(vals) >= 1) and not all(_is_year(t) for t in vals)

    last_slot_x = max(s.x1 for s in slots)

    def is_header_row(r: RawRow) -> bool:
        """Text over the value columns (dates, 'Years ended', '2025'), and no amounts."""
        if any(_is_value(t) and not _is_year(t) for t in r.tokens):
            return False
        over = [t for t in r.tokens if _overlap(t.x0 - tolerance, t.x1 + tolerance, first_slot_x, last_slot_x) > 0]
        return bool(over)

    first_data = next((i for i, r in enumerate(table.rows) if is_data_row(r)), len(table.rows))
    header_rows: list[RawRow] = []
    title_parts: list[str] = []
    body_start = first_data
    last_header = -1
    for i, r in enumerate(table.rows[:first_data]):
        if is_header_row(r):
            header_rows.append(r)
            last_header = i
    for i, r in enumerate(table.rows[:first_data]):
        if r in header_rows:
            continue
        if i > last_header and r.tokens and all(t.x0 < first_slot_x for t in r.tokens):
            # A label-only row between the column headers and the first number ("Net sales:")
            # is the first section header of the body, not part of the title.
            body_start = min(body_start, i)
        else:
            title_parts.append(" ".join(t.text for t in r.tokens))

    # Stack header text per slot, top to bottom.
    for s in slots:
        parts: list[str] = []
        for r in header_rows:
            for t in r.tokens:
                if _overlap(t.x0 - tolerance, t.x1 + tolerance, s.x0, s.x1) > 0 or (
                    t.x0 <= s.x0 and t.x1 >= s.x1
                ):
                    parts.append(t.text)
        s.header = clean_text(" ".join(parts))

    laid: list[LaidOutRow] = []
    for r in table.rows[body_start:]:
        if r in header_rows:
            continue
        labels = [t for t in r.tokens if not _is_value(t) and t.x0 < first_slot_x - 0.01]
        label = clean_text(" ".join(t.text for t in labels))
        lo = LaidOutRow(row=r, label=label, label_token=labels[0] if labels else None)
        for t in r.tokens:
            if t in labels:
                continue
            if not _is_value(t):
                # Text in a value column: "n/a", a footnote, a header repeated mid-table.
                si = _best_slot(t, slots, tolerance)
                if si is not None and t.text.strip():
                    lo.stray.append(t)
                continue
            si = _best_slot(t, slots, tolerance)
            if si is None:
                lo.stray.append(t)
                continue
            if si in lo.values:
                warnings.append(f"row {r.index}: two values in one column ('{lo.values[si].text}', '{t.text}')")
                lo.stray.append(t)
                continue
            lo.values[si] = t
        laid.append(lo)
    header_label = clean_text(" ".join(t.text for r in header_rows for t in r.tokens if t.x1 <= first_slot_x + tolerance))
    return Layout(slots, header_rows, laid, clean_text(" ".join(title_parts)), warnings, header_label)
