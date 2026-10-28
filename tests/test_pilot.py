"""The analyst pilot: fair sessions and an honest report (PILOT_PROTOCOL.md, DECISIONS D49)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from conftest import client_as
from spreader import api
from spreader.service import Service
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"
spec = importlib.util.spec_from_file_location("pilot_report", ROOT / "scripts" / "pilot_report.py")
pilot = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(pilot)  # type: ignore[union-attr]


@pytest.fixture()
def svc(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> Service:
    s = Service(Store(tmp_path / "spreader.sqlite3"), profile=profile)
    monkeypatch.setattr(api, "service", lambda: s)
    return s


def _timed(c: Any, doc: str, run: int, mode: str, seconds: float, **extra: Any) -> Any:
    r = c.post("/api/sessions", json={"mode": mode, "document_id": doc, "run_id": run, **extra})
    if r.status_code != 200:
        return r
    sid = r.json()["id"]
    svc_ = api.service()
    with svc_.store.tx() as conn:  # stands in for heartbeats (their clock limits are tested in test_roi.py)
        conn.execute("UPDATE work_sessions SET active_seconds=? WHERE id=?", (seconds, sid))
    return c.post(f"/api/sessions/{sid}/end", json={"note": "test"})


def test_the_same_analyst_cannot_be_timed_twice_on_one_document(svc: Service) -> None:
    view = client_as(api.app, "pat").post("/api/documents", files={"file": ("a.htm", DOC.read_bytes())}).json()
    doc, run = view["run"]["document_id"], view["run"]["id"]
    rae = client_as(api.app, "rae")
    assert _timed(rae, doc, run, "baseline", 900, difficulty="low", analyst_experience="1-3 years").status_code == 200
    again = rae.post("/api/sessions", json={"mode": "assisted", "document_id": doc, "run_id": run})
    assert again.status_code == 409 and "already timed this document" in again.json()["detail"]
    assert _timed(client_as(api.app, "erin"), doc, run, "assisted", 300).status_code == 200  # another analyst may


def test_session_context_is_validated(svc: Service) -> None:
    view = client_as(api.app, "pat").post("/api/documents", files={"file": ("a.htm", DOC.read_bytes())}).json()
    c = client_as(api.app, "rae")
    for bad in ({"difficulty": "extreme"}, {"analyst_experience": "lots"}):
        r = c.post("/api/sessions", json={"mode": "baseline", "document_id": view["run"]["document_id"],
                                          "run_id": view["run"]["id"], **bad})
        assert r.status_code == 400


def test_the_report_says_pending_and_computes_nothing_until_three_and_three() -> None:
    rows = [{"mode": "baseline", "active_seconds": 1800, "actor": "a", "document_id": "d1", "values_checked": 40,
             "errors_found": 2, "corrections": 0, "difficulty": "low", "analyst_experience": "1-3 years"},
            {"mode": "assisted", "active_seconds": 600, "actor": "b", "document_id": "d1", "values_checked": None,
             "errors_found": None, "corrections": 3, "difficulty": "low", "analyst_experience": "3-5 years"}]
    text = pilot.report(rows)
    assert "PENDING" in text and "1 of 3 by-hand" in text and "Difference" not in text
    assert "2 of 40 keyed values disagreed" in text


def test_the_report_with_enough_sessions_shows_medians_ranges_and_quality_side_by_side() -> None:
    rows = [{"mode": m, "active_seconds": s, "actor": f"{m}{i}", "document_id": f"d{i}", "values_checked": 50 if m == "baseline" else None,
             "errors_found": 1 if m == "baseline" else None, "corrections": 0 if m == "baseline" else 4,
             "difficulty": "medium", "analyst_experience": "over 5 years"}
            for m, secs in (("baseline", (1500, 1800, 2400)), ("assisted", (500, 700, 900))) for i, s in enumerate(secs)]
    text = pilot.report(rows)
    assert "FEASIBILITY DATA (not a benchmark)" in text
    assert "median 30.0 (range 25.0 to 40.0), n=3" in text and "median 11.7 (range 8.3 to 15.0), n=3" in text
    assert "+18.3 min per document" in text and "released analyst capacity, not cash" in text
    assert "3 of 150 keyed values disagreed" in text and "12 corrections" in text


def test_the_report_reads_the_database(svc: Service, tmp_path: Path) -> None:
    assert "PENDING" in pilot.report(pilot.sessions(tmp_path))
