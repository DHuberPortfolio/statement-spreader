"""Sums of detail lines no check covered, as confirm-only checks (D62), and the parent-only rows they exposed.

Measured on the dev sets: the right values accepted alone rose with none wrong on the commercial and insurer sets; on
banks they let Western Alliance's investing cash through three times, because its parent-company-only cash flow
statement was read in place of the consolidated one (its rows added up). The parent-only row pattern now knows that
bank's wording.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from conftest import statement_html
from spreader.contracts import (
    CheckResult,
    CheckStatus,
    Confirmation,
    Echo,
    Period,
    RowMapping,
    Scale,
    SourceFormat,
    SourceRef,
    SpreadValue,
    StatementResult,
    StatementRow,
    StatementTable,
    StatementType,
    ValueStatus,
)
from spreader.confirm import LabelRecord, find_confirmations
from spreader.echo import is_catch_all
from spreader.evaluation.ixbrl_truth import _rescale_untagged_shares
from spreader.evaluation.truth import AnswerKey, TruthValue
from spreader.pipeline import _PARENT_ROWS
from spreader.review import build_review, unconfirmed_items
from spreader.service import Service
from spreader.store import Store

P = "2025-12-31/12M"


def test_a_failed_confirm_only_check_flags_nothing(profile: Any) -> None:
    failed = [CheckResult(id=cid, title=cid, period=P, status=CheckStatus.FAIL, lines=["cfi", "capex"],
                          difference=Decimal(5), tolerance=Decimal(1)) for cid in ("cf_investing_parts", "cf_sum")]
    ids = {i.id for i in build_review({}, [], failed, profile)}
    assert f"check:cf_sum:{P}" in ids, "an ordinary failed check is still raised"
    assert f"check:cf_investing_parts:{P}" not in ids


@pytest.mark.parametrize("cid", ["cf_operating_parts", "cf_investing_parts", "cf_financing_parts", "bs_equity_components",
                                 "is_opex_parts", "is_costs_parts", "is_eps_diluted"])
def test_the_new_checks_only_confirm(profile: Any, cid: str) -> None:
    assert next(c for c in profile.checks if c.id == cid).role == "confirm"


BS = [("Cash and cash equivalents", "100", "80"), ("Total current assets", "100", "80"),
      ("Property, plant and equipment, net", "300", "260"), ("Total assets", "400", "340"),
      ("Accounts payable", "60", "50"), ("Total current liabilities", "60", "50"), ("Long-term debt", "140", "130"),
      ("Total liabilities", "200", "180"), ("Common stock and additional paid-in capital", "50", "50"),
      ("Retained earnings", "150", "110"), ("Total stockholders' equity", "200", "160"),
      ("Total liabilities and stockholders' equity", "400", "340")]


def test_equity_lines_that_add_up_are_confirmed_by_the_sum(tmp_path: Any, profile: Any,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """With one confirmation required, retained earnings needs a check that includes it: before D62 there was none."""
    monkeypatch.setenv("SPREADER_CONFIRMATIONS", "1")
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", ["December 31, 2025", "December 31, 2024"], BS)
    _, view = svc.upload("bs.htm", html.encode(), "tester")
    check = next(c for c in view.spread.checks if c.id == "bs_equity_components" and c.period == "2025-12-31/I")
    assert check.status is CheckStatus.PASS
    for line in ("retained_earnings", "common_stock_apic"):
        v = view.spread.value(line, "2025-12-31/I")
        assert v is not None and not any(f.startswith("unconfirmed:") for f in v.flags), line


def test_equity_lines_that_do_not_add_up_raise_no_new_item(tmp_path: Any, profile: Any) -> None:
    """A gap in the equity sum (in a filing, often a row no line takes, such as an employee benefit trust) makes the
    sum fail; a confirm-only check raises nothing for it."""
    rows = [r if r[0] != "Retained earnings" else ("Retained earnings", "140", "110") for r in BS]
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", ["December 31, 2025", "December 31, 2024"], rows)
    _, view = svc.upload("bs.htm", html.encode(), "tester")
    check = next(c for c in view.spread.checks if c.id == "bs_equity_components" and c.period == "2025-12-31/I")
    assert check.status is CheckStatus.FAIL
    assert not any(i.id.startswith("check:bs_equity_components") for i in view.spread.review)


@pytest.mark.parametrize("label", ["Equity in net undistributed earnings of subsidiaries",
                                   "Capital contributions to subsidiaries",
                                   "Equity in undistributed net income of bank subsidiary"])
def test_parent_only_rows(label: str) -> None:
    assert _PARENT_ROWS.search(label)


def test_ordinary_rows_are_not_parent_only() -> None:
    for label in ("Net income", "Capital expenditures", "Contributions from noncontrolling interests"):
        assert not _PARENT_ROWS.search(label)


def _v(line: str, value: str = "1") -> SpreadValue:
    return SpreadValue(line=line, period=P, value=Decimal(value), status=ValueStatus.EXTRACTED)


def _unconfirmed(profile: Any, checks: list[CheckResult], echoes: list[Echo] | None = None,
                 confirmations: list[Confirmation] | None = None) -> set[str]:
    return {ln for it in unconfirmed_items([_v("debt_repaid")], checks, [], profile, 2, echoes, confirmations)
            for ln in it.lines}


SUM = CheckResult(id="cf_financing_parts", title="t", period=P, status=CheckStatus.PASS, lines=["cff", "debt_repaid"])
OTHER_SUM = CheckResult(id="is_costs_parts", title="t", period=P, status=CheckStatus.PASS, lines=["debt_repaid"])
REGULAR = CheckResult(id="cf_sum", title="t", period=P, status=CheckStatus.PASS, lines=["debt_repaid"])
ECHO = Echo(line="debt_repaid", period=P, value=Decimal(1), label="repayment of funding agreements",
            ref=SourceRef(doc_id="d", format=SourceFormat.HTML, table=1, row=1, text="1"))


def test_a_sum_and_a_repeated_number_do_not_confirm_a_line(profile: Any) -> None:
    """Horace Mann's senior-note repayment sat in "other financing" and its funding-agreement repayment on debt repaid:
    the financing sum held and the amount was printed twice, so both agreed with the wrong line (found on the holdout)."""
    assert _unconfirmed(profile, [SUM], [ECHO]) == {"debt_repaid"}


def test_two_sums_count_once(profile: Any) -> None:
    assert _unconfirmed(profile, [SUM, OTHER_SUM]) == {"debt_repaid"}, "overlapping sums are one piece of evidence"


@pytest.mark.parametrize("source", ["prior", "label"])
def test_a_sum_counts_beside_evidence_about_the_line(profile: Any, source: str) -> None:
    other = Confirmation(line="debt_repaid", period=P, value=Decimal(1), source=source, detail="d")
    assert _unconfirmed(profile, [SUM], None, [other]) == set()


def test_a_sum_counts_beside_a_regular_check(profile: Any) -> None:
    assert _unconfirmed(profile, [SUM, REGULAR]) == set()


def _key(shares: str, eps: str = "11.95", net: str = "8563000000") -> AnswerKey:
    tv = [TruthValue(statement="income_statement", line=ln, period=P, value=Decimal(v), precision=Decimal("0.1"))
          for ln, v in (("shares_diluted", shares), ("eps_diluted", eps), ("net_income_parent", net))]
    return AnswerKey(document="d", source="s", spread=tv)


def test_a_share_count_tagged_without_its_scale_is_rescaled() -> None:
    """McDonald's tags "716.4" diluted shares, printed in millions, at scale 0: 11.95 x 716.4 is a millionth of net income."""
    key = _key("716.4")
    _rescale_untagged_shares(key)
    assert key.spread[0].value == Decimal("716400000.0") and key.spread[0].precision == Decimal(100000)


