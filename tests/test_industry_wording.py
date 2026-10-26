"""Bank and insurer overlay wording found wrong on the dev filings of the new answer keys (IMPROVEMENT_LOG B2, B3)."""

from __future__ import annotations

from typing import Any

from conftest import statement_html
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import load_profile

BANK = load_profile("config/profiles/us-bank.yaml")
INSURER = load_profile("config/profiles/us-insurer.yaml")
BS_HEAD = ["December 31, 2025", "December 31, 2024"]
IS_HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]


def _placed(profile: Any, title: str, head: list[str], rows: list[tuple]) -> dict[str, str | None]:
    sp, _ = spread_document(read_document("x.htm", statement_html(title, "(In thousands)", head, rows).encode()), profile)
    res = next(iter(sp.statements.values()))
    maps = {m.row_index: m.canonical for m in res.mappings}
    return {r.label: maps.get(r.index) for r in res.table.rows}


BANK_BS = [("Cash and due from banks", "500", "450"), ("Interest-bearing deposits in other banks", "800", "700"),
           ("Securities available for sale", "3,000", "2,800"), ("Trading account securities", "40", "35"),
           ("Loans and leases", "9,000", "8,500"), ("Total assets", "13,340", "12,485"),
           ("Deposits:", None, None), ("  Non-interest-bearing demand deposits", "4,000", "3,900"),
           ("  Interest-bearing", "6,000", "5,500"), ("Total deposits", "10,000", "9,400"),
           ("Total liabilities", "11,000", "10,300"),
           ("Preferred stock, par value $0.01 per share; 10,000 shares authorized", "150", "150"),
           ("Retained earnings", "2,190", "2,035"), ("Total shareholders' equity", "2,340", "2,185"),
           ("Total liabilities and shareholders' equity", "13,340", "12,485")]


def test_an_interest_bearing_deposit_at_another_bank_is_an_asset_not_a_deposit() -> None:
    """Four of eight dev banks had their deposits overstated by exactly the money they keep at other banks."""
    placed = _placed(BANK, "CONSOLIDATED BALANCE SHEETS", BS_HEAD, BANK_BS)
    assert placed["Interest-bearing deposits in other banks"] == "st_investments"
    assert placed["Interest-bearing"] == "deposits" and placed["Total deposits"] == "deposits"


def test_trading_securities_and_long_preferred_labels_are_placed() -> None:
    placed = _placed(BANK, "CONSOLIDATED BALANCE SHEETS", BS_HEAD, BANK_BS)
    assert placed["Trading account securities"] == "bank_securities"
    # "preferred stock*" is also a commercial common-stock alias: the tie left this row unplaced.
    assert placed["Preferred stock, par value $0.01 per share; 10,000 shares authorized"] == "preferred_equity"


def test_a_bank_s_interest_lines_under_a_net_interest_income_heading() -> None:
    rows = [("Net interest income", None, None), ("  Interest income", "900", "800"), ("  Interest expense", "300", "250"),
            ("  Net interest income", "600", "550"), ("Total noninterest income", "200", "190"),
            ("Total noninterest expense", "400", "380"), ("Income before income taxes", "400", "360"),
            ("Income tax expense", "80", "72"), ("Net income", "320", "288"),
            ("Per common share information", None, None), ("  Earnings", "1.60", "1.44"), ("  Diluted earnings", "1.58", "1.42")]
    placed = _placed(BANK, "CONSOLIDATED STATEMENT OF INCOME", IS_HEAD, rows)
    assert placed["Interest income"] == "bank_interest_income" and placed["Interest expense"] == "bank_interest_expense"
    assert placed["Earnings"] == "eps_basic" and placed["Diluted earnings"] == "eps_diluted"


def test_an_insurer_s_total_expenses_and_wording_from_several_insurers() -> None:
    rows = [("Revenues", None, None), ("  Net premiums", "5,000", "4,600"),
            ("  Investment income, net of expenses", "900", "850"), ("  Investment gains and losses, net", "120", "(40)"),
            ("  Total revenues", "6,020", "5,410"), ("Expenses", None, None),
            ("  Claims and other policy benefits", "3,500", "3,300"), ("  Other operating expenses", "1,000", "950"),
            ("  Total expenses", "4,500", "4,250"), ("Income before income taxes", "1,520", "1,160"),
            ("Income tax expense", "300", "230"), ("Net income", "1,220", "930"),
            ("Per common share", None, None), ("  Net income—basic", "8.00", "6.10")]
    placed = _placed(INSURER, "CONSOLIDATED STATEMENTS OF INCOME", IS_HEAD, rows)
    assert placed["Net premiums"] == "premiums_earned"
    assert placed["Investment income, net of expenses"] == "net_investment_income"
    assert placed["Investment gains and losses, net"] == "realized_investment_gains"
    assert placed["Claims and other policy benefits"] == "losses_lae"
    assert placed["Total expenses"] == "total_insurance_expenses"  # an exact tie with the commercial total before
    assert placed["Net income—basic"] == "eps_basic"
