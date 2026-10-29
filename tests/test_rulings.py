"""A senior's ruling on a disagreement, and what it leaves on the approved spread (DECISIONS D54).

Only seniors see the list and rule; they see the two answers as A and B until they have ruled; a ruling needs a reason
and a note, is final, and is never made by the spread's own approver. When the senior rules the approved line wrong,
the spread shows "corrected after review" to its analyst until they reopen it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from conftest import client_as
from spreader import api
from spreader.contracts import StatementRow, StatementTable
from spreader.profile import LineDef
from spreader.service import Service
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"


class Nowhere:
    """A model that says every row belongs nowhere: each placed row becomes a disagreement."""

    def ask(self, table: StatementTable, row: StatementRow, lines: list[LineDef]) -> str | None:
        return "none"


@pytest.fixture()
def env(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile, shadow=Nowhere(), shadow_id="local:test",
                  shadow_sync=True)
    monkeypatch.setattr(api, "service", lambda: svc)
    _, view = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    run = int(view.run["id"])
    svc.act(run, {"type": "approve"}, "dev:ana")
    return {"svc": svc, "run": run, "sam": client_as(api.app, "sam"), "ana": client_as(api.app, "ana")}


def _db(svc: Service, did: int) -> dict[str, Any]:
    return dict(svc.store.query("SELECT * FROM disagreements WHERE id=?", (did,))[0])


def _choice_for(item: dict[str, Any], line: str) -> str:
    return next(a["key"] for a in item["answers"] if a["line"] == line)


def _rule(client: Any, did: int, **body: Any) -> Any:
    return client.post(f"/api/disagreements/{did}/rule", json={"reason": "judgement_call", "note": "checked", **body})


def test_only_seniors_see_and_rule(env: dict[str, Any]) -> None:
    assert env["ana"].get("/api/disagreements").status_code == 403
    out = env["sam"].get("/api/disagreements").json()
    assert out["items"] and out["review_days"] == 14 and out["blind"] is True
    assert "judgement_call" in out["reasons"] and out["lines"]["income_statement"]
    assert _rule(env["ana"], out["items"][0]["id"], choice="a").status_code == 403


def test_the_senior_sees_a_and_b_until_they_have_ruled(env: dict[str, Any]) -> None:
    item = env["sam"].get("/api/disagreements").json()["items"][0]
    assert all("who" not in a for a in item["answers"]) and "approved_by" not in item
    assert {a["key"] for a in item["answers"]} == {"a", "b"}
    d = _db(env["svc"], item["id"])
    assert {a["line"] for a in item["answers"]} == {d["analyst_line"], d["model_line"]}
    done = _rule(env["sam"], item["id"], choice="a").json()
    assert {a["who"] for a in done["answers"]} == {"analyst", "model"} and done["approved_by"] == "dev:ana"


def test_which_answer_is_a_does_not_follow_whose_it_is(env: dict[str, Any]) -> None:
    items = env["sam"].get("/api/disagreements").json()["items"]
    a_is_analyst = [_db(env["svc"], i["id"])["analyst_line"] == i["answers"][0]["line"] for i in items]
    assert len(items) >= 6 and any(a_is_analyst) and not all(a_is_analyst)


def test_a_choice_becomes_the_verdict_and_the_correct_line(env: dict[str, Any]) -> None:
    items = env["sam"].get("/api/disagreements").json()["items"]
    first, second = items[0], items[1]
    d1, d2 = _db(env["svc"], first["id"]), _db(env["svc"], second["id"])
    assert _rule(env["sam"], first["id"], choice=_choice_for(first, d1["analyst_line"])).status_code == 200
    assert _rule(env["sam"], second["id"], choice=_choice_for(second, d2["model_line"]),
                 reason="analyst_slip", note="the analyst rushed this one").status_code == 200
    r1, r2 = _db(env["svc"], first["id"]), _db(env["svc"], second["id"])
    assert (r1["verdict"], r1["correct_line"], r1["status"], r1["ruled_by"]) == ("analyst", d1["analyst_line"], "ruled", "dev:sam")
    assert (r2["verdict"], r2["correct_line"], r2["reason"]) == ("model", d2["model_line"], "analyst_slip")
    assert r2["note"] == "the analyst rushed this one"


def test_neither_needs_a_third_line_that_belongs_to_the_statement(env: dict[str, Any]) -> None:
    item = env["sam"].get("/api/disagreements").json()["items"][0]
    d = _db(env["svc"], item["id"])
    assert _rule(env["sam"], item["id"], choice="neither").status_code == 400
    assert _rule(env["sam"], item["id"], choice="neither", correct_line=d["analyst_line"]).status_code == 400
    assert _rule(env["sam"], item["id"], choice="neither", correct_line="no_such_line").status_code == 400
    other = next(ln.id for ln in env["svc"].profile.statements[next(iter(env["svc"].profile.statements))].lines)
    stmt_lines = {ln.id for k, s in env["svc"].profile.statements.items() if k.value == d["statement"] for ln in s.lines}
    third = next(x for x in sorted(stmt_lines) if x not in {d["analyst_line"], d["model_line"]})
    assert other  # the profile has lines
    r = _rule(env["sam"], item["id"], choice="neither", correct_line=third)
    assert r.status_code == 200 and _db(env["svc"], item["id"])["correct_line"] == third


@pytest.mark.parametrize("body", [{"choice": "c"}, {"choice": "a", "reason": "felt_like_it"},
                                  {"choice": "a", "note": " "}], ids=["choice", "reason", "note"])
def test_a_ruling_needs_a_choice_a_known_reason_and_a_note(env: dict[str, Any], body: dict[str, Any]) -> None:
    item = env["sam"].get("/api/disagreements").json()["items"][0]
    r = env["sam"].post(f"/api/disagreements/{item['id']}/rule", json={"reason": "judgement_call", "note": "ok", **body})
    assert r.status_code == 400 and _db(env["svc"], item["id"])["status"] == "open"


def test_a_ruling_is_final_and_a_reopened_approval_has_nothing_to_rule_on(env: dict[str, Any]) -> None:
    items = env["sam"].get("/api/disagreements").json()["items"]
    assert _rule(env["sam"], items[0]["id"], choice="a").status_code == 200
    again = _rule(env["sam"], items[0]["id"], choice="b")
    assert again.status_code == 400 and "final" in again.json()["error"]
    env["svc"].act(env["run"], {"type": "reopen"}, "dev:ana")
    assert _db(env["svc"], items[0]["id"])["status"] == "ruled", "a ruling survives a reopen"
    gone = _rule(env["sam"], items[1]["id"], choice="a")
    assert gone.status_code == 400 and "reopened" in gone.json()["error"]


def test_nobody_rules_on_a_spread_they_approved(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile, shadow=Nowhere(), shadow_id="local:test",
                  shadow_sync=True)
    monkeypatch.setattr(api, "service", lambda: svc)
    sid = client_as(api.app, "sid")  # analyst and senior
    ana = client_as(api.app, "ana")  # uploads: the suite runs two-person sign-off, so the approver did not upload
    run = ana.post("/api/documents", files={"file": ("s.htm", SAMPLE.read_bytes())}).json()["run"]["id"]
    assert sid.post(f"/api/runs/{run}/actions", json={"type": "approve"}).status_code == 200
    item = sid.get("/api/disagreements").json()["items"][0]
    r = _rule(sid, item["id"], choice="a")
    assert r.status_code == 403 and "approved" in r.text
    assert _rule(client_as(api.app, "sam"), item["id"], choice="a").status_code == 200


def test_a_late_ruling_replaces_the_analyst_stands_default(env: dict[str, Any]) -> None:
    svc = env["svc"]
    item = env["sam"].get("/api/disagreements").json()["items"][0]
    due = _db(svc, item["id"])["due_at"]
    svc.settle_overdue((datetime.fromisoformat(due) + timedelta(days=1)).isoformat(timespec="seconds"))
    assert _db(svc, item["id"])["status"] == "analyst_stands"
    d = _db(svc, item["id"])
    listed = next(i for i in env["sam"].get("/api/disagreements").json()["items"] if i["id"] == item["id"])
    assert _rule(env["sam"], item["id"], choice=_choice_for(listed, d["model_line"])).status_code == 200
    r = _db(svc, item["id"])
    assert (r["status"], r["verdict"], r["ruled_by"]) == ("ruled", "model", "dev:sam")
    ev = [json.loads(e["payload"]) for e in svc.store.query("SELECT payload FROM events WHERE kind='ruling'")]
    assert ev == [{"disagreement": item["id"], "verdict": "model", "reason": "judgement_call", "late": True}]


def test_a_wrong_approved_line_shows_corrected_after_review_until_the_analyst_reopens(env: dict[str, Any]) -> None:
    svc, run, ana = env["svc"], env["run"], env["ana"]
    items = env["sam"].get("/api/disagreements").json()["items"]
    d0, d1 = _db(svc, items[0]["id"]), _db(svc, items[1]["id"])
    _rule(env["sam"], items[0]["id"], choice=_choice_for(items[0], d0["analyst_line"]))  # analyst right: nothing shown
    assert ana.get(f"/api/runs/{run}").json()["corrected_after_review"] == []
    _rule(env["sam"], items[1]["id"], choice=_choice_for(items[1], d1["model_line"]), reason="analyst_slip",
          note="belongs nowhere")
    shown = ana.get(f"/api/runs/{run}").json()["corrected_after_review"]
    assert [(c["label"], c["approved_line"], c["correct_line"], c["ruled_by"]) for c in shown] == \
        [(d1["label"], d1["analyst_line"], "none", "dev:sam")]
    assert shown[0]["correct_label"] == "left off the spread" and shown[0]["note"] == "belongs nowhere"
    docs = ana.get("/api/documents").json()
    assert next(d for d in docs if d["run_id"] == run)["corrected_after_review"] == 1
    assert all("local:test" not in json.dumps(c) for c in shown), "no model id reaches the analyst"
    assert not {e["kind"] for e in ana.get(f"/api/runs/{run}/events").json()} & {"ruling", "disagreements"}
    assert ana.post(f"/api/runs/{run}/actions", json={"type": "reopen"}).status_code == 200
    assert ana.get(f"/api/runs/{run}").json()["corrected_after_review"] == [], "reopening to fix it clears it"


def test_the_flag_and_blind_ruling_can_be_switched_off(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREADER_BLIND_RULING", "0")
    item = env["sam"].get("/api/disagreements").json()["items"][1]
    assert {a["who"] for a in item["answers"]} == {"analyst", "model"} and item["approved_by"] == "dev:ana"
    d = _db(env["svc"], item["id"])
    _rule(env["sam"], item["id"], choice=_choice_for(item, d["model_line"]))
    monkeypatch.setenv("SPREADER_FLAG_CORRECTED", "0")
    assert env["ana"].get(f"/api/runs/{env['run']}").json()["corrected_after_review"] == []
    monkeypatch.setenv("SPREADER_FLAG_CORRECTED", "maybe")
    with pytest.raises(ValueError, match="SPREADER_FLAG_CORRECTED"):
        Service(Store(Path(env["svc"].store.path).parent / "other.sqlite3"))


def test_rulings_are_in_the_audit_chain_under_the_senior(env: dict[str, Any]) -> None:
    item = env["sam"].get("/api/disagreements").json()["items"][0]
    _rule(env["sam"], item["id"], choice="b")
    ev = env["svc"].store.query("SELECT actor, run_id FROM events WHERE kind='ruling'")
    assert [(e["actor"], e["run_id"]) for e in ev] == [("dev:sam", env["run"])]
    assert env["svc"].store.verify_chain() == (True, None)
