"""The service's promises: idempotent runs, no partial runs, the approval gate, audited changes."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from conftest import statement_html
from openpyxl import load_workbook

from spreader.export import to_csv, to_xlsx
from spreader.service import ActionError, Service
from spreader.store import Store

BS = [
    ("Current assets:",),
    ("  Cash and cash equivalents", "100", "80"),
    ("  Accounts receivable, net", "50", "40"),
    ("Total current assets", "150", "120"),
    ("Property, plant and equipment, net", "250", "220"),
    ("Total assets", "400", "340"),
    ("Accounts payable", "60", "50"),
    ("Total current liabilities", "60", "50"),
    ("Long-term debt", "140", "130"),
    ("Total liabilities", "200", "180"),
    ("Retained earnings", "200", "160"),
    ("Total stockholders' equity", "200", "160"),
    ("Total liabilities and stockholders' equity", "400", "340"),
]
HEAD = ["December 31, 2025", "December 31, 2024"]


@pytest.fixture()
def svc(tmp_path, profile) -> Service:  # type: ignore[no-untyped-def]
    return Service(Store(tmp_path / "db.sqlite3"), profile=profile)


def _upload(svc: Service, unit: str = "(In thousands)", rows=BS):  # type: ignore[no-untyped-def]
    html = statement_html("CONSOLIDATED BALANCE SHEETS", unit, HEAD, rows).encode()
    return svc.upload("bs.htm", html, "tester")


def test_same_file_twice_is_one_document_and_one_run(svc: Service) -> None:
    _, a = _upload(svc)
    _, b = _upload(svc)
    assert a.run["id"] == b.run["id"]
    assert len(svc.store.query("SELECT * FROM runs")) == 1
    assert len(svc.store.query("SELECT * FROM documents")) == 1


def test_unsupported_file_is_refused_cleanly(svc: Service) -> None:
    with pytest.raises(ActionError):
        svc.upload("x.txt", b"just some text", "tester")
    assert svc.store.query("SELECT * FROM runs") == []


def test_failed_run_is_recorded_not_half_written(svc: Service, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import spreader.service as service_mod

    def boom(*a, **k):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated crash in the middle of a run")

    monkeypatch.setattr(service_mod, "spread_document", boom)
    _, view = _upload(svc)
    assert view.run["status"] == "failed" and view.spread is None
    assert "simulated" not in (view.run["error"] or "")  # the internal message is not leaked
    monkeypatch.undo()
    retry = svc.run(view.run["document_id"], "tester")
    assert retry.run["status"] == "succeeded" and retry.run["id"] != view.run["id"]


def test_approval_is_refused_while_a_blocker_is_open(svc: Service) -> None:
    _, view = _upload(svc, unit="")  # no unit statement -> assumed scale blocker
    rid = view.run["id"]
    with pytest.raises(ActionError, match="blocking"):
        svc.act(rid, {"type": "approve"}, "tester")
    item = next(i for i in view.spread.review if i.kind.value == "assumed_scale")
    with pytest.raises(ActionError, match="confirm"):
        svc.act(rid, {"type": "resolve_item", "item": item.id, "note": "looks fine"}, "tester")
    svc.act(rid, {"type": "resolve_item", "item": item.id, "note": "I confirm the statement is in whole dollars"}, "tester")
    approved = svc.act(rid, {"type": "approve"}, "tester")
    assert approved.run["state"]["approved"]["by"] == "tester"
    with pytest.raises(ActionError, match="approved"):
        svc.act(rid, {"type": "correct_value", "line": "cash", "period": "2025-12-31/I", "value": "1", "reason": "x"}, "tester")


def test_correction_recomputes_checks_and_is_audited(svc: Service) -> None:
    _, view = _upload(svc)
    rid = view.run["id"]
    assert all(c.status.value != "fail" for c in view.spread.checks)
    with pytest.raises(ActionError, match="reason"):
        svc.act(rid, {"type": "correct_value", "line": "cash", "period": "2025-12-31/I", "value": "101"}, "tester")
    after = svc.act(rid, {"type": "correct_value", "line": "cash", "period": "2025-12-31/I", "value": "110,000",
                          "reason": "typo in source"}, "tester")
    cash = after.spread.value("cash", "2025-12-31/I")
    assert cash.value == Decimal(110000) and cash.status.value == "human"
    failed = {c.id for c in after.spread.checks if c.status.value == "fail"}
    assert "bs_current_assets" in failed  # the correction now contradicts the printed total, and says so
    kinds = [e["kind"] for e in svc.events(rid)]
    assert "correct_value" in kinds


def test_remap_creates_a_new_run_and_logs_the_carry_over(svc: Service) -> None:
    _, view = _upload(svc)
    rid = view.run["id"]
    svc.act(rid, {"type": "correct_value", "line": "cash", "period": "2024-12-31/I", "value": "80000",
                  "reason": "checked"}, "tester")
    row = next(r for r in view.spread.statements["balance_sheet"].table.rows if r.label == "Long-term debt")
    new = svc.act(rid, {"type": "remap_row", "statement": "balance_sheet", "row": row.index,
                        "line": "other_noncurrent_liabilities"}, "tester")
    assert new.run["id"] != rid and new.run["parent_run"] == rid
    assert new.spread.value("lt_debt", "2025-12-31/I") is None
    assert new.spread.value("other_noncurrent_liabilities", "2025-12-31/I").value == Decimal(140000)
    assert "carry_over" in [e["kind"] for e in svc.events(new.run["id"])]
    with pytest.raises(ActionError):
        svc.act(rid, {"type": "remap_row", "statement": "balance_sheet", "row": row.index, "line": "revenue"}, "tester")


def test_exports_never_contain_live_formulas(svc: Service, profile) -> None:  # type: ignore[no-untyped-def]
    rows = list(BS) + [("=HYPERLINK(\"http://evil.example\",\"click\")", "1", "1")]
    _, view = _upload(svc, rows=rows)
    meta = {"run_id": view.run["id"], "filename": "bs.htm", "approved": None, "exported_at": "now"}
    wb = load_workbook(io.BytesIO(to_xlsx(view.spread, profile, meta)))
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                assert cell.data_type != "f", f"formula in {ws.title}!{cell.coordinate}"
    text = to_csv(view.spread, profile).decode()
    assert ",=" not in text
