"""Remembering each company across years (spreader.company): confirmed mappings, approved values, comparisons."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any

import pytest

from conftest import client_as, statement_html
from spreader.company import (
    ApprovedValue,
    CompanyContext,
    compare_with_approved,
    confirmed_mappings,
    detect_company_id,
)
from spreader.contracts import ReviewKind
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.service import ActionError, Service
from spreader.store import Store

BS = [("Cash and cash equivalents", "100", "80"), ("Accounts receivable, net", "50", "40"),
      ("Total current assets", "150", "120"), ("Property, plant and equipment, net", "250", "220"),
      ("Total assets", "400", "340"), ("Accounts payable", "60", "50"), ("Total current liabilities", "60", "50"),
      ("Long-term debt", "140", "130"), ("Total liabilities", "200", "180"), ("Retained earnings", "200", "160"),
      ("Total stockholders' equity", "200", "160"), ("Total liabilities and stockholders' equity", "400", "340")]


def _bs(head: list[str], rows: list[tuple] = BS, title: str = "CONSOLIDATED BALANCE SHEETS") -> bytes:
    return statement_html(title, "(In thousands)", head, rows).encode()


def _spread(data: bytes, profile: Any, ctx: CompanyContext | None = None) -> Any:
    return spread_document(read_document("bs.htm", data), profile, company=ctx)[0]


def _ctx(**values: str) -> CompanyContext:
    """Approved values for 2025-12-31 (thousands), line -> value."""
    return CompanyContext("acme", approved={("2025-12-31/I", ln): ApprovedValue("2025-12-31/I", ln, Decimal(v) * 1000, Decimal(500))
                                            for ln, v in values.items()})


def _prior(profile: Any, ctx: CompanyContext, rows: list[tuple] = BS, title: str = "CONSOLIDATED BALANCE SHEETS") -> list[Any]:
    spread = _spread(_bs(["December 31, 2026", "December 31, 2025"], rows, title), profile)
    return compare_with_approved(spread, ctx, profile, " ".join(p.label for r in spread.statements.values() for p in r.table.periods))


# -- the comparison --------------------------------------------------------------------------------------------------

def test_matching_values_raise_nothing(profile: Any) -> None:
    assert _prior(profile, _ctx(cash="80", receivables="40", total_assets="340")) == []


def test_a_power_of_ten_is_called_a_misread(profile: Any) -> None:
    (item,) = _prior(profile, _ctx(cash="80000"))
    assert item.kind is ReviewKind.PRIOR_PERIOD and "likely a misread" in item.message.lower() and "10^-3" in item.message
    assert "approved spread is not changed" in item.message


def test_a_flipped_sign_is_called_a_misread(profile: Any) -> None:
    (item,) = _prior(profile, _ctx(cash="-80"))
    assert "sign is flipped" in item.message


def test_an_amount_moved_between_lines_with_the_same_total_is_a_reclassification(profile: Any) -> None:
    items = _prior(profile, _ctx(cash="70", receivables="50", total_current_assets="120"))
    assert {i.lines[0] for i in items} == {"cash", "receivables"}
    assert all("reclassification" in i.message for i in items)


def test_columns_headed_as_restated_point_to_a_restatement(profile: Any) -> None:
    ctx = _ctx(lt_debt="125")
    spread = _spread(_bs(["December 31, 2026", "December 31, 2025 (As Restated)"]), profile)
    (item,) = compare_with_approved(spread, ctx, profile, " ".join(p.label for p in spread.periods))
    assert "restatement by the company" in item.message


def test_otherwise_the_item_says_it_cannot_tell(profile: Any) -> None:
    (item,) = _prior(profile, _ctx(lt_debt="125"))
    assert "restatement or misread" in item.message.lower() and "check the document" in item.message


def test_the_comparison_never_changes_the_approved_values(profile: Any) -> None:
    ctx = _ctx(cash="80000")
    before = dict(ctx.approved)
    _prior(profile, ctx)
    assert ctx.approved == before


# -- confirmed mappings ---------------------------------------------------------------------------------------------

def test_rows_behind_a_corrected_line_are_not_remembered(profile: Any) -> None:
    """Regression (company-memory-dev-remembered-corrected-rows): a corrected total's rows were remembered and reused
    the next year, unflagged, so three wrong values went silent."""
    spread = _spread(_bs(["December 31, 2025", "December 31, 2024"]), profile)
    every = confirmed_mappings(spread)
    assert ("balance_sheet", "cash and cash equivalents", "") in every
    kept = confirmed_mappings(spread, corrected_lines={"cash"})
    assert all(line != "cash" for line in kept.values()) and len(kept) == len(every) - 1


def test_the_company_s_confirmed_mapping_comes_first_and_is_calibrated(profile: Any) -> None:
    from finops.core import policy

    ctx = CompanyContext("acme", mappings={("balance_sheet", "accounts payable", ""): "accrued_liabilities"})
    spread = _spread(_bs(["December 31, 2026", "December 31, 2025"]), profile, ctx)
    m = next(m for r in spread.statements.values() for m in r.mappings if m.rule == "memory.company")
    assert m.canonical == "accrued_liabilities"
    assert m.confidence == pytest.approx(policy.load("statements").confidence("memory.company") or 0.0, abs=1e-4)


def test_cik_is_read_from_the_cover_page_tag() -> None:
    tag = b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="c-1">0000320193</ix:nonNumeric>'
    assert detect_company_id(b"<html>" + tag + b"</html>") == "cik:320193"
    assert detect_company_id(b"<html>no tag</html>") is None


# -- the service ----------------------------------------------------------------------------------------------------

@pytest.fixture()
def svc(tmp_path: Any, profile: Any) -> Service:
    return Service(Store(tmp_path / "db.sqlite3"), profile=profile)


def test_approval_is_remembered_compared_next_year_and_never_rewritten(svc: Service) -> None:
    _, last_year = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana", company_id="acme")
    svc.act(last_year.run["id"], {"type": "approve"}, "dana")
    assert svc.store.query("SELECT COUNT(*) AS n FROM approved_values WHERE company_id='acme'")[0]["n"] > 0
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), svc.store.tx() as c:
        c.execute("UPDATE approved_values SET value='1'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), svc.store.tx() as c:
        c.execute("DELETE FROM company_mappings")

    # This year's filing prints 2025 again (last year's first column), with cash at 85 instead of 100: one item.
    rows = [(label, str(int(v2025) + 10), "85" if label.startswith("Cash") else v2025) for label, v2025, _ in BS]
    _, this_year = svc.upload("2026.htm", _bs(["December 31, 2026", "December 31, 2025"], rows), "dana", company_id="acme")
    prior = [i for i in this_year.spread.review if i.kind is ReviewKind.PRIOR_PERIOD]
    assert [(i.lines, i.periods) for i in prior] == [(["cash"], ["2025-12-31/I"])]
    assert "dana" in prior[0].message
    assert any(m.rule == "memory.company" for r in this_year.spread.statements.values() for m in r.mappings)

    # A correction still sees the item (the review is rebuilt after every action).
    after = svc.act(this_year.run["id"], {"type": "correct_value", "line": "cash", "period": "2025-12-31/I",
                                          "value": "80000", "reason": "read the wrong row"}, "dana")
    item = next(i for i in after.spread.review if i.kind is ReviewKind.PRIOR_PERIOD)
    assert item.resolved  # every value it concerns was corrected by a reviewer

    # Reopening last year's spread withdraws its approval: a new run of this year compares with nothing.
    svc.act(last_year.run["id"], {"type": "reopen"}, "dana")
    again = svc.run(this_year.run["document_id"], "dana")
    assert again.run["id"] != this_year.run["id"]
    assert not any(i.kind is ReviewKind.PRIOR_PERIOD for i in again.spread.review)
    assert svc.store.query("SELECT COUNT(*) AS n FROM approved_values WHERE company_id='acme'")[0]["n"] > 0  # kept


def test_documents_of_other_companies_are_never_compared(svc: Service) -> None:
    _, a = svc.upload("a.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana", company_id="acme")
    svc.act(a.run["id"], {"type": "approve"}, "dana")
    rows = [("Cash and cash equivalents", "120", "85"), *BS[1:]]
    _, b = svc.upload("b.htm", _bs(["December 31, 2026", "December 31, 2025"], rows), "dana", company_id="globex")
    assert not any(i.kind is ReviewKind.PRIOR_PERIOD for i in b.spread.review)


def test_a_company_set_after_upload_brings_last_year_s_approval_in(svc: Service) -> None:
    _, last_year = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana", company_id="acme")
    svc.act(last_year.run["id"], {"type": "approve"}, "dana")
    rows = [(label, str(int(v2025) + 10), "85" if label.startswith("Cash") else v2025) for label, v2025, _ in BS]
    _, this_year = svc.upload("2026.htm", _bs(["December 31, 2026", "December 31, 2025"], rows), "dana")
    assert not any(i.kind is ReviewKind.PRIOR_PERIOD for i in this_year.spread.review)  # no company yet: nothing to compare

    again = svc.set_company(this_year.run["document_id"], "acme", "dana")
    assert again.run["id"] != this_year.run["id"]
    assert [i.lines for i in again.spread.review if i.kind is ReviewKind.PRIOR_PERIOD] == [["cash"]]
    assert [c["company_id"] for c in svc.companies()] == ["acme"]
    assert svc.companies()[0]["documents"] == 2 and svc.companies()[0]["approved_spreads"] == 1


def test_an_approved_document_keeps_its_company(svc: Service) -> None:
    _, run = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana", company_id="acme")
    svc.act(run.run["id"], {"type": "approve"}, "dana")
    with pytest.raises(ActionError, match="reopen it"):
        svc.set_company(run.run["document_id"], "globex", "dana")
    with pytest.raises(ActionError, match="needs a name"):
        svc.set_company(run.run["document_id"], "  ", "dana")


def test_the_upload_route_takes_a_company_id(tmp_path: Any, profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:

    from spreader import api

    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    monkeypatch.setattr(api, "service", lambda: svc)
    r = client_as(api.app, "dana").post("/api/documents", files={"file": ("a.htm", _bs(["December 31, 2025", "December 31, 2024"]))},
                                 data={"company_id": "acme"})
    assert r.status_code == 200
    assert svc.store.query("SELECT company_id FROM documents")[0]["company_id"] == "acme"