@pytest.mark.parametrize("shares", ["716400000", "716.4e3"])
def test_a_rightly_scaled_or_unexplained_count_is_left_alone(shares: str) -> None:
    key = _key(shares, net="8563000000" if shares == "716400000" else "1")
    _rescale_untagged_shares(key)
    assert key.spread[0].value == Decimal(shares)


@pytest.mark.parametrize("line", ["other_opex", "other_current_assets", "cf_other_financing", "cf_other_investing",
                                  "cf_other_noncash"])
def test_catch_alls_are_known_by_their_name_wherever_other_sits(line: str) -> None:
    assert is_catch_all(line)


@pytest.mark.parametrize("line", ["debt_repaid", "capex", "other", "total_opex"])
def test_named_lines_are_not_catch_alls(line: str) -> None:
    assert not is_catch_all(line)


def test_a_label_record_never_confirms_a_cash_flow_catch_all(profile: Any) -> None:
    row = StatementRow(index=4, label="Other, net", label_clean="other net", values={})
    table = StatementTable.model_construct(doc_id="d", table_index=0, statement=StatementType.CASH_FLOW, title="t",
                                           periods=[Period.model_construct(key=P)],
                                           scale=Scale.model_construct(multiplier=1000), rows=[row])
    st = {"cash_flow": StatementResult(table=table, mappings=[RowMapping(row_index=4, canonical="cf_other_financing",
                                                                         confidence=1.0, method="alias")])}
    v = SpreadValue(line="cf_other_financing", period=P, value=Decimal(5000), status=ValueStatus.EXTRACTED, source_rows=[4])
    rec = LabelRecord()
    for i in range(9):
        rec.add(("cash_flow", "other net", "cf_other_financing"), f"doc{i}", True)
    assert find_confirmations("d", st, [v], profile, None, rec) == []
