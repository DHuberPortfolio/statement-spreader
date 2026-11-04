"""Choosing and completing a document's statements with accounting evidence (D66).

Two things a table's own wording cannot settle, both found on the wide set of real filings:

- A statement printed across two tables (assets on one page, liabilities on the next; an income statement "continued").
  The half that was not read used to come out blank with nothing saying so.
- Which of several look-alike tables is the consolidated statement. Statements of one company tie to each other: the cash
  flow's ending cash is on the balance sheet, and its net income is on the income statement. A parent-only cash flow or a
  table of quarterly results does not tie, however much it reads like a statement.

- Which company a combined filing is about (D67). A utility holding company files one 10-K for itself and its subsidiaries, each
  with full statements. A subsidiary's add up perfectly, so nothing else catches reading the wrong company. The SEC's order
  puts the parent first, so the first full balance sheet anchors the choice, and the ties above find its other statements.

Only tables that were already candidates can be chosen here, and a tie only ever moves the choice to a table that ties, so
this cannot make a wrong number look confirmed: the checks and review run afterwards as they always did.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .contracts import DocumentIR, RawTable, StatementRow, StatementTable, StatementType
from .numbers import parse_amount

_TOTAL_ASSETS = re.compile(r"\btotal assets\b", re.I)
_TOTAL_CLAIMS = re.compile(r"\btotal (liabilities|equity|(stockholders|shareholders|members|partners)\W* (equity|investment|capital|deficit))\b|"
                           r"liabilities and (stockholders|shareholders|members|partners|equity|capital|deficit)", re.I)
_BOTTOM_LINE = re.compile(r"\bnet (income|loss|earnings|profit)\b|\bnet \(?(income|loss)", re.I)
_CASH_END = re.compile(r"\b(end of|ending|at end)\b.*|cash.*\b(end|close)\b", re.I)
_CONTINUED = re.compile(r"\bcontinued\b|\(cont", re.I)
_CF_NET_INCOME = re.compile(r"^(consolidated )?net (income|loss|earnings|\(loss\)|profit)", re.I)
INDEX_GAP = 100_000  # keeps a second table's row numbers apart from the first's
REGISTRANT_MARGIN = 7  # a subsidiary's sheet scores below the parent's; a summary or an average balance table scores far below
COMPANION_MARGIN = 10  # a parent's cash flow can score below a subsidiary's; a summary in the discussion scores far below both
REGISTRANT_ROWS = 15  # shorter than a full balance sheet, or its half on one page


def _labels(table: RawTable) -> list[str]:
    return [" ".join(t.text for t in r.tokens if parse_amount(t.text)[0] is None).strip() for r in table.rows]


def _numbers(table: RawTable) -> set[Decimal]:
    out: set[Decimal] = set()
    for r in table.rows:
        for t in r.tokens:
            amt, _ = parse_amount(t.text)
            if amt is not None and not amt.dash and not amt.percent and amt.displayed and abs(amt.displayed) >= 100:
                out.add(abs(amt.displayed))
    return out


def _row_numbers(table: RawTable, rx: re.Pattern[str], first_only: bool = False) -> set[Decimal]:
    """The numbers on rows whose label matches; with first_only, on the first such row."""
    out: set[Decimal] = set()
    for r, lab in zip(table.rows, _labels(table), strict=True):
        if not rx.search(lab):
            continue
        for t in r.tokens:
            amt, _ = parse_amount(t.text)
            if amt is not None and not amt.dash and not amt.percent and amt.displayed and abs(amt.displayed) >= 100:
                out.add(abs(amt.displayed))
        if first_only and out:
            break
    return out


def _neighbours(doc: DocumentIR, table: RawTable) -> list[RawTable]:
    i = next((n for n, t in enumerate(doc.tables) if t is table), None)
    return [] if i is None else [doc.tables[j] for j in (i - 1, i + 1) if 0 <= j < len(doc.tables)]


def first_registrant(best: dict[StatementType, tuple], rivals: dict[StatementType, list[tuple]]) -> int:
    """In a combined filing, anchor on the first company's balance sheet. Returns how many companies' sheets it holds (0: one).

    Several candidates count as different companies only if each scores like a primary statement, is long enough to be one, and
    shows its own total assets. A table of average balances or a summary falls short of the first two."""
    bs = best.get(StatementType.BALANCE)
    if bs is None:
        return 0
    totals = {c[0].index: _row_numbers(c[0], _TOTAL_ASSETS, first_only=True) for c in rivals[StatementType.BALANCE]}
    cands = [c for c in rivals[StatementType.BALANCE] if totals[c[0].index] and len(c[0].rows) >= REGISTRANT_ROWS]
    if not cands:  # a sheet split over two tables can have its liabilities half score higher, so the scores compared are of the asset halves
        return 0
    top = max(c[2].score for c in cands)
    cands = [c for c in cands if c[2].score >= top - REGISTRANT_MARGIN]
    distinct: list[set[Decimal]] = []
    for c in cands:
        if not any(totals[c[0].index] & seen for seen in distinct):
            distinct.append(totals[c[0].index])
    if len(distinct) < 2:
        return 0
    best[StatementType.BALANCE] = min(cands, key=lambda c: c[0].index)
    return len(distinct)


def _nearest(cands: list[tuple], anchor: tuple) -> tuple:
    """A combined filing keeps each company's statements together: the closest candidate, the earlier one if two are as close."""
    return min(cands, key=lambda c: (abs(c[0].index - anchor[0].index), c[0].index))


