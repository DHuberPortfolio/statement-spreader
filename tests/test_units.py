"""Each statement's unit and currency, from evidence, through the uncertainty policy (spreader.units, D39)."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import statement_html
from finops.core import policy
from spreader import units
from spreader.contracts import ReviewKind, Severity
from spreader.detect import detect_scale, document_unit_statements
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from test_company import BS
from test_redteam import HEAD, IS


def _body(html: str) -> str:
    return html.split("<body>", 1)[1].rsplit("</body>", 1)[0]


def _doc(*parts: str) -> bytes:
    return ("<html><body>" + "".join(parts) + "</body></html>").encode()


def _is(unit: str = "") -> str:
    return _body(statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", unit, HEAD, IS))


def _bs(unit: str = "") -> str:
    return _body(statement_html("CONSOLIDATED BALANCE SHEETS", unit, ["December 31, 2025", "December 31, 2024"], BS))


def _cal(**methods: tuple[int, int]) -> policy.Calibration:
    return policy.fit("units", "a statement's unit", [(m, i < right, "test") for m, (right, total) in methods.items()
                                                      for i in range(total)])


@pytest.fixture()
def trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every rule measured right 60 of 60 times (lower bound about 94%)."""
    cal = _cal(**{r: (60, 60) for r in ("scale.table", "scale.document", "scale.sibling",
                                        "scale.none")})
    monkeypatch.setattr(units.policy, "load", lambda engine: cal)


def _spread(data: bytes, profile: Any) -> Any:
    return spread_document(read_document("u.htm", data), profile)[0]


def test_a_unit_stated_once_for_the_document_is_used(profile: Any, trusted: None) -> None:
    """Deere prints "All amounts are presented in millions of U.S. dollars" once, in its notes, and nothing at its
    statements."""
    data = _doc(_is(), _bs(), "<p>Note 1. All amounts are presented in millions of U.S. dollars unless otherwise noted.</p>")
    sp = _spread(data, profile)
    for res in sp.statements.values():
        s = res.table.scale
        assert (s.multiplier, s.rule, s.assumed, s.currency) == (1_000_000, "scale.document", False, "USD")
    assert not any(i.kind is ReviewKind.ASSUMED_SCALE for i in sp.review)


def test_the_other_statements_unit_is_used_when_this_one_prints_none(profile: Any, trusted: None) -> None:
    sp = _spread(_doc(_is("(In thousands, except per share amounts)"), _bs()), profile)
    bs = sp.statements["balance_sheet"].table.scale
    assert (bs.multiplier, bs.rule, bs.assumed) == (1_000, "scale.sibling", False)


def test_a_rule_below_the_bar_keeps_its_guess_and_asks(profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    cal = _cal(**{"scale.table": (60, 60), "scale.sibling": (3, 3)})  # 3 of 3 right: at least 44%, under 80%
    monkeypatch.setattr(units.policy, "load", lambda engine: cal)
    sp = _spread(_doc(_is("(In thousands, except per share amounts)"), _bs()), profile)
    bs = sp.statements["balance_sheet"].table.scale
    assert (bs.multiplier, bs.rule, bs.assumed) == (1_000, "scale.sibling", True)
    item = next(i for i in sp.review if i.kind is ReviewKind.ASSUMED_SCALE)
    assert item.severity is Severity.BLOCKER and "Best guess: thousands" in item.message and "3 of 3" in item.message
    assert sp.value("total_assets", "2025-12-31/I").value == 400_000  # the guess is applied, and flagged
    assert "scale:balance_sheet" in sp.value("total_assets", "2025-12-31/I").flags


def test_no_evidence_is_never_accepted_however_it_measured(profile: Any, trusted: None) -> None:
    sp = _spread(_doc(_is(), _bs()), profile)
    for res in sp.statements.values():
        assert res.table.scale.rule == "scale.none" and res.table.scale.assumed


def test_document_and_statements_disagreeing_is_a_conflict(profile: Any, trusted: None) -> None:
    data = _doc(_is("(In thousands, except per share amounts)"), _bs(), "<p>Note 1. All amounts are in millions.</p>")
    bs = _spread(data, profile).statements["balance_sheet"].table.scale
    assert bs.rule == "scale.conflict" and bs.assumed and "doubtful" in bs.evidence


def test_an_uncalibrated_rule_fails_closed(profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(units.policy, "load", lambda engine: policy.Calibration(engine="units", unit="none"))
    sp = _spread(_doc(_is("(In millions)")), profile)
    assert sp.statements["income_statement"].table.scale.assumed


def test_new_unit_wordings() -> None:
    money, shares = detect_scale(["(Dollars and Shares in Millions Except Per Share Amounts)"])
    assert money.multiplier == 1_000_000 and not money.assumed
    assert detect_scale(["(EUR millions)"])[0].multiplier == 1_000_000
    assert detect_scale(["(€ in thousands)"])[0].multiplier == 1_000


def test_document_unit_statements_are_only_whole_document_claims() -> None:
    assert document_unit_statements("Unless otherwise indicated, all dollar amounts are in thousands.")
    assert not document_unit_statements("The table below (in millions) shows our revenue by segment.")


def test_a_foreign_currency_is_shown_not_converted(profile: Any, trusted: None) -> None:
    sp = _spread(_doc(_is("(EUR millions, except per share amounts)")), profile)
    s = sp.statements["income_statement"].table.scale
    assert (s.currency, s.multiplier) == ("EUR", 1_000_000)
    item = next(i for i in sp.review if i.kind is ReviewKind.CURRENCY)
    assert item.severity is Severity.WARNING and "nothing is converted" in item.message


def test_statements_in_different_currencies_block_approval(profile: Any, trusted: None) -> None:
    sp = _spread(_doc(_is("(EUR millions, except per share amounts)"), _bs("(In millions of U.S. dollars)")), profile)
    item = next(i for i in sp.review if i.kind is ReviewKind.CURRENCY)
    assert item.severity is Severity.BLOCKER


def test_a_dollar_sign_in_the_cells_reads_as_usd(profile: Any, trusted: None) -> None:
    sp = _spread(_doc(_is("(In millions)")), profile)  # statement_html prints "$" in its own cells
    s = sp.statements["income_statement"].table.scale
    assert s.currency == "USD" and "'$'" in s.currency_evidence
    assert not any(i.kind is ReviewKind.CURRENCY and i.severity is not Severity.INFO for i in sp.review)
