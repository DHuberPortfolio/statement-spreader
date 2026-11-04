"""The same number printed twice: a second, independent reading of a spread value (D60).

Annual reports repeat their numbers. Retained earnings and treasury stock appear again in the statement of changes in
equity, earnings per share and share counts in the earnings-per-share note, capital spending and depreciation in the
segment note. When a value's printed number appears in another table of the document under a similar label, two
separate readings agree on it, and that counts as one confirmation (review.unconfirmed_items).

Deliberately narrow, as measured on the dev sets: the number must have at least three significant digits (1.29 turns up
by chance), the labels must read alike (token-sort similarity of at least 80), and the value must come from exactly one
printed row. A catch-all line ("Other non-operating income") is never confirmed this way: the printed row can be read
right while the line holds a different set of rows than it should (8 wrong values passed on the dev sets otherwise).
Numbers are compared as printed, so a note in another unit confirms nothing.
"""

from __future__ import annotations

from decimal import Decimal

from rapidfuzz import fuzz

from .contracts import DocumentIR, Echo, SourceRef, SpreadValue, StatementResult
from .numbers import clean_label, parse_amount
from .profile import Profile

MIN_LABEL_SIMILARITY = 80


def is_catch_all(line: str) -> bool:
    """A line that collects what no other line took: "other_opex", and the cash flow's "cf_other_financing" (D62)."""
    return line.startswith("other_") or "_other_" in line


def significant(d: Decimal) -> bool:
    return len(str(abs(d)).replace(".", "").lstrip("0")) >= 3


def _printed(doc: DocumentIR) -> dict[Decimal, list[tuple[int, str, SourceRef]]]:
    """Every significant number printed in any table: absolute value -> (table, row label, where)."""
    out: dict[Decimal, list[tuple[int, str, SourceRef]]] = {}
    for t in doc.tables:
        for row in t.rows:
            label, nums = [], []
            for tok in row.tokens:
                amt, _ = parse_amount(tok.text)
                if amt is None:
                    label.append(tok.text)
                elif not amt.dash and not amt.percent and amt.displayed and significant(amt.displayed):
                    nums.append((abs(amt.displayed), tok.ref))
            lab = clean_label(" ".join(label))
            if lab:
                for n, ref in nums:
                    out.setdefault(n, []).append((t.index, lab, ref))
    return out


def find_echoes(doc: DocumentIR, statements: dict[str, StatementResult], values: list[SpreadValue],
                profile: Profile) -> list[Echo]:
    printed = _printed(doc)
    out = []
    for v in values:
        if v.value is None or is_catch_all(v.line) or len(v.source_rows) != 1:
            continue
        res = statements.get(profile.line_statement[v.line].value)
        if res is None:
            continue
        row = next((r for r in res.table.rows if r.index == v.source_rows[0]), None)
        pv = row.values.get(v.period) if row else None
        if row is None or pv is None or not pv.displayed or not significant(pv.displayed):
            continue
        for table, label, ref in printed.get(abs(pv.displayed), []):
            if table != res.table.table_index and fuzz.token_sort_ratio(label, row.label_clean) >= MIN_LABEL_SIMILARITY:
                out.append(Echo(line=v.line, period=v.period, value=v.value, label=label, ref=ref))
                break
    return out
