"""Income tax's sign from the statement's own arithmetic (DECISIONS D57), each case from a real filing.

Amazon, Netflix, Qualcomm, Union Pacific and YETI print only the tax in parentheses ("Provision for income taxes
(9,265)") among positive costs; AXIS and Etsy print "Income tax (expense) benefit", where a positive number is a
benefit. The platform took a lone tax line in parentheses for a benefit. Pre-tax income - tax = net income settles it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from conftest import statement_html
from spreader.ingest import read_document
from spreader.pipeline import spread_document

HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]


def _tax(profile: Any, rows: list[tuple]) -> dict[str, Any]:
    html = statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In millions)", HEAD, rows)
    spread, _ = spread_document(read_document("t.htm", html.encode()), profile)
    return {v.period: v for v in spread.values if v.line == "income_tax"}


TOP = [("Net sales", "1,000", "900"), ("Cost of sales", "600", "550"), ("Selling, general and administrative", "200", "180"),
       ("Operating income", "200", "170"), ("Income before income taxes", "200", "170")]


def test_an_expense_printed_as_the_only_deduction_is_an_expense(profile: Any) -> None:
    tax = _tax(profile, TOP + [("Provision for income taxes", "(40)", "(30)"), ("Net income", "160", "140")])
    assert tax["2025-12-31/12M"].value == Decimal(40_000_000)
    assert tax["2024-12-31/12M"].value == Decimal(30_000_000)
    assert any("only with this sign" in s.detail for s in tax["2025-12-31/12M"].steps)


def test_an_expense_benefit_label_prints_the_benefit_positive(profile: Any) -> None:
    tax = _tax(profile, TOP + [("Income tax (expense) benefit", "12", "(30)"), ("Net income", "212", "140")])
    assert tax["2025-12-31/12M"].value == Decimal(-12_000_000), "a benefit of 12"
    assert tax["2024-12-31/12M"].value == Decimal(30_000_000), "an expense of 30"


def test_a_tax_that_already_adds_up_is_left_alone(profile: Any) -> None:
    tax = _tax(profile, TOP + [("Provision for income taxes", "40", "30"), ("Net income", "160", "140")])
    assert tax["2025-12-31/12M"].value == Decimal(40_000_000)
    assert not any("only with this sign" in s.detail for s in tax["2025-12-31/12M"].steps)


def test_when_the_arithmetic_cannot_tell_nothing_changes(profile: Any) -> None:
    """Equity income after tax (Amazon, AXIS): neither sign makes pre-tax - tax = net income; the checks speak."""
    rows = TOP + [("Provision for income taxes", "(40)", "(30)"), ("Equity-method investment activity, net of tax", "5", "3"),
                  ("Net income", "165", "143")]
    tax = _tax(profile, rows)
    assert not any("only with this sign" in s.detail for s in tax["2025-12-31/12M"].steps)


def test_net_income_before_noncontrolling_interests_is_net_income(profile: Any) -> None:
    rows = TOP + [("Income tax expense", "(40)", "(30)"), ("Net income before noncontrolling interests", "160", "140"),
                  ("Noncontrolling interests", "(5)", "(4)"), ("Net income to common stockholders", "155", "136")]
    html = statement_html("CONSOLIDATED STATEMENTS OF INCOME", "(In millions)", HEAD, rows)
    spread, _ = spread_document(read_document("t.htm", html.encode()), profile)
    ni = spread.value("net_income", "2025-12-31/12M")
    assert ni is not None and ni.value == Decimal(160_000_000)
    assert spread.value("income_tax", "2025-12-31/12M").value == Decimal(40_000_000), "W. R. Berkley's case"
    # and its company share is the printed row, not derived from the consolidated figure (found when the line above
    # was added: three of W. R. Berkley's values went silently wrong until this label was known)
    parent = spread.value("net_income_parent", "2025-12-31/12M")
    assert parent is not None and parent.value == Decimal(155_000_000)
