"""Disagreements between the model's hidden opinion and what the analyst approved (DECISIONS D53).

At approval every row where the model would have placed the line differently becomes a disagreement waiting for a
senior; reopening withdraws them, re-approving opens them again, and after the review deadline the analyst's answer
stands. Analysts never see any of it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from spreader import auth_api
from spreader.contracts import StatementRow, StatementTable
from spreader.profile import LineDef
from spreader.service import DEADLINE_ACTOR, Service
from spreader.shadow import in_sample, review_days, share
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"


class FakeAsker:
    def __init__(self, answer: Any) -> None:
        self.answer = answer

    def ask(self, table: StatementTable, row: StatementRow, lines: list[LineDef]) -> str | None:
        return self.answer(row, [ln.id for ln in lines])


def _contrary(row: StatementRow, ids: list[str]) -> str | None:
    """Agrees on nothing it can contradict: says "none" for every row (so every placed row is a disagreement)."""
    return "none"


def _svc(tmp_path: Path, profile: Any, answer: Any = _contrary, name: str = "db") -> Service:
    return Service(Store(tmp_path / f"{name}.sqlite3"), profile=profile, shadow=FakeAsker(answer),
                   shadow_id="local:test", shadow_sync=True)


def _upload(svc: Service) -> int:
    _, view = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert view.run["status"] == "succeeded"
    return int(view.run["id"])


def _opinions(svc: Service, run: int, outcome: str) -> list[dict[str, Any]]:
    return [dict(r) for r in svc.store.query("SELECT * FROM shadow_opinions WHERE run_id=? AND outcome=?", (run, outcome))]


def _rows(svc: Service) -> list[dict[str, Any]]:
    return [dict(r) for r in svc.store.query("SELECT * FROM disagreements ORDER BY id")]


def test_approval_turns_every_row_the_model_placed_differently_into_a_disagreement(tmp_path: Path, profile: Any) -> None:
    svc = _svc(tmp_path, profile)
    run = _upload(svc)
    assert not _rows(svc), "nothing to compare with before the analyst approves"
    svc.act(run, {"type": "approve"}, "dev:ana")
    differ = _opinions(svc, run, "disagree")
    rows = _rows(svc)
    assert differ and {r["opinion_id"] for r in rows} == {o["id"] for o in differ}
    approved = svc.get(run).run["state"]["approved"]
    for r in rows:
        o = next(x for x in differ if x["id"] == r["opinion_id"])
        assert r["analyst_line"] == (o["platform_line"] if o["platform_line"] and not o["platform_excluded"] else "none")
        assert r["model_line"] == o["model_line"] == "none" and r["label"] == o["label"]
        assert r["status"] == "open" and r["approved_by"] == "dev:ana" and r["approved_at"] == approved["at"]
        assert datetime.fromisoformat(r["due_at"]) == datetime.fromisoformat(approved["at"]) + timedelta(days=14)
        assert r["verdict"] is None and r["ruled_by"] is None


def test_rows_where_the_model_agrees_or_gave_no_answer_are_not_disagreements(tmp_path: Path, profile: Any) -> None:
    plain = Service(Store(tmp_path / "plain.sqlite3"), profile=profile)  # where the platform places each label
    _, view = plain.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert view.spread is not None
    placed = {r.label: m.canonical for res in view.spread.statements.values() for r in res.table.rows
              for m in res.mappings if m.row_index == r.index and m.canonical and not m.excluded}

    def picky(row: StatementRow, ids: list[str]) -> str | None:
        if "tax" in row.label.lower():
            return None  # no answer
        if row.label in placed and len(row.label) % 2 == 0:
            return placed[row.label]  # agrees
        return "none"

    svc = _svc(tmp_path, profile, picky)
    run = _upload(svc)
    svc.act(run, {"type": "approve"}, "dev:ana")
    opinion_of = {r["opinion_id"] for r in _rows(svc)}
    assert opinion_of.isdisjoint({o["id"] for o in _opinions(svc, run, "agree") + _opinions(svc, run, "no_answer")})
    assert _opinions(svc, run, "no_answer") and _opinions(svc, run, "agree"), "the test needs all three outcomes"


def test_an_opinion_that_arrives_after_the_approval_is_still_compared(tmp_path: Path, profile: Any,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _svc(tmp_path, profile)
    monkeypatch.setenv("SPREADER_SHADOW_SHARE", "0.000000001")  # this document is out of the sample at upload
    run = _upload(svc)
    assert not svc.store.query("SELECT 1 FROM shadow_opinions"), "out of the sample: no opinion yet"
    svc.act(run, {"type": "approve"}, "dev:ana")
    assert not _rows(svc)
    svc.record_shadow(run)  # the background thread, finishing late
    assert len(_rows(svc)) == len(_opinions(svc, run, "disagree")) > 0


def test_reopening_withdraws_and_approving_again_reopens_with_a_new_deadline(tmp_path: Path, profile: Any,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _svc(tmp_path, profile)
    run = _upload(svc)
    svc.act(run, {"type": "approve"}, "dev:ana")
    n = len(_rows(svc))
    svc.act(run, {"type": "reopen"}, "dev:ana")
    assert {r["status"] for r in _rows(svc)} == {"withdrawn"}
    monkeypatch.setenv("SPREADER_SHADOW_REVIEW_DAYS", "3")
    svc.act(run, {"type": "approve"}, "dev:erin")
    rows = _rows(svc)
    assert len(rows) == n and {r["status"] for r in rows} == {"open"}
    assert {r["approved_by"] for r in rows} == {"dev:erin"}
    at = datetime.fromisoformat(svc.get(run).run["state"]["approved"]["at"])
    assert {datetime.fromisoformat(r["due_at"]) for r in rows} == {at + timedelta(days=3)}


def test_without_a_ruling_by_the_deadline_the_analysts_answer_stands(tmp_path: Path, profile: Any) -> None:
    svc = _svc(tmp_path, profile)
    run = _upload(svc)
    svc.act(run, {"type": "approve"}, "dev:ana")
    due = _rows(svc)[0]["due_at"]
    just_before = (datetime.fromisoformat(due) - timedelta(seconds=1)).isoformat(timespec="seconds")
    assert svc.settle_overdue(just_before) == 0 and {r["status"] for r in _rows(svc)} == {"open"}
    n = svc.settle_overdue(due)
    rows = _rows(svc)
    assert n == len(rows) and {r["status"] for r in rows} == {"analyst_stands"}
    assert {r["verdict"] for r in rows} == {"analyst"} and {r["ruled_by"] for r in rows} == {DEADLINE_ACTOR}
    assert svc.settle_overdue(due) == 0, "settled once"
    assert svc.store.verify_chain() == (True, None)


@pytest.mark.parametrize("name,value", [("SPREADER_SHADOW_SHARE", "0"), ("SPREADER_SHADOW_SHARE", "1.5"),
                                        ("SPREADER_SHADOW_SHARE", "all"), ("SPREADER_SHADOW_REVIEW_DAYS", "0"),
                                        ("SPREADER_SHADOW_REVIEW_DAYS", "two weeks"),
                                        ("SPREADER_SHADOW_REVIEW_DAYS", "400")])
def test_settings_that_make_no_sense_are_refused(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        share() if name == "SPREADER_SHADOW_SHARE" else review_days()


def test_a_nonsense_setting_stops_the_start_not_every_upload(tmp_path: Path, profile: Any,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREADER_SHADOW_REVIEW_DAYS", "fortnight")
    with pytest.raises(ValueError, match="SPREADER_SHADOW_REVIEW_DAYS"):
        _svc(tmp_path, profile)
    Service(Store(tmp_path / "plain.sqlite3"), profile=profile)  # without a shadow model the settings are unused


def test_the_defaults_are_every_document_and_fourteen_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPREADER_SHADOW_SHARE", raising=False)
    monkeypatch.delenv("SPREADER_SHADOW_REVIEW_DAYS", raising=False)
    assert share() == 1 and review_days() == 14
    assert all(in_sample(hashlib.sha256(str(i).encode()).hexdigest()) for i in range(500))


def test_a_sample_takes_about_its_share_and_keeps_a_document_in_or_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPREADER_SHADOW_SHARE", "0.2")
    ids = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(2000)]
    picked = [d for d in ids if in_sample(d)]
    assert 0.17 < len(picked) / len(ids) < 0.23
    assert all(in_sample(d) for d in picked), "the same document is always in or always out"


def test_analysts_never_see_disagreements(tmp_path: Path, profile: Any) -> None:
    svc = _svc(tmp_path, profile)
    run = _upload(svc)
    svc.act(run, {"type": "approve"}, "dev:ana")
    assert _rows(svc)
    assert not {e["kind"] for e in svc.events(run)} & {"shadow_opinion", "disagreements"}
    routes = [(p, perm) for _, p, perm in auth_api.ROUTE_PERMISSIONS if "disagree" in p or "shadow" in p]
    assert routes and all(perm == "adjudicate" for _, perm in routes), "only seniors reach them (D54)"
    assert "adjudicate" not in profile_roles("analyst")


def profile_roles(role: str) -> set[str]:
    from finops.core.identity import load_auth_config

    return set(load_auth_config(ROOT / "config" / "finops" / "auth" / "development.yaml").roles[role])


def test_erasing_a_document_erases_its_disagreements(tmp_path: Path, profile: Any) -> None:
    from types import SimpleNamespace

    from finops.core import retention as rt

    svc = _svc(tmp_path, profile)
    run = _upload(svc)
    svc.act(run, {"type": "approve"}, "dev:ana")
    doc = svc.get(run).run["document_id"]
    counts = rt._erase_statement(SimpleNamespace(store=svc.store), doc, "deletion request", "dev:adm")  # type: ignore[arg-type]
    assert counts["disagreements"] > 0 and not _rows(svc)


def test_the_command_lists_open_disagreements_and_settles_overdue_ones(tmp_path: Path, profile: Any,
                                                                      capsys: pytest.CaptureFixture[str]) -> None:
    from spreader import cli

    svc = _svc(tmp_path / "data", profile, name="spreader")
    run = _upload(svc)
    svc.act(run, {"type": "approve"}, "dev:ana")
    n = len(_rows(svc))
    assert cli.main(["disagreements", "--data", str(tmp_path / "data")]) == 0
    out = capsys.readouterr().out
    assert f"{n} disagreements: open {n}" in out and "after 14 days" in out and out.count("  #") == n
    with svc.store.tx() as c:  # as if the deadline passed
        c.execute("UPDATE disagreements SET due_at='2000-01-01T00:00:00+00:00'")
    assert cli.main(["disagreements", "--data", str(tmp_path / "data")]) == 0
    assert f"analyst_stands {n}" in capsys.readouterr().out
    assert json.loads(svc.store.query("SELECT payload FROM events WHERE kind='disagreements_settled'")[0]["payload"]) \
        == {"analyst_stands": n}
