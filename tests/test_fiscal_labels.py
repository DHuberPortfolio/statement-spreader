"""Year-only columns in fiscal years labelled by the year they start in (2026-10-25).

Retailers end their year in late January or early February and call it by the year it began: Home Depot's "Fiscal
2025" ended February 1, 2026. Matching "Fiscal 2025" to the printed date in calendar 2025 (February 2, 2025) dated
every column a year early, and since that date looked printed the doubt flag was dropped (found by the XBRL second
reader on the holdout; reproduced here on synthetic tables). 52/53-week years ending in the first days of January
(Snap-on) have the same shape. Others label the year by its end (Walmart's "Fiscal 2026" ended January 31, 2026);
the newest column always belongs to the newest year-end the filing prints, which tells the two apart.
"""

from __future__ import annotations

from spreader.contracts import Period, Scale, StatementTable, StatementType
from spreader.detect import parse_period
from spreader.structure import harmonize_periods


def _table(stype: StatementType, headers: list[str]) -> StatementTable:
    periods = [parse_period(h, stype) for h in headers]
    return StatementTable(doc_id="d", table_index=0, statement=stype, title="t", periods=[p for p in periods if p],
                          scale=Scale(multiplier=1000, evidence="test"), rows=[])


def _bs(*dates: str) -> StatementTable:
    return _table(StatementType.BALANCE, list(dates))


def _date_doubted(p: Period) -> bool:
    """Whether the column's end date is a guess (a "2025" heading is also doubted for its length; not counted here)."""
    return any("full year" not in a for a in p.assumed)


def _ends(t: StatementTable) -> list[tuple[str, bool]]:
    return [(p.end, _date_doubted(p)) for p in t.periods]


def test_a_year_labelled_by_its_start_takes_the_next_year_s_date() -> None:
    bs = _bs("February 1, 2026", "February 2, 2025")
    inc = _table(StatementType.INCOME, ["Fiscal 2025", "Fiscal 2024", "Fiscal 2023"])
    harmonize_periods([bs, inc], "For the fiscal year ended February 1, 2026")
    assert _ends(inc) == [("2026-02-01", False), ("2025-02-02", False), ("2024-02-01", True)]


def test_the_same_without_a_cover_page() -> None:
    bs = _bs("January 31, 2026", "February 1, 2025")
    inc = _table(StatementType.INCOME, ["2025", "2024", "2023"])
    harmonize_periods([bs, inc])
    assert _ends(inc) == [("2026-01-31", False), ("2025-02-01", False), ("2024-01-31", True)]


def test_a_year_labelled_by_its_end_keeps_its_own_year() -> None:
    bs = _bs("January 31, 2026", "January 31, 2025")
    inc = _table(StatementType.INCOME, ["Fiscal 2026", "Fiscal 2025", "Fiscal 2024"])
    harmonize_periods([bs, inc], "For the fiscal year ended January 31, 2026")
    assert _ends(inc)[:2] == [("2026-01-31", False), ("2025-01-31", False)]


def test_a_52_53_week_year_ending_in_early_january() -> None:
    bs = _bs("January 3, 2026", "December 28, 2024")
    inc = _table(StatementType.INCOME, ["2025", "2024", "2023"])
    harmonize_periods([bs, inc], "For the fiscal year ended January 3, 2026")
    assert _ends(inc)[:2] == [("2026-01-03", False), ("2024-12-28", False)]
    assert inc.periods[2].assumed  # 2023 has no printed date anywhere: still a visible assumption


def test_a_calendar_year_is_unchanged() -> None:
    bs = _bs("December 31, 2025", "December 31, 2024")
    inc = _table(StatementType.INCOME, ["2025", "2024", "2023"])
    harmonize_periods([bs, inc], "For the fiscal year ended December 31, 2025")
    assert _ends(inc)[:2] == [("2025-12-31", False), ("2024-12-31", False)]
    assert inc.periods[2].end == "2023-12-31"


def test_a_date_that_does_not_fit_the_columns_changes_nothing() -> None:
    """A newest year-end two years after the newest column is not a labelling convention: the guess stays flagged and
    stays in the column's own year."""
    bs = _bs("March 31, 2027", "March 31, 2026")
    inc = _table(StatementType.INCOME, ["2025", "2024"])
    harmonize_periods([bs, inc])
    assert [p.end[:4] for p in inc.periods] == ["2025", "2024"] and all(_date_doubted(p) for p in inc.periods)


def test_cash_and_equity_statements_follow_too() -> None:
    bs = _bs("February 1, 2026", "February 2, 2025")
    cf = _table(StatementType.CASH_FLOW, ["Fiscal 2025", "Fiscal 2024", "Fiscal 2023"])
    harmonize_periods([bs, cf])
    assert [p.key for p in cf.periods][:2] == ["2026-02-01/12M", "2025-02-02/12M"]


def test_periods_built_by_hand_are_accepted() -> None:
    """The helper's parse matches what the reader produces for these headings."""
    p = parse_period("Fiscal 2025", StatementType.INCOME)
    assert isinstance(p, Period) and p.end == "2025-12-31" and any("Only the year" in a for a in p.assumed)


def test_a_balance_sheet_headed_only_by_years_is_aligned_too() -> None:
    """Snap-on heads its balance sheet "Fiscal Year End 2025": once the income statement was aligned, the balance
    sheet was left behind a year (dev, Snap-on)."""
    bs = _table(StatementType.BALANCE, ["Fiscal Year End 2025", "Fiscal Year End 2024"])
    inc = _table(StatementType.INCOME, ["2025", "2024", "2023"])
    harmonize_periods([bs, inc], "For the fiscal year ended January 3, 2026")
    assert bs.periods[0].key == "2026-01-03/I" and not _date_doubted(bs.periods[0])
    assert inc.periods[0].key == "2026-01-03/12M" and not _date_doubted(inc.periods[0])
    assert _date_doubted(bs.periods[1]) and _date_doubted(inc.periods[1])  # no printed date for 2024
