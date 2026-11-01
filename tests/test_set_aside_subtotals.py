"""Printed subtotals left out as "a subtotal of rows placed on other lines" while a template total stayed blank (D58).

Found by tracing the commercial, bank and insurer dev sets' silent blanks: 13 such subtotals hid 32 values. They were
the template's own totals under wordings no alias knew (Boeing's "Earnings/(loss) from operations", McDonald's "Cash
provided by operations") and parent-equity totals named after the company ("Total AIG shareholders' equity"). The
wordings are now known, and a subtotal that is still left out while a total is blank goes to a person.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import statement_html
from spreader.contracts import RowRole, StatementRow, StatementTable, StatementType
from spreader.ingest import read_document
from spreader.mapping import map_row
from spreader.pipeline import spread_document
from spreader.structure import clean_label


def _line(profile: Any, label: str, statement: StatementType) -> str | None:
    row = StatementRow(index=0, label=label, label_clean=clean_label(label), role=RowRole.TOTAL, values={})
    t = StatementTable.model_construct(doc_id="x", table_index=0, statement=statement, rows=[row])
    return map_row(row, t, profile).canonical


@pytest.mark.parametrize("label,statement,line", [
    ("Earnings/(loss) from operations", StatementType.INCOME, "operating_income"),
    ("Earnings/(loss) before income taxes", StatementType.INCOME, "pretax_income"),
    ("Net income before allocation to noncontrolling interests", StatementType.INCOME, "net_income"),
    ("Total revenue, net of interest expense", StatementType.INCOME, "revenue"),
    ("Cash provided by operations", StatementType.CASH_FLOW, "cfo"),
    ("Cash and equivalents increase (decrease)", StatementType.CASH_FLOW, "net_change_cash"),
    ("Total liabilities, noncontrolling interests and shareholders' equity", StatementType.BALANCE,
     "total_liabilities_equity"),
    ("Total AIG shareholders’ equity", StatementType.BALANCE, "total_equity_parent"),
    ("Total MetLife, Inc.’s stockholders’ equity", StatementType.BALANCE, "total_equity_parent"),
    ("FHN shareholders' equity", StatementType.BALANCE, "total_equity_parent"),
])
def test_wordings_of_template_totals(profile: Any, label: str, statement: StatementType, line: str) -> None:
    assert _line(profile, label, statement) == line


@pytest.mark.parametrize("label", ["Total liabilities and shareholders' equity", "Total preferred shareholders' equity",
                                   "Total noncontrolling interests in shareholders' equity",
                                   "Total equity including noncontrolling interests"])
def test_other_equity_totals_are_not_the_parents_own(profile: Any, label: str) -> None:
    assert _line(profile, label, StatementType.BALANCE) != "total_equity_parent"


HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]


def _income(subtotal: str) -> bytes:
    return statement_html("CONSOLIDATED STATEMENTS OF INCOME", "(in millions)", HEAD, [
        ("Net sales", "1,000", "880"), ("Cost of goods sold", "(600)", "(520)"), (subtotal, "400", "360"),
        ("Interest expense", "(50)", "(40)"), ("Earnings before income taxes", "350", "320"),
        ("Income taxes", "(70)", "(64)"), ("Net earnings", "280", "256")]).encode()


def test_a_subtotal_left_out_while_a_total_is_blank_goes_to_a_person(profile: Any) -> None:
    spread, _ = spread_document(read_document("co.htm", _income("Segment earnings before financial services")), profile)
    if spread.value("operating_income", "2025-12-31/12M") is not None:
        pytest.skip("operating income was derived, so nothing is blank")
    items = [i for i in spread.review if i.id.startswith("set_aside:")]
    assert items and items[0].severity.value == "warning" and "Operating income" in items[0].message


def test_no_item_when_the_subtotal_leaves_nothing_blank(profile: Any) -> None:
    spread, _ = spread_document(read_document("co.htm", _income("Operating income")), profile)
    assert spread.value("operating_income", "2025-12-31/12M") is not None
    assert not any(i.id.startswith("set_aside:") for i in spread.review)
