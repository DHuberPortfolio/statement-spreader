"""A statement printed without column headings next to a dated balance sheet (found on a prior-year 10-K)."""

from __future__ import annotations

from spreader.contracts import Period, Scale, StatementTable, StatementType
from spreader.structure import harmonize_periods


def _table(stype: StatementType, periods: list[Period]) -> StatementTable:
    return StatementTable(doc_id="d", table_index=0, statement=stype, title="t", periods=periods,
                          scale=Scale(multiplier=1000, evidence="test"), rows=[])


def test_undated_columns_are_left_assumed_not_crashed_on() -> None:
    """Columns with no heading get placeholder periods ("col1"); re-dating flow statements to the balance sheet's
    year-end read a year from every period end and crashed (ValueError) on them, so the whole filing failed."""
    bs = _table(StatementType.BALANCE, [Period(key="2024-12-31/I", end="2024-12-31", months=None, label="December 31, 2024")])
    undated = [Period(key=f"col{i}", end=f"col{i}", months=12, label=f"Column {i}", assumed=["The column has no period header."])
               for i in (1, 2)]
    cf = _table(StatementType.CASH_FLOW, undated)
    harmonize_periods([bs, cf])
    assert [p.key for p in cf.periods] == ["col1", "col2"] and all(p.assumed for p in cf.periods)
