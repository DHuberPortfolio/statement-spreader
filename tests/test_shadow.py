"""The model's hidden second opinion during a learning period (DECISIONS D52).

The opinion must never change what the analyst gets, never be shown to them, survive any model failure, and record
for every row where the model would have placed it next to where the platform did.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from conftest import client_as
from spreader import api
from spreader.contracts import RowRole, StatementRow, StatementTable
from spreader.llm import configured_model, shadow_model
from spreader.llm import local as local_mod
from spreader.profile import LineDef
from spreader.service import SHADOW_ACTOR, Service
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"


class FakeAsker:
    """A model that answers by a rule: `answer(row, line_ids)` returns a line id, "none" or None."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.asked: list[tuple[str, str]] = []

    def ask(self, table: StatementTable, row: StatementRow, lines: list[LineDef]) -> str | None:
        self.asked.append((table.statement.value, row.label))
        return self.answer(row, [ln.id for ln in lines])


def _first_line(row: StatementRow, ids: list[str]) -> str | None:
    return ids[0] if ids else "none"


def _svc(tmp_path: Path, profile: Any, shadow: Any = None, name: str = "db") -> Service:
    return Service(Store(tmp_path / f"{name}.sqlite3"), profile=profile, shadow=shadow, shadow_id="local:test",
                   shadow_sync=True)


def _opinions(svc: Service) -> list[dict[str, Any]]:
    return [dict(r) for r in svc.store.query("SELECT * FROM shadow_opinions ORDER BY id")]


def test_the_role_decides_whether_the_model_spreads_or_only_gives_a_second_opinion(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local_mod, "CACHE", tmp_path / "llm-cache.sqlite3")
    monkeypatch.delenv("SPREADER_MODEL_ROLE", raising=False)
    monkeypatch.delenv("SPREADER_MODEL_URL", raising=False)
    assert configured_model() == (None, "none") and shadow_model() == (None, "none")
    monkeypatch.setenv("SPREADER_MODEL_URL", "http://127.0.0.1:1")
    assert configured_model()[1] == "local:local" and shadow_model() == (None, "none"), "live stays the default"
    monkeypatch.setenv("SPREADER_MODEL_ROLE", "shadow")
    assert configured_model() == (None, "none"), "in a learning period the model takes no part in spreading"
    assert shadow_model()[1] == "local:local"
    monkeypatch.setenv("SPREADER_MODEL_ROLE", "shadwo")
    with pytest.raises(ValueError, match="SPREADER_MODEL_ROLE"):
        shadow_model()


def test_the_second_opinion_never_changes_what_the_analyst_gets(tmp_path: Path, profile: Any) -> None:
    plain = _svc(tmp_path, profile, name="plain")
    asker = FakeAsker(_first_line)
    shadowed = _svc(tmp_path, profile, asker, name="shadow")
    _, a = plain.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    _, b = shadowed.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert asker.asked, "the model was asked"
    assert plain.idempotency_key(a.run["document_id"]) == shadowed.idempotency_key(b.run["document_id"])
    assert a.spread is not None and b.spread is not None
    assert a.spread.model_dump_json() == b.spread.model_dump_json()
    assert b.run["model"] == "none", "the run records no model: none took part"


def test_every_labelled_row_gets_an_opinion_next_to_the_platforms_placement(tmp_path: Path, profile: Any) -> None:
    def contrary(row: StatementRow, ids: list[str]) -> str | None:
        return "none" if "total" in row.label.lower() else (ids[-1] if ids else "none")

    svc = _svc(tmp_path, profile, FakeAsker(contrary))
    _, view = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert view.spread is not None
    expected = {(k, r.index) for k, res in view.spread.statements.items() for r in res.table.rows
                if r.role is not RowRole.HEADER and r.label and r.index in {m.row_index for m in res.mappings}}
    ops = _opinions(svc)
    assert {(o["statement"], o["row_index"]) for o in ops} == expected
    placed = {(k, m.row_index): m for k, res in view.spread.statements.items() for m in res.mappings}
    for o in ops:
        m = placed[(o["statement"], o["row_index"])]
        assert o["platform_line"] == m.canonical and o["platform_rule"] == m.rule
        assert o["model_id"] == "local:test" and o["label"]
        platform = m.canonical if m.canonical and not m.excluded else "none"
        assert o["outcome"] == ("agree" if o["model_line"] == platform else "disagree")
    assert {o["outcome"] for o in ops} == {"agree", "disagree"}, "the contrary model agrees on some rows only"


