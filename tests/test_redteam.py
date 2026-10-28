"""Regression tests for the red-team findings (each one reproduced first; see THREAT_MODEL.md)."""

from __future__ import annotations

import io
import time
from decimal import Decimal

import pytest
from openpyxl import Workbook

from conftest import client_as, statement_html
from spreader import api, roi
from spreader.ingest import read_document
from spreader.numbers import clean_label, parse_amount
from spreader.pipeline import spread_document
from spreader.service import ActionError, Service
from spreader.store import Store

IS = [("Revenue", "400", "250"), ("Cost of sales", "150", "100"), ("Gross profit", "250", "150"),
      ("Selling, general and administrative", "80", "60"), ("Operating income", "170", "90"),
      ("Provision for income taxes", "50", "25"), ("Net income", "120", "65")]
FAKE = [("Revenue", "500", "300"), ("Cost of sales", "150", "100"), ("Gross profit", "350", "200"),
        ("Selling, general and administrative", "80", "60"), ("Operating income", "270", "140"),
        ("Provision for income taxes", "50", "25"), ("Net income", "220", "115")]
HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]


def _table(rows: list[tuple], attrs: str = "") -> str:
    html = statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, rows)
    return html.replace("<table>", f"<table {attrs}>", 1).replace("<html><body>", "").replace("</body></html>", "")


@pytest.mark.parametrize("hide", [
    'class="x"', 'style="display:/**/none"', 'style="font-size:0"', 'style="position:absolute;left:-9999px"',
    'style="opacity:0"'])
def test_hidden_fake_statement_is_ignored(profile, hide: str) -> None:  # type: ignore[no-untyped-def]
    html = ("<html><head><style>.x { display: none }</style></head><body>" + _table(FAKE, hide) + _table(IS)
            + "</body></html>")
    sp, _ = spread_document(read_document("h.htm", html.encode()), profile)
    assert sp.value("revenue", "2025-12-31/12M").value == Decimal(400_000)


def test_restated_and_budget_columns(profile) -> None:  # type: ignore[no-untyped-def]
    html = statement_html("STATEMENTS OF OPERATIONS", "(In thousands)",
                          ["Budget 2025", "Year Ended December 31, 2025", "Year Ended December 31, 2024"],
                          [(r[0], "999", r[1], r[2]) for r in IS])
    sp, _ = spread_document(read_document("b.htm", html.encode()), profile)
    assert sp.value("revenue", "2025-12-31/12M").value == Decimal(400_000)


def test_duplicate_period_columns_are_a_blocker(profile) -> None:  # type: ignore[no-untyped-def]
    html = statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", ["Year Ended December 31, 2025",
                          "Year Ended December 31, 2025"], [(r[0], r[1], r[2]) for r in IS])
    sp, _ = spread_document(read_document("d.htm", html.encode()), profile)
    assert any(i.id.startswith("dup_period:") and i.severity.value == "blocker" for i in sp.review)
    assert sp.value("revenue", "2025-12-31/12M").flags


def test_pro_forma_table_does_not_win(profile) -> None:  # type: ignore[no-untyped-def]
    fake = statement_html("UNAUDITED PRO FORMA STATEMENTS OF OPERATIONS", "(In thousands)", HEAD,
                          FAKE + [("Research and development", "10", "10")])
    real = statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, IS)
    sp, _ = spread_document(read_document("p.htm", (fake + real).encode()), profile)
    assert sp.value("revenue", "2025-12-31/12M").value == Decimal(400_000)


