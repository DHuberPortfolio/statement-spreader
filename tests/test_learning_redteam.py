"""Red-team checks on the learning period as a whole (DECISIONS D52-D55): races, stale caches, reopened approvals,
settings, and the size of what the senior's page returns."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from conftest import client_as
from spreader import api
from spreader.contracts import StatementRow, StatementTable
from spreader.profile import LineDef
from spreader.service import ActionError, Service
from spreader.store import Store
from spreader.teaching import MODEL_METHOD

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "eval" / "synthetic"
DOC1, DOC2 = SYN / "s7-001-clean" / "statement.html", SYN / "s7-002-clean" / "statement.html"


class Nowhere:
    def ask(self, table: StatementTable, row: StatementRow, lines: list[LineDef]) -> str | None:
        return "none"


def _svc(tmp_path: Path, profile: Any) -> Service:
    return Service(Store(tmp_path / "db.sqlite3"), profile=profile, shadow=Nowhere(), shadow_id="local:test",
                   shadow_sync=True)


def _approved(svc: Service, path: Path, company: str | None = None) -> int:
    _, view = svc.upload(path.name, path.read_bytes(), "dev:ana", company)
    run = int(view.run["id"])
    svc.act(run, {"type": "approve"}, "dev:ana")
    return run


def _open(svc: Service, run: int) -> list[dict[str, Any]]:
    return [dict(r) for r in svc.store.query("SELECT * FROM disagreements WHERE run_id=? AND status='open' ORDER BY id",
                                             (run,))]


def test_two_seniors_ruling_at_the_same_moment_leave_one_ruling_one_memory_and_one_outcome(tmp_path: Path,
                                                                                          profile: Any) -> None:
    svc = _svc(tmp_path, profile)
    d = _open(svc, _approved(svc, DOC1))[0]
    results: list[Any] = []
    start = threading.Barrier(2)

    def go(who: str, verdict: str) -> None:
        start.wait()
        try:
            results.append(svc.rule(d["id"], verdict, who, "judgement_call", f"{who} ruled"))
        except ActionError as exc:
            results.append(exc)

    threads = [threading.Thread(target=go, args=a) for a in (("dev:sam", "model"), ("dev:sid", "analyst"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in results if isinstance(r, dict)]
    assert len(ok) == 1 and sum(isinstance(r, ActionError) for r in results) == 1
    assert len(svc.store.query("SELECT 1 FROM mapping_memory")) == 1
    lines = [json.loads(x) for x in (Path(os.environ["FINOPS_OUTCOMES_DIR"]) / "statements.jsonl").read_text().splitlines()]
    assert sum(1 for o in lines if o["method"] == MODEL_METHOD) == 1, "the losing ruling recorded nothing"
    assert svc.store.verify_chain() == (True, None)


def test_a_reopened_approval_does_not_undo_what_the_senior_taught(tmp_path: Path, profile: Any) -> None:
    svc = _svc(tmp_path, profile)
    run1 = _approved(svc, DOC1, company="Acme")
    peek = Service(Store(tmp_path / "peek.sqlite3"), profile=profile)
    _, v2 = peek.upload(DOC2.name, DOC2.read_bytes(), "dev:ana")
    assert v2.spread is not None
    in2 = {(k, r.label, r.section) for k, res in v2.spread.statements.items() for r in res.table.rows}
    d = next(x for x in _open(svc, run1) if (x["statement"], x["label"], x["section"]) in in2)
    svc.rule(d["id"], "model", "dev:sam", "analyst_slip", "belongs nowhere")
    svc.act(run1, {"type": "reopen"}, "dev:ana")  # the analyst reopens to fix it
    _, view = svc.upload(DOC2.name, DOC2.read_bytes(), "dev:ana", "Acme")
    assert view.spread is not None
    res = view.spread.statements[d["statement"]]
    row = next(r for r in res.table.rows if r.label == d["label"])
    m = next(x for x in res.mappings if x.row_index == row.index)
    assert m.excluded and m.rule == "memory", "the senior's ruling still decides after the reopen"


def test_a_new_ruling_is_an_example_at_once(tmp_path: Path, profile: Any) -> None:
    svc = _svc(tmp_path, profile)
    rows = _open(svc, _approved(svc, DOC1))
    allowed = {ln.id for s in profile.statements.values() for ln in s.lines}
    ex = svc.examples
    assert ex.for_row(rows[0]["statement"], rows[0]["label"], "elsewhere", allowed) == []  # cached: nothing ruled
    svc.rule(rows[0]["id"], "model", "dev:sam", "analyst_slip", "nowhere")
    got = ex.for_row(rows[0]["statement"], rows[0]["label"], "elsewhere", allowed)
    assert got and got[0].line == "none", "the cache does not hide a ruling made a moment ago"


@pytest.mark.parametrize("name,value", [("SPREADER_GOLIVE_MARGIN", "half"), ("SPREADER_BLIND_RULING", "maybe")])
def test_a_learning_setting_that_makes_no_sense_stops_the_start(tmp_path: Path, profile: Any,
                                                                monkeypatch: pytest.MonkeyPatch, name: str,
                                                                value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        Service(Store(tmp_path / "db.sqlite3"), profile=profile)


def test_the_seniors_page_lists_everything_open_and_only_recent_rulings(tmp_path: Path, profile: Any,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _svc(tmp_path, profile)
    monkeypatch.setattr(api, "service", lambda: svc)
    monkeypatch.setattr(api, "RECENT_RULINGS", 2)
    rows = _open(svc, _approved(svc, DOC1))
    for d in rows[:5]:
        svc.rule(d["id"], "analyst", "dev:sam", "judgement_call", "right")
    out = client_as(api.app, "sam").get("/api/disagreements").json()
    statuses = [i["status"] for i in out["items"]]
    assert statuses.count("open") == len(rows) - 5 and statuses.count("ruled") == 2
    assert out["recent_rulings_shown"] == 2 and out["counts"]["ruled"] == 5


def test_a_ruling_never_lets_a_model_placement_skip_a_person(tmp_path: Path, profile: Any) -> None:
    """Calibration may fit the model's ruled opinions, but they are declared never-auto (D48), like the live tier."""
    text = (ROOT / "scripts" / "calibrate.py").read_text(encoding="utf-8")
    assert '"never_auto": ["model", "model.shadow"]' in text