def test_a_failing_or_crashing_model_leaves_the_run_untouched(tmp_path: Path, profile: Any) -> None:
    svc = _svc(tmp_path, profile, FakeAsker(lambda row, ids: None))
    _, view = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert view.run["status"] == "succeeded"
    assert {o["outcome"] for o in _opinions(svc)} == {"no_answer"} and all(o["model_line"] is None for o in _opinions(svc))

    def boom(row: StatementRow, ids: list[str]) -> str:
        raise RuntimeError("the model server fell over")

    svc2 = _svc(tmp_path, profile, FakeAsker(boom), name="crash")
    _, view2 = svc2.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert view2.run["status"] == "succeeded" and view2.spread is not None
    assert not _opinions(svc2)
    failed = [json.loads(r["payload"]) for r in svc2.store.query("SELECT payload FROM events WHERE kind='shadow_opinion'")]
    assert failed == [{"model": "local:test", "failed": "RuntimeError"}]


def test_one_opinion_per_run_and_model_and_the_audit_log_names_the_model(tmp_path: Path, profile: Any) -> None:
    asker = FakeAsker(_first_line)
    svc = _svc(tmp_path, profile, asker)
    _, view = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    n, asked = len(_opinions(svc)), len(asker.asked)
    again = svc.record_shadow(view.run["id"])
    assert len(_opinions(svc)) == n and len(asker.asked) == asked, "asked once per run"
    assert again is not None and again["rows"] == n
    ev = svc.store.query("SELECT actor, payload FROM events WHERE kind='shadow_opinion'")
    assert len(ev) == 1 and ev[0]["actor"] == SHADOW_ACTOR
    assert set(json.loads(ev[0]["payload"])) == {"model", "rows", "agree", "disagree", "no_answer"}, "counts only"
    assert svc.store.verify_chain() == (True, None)


def test_analysts_never_see_the_second_opinion(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _svc(tmp_path, profile, FakeAsker(_first_line))
    monkeypatch.setattr(api, "service", lambda: svc)
    ana = client_as(api.app, "ana")
    up = ana.post("/api/documents", files={"file": ("s.htm", SAMPLE.read_bytes())})
    assert up.status_code == 200 and _opinions(svc), "the upload recorded the opinion"
    run = up.json()["run"]["id"]
    for path in (f"/api/runs/{run}", f"/api/runs/{run}/events", "/api/documents"):
        body = ana.get(path).text
        assert "shadow" not in body and "local:test" not in body, path


def test_erasing_a_document_erases_its_second_opinions(tmp_path: Path, profile: Any) -> None:
    from types import SimpleNamespace

    from finops.core import retention as rt

    svc = _svc(tmp_path, profile, FakeAsker(_first_line))
    doc, _ = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert _opinions(svc)
    counts = rt._erase_statement(SimpleNamespace(store=svc.store), doc["id"], "deletion request", "dev:adm")  # type: ignore[arg-type]
    assert counts["shadow_opinions"] > 0 and not _opinions(svc)


def test_the_backfill_command_records_opinions_for_earlier_documents(tmp_path: Path, profile: Any,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    from spreader import cli

    plain = _svc(tmp_path / "data", profile, name="spreader")  # documents spread before the learning period
    plain.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    monkeypatch.delenv("SPREADER_MODEL_URL", raising=False)
    assert cli.main(["shadow", "--data", str(tmp_path / "data")]) == 1, "refused without a shadow model"
    asker = FakeAsker(_first_line)
    monkeypatch.setattr("spreader.llm.shadow_model", lambda: (asker, "local:test"))
    assert cli.main(["shadow", "--data", str(tmp_path / "data")]) == 0
    assert _opinions(plain) and asker.asked
    asked = len(asker.asked)
    assert cli.main(["shadow", "--data", str(tmp_path / "data")]) == 0
    assert len(asker.asked) == asked, "a second backfill asks nothing again"


@pytest.mark.parametrize("reply,expected", [
    (json.dumps({"line": "none", "confidence": 1}), "none"),
    (json.dumps({"line": "invented_line", "confidence": 1}), None),
    ("{not json", None),
], ids=["none", "invented", "malformed"])
def test_the_model_tells_belongs_nowhere_apart_from_no_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                              profile: Any, reply: str, expected: str | None) -> None:
    monkeypatch.setattr(local_mod, "CACHE", tmp_path / "llm-cache.sqlite3")
    req = httpx.Request("POST", "http://127.0.0.1:1")
    monkeypatch.setattr(local_mod.httpx, "post", lambda url, timeout, json: httpx.Response(  # noqa: A006
        200, json={"choices": [{"message": {"content": reply}}]}, request=req))
    m = local_mod.LocalModelMapper("http://127.0.0.1:1", model_name="t")
    svc = _svc(tmp_path, profile, m)
    _, view = svc.upload("s.htm", SAMPLE.read_bytes(), "dev:ana")
    assert {o["model_line"] for o in _opinions(svc)} == {expected}
