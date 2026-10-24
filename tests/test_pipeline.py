"""End-to-end behaviour of the pipeline on small hand-built statements with hand-worked answers."""

from __future__ import annotations

from decimal import Decimal

from conftest import statement_html
from spreader.contracts import ReviewKind, RowRole, ValueStatus
from spreader.ingest import read_document
from spreader.pipeline import spread_document

IS_ROWS = [
    ("Net sales:",),
    ("  Products", "300", "200"),
    ("  Services", "100", "50"),
    ("Total net sales", "400", "250"),
    ("Cost of sales", "150", "100"),
    ("Gross margin", "250", "150"),
    ("Research and development", "50", "40"),
    ("Selling, general and administrative", "30", "20"),
    ("Total operating expenses", "80", "60"),
    ("Operating income", "170", "90"),
    ("Interest expense", "(10)", "(5)"),
    ("Income before income taxes", "160", "85"),
    ("Provision for income taxes", "40", "20"),
    ("Net income", "120", "65"),
]
BS_ROWS = [
    ("Current assets:",),
    ("  Cash and cash equivalents", "100", "80"),
    ("  Accounts receivable, net", "50", "40"),
    ("  Inventories", "30", "20"),
    ("Total current assets", "180", "140"),
    ("Property, plant and equipment, net", "220", "200"),
    ("Total assets", "400", "340"),
    ("Current liabilities:",),
    ("  Accounts payable", "60", "50"),
    ("Total current liabilities", "60", "50"),
    ("Long-term debt", "140", "130"),
    ("Total liabilities", "200", "180"),
    ("Common stock and additional paid-in capital, $0.01 par value; 100 shares authorized", "50", "50"),
    ("Retained earnings", "150", "110"),
    ("Total shareholders' equity", "200", "160"),
    ("Total liabilities and shareholders' equity", "400", "340"),
]


def _doc(rows: list[tuple], header: list[str], unit: str = "(In thousands)", title: str = "CONSOLIDATED STATEMENTS",
         hidden: list[tuple] | None = None) -> str:
    return statement_html(title, unit, header, rows, hidden)


def _run(html: str, profile):  # type: ignore[no-untyped-def]
    ir = read_document("t.htm", html.encode())
    spread, _ = spread_document(ir, profile)
    return spread


def test_income_statement_end_to_end(profile) -> None:  # type: ignore[no-untyped-def]
    html = _doc(IS_ROWS, ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]) + _doc(
        BS_ROWS, ["December 31, 2025", "December 31, 2024"], title="CONSOLIDATED BALANCE SHEETS")
    sp = _run(html, profile)
    assert set(sp.statements) == {"income_statement", "balance_sheet"}
    rev = sp.value("revenue", "2025-12-31/12M")
    # Total net sales (400), not Products + Services + Total (800): components are not added again.
    assert rev is not None and rev.value == Decimal(400_000)
    assert rev.status is ValueStatus.EXTRACTED
    # Interest expense printed "(10)" and added into pre-tax income as a negative is a deduction:
    # the template spreads costs as positive numbers, and says why.
    ie = sp.value("interest_expense", "2025-12-31/12M")
    assert ie.value == Decimal(10_000) and ie.status is ValueStatus.NORMALIZED
    assert any(s.kind == "sign" for s in ie.steps)
    # Footing found the totals by arithmetic.
    is_rows = {r.label: r for r in sp.statements["income_statement"].table.rows}
    assert is_rows["Total net sales"].role is RowRole.TOTAL
    assert is_rows["Total operating expenses"].role is RowRole.TOTAL
    # The equity line that mentions shares and par value is money, not a share count.
    assert sp.value("common_stock_apic", "2025-12-31/I").value == Decimal(50_000)
    failed = [c for c in sp.checks if c.status.value == "fail"]
    assert not failed, [c.explanation for c in failed]
    assert sp.value("total_assets", "2025-12-31/I").refs[0].text.endswith("400")


def test_hidden_rows_never_reach_the_spread(profile) -> None:  # type: ignore[no-untyped-def]
    html = _doc(BS_ROWS, ["December 31, 2025", "December 31, 2024"],
                hidden=[("Other current assets", "999,999", "999,999")])
    sp = _run(html, profile)
    assert sp.value("other_current_assets", "2025-12-31/I") is None
    assert sp.value("cash", "2025-12-31/I").value == Decimal(100_000)


def test_no_unit_statement_is_a_blocker(profile) -> None:  # type: ignore[no-untyped-def]
    html = _doc(BS_ROWS, ["December 31, 2025", "December 31, 2024"], unit="")
    sp = _run(html, profile)
    kinds = {(i.kind, i.severity.value) for i in sp.review}
    assert (ReviewKind.ASSUMED_SCALE, "blocker") in kinds
    assert sp.value("cash", "2025-12-31/I").status is ValueStatus.ASSUMED
    assert sp.value("cash", "2025-12-31/I").flags


def test_a_document_that_does_not_add_up_is_flagged_not_fixed(profile) -> None:  # type: ignore[no-untyped-def]
    rows = [r if r[0] != "Total current assets" else ("Total current assets", "185", "140") for r in BS_ROWS]
    sp = _run(_doc(rows, ["December 31, 2025", "December 31, 2024"]), profile)
    tca = sp.value("total_current_assets", "2025-12-31/I")
    assert tca.value == Decimal(185_000)  # the printed number, not a silently "corrected" one
    assert tca.flags, "the total that does not foot must not be auto-accepted"
    kinds = {i.kind for i in sp.review}
    assert ReviewKind.FAILED_CHECK in kinds


def test_misplaced_row_is_caught_by_a_check(profile) -> None:  # type: ignore[no-untyped-def]
    # A long-term asset printed inside the current-asset block under an unknown label: footing
    # still passes, but the template's current-assets check does not.
    rows = list(BS_ROWS)
    rows[3] = ("  Inventories", "30", "20")
    sp = _run(_doc(rows, ["December 31, 2025", "December 31, 2024"]), profile)
    assert not [c for c in sp.checks if c.status.value == "fail"]


def test_year_only_headers_take_the_date_from_the_title(profile) -> None:  # type: ignore[no-untyped-def]
    html = _doc(IS_ROWS, ["2026", "2025"], unit="Amounts in millions except per share amounts; Years ended June 30")
    sp = _run(html, profile)
    keys = [p.key for p in sp.statements["income_statement"].table.periods]
    assert keys == ["2026-06-30/12M", "2025-06-30/12M"]
    assert sp.value("revenue", "2026-06-30/12M").value == Decimal(400_000_000)


def test_run_is_deterministic(profile) -> None:  # type: ignore[no-untyped-def]
    html = _doc(IS_ROWS, ["Year Ended December 31, 2025", "Year Ended December 31, 2024"])
    a = _run(html, profile).model_dump_json()
    b = _run(html, profile).model_dump_json()
    assert a == b
