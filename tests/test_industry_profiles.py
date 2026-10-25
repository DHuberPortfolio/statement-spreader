"""Bank, insurer and IFRS overlays (configuration only), and the two engine changes they needed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import statement_html
from spreader.contracts import ReviewKind
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import load_profile

PROFILES = Path(__file__).resolve().parents[1] / "config" / "profiles"
HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]
BS_HEAD = ["December 31, 2025", "December 31, 2024"]


def _spread(html: str, profile_file: str) -> Any:
    return spread_document(read_document("x.htm", html.encode()), load_profile(PROFILES / profile_file))[0]


def _value(spread: Any, line: str, period: str) -> Any:
    v = spread.value(line, period)
    return None if v is None else v.value


def test_bank_lines_and_checks(tmp_path: Path) -> None:
    income = [("Interest and fees on loans", "700", "650"), ("Interest on securities", "300", "250"),
              ("Total interest income", "1,000", "900"), ("Interest on deposits", "350", "300"),
              ("Total interest expense", "400", "350"), ("Net interest income", "600", "550"),
              ("Provision for credit losses", "50", "40"), ("Net interest income after provision for credit losses", "550", "510"),
              ("Total noninterest income", "300", "280"), ("Total noninterest expense", "500", "480"),
              ("Income before income taxes", "350", "310"), ("Applicable income tax expense", "70", "62"),
              ("Net income", "280", "248"), ("Dividends on preferred stock", "20", "20"),
              ("Net income available to common shareholders", "260", "228")]
    balance = [("Cash and due from banks", "100", "90"), ("Available-for-sale debt securities", "2,000", "1,800"),
               ("Portfolio loans and leases", "6,000", "5,500"), ("Allowance for loan and lease losses", "(100)", "(90)"),
               ("Portfolio loans and leases, net", "5,900", "5,410"), ("Other assets", "500", "450"),
               ("Total assets", "8,500", "7,750"), ("Noninterest-bearing deposits", "2,000", "1,900"),
               ("Interest-bearing deposits", "5,000", "4,500"), ("Total deposits", "7,000", "6,400"),
               ("Long-term debt", "500", "450"), ("Total liabilities", "7,500", "6,850"), ("Preferred stock", "100", "100"),
               ("Retained earnings", "900", "800"), ("Total equity", "1,000", "900"),
               ("Total liabilities and equity", "8,500", "7,750")]
    html = (statement_html("CONSOLIDATED STATEMENTS OF INCOME", "(In millions)", HEAD, income)
            + statement_html("CONSOLIDATED BALANCE SHEETS", "(In millions)", BS_HEAD, balance))
    spread = _spread(html, "us-bank.yaml")
    p, i = "2025-12-31/12M", "2025-12-31/I"
    m = 1_000_000
    assert _value(spread, "net_interest_income", p) == 600 * m and _value(spread, "provision_credit_losses", p) == 50 * m
    assert _value(spread, "net_income_common", p) == 260 * m and _value(spread, "preferred_dividends", p) == 20 * m
    assert _value(spread, "deposits", i) == 7000 * m  # the components are inside the printed total: not added twice
    assert _value(spread, "loans_net", i) == 5900 * m and _value(spread, "allowance_loan_losses", i) == -100 * m
    status = {c.id: c.status.value for c in spread.checks if c.period in (p, i)}
    for cid in ("bank_nii", "bank_nii_after_provision", "bank_pretax", "bank_common", "bank_loans_net", "bs_balance"):
        assert status.get(cid) == "pass", (cid, status.get(cid))


def test_insurer_lines_and_check() -> None:
    income = [("Premiums", "4,000", "3,800"), ("Net investment income", "400", "380"), ("Other revenues", "100", "90"),
              ("Total revenues", "4,500", "4,270"), ("Claims and claim adjustment expenses", "2,600", "2,500"),
              ("Amortization of deferred acquisition costs", "700", "680"), ("General and administrative expenses", "500", "480"),
              ("Total claims and expenses", "3,800", "3,660"), ("Income before income taxes", "700", "610"),
              ("Income tax expense", "140", "122"), ("Net income", "560", "488")]
    spread = _spread(statement_html("CONSOLIDATED STATEMENT OF INCOME", "(In millions)", HEAD, income), "us-insurer.yaml")
    p = "2025-12-31/12M"
    assert _value(spread, "premiums_earned", p) == 4_000_000_000 and _value(spread, "losses_lae", p) == 2_600_000_000
    assert _value(spread, "acquisition_costs", p) == 700_000_000 and _value(spread, "revenue", p) == 4_500_000_000
    assert next(c for c in spread.checks if c.id == "insurer_pretax" and c.period == p).status.value == "pass"


def test_ifrs_wording_finds_and_places_an_ifrs_income_statement() -> None:
    income = [("Turnover", "5,000", "4,800"), ("Cost of sales", "(3,000)", "(2,900)"), ("Gross profit", "2,000", "1,900"),
              ("Distribution and administrative expenses", "(1,200)", "(1,150)"), ("Operating profit", "800", "750"),
              ("Finance income", "20", "15"), ("Finance costs", "(70)", "(65)"), ("Profit before tax", "750", "700"),
              ("Taxation", "(150)", "(140)"), ("Profit for the year", "600", "560"),
              ("Attributable to owners of the parent", "590", "550"), ("Non-controlling interests", "10", "10")]
    html = statement_html("CONSOLIDATED INCOME STATEMENT", "(In millions)", HEAD, income)
    assert "income_statement" not in _spread(html, "../profiles/us-commercial.yaml").statements  # US wording: not found
    spread = _spread(html, "ifrs-commercial.yaml")
    p = "2025-12-31/12M"
    assert _value(spread, "revenue", p) == 5_000_000_000 and _value(spread, "operating_income", p) == 800_000_000
    assert _value(spread, "pretax_income", p) == 750_000_000 and _value(spread, "net_income", p) == 600_000_000
    assert _value(spread, "net_income_parent", p) == 590_000_000


def test_an_overlay_can_add_lines_but_never_redefine_one(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_bytes((PROFILES / "us-commercial.yaml").read_bytes())
    over = {"extends": "base.yaml", "id": "x", "version": "1",
            "add_lines": {"balance_sheet": [{"id": "cash", "label": "Cash again", "kind": "asset"}]}}
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(over))
    with pytest.raises(ValueError, match="redefine the template line 'cash'"):
        load_profile(tmp_path / "bad.yaml")
    base = load_profile(PROFILES / "us-commercial.yaml")
    bank = load_profile(PROFILES / "us-bank.yaml")
    assert set(base.lines) < set(bank.lines)  # every template line is still there
    assert "deposits" not in base.lines  # and the base itself is untouched by loading an overlay


def test_a_parent_company_only_statement_is_a_blocker() -> None:
    """Found on an insurer's 10-K whose consolidated statements are in an exhibit: the parent's own condensed balance
    sheet was the only one in the document and was spread, unflagged, as if it were the group's."""
    rows = [("Cash", "100", "90"), ("Investment in subsidiaries", "4,000", "3,800"), ("Total assets", "4,100", "3,890"),
            ("Debt", "1,000", "1,000"), ("Total liabilities", "1,000", "1,000"), ("Retained earnings", "3,100", "2,890"),
            ("Total shareholders' equity", "3,100", "2,890"), ("Total liabilities and shareholders' equity", "4,100", "3,890")]
    html = statement_html("Schedule II - Condensed Financial Information of Registrant Condensed Balance Sheets "
                          "(Parent Company)", "(In millions)", BS_HEAD, rows)
    spread = _spread(html, "us-commercial.yaml")
    items = [i for i in spread.review if i.id.startswith("parent_only:")]
    assert items and items[0].severity.value == "blocker" and items[0].kind is ReviewKind.CONFLICT
    assert spread.value("total_assets", "2025-12-31/I").flags  # the value is not accepted alone
