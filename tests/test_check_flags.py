"""What a failed check flags (IMPROVEMENT_LOG #22): every input, except one confirmed against another statement."""

from __future__ import annotations

from typing import Any

from spreader.contracts import CheckResult, CheckStatus, ReviewKind
from spreader.review import build_review

P = "2025-12-31/12M"


def _check(cid: str, status: CheckStatus, lines: list[str], period: str = P) -> CheckResult:
    return CheckResult(id=cid, title=cid.replace("_", " "), period=period, status=status, lines=lines)


def _lines_flagged(checks: list[CheckResult], profile: Any, cid: str = "is_net") -> list[str]:
    items = build_review({}, [], checks, profile)
    return next(i.lines for i in items if i.kind is ReviewKind.FAILED_CHECK and i.id.startswith(f"check:{cid}:"))


def test_a_value_confirmed_by_the_cash_flow_statement_is_not_flagged_by_an_income_check(profile: Any) -> None:
    """Net income ties to the cash-flow statement's starting line: if the income statement's pre-tax-minus-tax check
    fails, net income would have to be misread in two tables the same way to be the cause."""
    checks = [_check("is_net", CheckStatus.FAIL, ["net_income", "pretax_income", "income_tax"]),
              _check("cross_net_income", CheckStatus.PASS, ["cf_net_income", "net_income"])]
    assert _lines_flagged(checks, profile) == ["pretax_income", "income_tax"]
    item = next(i for i in build_review({}, [], checks, profile) if i.id.startswith("check:is_net:"))
    assert "confirms them: Net income" in item.message


def test_confirmation_inside_the_same_statement_does_not_count(profile: Any) -> None:
    """A row placed on the wrong line moves an amount within one statement, which that statement's own checks cannot
    see (the reverted IMPROVEMENT_LOG #12; measured again tonight: 3 wrong values would have lost their flag)."""
    checks = [_check("is_net", CheckStatus.FAIL, ["net_income", "pretax_income", "income_tax"]),
              _check("is_pretax", CheckStatus.PASS, ["pretax_income", "operating_income"])]
    assert _lines_flagged(checks, profile) == ["net_income", "pretax_income", "income_tax"]


def test_a_confirmation_whose_other_side_is_itself_in_doubt_does_not_count(profile: Any) -> None:
    checks = [_check("is_net", CheckStatus.FAIL, ["net_income", "pretax_income", "income_tax"]),
              _check("cross_net_income", CheckStatus.PASS, ["cf_net_income", "net_income"]),
              _check("cf_sum", CheckStatus.FAIL, ["net_change_cash", "cfo", "cf_net_income"])]
    assert "net_income" in _lines_flagged(checks, profile)


def test_another_period_confirms_nothing(profile: Any) -> None:
    checks = [_check("is_net", CheckStatus.FAIL, ["net_income", "pretax_income", "income_tax"]),
              _check("cross_net_income", CheckStatus.PASS, ["cf_net_income", "net_income"], period="2024-12-31/12M")]
    assert "net_income" in _lines_flagged(checks, profile)
