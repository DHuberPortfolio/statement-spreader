"""The answer key's sign and per-share rules (DECISIONS D57), each from a case found on real filings.

- Disney prints its tax expense in parentheses; the key copied the printed sign and keyed the expense negative, while
  the template (and the platform) spread tax expense positive.
- Amazon tags "Other operating expense (income), net" with a concept whose positive is income; on a cost line the key
  took its value as tagged and keyed an expense of 763 as -763.
- Disney's diluted EPS from continuing operations (1.75) and in total (1.72) both map to the EPS line; the key added
  them (3.47).
- Hasbro prints Advertising as its own selling cost; the key did not count it on selling, general and administrative.
"""

from __future__ import annotations

from spreader.evaluation.ixbrl_truth import build_key
from spreader.profile import load_profile
from test_industry_keys import _doc, _lines
from test_second_reader import _row

PROFILE = load_profile()


def _neg_cell(concept: str, ctx: str, text: str, sign: str = "") -> str:
    """A number printed in parentheses; `sign="-"` makes the tagged fact itself negative."""
    s = f' sign="{sign}"' if sign else ""
    return (f'<td>$</td><td>(<ix:nonFraction name="us-gaap:{concept}" contextRef="{ctx}" unitRef="usd" decimals="-6" '
            f'scale="6"{s}>{text}</ix:nonFraction>)</td><td></td>')


def _pos_cell(concept: str, ctx: str, text: str, sign: str = "", unit: str = "usd", scale: int = 6) -> str:
    s = f' sign="{sign}"' if sign else ""
    return (f'<td>$</td><td><ix:nonFraction name="us-gaap:{concept}" contextRef="{ctx}" unitRef="{unit}" decimals="-6" '
            f'scale="{scale}"{s}>{text}</ix:nonFraction></td><td></td>')


# enough of an income statement for the key to recognise it (it finds statements by their concepts)
BASE = [_row("Revenues", "Revenues", "1000", "900"), _row("Cost of revenues", "CostOfRevenue", "600", "550"),
        _row("Operating income", "OperatingIncomeLoss", "200", "150"), _row("Net income", "NetIncomeLoss", "150", "110")]


def test_tax_expense_printed_in_parentheses_is_keyed_positive_and_a_benefit_negative() -> None:
    rows = BASE + [("Income taxes", _neg_cell("IncomeTaxExpenseBenefit", "d25", "40")
                    + _pos_cell("IncomeTaxExpenseBenefit", "d24", "12", sign="-"))]
    key, _ = build_key("t.htm", _doc(rows), PROFILE)
    assert _lines(key)["income_tax"] == "40000000", "an expense printed (40) is a 40 expense"
    assert _lines(key, "2024-12-31/12M")["income_tax"] == "-12000000", "a tagged benefit stays a benefit"
    printed = {c.period: str(c.value) for c in key.cells if c.line == "income_tax"}
    assert printed["2025-12-31/12M"] == "-40000000", "the printed cell still records the parentheses"


def test_an_income_positive_concept_on_a_cost_line_is_negated() -> None:
    rows = BASE + [("Other operating expense (income), net",
                    _pos_cell("OtherOperatingIncomeExpenseNet", "d25", "763", sign="-")
                    + _pos_cell("OtherOperatingIncomeExpenseNet", "d24", "50"))]
    key, _ = build_key("t.htm", _doc(rows), PROFILE)
    assert _lines(key)["other_opex"] == "763000000", "an expense of 763 is a cost of 763"
    assert _lines(key, "2024-12-31/12M")["other_opex"] == "-50000000", "operating income of 50 is a negative cost"


def test_per_share_figures_on_one_line_are_never_added() -> None:
    eps = [("Continuing operations",
            _pos_cell("IncomeLossFromContinuingOperationsPerDilutedShare", "d25", "1.75", unit="usdPerShare", scale=0)
            + _pos_cell("IncomeLossFromContinuingOperationsPerDilutedShare", "d24", "1.29", unit="usdPerShare", scale=0)),
           ("Diluted",
            _pos_cell("EarningsPerShareDiluted", "d25", "1.72", unit="usdPerShare", scale=0)
            + _pos_cell("EarningsPerShareDiluted", "d24", "1.29", unit="usdPerShare", scale=0))]
    key, _ = build_key("t.htm", _doc(BASE + eps), PROFILE)
    assert _lines(key)["eps_diluted"] == "1.72", "the total diluted EPS, not 1.75 + 1.72"
    assert _lines(key, "2024-12-31/12M")["eps_diluted"] == "1.29"


def test_advertising_printed_as_its_own_line_counts_as_a_selling_cost() -> None:
    rows = BASE + [_row("Advertising", "AdvertisingExpense", "319.5", "358.4"),
                   _row("Selling, distribution and administration", "SellingGeneralAndAdministrativeExpense",
                        "1213.2", "1480.4")]
    key, _ = build_key("t.htm", _doc(rows), PROFILE)
    assert _lines(key)["sga"] == "1532700000.0"


def test_the_platform_places_selling_distribution_and_administration_on_sga() -> None:
    from spreader.contracts import RowRole, StatementRow, StatementTable, StatementType
    from spreader.mapping import map_row

    row = StatementRow(index=0, label="Selling, distribution and administration",
                       label_clean="selling distribution and administration", role=RowRole.DETAIL, values={})
    table = StatementTable.model_construct(doc_id="x", table_index=0, statement=StatementType.INCOME, rows=[row])
    m = map_row(row, table, PROFILE)
    assert m.canonical == "sga" and m.rule.startswith("alias")
