"""A parent company's own statements, known by their rows; and "cash surrender value" is not the change in cash (D57).

Found on Hancock Whitney's 10-K: its "Condensed Statements of Cash Flows" (the holding company's own, headed "parent
company only" pages above) outscored the consolidated statement. Once a figure printed twice was counted once (D56) it
added up, and three wrong values a year went out without review. Its consolidated statement then showed the second
problem: "Increase in cash surrender value of life insurance contracts" matched "increase in cash*".
"""

from __future__ import annotations

from typing import Any

from conftest import statement_html
from spreader.contracts import RowRole, StatementRow, StatementTable, StatementType
from spreader.ingest import read_document
from spreader.mapping import map_row
from spreader.pipeline import spread_document
from spreader.structure import clean_label

HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]


def _cf(title: str, rows: list[tuple]) -> str:
    return statement_html(title, "($ in thousands)", HEAD, rows).split("<body>", 1)[1].rsplit("</body>", 1)[0]


CONSOLIDATED = _cf("CONSOLIDATED STATEMENTS OF CASH FLOWS", [
    ("Net income", "500", "450"), ("Depreciation and amortization", "60", "55"),
    ("Net cash provided by operating activities", "560", "505"),
    ("Purchases of securities", "(900)", "(800)"), ("Proceeds from maturities of securities", "700", "650"),
    ("Net cash used in investing activities", "(200)", "(150)"),
    ("Dividends paid", "(100)", "(90)"), ("Net cash used in financing activities", "(100)", "(90)"),
    ("Net increase in cash and cash equivalents", "260", "265"),
    ("Cash and cash equivalents, beginning of year", "1,000", "735"), ("Cash and cash equivalents, end of year", "1,260", "1,000")])
PARENT = _cf("Condensed Statements of Cash Flows", [
    ("Net income", "500", "450"), ("Equity in undistributed earnings of subsidiaries", "(273)", "(223)"),
    ("Cash flows from operating activities - principally dividends received from subsidiaries", "227", "227"),
    ("Net cash provided by operating activities", "227", "227"),
    ("Net cash provided by investing activities", "0", "320"),
    ("Dividends paid", "(173)", "(173)"), ("Net cash used in financing activities", "(173)", "(173)"),
    ("Net increase (decrease) in cash", "54", "374"), ("Cash, beginning of year", "219", "(155)"),
    ("Cash, end of year", "273", "219")])


def test_the_consolidated_cash_flow_wins_over_the_parent_companys_own(profile: Any) -> None:
    html = f"<html><body>{CONSOLIDATED}<p>Note 22. Parent company</p>{PARENT}</body></html>"
    spread, _ = spread_document(read_document("bank.htm", html.encode()), profile)
    cfi = spread.value("cfi", "2025-12-31/12M")
    assert cfi is not None and int(cfi.value) == -200_000
    assert not any(i.id.startswith("parent_only") for i in spread.review)


def test_a_parent_only_statement_alone_is_a_blocker_even_without_its_heading(profile: Any) -> None:
    spread, _ = spread_document(read_document("bank.htm", f"<html><body>{PARENT}</body></html>".encode()), profile)
    assert any(i.id.startswith("parent_only") and i.severity.value == "blocker" for i in spread.review)


def test_cash_surrender_value_is_not_the_change_in_cash(profile: Any) -> None:
    def line(label: str) -> str | None:
        row = StatementRow(index=0, label=label, label_clean=clean_label(label), role=RowRole.DETAIL, values={})
        t = StatementTable.model_construct(doc_id="x", table_index=0, statement=StatementType.CASH_FLOW, rows=[row])
        return map_row(row, t, profile).canonical

    assert line("Increase in cash surrender value of life insurance contracts") != "net_change_cash"
    assert line("Increase (decrease) in cash surrender value") != "net_change_cash"
    for ok in ("Net increase (decrease) in cash and cash equivalents", "Increase (decrease) in cash, cash equivalents and "
               "restricted cash", "Decrease in cash and due from banks", "Change in cash", "Net change in cash"):
        assert line(ok) == "net_change_cash", ok
