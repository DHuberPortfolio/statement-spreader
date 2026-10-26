"""Answer keys for banks and insurers: the crosswalk's industry overlays (DECISIONS D41).

The commercial crosswalk calls a bank's InterestExpense the template's non-operating interest expense, and its revenue
concept (tagged by banks on one component, "service charges on deposit accounts") revenue. With the bank profile, the
key now puts interest expense on the overlay's bank line and leaves that revenue component unjudged; the commercial
keys are unchanged (six of them rebuilt byte for byte when this was written).
"""

from __future__ import annotations

from spreader.evaluation.ixbrl_truth import CROSSWALK, build_key, crosswalk_for
from spreader.profile import load_profile
from test_second_reader import CONTEXTS, _row

BANK = load_profile("config/profiles/us-bank.yaml")
INSURER = load_profile("config/profiles/us-insurer.yaml")
COMMERCIAL = load_profile()


def _doc(rows: list[tuple[str, str]]) -> bytes:
    head = '<tr><td></td><td colspan="3">Year Ended December 31, 2025</td><td colspan="3">Year Ended December 31, 2024</td></tr>'
    table = ("<p>CONSOLIDATED STATEMENTS OF INCOME</p><p>(In millions)</p><table>" + head
             + "".join(f"<tr><td>{label}</td>{cells}</tr>" for label, cells in rows) + "</table>")
    return ('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
            'xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2024"><body>'
            f'<div style="display:none"><ix:header><ix:resources>{CONTEXTS}</ix:resources></ix:header></div>'
            + table + "</body></html>").encode()


BANK_IS = [_row("Total interest income", "InterestAndDividendIncomeOperating", "900", "800"),
           _row("Total interest expense", "InterestExpense", "300", "250"),
           _row("Net interest income", "InterestIncomeExpenseNet", "600", "550"),
           _row("Provision for credit losses", "ProvisionForLoanLeaseAndOtherLosses", "50", "40"),
           _row("Service charges on deposit accounts", "RevenueFromContractWithCustomerExcludingAssessedTax", "70", "65"),
           _row("Total noninterest income", "NoninterestIncome", "200", "190"),
           _row("Total noninterest expense", "NoninterestExpense", "400", "380"),
           _row("Income before income taxes", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "350", "320"),
           _row("Income tax expense", "IncomeTaxExpenseBenefit", "70", "64"),
           _row("Net income", "NetIncomeLoss", "280", "256")]


def _lines(key, period: str = "2025-12-31/12M") -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {v.line: str(v.value) for v in key.spread if v.period == period}


def test_a_bank_key_puts_interest_on_the_bank_lines_and_leaves_the_revenue_component_unjudged() -> None:
    key, _ = build_key("bank.htm", _doc(BANK_IS), BANK)
    lines = _lines(key)
    assert lines["bank_interest_income"] == "900000000" and lines["bank_interest_expense"] == "300000000"
    assert lines["net_interest_income"] == "600000000" and lines["provision_credit_losses"] == "50000000"
    assert lines["noninterest_income"] == "200000000" and lines["noninterest_expense"] == "400000000"
    assert "interest_expense" not in lines and "revenue" not in lines


def test_the_same_document_under_the_commercial_profile_keeps_the_base_meanings() -> None:
    key, _ = build_key("bank.htm", _doc(BANK_IS), COMMERCIAL)
    lines = _lines(key)
    assert lines["interest_expense"] == "300000000" and lines["revenue"] == "70000000"
    assert "bank_interest_expense" not in lines


def test_insurer_overlay_maps_premiums_and_moves_investment_gains() -> None:
    rows = [_row("Net premiums earned", "PremiumsEarnedNet", "500", "450"),
            _row("Net investment income", "NetInvestmentIncome", "80", "70"),
            _row("Net investment gains (losses)", "GainLossOnInvestments", "10", "(5)"),
            _row("Total revenues", "Revenues", "590", "515"),
            _row("Losses and loss adjustment expenses", "PolicyholderBenefitsAndClaimsIncurredNet", "300", "280"),
            _row("Total expenses", "OperatingExpenses", "450", "420"),
            _row("Income tax expense", "IncomeTaxExpenseBenefit", "30", "20"),
            _row("Net income", "NetIncomeLoss", "110", "75")]
    lines = _lines(build_key("ins.htm", _doc(rows), INSURER)[0])
    assert lines["premiums_earned"] == "500000000" and lines["net_investment_income"] == "80000000"
    assert lines["realized_investment_gains"] == "10000000" and lines["total_insurance_expenses"] == "450000000"
    assert "other_nonoperating" not in lines and "total_opex" not in lines


def test_the_overlay_only_adds_to_the_profile_it_belongs_to() -> None:
    assert crosswalk_for(COMMERCIAL) == CROSSWALK
    assert crosswalk_for(BANK)["InterestExpense"] == "bank_interest_expense" and CROSSWALK["InterestExpense"] == "interest_expense"
    assert crosswalk_for(INSURER)["PreferredStockValue"] is None
    # Every line an overlay names exists in its profile (a typo would silently leave values unjudged).
    for profile in (BANK, INSURER):
        from spreader.evaluation.ixbrl_truth import INDUSTRY_CROSSWALK

        assert {ln for ln in INDUSTRY_CROSSWALK[profile.id].values() if ln} <= set(profile.lines)
