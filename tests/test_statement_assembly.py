"""Statements found on real filings of every size and industry (the wide set, D66): each test failed on the code before it."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from conftest import statement_html

from spreader.contracts import StatementType
from spreader.ingest import read_document
from spreader.pipeline import spread_document

Y = ["December 31, 2025", "December 31, 2024"]


def _spread(html: str, profile: Any) -> Any:
    return spread_document(read_document("f.htm", html.encode()), profile)[0]


def _body(html: str) -> str:
    return html.split("<body>")[1].split("</body>")[0]


def _two(a: str, b: str) -> str:
    return f"<html><body>{_body(a)}{_body(b)}</body></html>"


ASSETS = [("Cash and cash equivalents", "100", "80"), ("Accounts receivable", "50", "40"), ("Total current assets", "150", "120"),
          ("Property and equipment, net", "250", "200"), ("Total assets", "400", "320")]
CLAIMS = [("Accounts payable", "60", "50"), ("Total current liabilities", "60", "50"), ("Long-term debt", "140", "110"),
          ("Total liabilities", "200", "160"), ("Retained earnings", "200", "160"), ("Total stockholders' equity", "200", "160"),
          ("Total liabilities and stockholders' equity", "400", "320")]


def _lines(sp: Any, period: str = "2025-12-31/I") -> dict[str, Decimal]:
    return {v.line: v.value for v in sp.values if v.period == period and v.value is not None}


def test_a_balance_sheet_on_two_tables_is_read_whole(profile: Any) -> None:
    html = _two(statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, ASSETS),
                statement_html("CONSOLIDATED BALANCE SHEETS (continued)", "(In thousands)", Y, CLAIMS))
    sp = _spread(html, profile)
    got = _lines(sp)
    assert got["total_assets"] == 400_000 and got["payables"] == 60_000 and got["total_liabilities"] == 200_000
    bs = sp.statements["balance_sheet"].table
    assert bs.joined_tables, "the other half is recorded"


def test_a_number_in_the_other_half_is_not_its_own_second_reading(profile: Any) -> None:
    html = _two(statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, ASSETS),
                statement_html("CONSOLIDATED BALANCE SHEETS (continued)", "(In thousands)", Y, CLAIMS))
    sp = _spread(html, profile)
    tables = {sp.statements["balance_sheet"].table.table_index, *sp.statements["balance_sheet"].table.joined_tables}
    assert not [e for e in sp.echoes if e.ref.table in tables]


def _flow(end: str, net: str, parent: bool = False) -> list[tuple[str, str, str]]:
    first = ("Equity in undistributed income of Bank", "-5", "-4") if parent else ("Depreciation", "10", "8")
    return [("Cash flows from operating activities", None, None), ("Net income", net, "30"), first,  # type: ignore[list-item]
            ("Net cash provided by operating activities", "50", "38"), ("Net cash used in investing activities", "(20", "(18"),
            ("Net cash used in financing activities", "(10", "(8"), ("Net increase in cash", "20", "12"),
            ("Cash and cash equivalents, beginning of year", "80", "68"), ("Cash and cash equivalents, end of year", end, "80")]


def test_the_cash_flow_that_ties_to_the_balance_sheet_is_chosen(profile: Any) -> None:
    """A parent-only cash flow reads just like the real one, and may score higher; its ending cash is not on the balance sheet."""
    sheet = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, [*ASSETS, *CLAIMS])
    real = statement_html("CONSOLIDATED STATEMENTS OF CASH FLOWS", "(In thousands)", Y, _flow("100", "40"))
    parent = statement_html("STATEMENTS OF CASH FLOWS", "(In thousands)", Y,
                            [*_flow("7", "40", parent=True), ("Depreciation and amortization", "1", "1"), ("Stock-based compensation", "1", "1")])
    sp = _spread(f"<html><body>{_body(sheet)}{_body(parent)}{_body(real)}</body></html>", profile)
    end = next(v for v in sp.values if v.line == "cash_end" and v.period.startswith("2025"))
    assert end.value == 100_000


def _income(eps: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return [("Revenue", "500", "400"), ("Cost of revenue", "(300", "(240"), ("Gross profit", "200", "160"),
            ("Income before income taxes", "100", "80"), ("Income tax expense", "(20", "(16"), ("Net income", "80", "64"), *eps]


def test_one_row_for_basic_and_diluted_fills_both(profile: Any) -> None:
    rows = _income([("Net income per share, basic and diluted", "0.80", "0.64"),
                    ("Weighted average shares outstanding, basic and diluted", "100", "100")])
    got = _lines(_spread(statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In thousands, except per share data)", Y, rows), profile), "2025-12-31/12M")
    assert got["eps_basic"] == got["eps_diluted"] == Decimal("0.80")
    assert got["shares_basic"] == got["shares_diluted"] == 100_000


def test_per_share_rows_never_add_up(profile: Any) -> None:
    rows = _income([("Continuing operations", None, None), ("  Basic", "0.70", "0.60"), ("Net income per share", None, None), ("  Basic", "0.80", "0.64")])
    got = _lines(_spread(statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In thousands, except per share data)", Y, rows), profile), "2025-12-31/12M")
    assert got["eps_basic"] == Decimal("0.80")


def test_a_share_count_in_millions_is_not_a_per_share_figure(profile: Any) -> None:
    rows = _income([("Weighted average shares", None, None), ("  Basic", "123.4", "120.1")])
    html = statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In millions, except per share data)", Y, rows)
    lines = _lines(_spread(html, profile), "2025-12-31/12M")
    assert "eps_basic" not in lines


def test_what_sits_below_total_assets_is_not_an_asset(profile: Any) -> None:
    rows = [*ASSETS[:-1], ("Total assets", "400", "320"), ("Accounts payable", "60", "50"), ("Deferred income taxes", "40", "30"),
            ("Total liabilities", "100", "80"), ("Retained earnings", "300", "240"), ("Total liabilities and stockholders' equity", "400", "320")]
    got = _lines(_spread(statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, rows), profile))
    assert "deferred_tax_assets" not in got and got["deferred_tax_liabilities"] == 40_000


def test_a_subtotal_worded_like_one_of_its_rows_does_not_count_the_other_twice(profile: Any) -> None:
    rows = [("Cash", "10", "8"), ("Short-term investments", "90", "72"), ("Cash and cash equivalents", "100", "80"), ("Accounts receivable", "50", "40"),
            ("Total current assets", "150", "120"), ("Property and equipment, net", "250", "200"), ("Total assets", "400", "320"), *CLAIMS]
    got = _lines(_spread(statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, rows), profile))
    assert got["cash"] == 10_000 and got["st_investments"] == 90_000


def test_a_statement_of_income_and_comprehensive_income_is_an_income_statement(profile: Any) -> None:
    rows = _income([("Other comprehensive income:", None, None), ("  Foreign currency translation", "5", "4"), ("Net income", "80", "64"),
                    ("Total comprehensive income", "85", "68")])
    sp = _spread(statement_html("CONSOLIDATED STATEMENTS OF INCOME AND COMPREHENSIVE INCOME", "(In thousands)", Y, rows), profile)
    assert StatementType.INCOME.value in sp.statements
    assert _lines(sp, "2025-12-31/12M")["net_income"] == 80_000


def test_a_unit_printed_in_the_column_heading_is_read(profile: Any) -> None:
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "", Y, [("$’000", "$’000", "$’000"), *ASSETS, *CLAIMS])
    sp = _spread(html, profile)
    assert sp.statements["balance_sheet"].table.scale.multiplier == 1_000


def test_weeks_written_out_are_read_as_quarters_and_year_to_date(profile: Any) -> None:
    from spreader.detect import parse_period

    assert parse_period("Thirteen Weeks Ended May 30, 2026", StatementType.INCOME).key == "2026-05-30/3M"
    assert parse_period("Thirty-Nine Weeks Ended May 30, 2026", StatementType.INCOME).key == "2026-05-30/9M"
    assert parse_period("Twenty-Six Weeks Ended May 30, 2026", StatementType.CASH_FLOW).key == "2026-05-30/6M"
    assert parse_period("Fifty-Three Weeks Ended January 3, 2026", StatementType.INCOME).key == "2026-01-03/12M"


def test_a_fiscal_year_that_ends_in_january_keeps_the_date_in_the_title() -> None:
    from spreader.detect import parse_period

    title = "Fiscal years ended January 3, 2026, December 28, 2024, and December 30, 2023"
    assert parse_period("2025", StatementType.INCOME, title=title).key == "2026-01-03/12M"
    assert parse_period("2024", StatementType.INCOME, title=title).key == "2024-12-28/12M"


FIGURES = [("Cash and cash equivalents", "1,234,567", "1,111,223"), ("Accounts receivable", "2,345,671", "2,111,227"), ("Total current assets", "3,580,238", "3,222,450"),
           ("Property and equipment, net", "9,876,543", "8,888,881"), ("Total assets", "13,456,781", "12,111,331"), ("Accounts payable", "3,456,781", "2,111,331"),
           ("Total liabilities", "3,456,781", "2,111,331"), ("Retained earnings", "10,000,000", "10,000,000"), ("Total liabilities and stockholders' equity", "13,456,781", "12,111,331")]


def test_figures_to_the_dollar_with_no_unit_anywhere_are_whole_dollars(profile: Any) -> None:
    t = _spread(statement_html("BALANCE SHEETS", "", Y, FIGURES), profile).statements["balance_sheet"].table
    assert t.scale.rule == "scale.whole_dollars" and t.scale.multiplier == 1


def test_a_unit_stated_anywhere_rules_out_whole_dollars(profile: Any) -> None:
    other = statement_html("Note 5: segments", "(in thousands)", Y, [("Segment one", "10", "9"), ("Segment two", "20", "18"), ("Segment three", "5", "4"), ("Total segments", "35", "31")])
    html = _two(statement_html("BALANCE SHEETS", "", Y, FIGURES), other)
    t = _spread(html, profile).statements["balance_sheet"].table
    assert t.scale.rule != "scale.whole_dollars"


def test_an_audit_report_date_is_not_a_fiscal_year_end() -> None:
    """Three whole filings came out blank: "February 12, 2026" above the statement was read as the year-end of a 2025 column."""
    from spreader.detect import parse_period

    title = "Years ended December 31, 2025 and 2024. We have served as auditor since 2005. New York, February 12, 2026"
    assert parse_period("2025", StatementType.INCOME, title=title).key == "2025-12-31/12M"


def test_a_march_year_end_keeps_each_columns_own_year() -> None:
    from spreader.detect import parse_period

    title = "Years ended March 31, 2024"
    assert parse_period("2023", StatementType.INCOME, title=title).key == "2023-03-31/12M"



def _sheet(index: int, total: str, score: float, rows: int = 20) -> tuple:
    from types import SimpleNamespace

    filler = [SimpleNamespace(tokens=[SimpleNamespace(text="Line"), SimpleNamespace(text="5")]) for _ in range(rows - 1)]
    last = SimpleNamespace(tokens=[SimpleNamespace(text="Total assets"), SimpleNamespace(text=total)])
    return (SimpleNamespace(index=index, rows=[*filler, last]), None, SimpleNamespace(score=score))


def test_a_combined_filing_reads_the_first_company_not_the_best_scoring_one() -> None:
    """Southern, Sempra and MGE: a subsidiary's statements add up, so reading them passed every check and went out unflagged."""
    from spreader.assembly import first_registrant

    parent, subsidiary = _sheet(10, "145,180", 21.0), _sheet(20, "36,538", 24.0)
    best = {StatementType.BALANCE: subsidiary}
    assert first_registrant(best, {StatementType.BALANCE: [parent, subsidiary]}) == 2
    assert best[StatementType.BALANCE] is parent


def test_a_table_that_scores_far_below_is_not_a_second_company() -> None:
    from spreader.assembly import first_registrant

    average_balances, sheet = _sheet(3, "9,000", 8.0), _sheet(30, "10,000", 24.0)
    best = {StatementType.BALANCE: sheet}
    assert first_registrant(best, {StatementType.BALANCE: [average_balances, sheet]}) == 0
    assert best[StatementType.BALANCE] is sheet


def test_a_short_table_is_not_a_second_company() -> None:
    from spreader.assembly import first_registrant

    summary, sheet = _sheet(3, "9,000", 24.0, rows=6), _sheet(30, "10,000", 24.0)
    assert first_registrant({StatementType.BALANCE: sheet}, {StatementType.BALANCE: [summary, sheet]}) == 0


def test_one_company_printed_twice_is_one_company() -> None:
    from spreader.assembly import first_registrant

    a, b = _sheet(3, "10,000", 24.0), _sheet(30, "10,000", 24.0)
    assert first_registrant({StatementType.BALANCE: b}, {StatementType.BALANCE: [a, b]}) == 0