def test_excel_hidden_column_range_and_hidden_format(profile) -> None:  # type: ignore[no-untyped-def]
    wb = Workbook()
    ws = wb.active
    ws.append(["Statements of operations"])
    ws.append(["(In thousands)"])
    ws.append([None, "Year Ended December 31, 2025", "FAKE", "FAKE", "Year Ended December 31, 2024"])
    for label, a, b in IS:
        ws.append([label, int(a), 999, 999, int(b)])
    ws.column_dimensions.group("C", "D", hidden=True)
    for row in ws.iter_rows(min_row=4, min_col=3, max_col=4):
        for cell in row:
            cell.number_format = ";;;"
    buf = io.BytesIO()
    wb.save(buf)
    sp, _ = spread_document(read_document("x.xlsx", buf.getvalue()), profile)
    assert sp.value("revenue", "2024-12-31/12M").value == Decimal(250_000)


def test_no_catastrophic_backtracking() -> None:
    t0 = time.perf_counter()
    clean_label("Revenue " + "*" * 40 + "x")
    parse_amount("1" * 5000)
    assert time.perf_counter() - t0 < 0.5


def test_span_bomb_is_refused_quickly(profile) -> None:  # type: ignore[no-untyped-def]
    cells = "".join('<td rowspan="50" colspan="50">1</td>' for _ in range(40))
    rows = "".join(f"<tr><td>Row {i}</td>{cells}</tr>" for i in range(60))
    t0 = time.perf_counter()
    with pytest.raises(Exception):  # noqa: B017 - no tables survive: an IngestError
        read_document("bomb.htm", f"<html><body><table>{rows}</table></body></html>".encode())
    assert time.perf_counter() - t0 < 10


def test_other_digit_scripts_are_refused() -> None:
    assert parse_amount("1,৪00")[0] is None


@pytest.fixture()
def client(tmp_path, profile):  # type: ignore[no-untyped-def]
    api.set_service(Service(Store(tmp_path / "db.sqlite3"), profile=profile))
    return client_as(api.app, "dana")


def test_cross_site_writes_and_foreign_hosts_are_refused(client) -> None:  # type: ignore[no-untyped-def]
    html = statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, IS).encode()
    rid = client.post("/api/documents", files={"file": ("a.htm", html, "text/html")}).json()["run"]["id"]
    body = '{"type": "approve"}'
    r = client.post(f"/api/runs/{rid}/actions", content=body, headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    r = client.post(f"/api/runs/{rid}/actions", content=body,
                    headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.get(f"/api/runs/{rid}", headers={"Host": "attacker.example"}).status_code == 400


def test_assumptions_must_be_finite(client) -> None:  # type: ignore[no-untyped-def]
    assert client.put("/api/roi/assumptions", json={"cash_realization_share": "0.5"}).status_code == 403  # not an admin
    assert client_as(api.app, "adm").put("/api/roi/assumptions", json={"cash_realization_share": "nan"}).status_code == 400


def test_roi_ignores_empty_sessions() -> None:
    s = [roi.Session("baseline", d, 1800) for d in "abc"] + [roi.Session("assisted", d, 0) for d in "abc"]
    a = {k: (v, "default") for k, (v, _) in roi.DEFAULT_ASSUMPTIONS.items()}
    rep = roi.compute(roi.RoiInputs(assumptions=a, sessions=s, compute_seconds=[]))
    assert rep.numbers["minutes_saved"].value is None


def test_resolution_reopens_when_its_numbers_change(tmp_path, profile) -> None:  # type: ignore[no-untyped-def]
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    rows = [r if r[0] != "Gross profit" else ("Gross profit", "252", "150") for r in IS]
    html = statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, rows).encode()
    _, view = svc.upload("g.htm", html, "t")
    rid = view.run["id"]
    item = next(i for i in view.spread.review if i.id.startswith("check:is_gross_profit:2025"))
    svc.act(rid, {"type": "resolve_item", "item": item.id, "note": "2 thousand rounding in the source"}, "t")
    view = svc.act(rid, {"type": "correct_value", "line": "revenue", "period": "2025-12-31/12M", "value": "40000000",
                         "reason": "test"}, "t")
    reopened = next(i for i in view.spread.review if i.id == item.id)
    assert not reopened.resolved
    with pytest.raises(ActionError):
        svc.act(rid, {"type": "approve"}, "t")
