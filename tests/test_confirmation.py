"""A value goes out without a person only when two checks that ran and held confirm it (D59, Devin: strict for now).

Measured on the dev sets: values in at least one passing check were still wrong 0.8-3.0% of the time (AMD's other
non-operating income: an amount moved between two lines of one sum; Western Alliance's operating and investing cash
flows: a set that still balanced), in at least two 0 of 489. The price: most values go to review until more independent
confirmations exist (last year's approved spread, cross-statement ties).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from conftest import statement_html
from spreader.contracts import CheckResult, CheckStatus, ReviewItem, ReviewKind, Severity, SpreadValue, ValueStatus
from spreader.review import confirmations_required, unconfirmed_items
from spreader.service import Service
from spreader.store import Store

P = "2025-12-31/12M"


def _v(line: str, period: str = P, status: ValueStatus = ValueStatus.EXTRACTED) -> SpreadValue:
    return SpreadValue(line=line, period=period, value=Decimal(1), status=status)


def _check(cid: str, lines: list[str], status: CheckStatus = CheckStatus.PASS) -> CheckResult:
    return CheckResult(id=cid, title=cid, period=P, status=status, lines=lines)


CHECKS = [_check("is_net", ["net_income", "pretax_income", "income_tax"]),
          _check("cross_net_income", ["cf_net_income", "net_income"]),
          _check("is_pretax", ["pretax_income", "operating_income"], CheckStatus.FAIL)]


def _unconfirmed(values: list[SpreadValue], profile: Any, items: list[ReviewItem] | None = None,
                 required: int | None = 2) -> set[str]:
    return {ln for it in unconfirmed_items(values, CHECKS, items or [], profile, required) for ln in it.lines}


def test_two_holding_checks_confirm_one_does_not(profile: Any) -> None:
    values = [_v("net_income"), _v("income_tax"), _v("operating_income")]
    assert _unconfirmed(values, profile) == {"income_tax", "operating_income"}
    assert _unconfirmed(values, profile, required=1) == {"operating_income"}  # a failed check confirms nothing


def test_one_item_per_statement_and_period_naming_the_values(profile: Any) -> None:
    items = unconfirmed_items([_v("income_tax"), _v("operating_income")], CHECKS, [], profile, 2)
    assert len(items) == 1 and items[0].kind is ReviewKind.UNCONFIRMED and items[0].severity is Severity.WARNING
    assert items[0].id == f"unconfirmed:income_statement:{P}" and items[0].periods == [P]
    assert "Income tax" in items[0].message and "2 values" in items[0].message


def test_values_a_person_entered_or_already_doubted_are_not_listed_again(profile: Any) -> None:
    doubt = ReviewItem(id="x", kind=ReviewKind.SUSPICIOUS, severity=Severity.WARNING, message="m",
                       lines=["operating_income"], periods=[P])
    values = [_v("income_tax", status=ValueStatus.HUMAN), _v("operating_income")]
    assert _unconfirmed(values, profile, [doubt]) == set()


def test_a_balance_sheet_value_is_confirmed_by_checks_on_flows_ending_that_day(profile: Any) -> None:
    checks = [_check("cross_cash", ["cash_end", "cash"]), _check("cf_rollforward", ["cash_end", "cash_begin", "net_change_cash"])]
    assert not unconfirmed_items([_v("cash", "2025-12-31/I"), _v("cash_end")], checks, [], profile, 1)


def test_the_setting(profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    assert confirmations_required() == 2
    monkeypatch.setenv("SPREADER_CONFIRMATIONS", "0")
    assert unconfirmed_items([_v("operating_income")], CHECKS, [], profile) == []
    monkeypatch.setenv("SPREADER_CONFIRMATIONS", "two")
    with pytest.raises(ValueError, match="SPREADER_CONFIRMATIONS"):
        confirmations_required()


BS = [("Cash and cash equivalents", "100", "80"), ("Accounts receivable, net", "50", "40"),
      ("Total current assets", "150", "120"), ("Property, plant and equipment, net", "250", "220"),
      ("Total assets", "400", "340"), ("Accounts payable", "60", "50"), ("Total current liabilities", "60", "50"),
      ("Long-term debt", "140", "130"), ("Total liabilities", "200", "180"), ("Retained earnings", "200", "160"),
      ("Total stockholders' equity", "200", "160"), ("Total liabilities and stockholders' equity", "400", "340")]


def test_an_unconfirmed_value_is_reviewed_and_resolving_the_item_accepts_it(tmp_path: Any, profile: Any) -> None:
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", ["December 31, 2025", "December 31, 2024"], BS)
    _, view = svc.upload("bs.htm", html.encode(), "tester")
    ppe = view.spread.value("ppe_net", "2025-12-31/I")
    assert ppe is not None and any(f.startswith("unconfirmed:") for f in ppe.flags)
    item = next(i for i in view.spread.review if i.id == "unconfirmed:balance_sheet:2025-12-31/I")
    after = svc.act(view.run["id"], {"type": "resolve_item", "item": item.id, "note": "Compared with the filing"}, "tester")
    ppe = after.spread.value("ppe_net", "2025-12-31/I")
    assert ppe is not None and not any(f.startswith("unconfirmed:") for f in ppe.flags)
