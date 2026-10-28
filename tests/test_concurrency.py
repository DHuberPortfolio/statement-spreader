"""Several people at once, interrupted operations, backups and audit anchors (DECISIONS D47).

Two Service objects on one database file stand in for two server processes: each has its own SQLite connection, so
their writes really compete for the database lock.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from finops.core import backup as bk
from finops.core.audit import Database
from finops.core.vault import Vault, load_keys, new_key, set_vault
from spreader.service import ActionError, SeparationError, Service
from spreader.store import Store, _event_hash, _sha

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"


@pytest.fixture()
def two(tmp_path: Path, profile: Any) -> tuple[Service, Service, int]:
    a = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    _, view = a.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    b = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    return a, b, view.run["id"]


def _race(fns: list[Any]) -> list[Any]:
    start = threading.Barrier(len(fns))
    out: list[Any] = [None] * len(fns)

    def go(i: int) -> None:
        start.wait()
        try:
            out[i] = fns[i]()
        except Exception as exc:  # noqa: BLE001 - the outcome is what is being tested
            out[i] = exc

    threads = [threading.Thread(target=go, args=(i,)) for i in range(len(fns))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return out


def test_two_reviewers_cannot_silently_overwrite_each_other(two: tuple[Service, Service, int]) -> None:
    a, b, run = two
    values = [v for v in a.get(run).spread.values if v.value is not None][:12]  # type: ignore[union-attr]
    ok = 0
    for i in range(0, len(values) - 1, 2):
        va, vb = values[i], values[i + 1]
        res = _race([
            lambda va=va: a.act(run, {"type": "correct_value", "line": va.line, "period": va.period,
                                      "value": str(va.value), "reason": "checked A"}, "dev:rae"),
            lambda vb=vb: b.act(run, {"type": "correct_value", "line": vb.line, "period": vb.period,
                                      "value": str(vb.value), "reason": "checked B"}, "dev:erin"),
        ])
        assert not [r for r in res if isinstance(r, Exception)], f"two edits to different cells must both land: {res}"
        ok += 2
    state = a.get(run).run["state"]
    events = a.store.query("SELECT COUNT(*) AS n FROM events WHERE run_id=? AND kind='correct_value'", (run,))[0]["n"]
    assert len(state.get("overrides", {})) == ok == events, "every correction is in the state and the log"
    assert a.store.verify_chain() == (True, None)


def test_two_reviewers_changing_the_same_cell_at_once_one_is_refused(two: tuple[Service, Service, int]) -> None:
    a, b, run = two
    vals = [x for x in a.get(run).spread.values if x.value is not None][:10]  # type: ignore[union-attr]
    for v in vals:
        res = _race([
            lambda v=v: a.act(run, {"type": "correct_value", "line": v.line, "period": v.period, "value": "1",
                                    "reason": "A thinks 1"}, "dev:rae"),
            lambda v=v: b.act(run, {"type": "correct_value", "line": v.line, "period": v.period, "value": "2",
                                    "reason": "B thinks 2"}, "dev:erin"),
        ])
        won = [r for r in res if not isinstance(r, Exception)]
        lost = [r for r in res if isinstance(r, Exception)]
        # Either the second arrived after the first had committed (it saw the first's value: a normal, logged
        # change), or both raced on the same state and exactly one was refused. Never a silent overwrite:
        assert len(won) + len(lost) == 2 and all("Someone else changed this" in str(e) for e in lost), res
        o = a.get(run).run["state"]["overrides"][f"{v.line}@{v.period}"]
        last = a.store.query("SELECT actor FROM events WHERE run_id=? AND kind='correct_value' ORDER BY id DESC LIMIT 1",
                             (run,))[0]["actor"]
        assert o["actor"] == last, "the state shows the last correction the log recorded"


def test_approving_a_spread_that_changed_since_it_was_opened_is_refused(two: tuple[Service, Service, int]) -> None:
    from spreader.service import StaleError

    a, b, run = two
    seen = a.get(run).run["version"]
    v = next(x for x in a.get(run).spread.values if x.value is not None)  # type: ignore[union-attr]
    b.act(run, {"type": "correct_value", "line": v.line, "period": v.period, "value": str(v.value), "reason": "x"}, "dev:rae")
    with pytest.raises(StaleError):
        a.act(run, {"type": "approve", "expected_version": seen}, "dev:ari")
    fresh = a.get(run).run["version"]
    assert fresh != seen
    a.act(run, {"type": "approve", "expected_version": fresh}, "dev:ari")
    assert a.get(run).run["state"]["approved"]["by"] == "dev:ari"


def test_a_correction_racing_an_approval_by_the_same_person_cannot_both_land(two: tuple[Service, Service, int]) -> None:
    a, b, run = two
    v = next(x for x in a.get(run).spread.values if x.value is not None)  # type: ignore[union-attr]
    for _ in range(5):
        res = _race([
            lambda: a.act(run, {"type": "correct_value", "line": v.line, "period": v.period, "value": str(v.value),
                                "reason": "same"}, "dev:erin"),
            lambda: b.act(run, {"type": "approve"}, "dev:erin", separation=(True, True)),
        ])
        state = a.get(run).run["state"]
        if state.get("approved"):
            assert not any(o["actor"] == "dev:erin" for o in state.get("overrides", {}).values()), res
            a.act(run, {"type": "reopen"}, "dev:ari")
        assert all(not isinstance(r, Exception) or isinstance(r, (ActionError, SeparationError, sqlite3.OperationalError))
                   for r in res), res


def test_duplicate_requests_do_not_duplicate_business_actions(two: tuple[Service, Service, int], profile: Any) -> None:
    a, b, run = two
    res = _race([lambda: a.act(run, {"type": "approve"}, "dev:ari"), lambda: b.act(run, {"type": "approve"}, "dev:ari")])
    assert sum(1 for r in res if not isinstance(r, Exception)) == 1
    assert a.store.query("SELECT COUNT(*) AS n FROM events WHERE run_id=? AND kind='approve'", (run,))[0]["n"] == 1
    # the same upload twice (a retry, a double click): one document, the same run
    d1, v1 = a.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    d2, v2 = b.upload("a-again.htm", STATEMENT.read_bytes(), "dev:pat")
    assert d1["id"] == d2["id"] and a.store.query("SELECT COUNT(*) AS n FROM documents")[0]["n"] == 1


def test_an_action_interrupted_before_commit_leaves_nothing_behind(two: tuple[Service, Service, int],
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    a, _, run = two
    before = a.get(run).run["state"]
    n_events = a.store.query("SELECT COUNT(*) AS n FROM events")[0]["n"]

    def crash(*args: Any, **kw: Any) -> None:
        raise OSError("power cut while writing the audit event")

    monkeypatch.setattr(a.store, "log", crash)
    with pytest.raises(OSError):
        a.act(run, {"type": "approve"}, "dev:ari")
    monkeypatch.undo()
    assert a.get(run).run["state"] == before, "no approval without its audit event"
    assert a.store.query("SELECT COUNT(*) AS n FROM events")[0]["n"] == n_events
    assert a.store.query("SELECT COUNT(*) AS n FROM approved_values")[0]["n"] == 0
    a.act(run, {"type": "approve"}, "dev:ari")  # and the retry works
    assert a.get(run).run["state"]["approved"]["by"] == "dev:ari"


def test_an_upload_interrupted_after_the_file_was_stored_can_be_retried(tmp_path: Path, profile: Any,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    real_tx = svc.store.tx
    calls = {"n": 0}

    def failing_tx() -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("database unavailable")
        return real_tx()

    monkeypatch.setattr(svc.store, "tx", failing_tx)
    with pytest.raises(OSError):
        svc.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    monkeypatch.undo()
    assert svc.store.query("SELECT COUNT(*) AS n FROM documents")[0]["n"] == 0  # the stored file alone is not a document
    _, view = svc.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    assert view.run["status"] == "succeeded"


# -- backups and anchors -------------------------------------------------------------------------------------------


@pytest.fixture()
def keyed(tmp_path: Path) -> Any:
    key = tmp_path / "keys" / "k.key"
    key.parent.mkdir()
    key.write_text(new_key(), encoding="ascii")
    set_vault(Vault(load_keys(key)))
    yield key
    set_vault(None)


def test_a_backup_taken_while_people_work_restores_to_a_verified_state(tmp_path: Path, profile: Any, keyed: Any) -> None:
    data = tmp_path / "data"
    svc = Service(Store(data / "spreader.sqlite3"), profile=profile)
    _, view = svc.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    run = view.run["id"]
    svc.act(run, {"type": "approve"}, "dev:ari")
    Database(data / "finops.sqlite3")
    stop = threading.Event()

    def keep_writing() -> None:
        while not stop.is_set():
            svc.act(run, {"type": "reopen"}, "dev:ari")
            svc.act(run, {"type": "approve"}, "dev:ari")

    t = threading.Thread(target=keep_writing)
    t.start()
    try:
        m = bk.backup(data, tmp_path / "backup")
    finally:
        stop.set()
        t.join(30)
    assert m["files"] and not m["key_included"]
    assert bk.verify_backup(tmp_path / "backup") == []
    # restore: copy the backup into an empty data folder and open it
    restored = tmp_path / "restored"
    shutil.copytree(tmp_path / "backup", restored)
    r = Service(Store(restored / "spreader.sqlite3"), profile=profile)
    assert r.store.verify_chain() == (True, None)
    assert r.get(run).spread is not None and r.store.document_bytes(view.run["document_id"], "html") == STATEMENT.read_bytes()
    assert bk.check_anchor(restored, m["anchor"]) == []
    # a changed backup is caught
    f = next((tmp_path / "backup" / "documents").iterdir())
    f.write_bytes(f.read_bytes()[:-1] + b"x")
    assert any("changed since the backup" in p for p in bk.verify_backup(tmp_path / "backup"))


def test_a_backup_is_refused_inside_the_data_folder(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    with pytest.raises(bk.BackupError, match="outside"):
        bk.backup(tmp_path / "data", tmp_path / "data" / "b")


def test_an_anchor_detects_a_rebuilt_chain_that_verifies_on_its_own(tmp_path: Path, profile: Any) -> None:
    data = tmp_path / "data"
    svc = Service(Store(data / "spreader.sqlite3"), profile=profile)
    _, view = svc.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    svc.act(view.run["id"], {"type": "approve"}, "dev:ari")
    Database(data / "finops.sqlite3")
    a = bk.anchor(data)
    assert bk.check_anchor(data, a) == []
    # someone with the file rewrites the approver of an early event and recomputes every hash after it
    raw = sqlite3.connect(data / "spreader.sqlite3", isolation_level=None)
    raw.row_factory = sqlite3.Row
    raw.execute("DROP TRIGGER events_no_update")
    raw.execute("UPDATE events SET actor='dev:mallory' WHERE kind='approve'")
    prev = "genesis"
    for r in raw.execute("SELECT * FROM events ORDER BY id").fetchall():
        h = _event_hash(prev, r, _sha(r["payload"]))
        raw.execute("UPDATE events SET prev_hash=?, hash=?, payload_sha=? WHERE id=?", (prev, h, _sha(r["payload"]), r["id"]))
        prev = h
    raw.close()
    assert Store(data / "spreader.sqlite3").verify_chain() == (True, None), "the rebuilt chain fits on its own"
    problems = bk.check_anchor(data, a)
    assert problems and "rewritten" in problems[0]


def test_the_backup_commands(tmp_path: Path, profile: Any) -> None:
    from spreader.cli import main

    data = tmp_path / "data"
    svc = Service(Store(data / "spreader.sqlite3"), profile=profile)
    svc.upload("a.htm", STATEMENT.read_bytes(), "dev:pat")
    assert main(["backup", "backup", str(tmp_path / "b"), "--data", str(data)]) == 0
    assert main(["backup", "backup", str(tmp_path / "b"), "--data", str(data)]) == 1  # not into a used folder
    assert main(["backup", "verify-backup", str(tmp_path / "b")]) == 0
    assert main(["backup", "anchor", str(tmp_path / "anchor.json"), "--data", str(data)]) == 0
    assert main(["backup", "check-anchor", str(tmp_path / "anchor.json"), "--data", str(data)]) == 0
    a = json.loads((tmp_path / "anchor.json").read_text())
    a["statement"]["hash"] = "0" * 64
    (tmp_path / "anchor.json").write_text(json.dumps(a))
    assert main(["backup", "check-anchor", str(tmp_path / "anchor.json"), "--data", str(data)]) == 1


def test_a_stale_approval_through_the_api_is_a_409(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import client_as
    from spreader import api

    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    monkeypatch.setattr(api, "service", lambda: svc)
    view = client_as(api.app, "pat").post("/api/documents", files={"file": ("a.htm", STATEMENT.read_bytes())}).json()
    run, seen = view["run"]["id"], view["run"]["version"]
    v = next(x for x in view["spread"]["values"] if x["value"] is not None)
    rae = client_as(api.app, "rae")
    assert rae.post(f"/api/runs/{run}/actions", json={"type": "correct_value", "line": v["line"], "period": v["period"],
                                                      "value": str(v["value"]), "reason": "checked"}).status_code == 200
    ari = client_as(api.app, "ari")
    r = ari.post(f"/api/runs/{run}/actions", json={"type": "approve", "expected_version": seen})
    assert r.status_code == 409 and "changed since you opened it" in r.json()["detail"]
    fresh = ari.get(f"/api/runs/{run}").json()["run"]["version"]
    assert ari.post(f"/api/runs/{run}/actions", json={"type": "approve", "expected_version": fresh}).status_code == 200
