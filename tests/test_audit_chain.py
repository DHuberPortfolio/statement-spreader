"""The statement engine's audit log is append-only and hash-chained (DECISIONS D44, THREAT_MODEL T41)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from conftest import client_as
from spreader import api
from spreader.service import Service
from spreader.store import SCHEMA_VERSION, Store

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"


def _store_with_events(tmp_path: Path, profile: Any) -> Store:
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    _, view = svc.upload("a.htm", SAMPLE.read_bytes(), "dev:pat")
    svc.act(view.run["id"], {"type": "approve"}, "dev:ari")
    return svc.store


def test_the_chain_verifies_and_the_database_refuses_edits(tmp_path: Path, profile: Any) -> None:
    store = _store_with_events(tmp_path, profile)
    assert store.verify_chain() == (True, None)
    with store.tx() as c, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        c.execute("UPDATE events SET actor='dev:mallory'")
    with store.tx() as c, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        c.execute("DELETE FROM events")


@pytest.mark.parametrize("attack", ["edit_actor", "edit_payload", "delete_middle", "insert_forged", "reorder"])
def test_an_edit_made_around_the_guards_is_detected(tmp_path: Path, profile: Any, attack: str) -> None:
    store = _store_with_events(tmp_path, profile)
    ids = [r["id"] for r in store.query("SELECT id FROM events ORDER BY id")]
    assert len(ids) >= 3
    raw = sqlite3.connect(tmp_path / "db.sqlite3", isolation_level=None)  # another tool, with the triggers removed
    raw.execute("DROP TRIGGER events_no_update")
    raw.execute("DROP TRIGGER events_no_delete")
    if attack == "edit_actor":
        raw.execute("UPDATE events SET actor='dev:mallory' WHERE id=?", (ids[1],))
    elif attack == "edit_payload":
        raw.execute("UPDATE events SET payload='{}' WHERE id=?", (ids[1],))
    elif attack == "delete_middle":
        raw.execute("DELETE FROM events WHERE id=?", (ids[1],))
    elif attack == "insert_forged":
        raw.execute("INSERT INTO events(run_id, document_id, at, actor, kind, payload, prev_hash, hash) "
                    "SELECT run_id, document_id, at, 'dev:mallory', 'approve', '{}', prev_hash, hash FROM events WHERE id=?",
                    (ids[-1],))
    else:
        a, b = raw.execute("SELECT kind, payload FROM events WHERE id IN (?, ?) ORDER BY id", (ids[0], ids[1])).fetchall()
        assert a != b
        raw.execute("UPDATE events SET kind=?, payload=? WHERE id=?", (*b, ids[0]))
        raw.execute("UPDATE events SET kind=?, payload=? WHERE id=?", (*a, ids[1]))
    raw.close()
    ok, first_bad = Store(tmp_path / "db.sqlite3").verify_chain()
    assert not ok and first_bad is not None


def test_a_schema_3_database_is_migrated_with_its_history_kept(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    c.execute("INSERT INTO meta VALUES ('schema_version', '3')")
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, document_id TEXT, at TEXT NOT NULL,"
              " actor TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
    for i in range(3):
        c.execute("INSERT INTO events(run_id, document_id, at, actor, kind, payload) VALUES (?,?,?,?,?,?)",
                  (None, f"d{i}", f"2026-10-2{i}T00:00:00+00:00", "dana", "upload", '{"size": 1}'))
    c.close()
    store = Store(path)
    rows = store.query("SELECT * FROM events ORDER BY id")
    assert [r["document_id"] for r in rows] == ["d0", "d1", "d2"] and all(r["hash"] for r in rows)
    assert store.verify_chain() == (True, None)
    assert store.query("SELECT value FROM meta WHERE key='chain_legacy_events'")[0]["value"] == "3"
    assert store.query("SELECT value FROM meta WHERE key='schema_version'")[0]["value"] == str(SCHEMA_VERSION)
    with store.tx() as c2:
        store.log(c2, "note", {"x": 1}, "dev:pat")
    assert store.verify_chain() == (True, None)
    Store(path)  # opening again changes nothing
    assert Store(path).verify_chain() == (True, None)


def test_the_audit_verify_route_needs_the_audit_permission(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store_with_events(tmp_path, profile)
    svc = Service(store, profile=profile)
    monkeypatch.setattr(api, "service", lambda: svc)
    from finops import api as fapi
    from finops.core.audit import Database

    monkeypatch.setattr(fapi, "_db", Database(tmp_path / "finops.sqlite3"))
    assert client_as(api.app, "pat").get("/api/audit/verify").status_code == 403
    r = client_as(api.app, "aud").get("/api/audit/verify")
    assert r.status_code == 200 and r.json()["statements"]["intact"] and r.json()["platform"]["intact"]