def choose_by_ties(doc: DocumentIR, best: dict[StatementType, tuple], rivals: dict[StatementType, list[tuple]], combined: bool = False) -> None:
    """Move the cash flow and income statement to the candidates that tie to the other statements, when the current ones do not.
    combined: the filing holds several companies. Their statements look alike, so the choice stays beside the anchor."""
    if combined:
        anchor = best[StatementType.BALANCE]
        for stype in (StatementType.CASH_FLOW, StatementType.INCOME):
            if stype in best:
                top = max(c[2].score for c in rivals[stype])
                near = [c for c in rivals[stype] if c[2].score >= top - COMPANION_MARGIN and len(c[0].rows) >= REGISTRANT_ROWS]
                if near:
                    best[stype] = _nearest(near, anchor)
        return  # the ties below would look across companies, and a subsidiary's table can match on a shared figure
    bs = best.get(StatementType.BALANCE)
    if bs is not None and StatementType.CASH_FLOW in best:
        sheet = _numbers(bs[0]).union(*(_numbers(t) for t in _neighbours(doc, bs[0])))

        def cash_ties(cand: tuple) -> bool:
            return bool(_row_numbers(cand[0], _CASH_END) & sheet)

        if not cash_ties(best[StatementType.CASH_FLOW]):
            tied = [c for c in rivals[StatementType.CASH_FLOW] if cash_ties(c)]
            if tied:
                best[StatementType.CASH_FLOW] = max(tied, key=lambda c: c[2].score)
    cf = best.get(StatementType.CASH_FLOW)
    if cf is not None and StatementType.INCOME in best:
        net = _row_numbers(cf[0], _CF_NET_INCOME, first_only=True)

        def income_ties(cand: tuple) -> bool:
            return bool(net & _numbers(cand[0]).union(*(_numbers(t) for t in _neighbours(doc, cand[0]))))

        if net and not income_ties(best[StatementType.INCOME]):
            tied = [c for c in rivals[StatementType.INCOME] if income_ties(c)]
            if tied:
                best[StatementType.INCOME] = max(tied, key=lambda c: c[2].score)


def _other_half(stype: StatementType, table: RawTable, doc: DocumentIR) -> tuple[RawTable, bool] | None:
    """The table holding the rest of this statement, and whether it comes after this one."""
    labels = " | ".join(_labels(table))
    i = next((n for n, t in enumerate(doc.tables) if t is table), None)
    if i is None:
        return None
    before = doc.tables[i - 1] if i > 0 else None
    after = doc.tables[i + 1] if i + 1 < len(doc.tables) else None
    if stype is StatementType.BALANCE:
        has_assets, has_claims = bool(_TOTAL_ASSETS.search(labels)), bool(_TOTAL_CLAIMS.search(labels))
        if has_assets and not has_claims and after is not None and _TOTAL_CLAIMS.search(" | ".join(_labels(after))):
            return after, True
        if has_claims and not has_assets and before is not None and _TOTAL_ASSETS.search(" | ".join(_labels(before))):
            return before, False
        return None
    if after is None:
        return None
    head = " ".join(_labels(after)[:3]) + " " + after.context[-160:]
    if _CONTINUED.search(head):
        return after, True
    if stype is StatementType.INCOME and not _BOTTOM_LINE.search(labels) and _BOTTOM_LINE.search(" | ".join(_labels(after))):
        return after, True
    if stype is StatementType.CASH_FLOW and not _CASH_END.search(labels) and _CASH_END.search(" | ".join(_labels(after))):
        return after, True
    return None


def _shifted(row: StatementRow, by: int) -> StatementRow:
    return row.model_copy(update={"index": row.index + by, "children": [c + by for c in row.children]})


def _align(rest: StatementTable, st: StatementTable) -> dict[str, str] | None:
    """Period keys of the other half -> this one's: the same keys, or the same number of columns when its own are assumed."""
    if {p.key for p in rest.periods} == {p.key for p in st.periods}:
        return {p.key: p.key for p in st.periods}
    if len(rest.periods) == len(st.periods) and all(p.assumed for p in rest.periods):
        return {a.key: b.key for a, b in zip(rest.periods, st.periods, strict=True)}
    return None


def join_halves(doc: DocumentIR, picked: dict[StatementType, tuple], built: dict[StatementType, StatementTable],
                lay: Any, build: Any) -> None:
    """Complete each statement printed across two tables. `lay` lays out a table; `build` builds one as a given statement."""
    for stype, (table, _layout, det) in picked.items():
        other = _other_half(stype, table, doc)
        if other is None:
            continue
        neighbour, comes_after = other
        layout = lay(neighbour)
        rest = build(neighbour, layout, stype, doc.doc_id, det.score)
        st = built[stype]
        keys = _align(rest, st)
        if keys is None or not rest.rows:
            st.warnings.append(f"SPLIT_STATEMENT: the {stype.value.replace('_', ' ')} seems to continue in table "
                               f"{neighbour.index + 1}, whose columns do not line up with this one; those rows were not read.")
            continue
        first, second = (st.rows, rest.rows) if comes_after else (rest.rows, st.rows)
        moved = [_shifted(r, INDEX_GAP) for r in second]
        if keys and any(a != b for a, b in keys.items()) and second is rest.rows:
            moved = [m.model_copy(update={"values": {keys.get(k, k): v for k, v in m.values.items()}}) for m in moved]
        st.rows = [*first, *moved]
        st.joined_tables.append(neighbour.index)
        st.warnings.extend(w for w in rest.warnings if w not in st.warnings)
