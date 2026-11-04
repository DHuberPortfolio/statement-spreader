"""Review time is measured quietly, for management, and never shown to those it measures (D65)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import client_as

from spreader import api, roi_api
from spreader.service import Service
from spreader.store import Store

DOC = Path(__file__).resolve().parents[1] / "eval" / "synthetic" / "s7-001-clean" / "statement.html"


@pytest.fixture()
def svc(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> Service:
    s = Service(Store(tmp_path / "spreader.sqlite3"), profile=profile)
    monkeypatch.setattr(api, "service", lambda: s)
    return s


def _opened(svc: Service, who: Any) -> tuple[str, int]:
    """A document uploaded and opened by a reviewer, long enough ago that seconds can be added."""
    view = client_as(api.app, "ana").post("/api/documents", files={"file": ("a.htm", DOC.read_bytes())}).json()
    run = view["run"]["id"]
    assert who.post(f"/api/runs/{run}/activity", json={"active_seconds": 0}).json() == {}
    _age(svc)
    return view["run"]["document_id"], run


def _age(svc: Service) -> None:
    with svc.store.tx() as c:
        c.execute("UPDATE work_sessions SET started_at=?", ((datetime.now(UTC) - timedelta(hours=1)).isoformat(),))


def _sessions(svc: Service) -> list[Any]:
    return svc.store.query("SELECT * FROM work_sessions")


def test_reviewing_records_time_with_nothing_to_start(svc: Service) -> None:
    ana = client_as(api.app, "ana")
    _, run = _opened(svc, ana)
    for _ in range(2):
        assert ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 15}).json() == {}
    rows = _sessions(svc)
    assert len(rows) == 1 and rows[0]["active_seconds"] == 30 and rows[0]["background"] == 1 and rows[0]["ended_at"] is None


def test_one_report_cannot_add_more_than_a_heartbeat_or_the_clock(svc: Service) -> None:
    ana = client_as(api.app, "ana")
    _, run = _opened(svc, ana)
    ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 99999})
    assert _sessions(svc)[0]["active_seconds"] <= roi_api.MAX_HEARTBEAT_SECONDS
    with svc.store.tx() as c:
        c.execute("UPDATE work_sessions SET started_at=?", (datetime.now(UTC).isoformat(),))
    before = _sessions(svc)[0]["active_seconds"]
    ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 30})
    assert _sessions(svc)[0]["active_seconds"] == before


def test_approval_closes_the_time_and_only_then_it_counts(svc: Service) -> None:
    ana = client_as(api.app, "ana")
    doc, run = _opened(svc, ana)
    ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 20})
    mia = client_as(api.app, "mia")
    assert mia.get("/api/roi").json()["sessions"]["assisted"] == 0
    with svc.store.tx() as c:
        c.execute("UPDATE work_sessions SET ended_at=? WHERE document_id=?", (datetime.now(UTC).isoformat(), doc))
    assert mia.get("/api/roi").json()["sessions"]["assisted"] == 1


def test_the_approve_action_itself_ends_the_review(tmp_path: Path, profile: Any) -> None:
    from conftest import statement_html

    rows = [("Cash", "100", "80"), ("Total assets", "100", "80"), ("Total liabilities", "40", "30"),
            ("Total stockholders' equity", "60", "50"), ("Total liabilities and stockholders' equity", "100", "80")]
    svc = Service(Store(tmp_path / "s.sqlite3"), profile=profile)
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", ["December 31, 2025", "December 31, 2024"], rows)
    view = svc.upload("bs.htm", html.encode(), "tester")[1]
    with svc.store.tx() as c:
        c.execute("INSERT INTO work_sessions(document_id, run_id, mode, actor, started_at, background, active_seconds) "
                  "VALUES (?,?,?,?,?,1,60)", (view.run["document_id"], view.run["id"], "assisted", "dev:ana", "2026-01-01T00:00:00+00:00"))
    for item in view.spread.review:
        if item.severity.value == "blocker":
            svc.act(view.run["id"], {"type": "resolve_item", "item": item.id, "note": "Checked against the filing"}, "tester")
    svc.act(view.run["id"], {"type": "approve"}, "tester")
    assert svc.store.query("SELECT ended_at FROM work_sessions")[0]["ended_at"] is not None


def test_people_reviewing_one_document_count_as_one_document(svc: Service) -> None:
    ana, sid = client_as(api.app, "ana"), client_as(api.app, "sid")
    doc, run = _opened(svc, ana)
    sid.post(f"/api/runs/{run}/activity", json={"active_seconds": 0})
    _age(svc)
    ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 30})
    sid.post(f"/api/runs/{run}/activity", json={"active_seconds": 20})
    with svc.store.tx() as c:
        c.execute("UPDATE work_sessions SET ended_at=?", (datetime.now(UTC).isoformat(),))
    assert client_as(api.app, "mia").get("/api/roi").json()["sessions"]["assisted"] == 1


def test_a_finished_review_is_not_timed_again(svc: Service) -> None:
    ana = client_as(api.app, "ana")
    _, run = _opened(svc, ana)
    with svc.store.tx() as c:
        c.execute("UPDATE work_sessions SET ended_at=?", (datetime.now(UTC).isoformat(),))
    ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 15})
    assert len(_sessions(svc)) == 1 and _sessions(svc)[0]["active_seconds"] == 0


def test_a_manager_looking_at_a_spread_is_not_measured(svc: Service) -> None:
    view = client_as(api.app, "ana").post("/api/documents", files={"file": ("a.htm", DOC.read_bytes())}).json()
    both = client_as(api.app, "both")
    assert both.post(f"/api/runs/{view['run']['id']}/activity", json={"active_seconds": 5}).json() == {}
    assert not _sessions(svc)


@pytest.mark.parametrize("who", ["ana", "sam", "pat", "rae", "ari", "aud", "vic"])
@pytest.mark.parametrize("path", ["/api/roi", "/api/finops/roi", "/api/sessions"])
def test_time_and_roi_figures_are_closed_to_everyone_but_management(svc: Service, who: str, path: str) -> None:
    assert client_as(api.app, who).get(path).status_code == 403


@pytest.mark.parametrize("who", ["mia", "adm"])
def test_management_can_see_them(svc: Service, who: str) -> None:
    c = client_as(api.app, who)
    assert c.get("/api/roi").status_code == 200 and c.get("/api/sessions").status_code == 200


def test_an_analyst_cannot_start_a_visible_timer(svc: Service) -> None:
    assert client_as(api.app, "ana").post("/api/sessions", json={"mode": "baseline", "document_id": "x"}).status_code == 403


def test_managers_see_time_but_not_who_spent_it(svc: Service) -> None:
    _opened(svc, client_as(api.app, "ana"))
    rows = client_as(api.app, "mia").get("/api/sessions").json()
    assert len(rows) == 1 and "actor" not in rows[0]


def test_nothing_about_timing_reaches_the_audit_log_an_analyst_reads(svc: Service) -> None:
    ana, adm = client_as(api.app, "ana"), client_as(api.app, "adm")
    doc, run = _opened(svc, ana)
    ana.post(f"/api/runs/{run}/activity", json={"active_seconds": 15})
    assert adm.post("/api/sessions", json={"mode": "baseline", "document_id": doc, "run_id": run}).status_code == 200
    kinds = [e["kind"] for e in ana.get(f"/api/runs/{run}/events").json()]
    assert kinds and not [k for k in kinds if k.startswith("session")]
    assert "session_start" in [e["kind"] for e in adm.get(f"/api/runs/{run}/events").json()]


def test_the_roi_page_uses_the_accuracy_pages_figure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    rates = {"silent_error_rate": {"n": 5, "d": 1080}}
    (tmp_path / "stmt-holdout-d62.json").write_text(json.dumps({"name": "stmt-holdout-d62", "documents": 30, "rates": rates}))
    (tmp_path / "latest-holdout.json").write_text(json.dumps({"name": "old", "documents": 30, "rates": {"silent_error_rate": {"n": 32, "d": 2154}}}))
    monkeypatch.setattr(roi_api, "REPORTS", tmp_path)
    rate, source = roi_api.silent_error_rate()
    assert rate == (5, 1080) and "Accuracy page" in source
