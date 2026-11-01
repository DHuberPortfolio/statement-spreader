"""Confirmations from approved work: the company's approved spread, and a label's record across documents (D61)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from finops.core.outcomes import Outcome
from spreader.company import ApprovedValue, CompanyContext
from spreader.confirm import LabelRecord, find_confirmations, record_docs_required, record_from_outcomes
from spreader.contracts import (
    CheckResult,
    CheckStatus,
    Confirmation,
    Period,
    RowMapping,
    Scale,
    SpreadValue,
    StatementResult,
    StatementRow,
    StatementTable,
    StatementType,
    ValueStatus,
)
from spreader.review import unconfirmed_items

P = "2025-12-31/12M"


def _statements(label: str = "Income tax expense") -> dict[str, StatementResult]:
    row = StatementRow(index=4, label=label, label_clean=label.lower(), values={})
    table = StatementTable.model_construct(doc_id="d", table_index=0, statement=StatementType.INCOME, title="t",
                                           periods=[Period.model_construct(key=P)], scale=Scale.model_construct(multiplier=1000),
                                           rows=[row])
    return {"income_statement": StatementResult(table=table, mappings=[RowMapping(row_index=4, canonical="income_tax",
                                                                                   confidence=1.0, method="alias")])}


def _v(value: str = "404000") -> SpreadValue:
    return SpreadValue(line="income_tax", period=P, value=Decimal(value), status=ValueStatus.EXTRACTED, source_rows=[4])


def _company(value: str) -> CompanyContext:
    return CompanyContext(company_id="cik:1", approved={(P, "income_tax"): ApprovedValue(
        P, "income_tax", Decimal(value), Decimal(500), 7, "last year's 10-K", "Rae Analyst", "2025-03-01T10:00:00")})


def test_a_value_equal_to_the_approved_spread_is_confirmed_by_it(profile: Any) -> None:
    got = find_confirmations("d", _statements(), [_v()], profile, _company("404000"))
    assert [c.source for c in got] == ["prior"] and "Rae Analyst, 2025-03-01" in got[0].detail
    # rounding: half a thousand from this year's print plus the 500 the approved value carries
    assert find_confirmations("d", _statements(), [_v()], profile, _company("405200")) == [], "beyond rounding"
    assert [c.source for c in find_confirmations("d", _statements(), [_v()], profile, _company("404900"))] == ["prior"]


def _record(right_docs: int, wrong_docs: int = 0, label: str = "income tax expense") -> LabelRecord:
    rec = LabelRecord()
    for i in range(right_docs):
        rec.add(("income_statement", label, "income_tax"), f"doc{i}", True)
    for i in range(wrong_docs):
        rec.add(("income_statement", label, "income_tax"), f"bad{i}", False)
    return rec


def test_a_label_approved_in_enough_other_documents_confirms_the_line(profile: Any) -> None:
    assert [c.source for c in find_confirmations("d", _statements(), [_v()], profile, None, _record(7))] == ["label"]
    assert find_confirmations("d", _statements(), [_v()], profile, None, _record(6)) == [], "too few documents"
    assert find_confirmations("d", _statements(), [_v()], profile, None, _record(9, wrong_docs=1)) == [], "moved once"


def test_a_label_record_never_confirms_a_catch_all_line(profile: Any) -> None:
    """Found on the holdout: Old Dominion's other current assets and YETI's other non-operating income went out wrong
    under labels with a perfect record; the line collected different rows from the ones it should."""
    st = _statements("Other income, net")
    st["income_statement"].mappings[0].canonical = "other_nonoperating"
    v = SpreadValue(line="other_nonoperating", period=P, value=Decimal(125000), status=ValueStatus.EXTRACTED, source_rows=[4])
    rec = LabelRecord()
    for i in range(9):
        rec.add(("income_statement", "other income, net", "other_nonoperating"), f"doc{i}", True)
    assert find_confirmations("d", st, [v], profile, None, rec) == []


def test_a_document_never_counts_toward_its_own_record() -> None:
    rec = _record(7)
    key = ("income_statement", "income tax expense", "income_tax")
    assert rec.vouches(key, "elsewhere", 7) == 7
    assert rec.vouches(key, "doc0", 7) == 0, "only six other documents"


def test_prior_or_label_count_beside_a_check_but_not_alone(profile: Any) -> None:
    checks = [CheckResult(id="is_net", title="t", period=P, status=CheckStatus.PASS,
                          lines=["net_income", "pretax_income", "income_tax"])]
    prior = Confirmation(line="income_tax", period=P, value=Decimal(404000), source="prior", detail="d")
    assert unconfirmed_items([_v()], checks, [], profile, 2, [], [prior]) == []
    assert unconfirmed_items([_v()], [], [], profile, 2, [], [prior]), "no check: still reviewed"
    changed = _v("405000")
    assert unconfirmed_items([changed], checks, [], profile, 2, [], [prior]), "the value changed since"


def test_the_record_is_built_from_reviewer_outcomes_with_their_labels() -> None:
    def o(doc: str, right: bool) -> Outcome:
        return Outcome(engine="statements", method="alias.exact", right=right, how="approved_unchanged", subject="s",
                       decided_by="r", decided_at="t", refs={"document": doc, "statement": "income_statement",
                                                             "line": "income_tax", "label": "income tax expense"})
    rec = record_from_outcomes([o("a", True), o("b", True), o("c", False)])
    key = ("income_statement", "income tax expense", "income_tax")
    assert rec.right[key] == {"a", "b"} and rec.wrong[key] == {"c"}


def test_approval_outcomes_carry_the_rows_label(profile: Any) -> None:
    from spreader.contracts import Spread
    from spreader.learning import approval_outcomes

    spread = Spread(doc_id="d", profile_id="p", profile_version="v", statements=_statements())
    out = approval_outcomes(spread, {}, {"document": "d"}, "rae", "now", profile.line_statement)
    assert any(x.refs.get("label") == "income tax expense" for x in out if x.engine == "statements")


def test_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert record_docs_required() == 7
    monkeypatch.setenv("SPREADER_LABEL_RECORD_DOCS", "seven")
    with pytest.raises(ValueError, match="SPREADER_LABEL_RECORD_DOCS"):
        record_docs_required()
