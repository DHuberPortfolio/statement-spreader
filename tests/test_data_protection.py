"""Encryption at rest, retention, erasure and legal holds (DECISIONS D45, D46), through the services and the API."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from conftest import client_as
from finops import api as fapi
from finops.core import retention as rt
from finops.core.audit import Database
from finops.core.vault import MAGIC, Vault, VaultError, load_keys, new_key, set_vault, vault
from spreader import api
from spreader.service import Service
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html"
STATEMENT_2 = ROOT / "eval" / "synthetic" / "s7-002-clean" / "statement.html"
INVOICES = ROOT / "eval" / "invoice" / "dev"


@pytest.fixture()
def env(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from finops.dq.service import DQService
    from finops.invoice.service import InvoiceService
    from finops.recon.service import ReconService
    from finops.sheets.service import SheetsService

    keys = tmp_path / "keys" / "data.key"
    keys.parent.mkdir()
    keys.write_text(new_key() + "\n", encoding="ascii")
    data = tmp_path / "data"
    set_vault(Vault(load_keys(keys, data)))
    db = Database(data / "finops.sqlite3")
    fd = data / "finops-files"
    fapi.configure(db, ReconService(db, fd, ROOT / "config" / "finops" / "recon"),
                   InvoiceService(db, fd / "invoices", ROOT / "config" / "finops" / "invoice" / "default-ap.yaml",
                                  INVOICES / "master", data / "bank-fingerprint.key"),
                   DQService(db, fd / "dq", ROOT / "config" / "finops" / "dq"),
                   SheetsService(db, fd / "sheets", ROOT / "config" / "finops" / "sheets" / "default.yaml"))
    svc = Service(Store(data / "spreader.sqlite3"), profile=profile)
    monkeypatch.setattr(api, "service", lambda: svc)
    monkeypatch.setattr(api, "DATA_DIR", data)
    monkeypatch.setenv("FINOPS_OUTCOMES_DIR", str(data / "outcomes"))
    yield {"data": data, "db": db, "svc": svc, "keys": keys,
           "platform": rt.Platform(store=svc.store, db=db, data_dir=data, outcomes_dir=data / "outcomes")}
    set_vault(None)
    fapi.configure(None)  # type: ignore[arg-type]


def _stored(data: Path) -> list[Path]:
    return [p for p in (data / "documents").rglob("*") if p.is_file()] + \
           [p for p in (data / "finops-files").rglob("*") if p.is_file()]


def _fill(env: Any) -> dict[str, Any]:
    """One unit of every engine, through the API as the people who would do it."""
    pat, rae, ari = client_as(api.app, "pat"), client_as(api.app, "rae"), client_as(api.app, "ari")
    a = pat.post("/api/documents", files={"file": ("a.htm", STATEMENT.read_bytes())}, data={"company_id": "acme"}).json()
    b = pat.post("/api/documents", files={"file": ("b.htm", STATEMENT_2.read_bytes())}, data={"company_id": "acme"}).json()
    assert ari.post(f"/api/runs/{a['run']['id']}/actions", json={"type": "approve"}).status_code == 200
    wid = pat.post("/api/finops/recon/workspaces", json={"name": "Op account", "profile": "bank-vs-gl.yaml"}).json()["id"]
    run = pat.post(f"/api/finops/recon/workspaces/{wid}/sample", json={}).json()
    prop = next(g for g in run["result"]["groups"] if g["status"] == "proposed")
    assert rae.post(f"/api/finops/recon/runs/{run['run']['id']}/accept", json={"group_id": prop["id"], "note": "checked"}).status_code == 200
    truth = json.loads((INVOICES / "truth.json").read_text(encoding="utf-8"))
    inv = pat.post("/api/finops/invoices", files={"file": (Path(truth["inbox"][0]["file"]).name,
                                                           (INVOICES / truth["inbox"][0]["file"]).read_bytes())}).json()
    pat.post("/api/finops/dq/sample", json={})
    pat.post("/api/finops/sheets/sample", json={})
    return {"doc_a": a["run"]["document_id"], "doc_b": b["run"]["document_id"], "workspace": wid,
            "invoice": inv["document"]["doc_id"] if "document" in inv else inv["doc_id"]}


# -- encryption at rest -------------------------------------------------------------------------------------------


def test_every_engines_stored_files_are_encrypted_and_still_work(env: Any) -> None:
    _fill(env)
    files = _stored(env["data"])
    assert len(files) >= 8
    plain = [f for f in files if not f.read_bytes().startswith(MAGIC)]
    assert not plain, f"stored unencrypted: {plain}"
    assert b"Revenue" not in (env["data"] / "documents").glob("*").__next__().read_bytes()
    # the documents still read back: re-run a statement and fetch a PDF-free view
    rid = client_as(api.app, "pat").post(f"/api/documents/{env['svc'].documents()[0]['id']}/runs", json={}).json()["run"]["id"]
    assert client_as(api.app, "vic").get(f"/api/runs/{rid}").status_code == 200


def test_a_stored_file_that_was_altered_or_swapped_does_not_decrypt(env: Any) -> None:
    v = vault()
    a, b = env["data"] / "x" / "aaa", env["data"] / "x" / "bbb"
    v.write(a, b"statement A")
    v.write(b, b"statement B")
    assert v.read(a) == b"statement A"
    b.write_bytes(a.read_bytes())  # swap: A's ciphertext under B's name
    with pytest.raises(VaultError, match="does not decrypt"):
        v.read(b)
    blob = bytearray(a.read_bytes())
    blob[-1] ^= 1
    a.write_bytes(bytes(blob))
    with pytest.raises(VaultError, match="does not decrypt"):
        v.read(a)
    with pytest.raises(VaultError, match="not configured"):
        Vault([b"\x01" * 32]).read(env["data"] / "x" / "bbb")


def test_keys_are_kept_away_from_the_data_and_never_printed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    inside = data / "k.key"
    inside.parent.mkdir()
    inside.write_text(new_key(), encoding="ascii")
    with pytest.raises(VaultError, match="inside the data folder"):
        load_keys(inside, data)
    bad = tmp_path / "bad.key"
    bad.write_text("not base64 !!", encoding="ascii")
    with pytest.raises(VaultError):
        load_keys(bad)
    short = tmp_path / "short.key"
    short.write_text("AAAA", encoding="ascii")
    with pytest.raises(VaultError, match="32 bytes"):
        Vault(load_keys(short))
    key = load_keys(inside)[0]
    assert key.hex() not in repr(Vault([key])) and str(key) not in repr(Vault([key]))
    set_vault(None)
    monkeypatch.delenv("FINOPS_DATA_KEY_FILE", raising=False)
    monkeypatch.setenv("FINOPS_ENV", "production")
    try:
        with pytest.raises(VaultError, match="production"):
            vault()
    finally:
        set_vault(None)


def test_migration_encrypts_old_files_and_rotates_keys(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "old1").write_bytes(b"plain one")
    (folder / "old2").write_bytes(b"plain two")
    k1, k2 = load_keys_from(tmp_path, "k1"), load_keys_from(tmp_path, "k2")
    v1 = Vault([k1])
    assert v1.migrate(folder) == {"encrypted": 2, "re-encrypted": 0, "already": 0}
    assert v1.migrate(folder) == {"encrypted": 0, "re-encrypted": 0, "already": 2}  # safe to run again
    v2 = Vault([k2, k1])  # new key first, old key still there to read
    assert v2.migrate(folder) == {"encrypted": 0, "re-encrypted": 2, "already": 0}
    assert Vault([k2]).read(folder / "old1") == b"plain one"


def load_keys_from(tmp: Path, name: str) -> bytes:
    f = tmp / f"{name}.key"
    f.write_text(new_key(), encoding="ascii")
    return load_keys(f)[0]


def test_the_vault_command_reports_and_migrates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from spreader.cli import main

    data = tmp_path / "data"
    (data / "documents").mkdir(parents=True)
    (data / "documents" / "d1.htm").write_bytes(b"<html>plain</html>")
    key = tmp_path / "keys" / "k.key"
    assert main(["vault", "new-key", "--out", str(key)]) == 0
    assert main(["vault", "new-key", "--out", str(key)]) == 1  # never overwrites a key
    assert main(["vault", "new-key", "--out", str(data / "k2.key"), "--data", str(data)]) == 1  # not inside the data
    assert main(["vault", "status", "--data", str(data), "--key", str(key)]) == 1  # plain files while a key exists
    assert main(["vault", "migrate", "--data", str(data), "--key", str(key)]) == 0
    assert main(["vault", "status", "--data", str(data), "--key", str(key)]) == 0
    assert (data / "documents" / "d1.htm").read_bytes().startswith(MAGIC)


# -- erasure --------------------------------------------------------------------------------------------------------


def test_erasing_a_statement_removes_its_content_and_keeps_a_minimal_record(env: Any) -> None:
    ids = _fill(env)
    store, doc = env["svc"].store, ids["doc_a"]
    assert store.query("SELECT COUNT(*) AS n FROM approved_values WHERE document_id=?", (doc,))[0]["n"] > 0
    adm = client_as(api.app, "adm")
    assert client_as(api.app, "ari").post("/api/admin/erasures", json={"engine": "statement", "unit": doc,
                                                                        "reason": "client request 42"}).status_code == 403
    r = adm.post("/api/admin/erasures", json={"engine": "statement", "unit": doc, "reason": "client request 42"})
    assert r.status_code == 200, r.text
    assert not list((env["data"] / "documents").glob(f"{doc}.*")), "the upload itself"
    assert store.query("SELECT COUNT(*) AS n FROM approved_values WHERE document_id=?", (doc,))[0]["n"] == 0
    runs = store.query("SELECT spread, state FROM runs WHERE document_id=?", (doc,))
    assert runs and all(r["spread"] is None and r["state"] == "{}" for r in runs), "spreads and review state"
    evs = store.query("SELECT kind, actor, payload FROM events WHERE document_id=?", (doc,))
    assert evs and all(e["payload"] == '{"erased": true}' for e in evs)
    assert {e["kind"] for e in evs} >= {"upload", "approve"} and {e["actor"] for e in evs} >= {"dev:pat", "dev:ari"}
    assert store.query("SELECT filename FROM documents WHERE id=?", (doc,))[0]["filename"] == "[erased]"
    assert store.verify_chain() == (True, None) and env["db"].verify_chain() == (True, None)
    # the other document is untouched
    other = store.query("SELECT payload FROM events WHERE document_id=?", (ids["doc_b"],))
    assert all(e["payload"] != '{"erased": true}' for e in other) and list((env["data"] / "documents").glob(f"{ids['doc_b']}.*"))
    done = adm.get("/api/admin/erasures").json()
    assert done["statement"][0]["completed_at"] and not done["incomplete"]
    outcome_lines = [json.loads(x) for f in (env["data"] / "outcomes").glob("*.jsonl") for x in f.read_text().splitlines()]
    assert not [o for o in outcome_lines if o.get("refs", {}).get("document") == doc]
    assert adm.get(f"/api/runs/{runs and store.query('SELECT id FROM runs WHERE document_id=?', (doc,))[0]['id']}").status_code != 500


@pytest.mark.parametrize("engine", ["recon", "invoice", "dq", "sheets"])
def test_erasing_a_platform_unit_removes_its_files_results_decisions_and_payloads(env: Any, engine: str) -> None:
    ids = _fill(env)
    p = env["platform"]
    unit = {"recon": f"workspace:{ids['workspace']}", "invoice": f"doc:{ids['invoice'][:12]}",
            "dq": "dataset:vendors", "sheets": next(u.unit for u in rt.units(p) if u.engine == "sheets")}[engine]
    before = {f.name for f in _stored(env["data"])}
    files = rt._files_of(p, engine, unit)
    counts = rt.erase(p, engine, unit, "retention test", "dev:adm")
    after = {f.name for f in _stored(env["data"])}
    assert files and not (files & after) and (files & before), "its stored files are gone"
    payloads = env["db"].query("SELECT payload FROM audit_events WHERE engine=? AND scope=?", (engine, unit))
    assert payloads and all(r["payload"] == '{"erased": true}' for r in payloads)
    assert counts["results"] > 0
    assert env["db"].verify_chain() == (True, None)
    assert (engine, unit) not in {(u.engine, u.unit) for u in rt.units(p)}
    assert rt.erase(p, engine, unit, "retention test", "dev:adm")["audit_payloads"] == 0  # again: nothing left to do


def test_a_file_shared_with_a_live_unit_is_kept(env: Any) -> None:
    pat = client_as(api.app, "pat")
    from finops.recon.synthetic import generate

    bank, ledger, _ = generate(7, 60)
    w1 = pat.post("/api/finops/recon/workspaces", json={"name": "one", "profile": "bank-vs-gl.yaml"}).json()["id"]
    w2 = pat.post("/api/finops/recon/workspaces", json={"name": "two", "profile": "bank-vs-gl.yaml"}).json()["id"]
    for w in (w1, w2):
        r = pat.post(f"/api/finops/recon/workspaces/{w}/run", files={"left": ("b.csv", bank), "right": ("l.csv", ledger)})
        assert r.status_code == 200, r.text
    p = env["platform"]
    shared = rt._files_of(p, "recon", f"workspace:{w1}")
    rt.erase(p, "recon", f"workspace:{w1}", "retention test", "dev:adm")
    assert all((env["data"] / "finops-files" / s).exists() for s in shared), "workspace two still uses them"
    rt.erase(p, "recon", f"workspace:{w2}", "retention test", "dev:adm")
    assert not any((env["data"] / "finops-files" / s).exists() for s in shared)


def test_a_legal_hold_blocks_erasure_until_released(env: Any) -> None:
    ids = _fill(env)
    adm = client_as(api.app, "adm")
    h = adm.post("/api/admin/holds", json={"engine": "statement", "unit": ids["doc_a"], "reason": "litigation hold LH-7"})
    assert h.status_code == 200
    r = adm.post("/api/admin/erasures", json={"engine": "statement", "unit": ids["doc_a"], "reason": "client request"})
    assert r.status_code == 409 and list((env["data"] / "documents").glob(f"{ids['doc_a']}.*"))
    with env["db"].tx() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("DELETE FROM legal_holds")
    assert adm.post(f"/api/admin/holds/{h.json()['id']}/release", json={"note": "x"}).status_code == 400  # needs a note
    assert adm.post(f"/api/admin/holds/{h.json()['id']}/release", json={"note": "counsel approved, ticket 9"}).status_code == 200
    assert adm.post("/api/admin/erasures", json={"engine": "statement", "unit": ids["doc_a"], "reason": "client request"}).status_code == 200


def test_an_interrupted_erasure_is_visible_and_finishes_when_run_again(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _fill(env)
    p = env["platform"]

    def boom(*a: Any, **k: Any) -> int:
        raise OSError("disk unavailable")

    monkeypatch.setattr(rt, "_delete_unreferenced_files", boom)
    with pytest.raises(OSError):
        rt.erase(p, "statement", ids["doc_a"], "client request", "dev:adm")
    assert [u["unit"] for u in rt.incomplete(p)] == [ids["doc_a"]]
    assert env["svc"].store.verify_chain() == (True, None)  # the half-done state is still consistent
    monkeypatch.undo()
    rt.erase(p, "statement", ids["doc_a"], "client request", "dev:adm")
    assert rt.incomplete(p) == [] and not list((env["data"] / "documents").glob(f"{ids['doc_a']}.*"))


def test_erasure_cannot_be_used_to_rewrite_other_history(env: Any) -> None:
    ids = _fill(env)
    store = env["svc"].store
    rt.erase(env["platform"], "statement", ids["doc_a"], "client request", "dev:adm")
    with store.tx() as c, pytest.raises(sqlite3.IntegrityError):  # an erased document's event: only the payload may go
        c.execute("UPDATE events SET actor='dev:mallory' WHERE document_id=?", (ids["doc_a"],))
    with store.tx() as c, pytest.raises(sqlite3.IntegrityError):  # a live document's event cannot be erased
        c.execute("UPDATE events SET payload='{\"erased\": true}' WHERE document_id=?", (ids["doc_b"],))
    with store.tx() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("DELETE FROM erasures")
    run_b = store.query("SELECT id FROM runs WHERE document_id=? ORDER BY id DESC", (ids["doc_b"],))[0]["id"]
    assert client_as(api.app, "ari").post(f"/api/runs/{run_b}/actions", json={"type": "approve"}).status_code == 200
    with store.tx() as c, pytest.raises(sqlite3.IntegrityError):  # a live document's approval cannot be deleted
        c.execute("DELETE FROM approved_values WHERE document_id=?", (ids["doc_b"],))
    with env["db"].tx() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE audit_events SET payload='{\"erased\": true}' WHERE engine='recon'")
    # and with the guards removed by another tool, faking an erasure is still detected
    raw = sqlite3.connect(env["data"] / "spreader.sqlite3", isolation_level=None)
    raw.execute("DROP TRIGGER events_no_update")
    raw.execute("UPDATE events SET payload='{\"erased\": true}' WHERE document_id=?", (ids["doc_b"],))
    raw.close()
    assert Store(env["data"] / "spreader.sqlite3").verify_chain()[0] is False


def test_the_policy_decides_what_is_due_and_never_deletes_by_default(env: Any) -> None:
    ids = _fill(env)
    p = env["platform"]
    later = datetime.now(UTC) + timedelta(days=40)
    assert rt.due(p, rt.load_policy(ROOT / "config" / "finops" / "retention" / "default.yaml"), later) == []
    pol = rt.RetentionPolicy.model_validate({"statement": {"keep_days": 30}, "recon": {"keep_days": 60}})
    assert {u.engine for u in rt.due(p, pol, later)} == {"statement"}
    rt.place_hold(p.db, "statement", ids["doc_a"], "audit request AR-1", "dev:adm")
    assert {u.unit for u in rt.due(p, pol, later)} == {ids["doc_b"]}
    (env["data"] / "stale.tmp").write_bytes(b"x")
    plan = rt.run(p, pol, "cli:test", apply=False, at=later + timedelta(days=2))
    assert plan["temporary_files"] == 1 and (env["data"] / "stale.tmp").exists()  # a plan changes nothing
    out = rt.run(p, pol, "cli:test", apply=True, at=later + timedelta(days=2))
    assert [e["unit"] for e in out["erased"]] == [ids["doc_b"]] and not out["failed"]
    assert not (env["data"] / "stale.tmp").exists()
    assert list((env["data"] / "documents").glob(f"{ids['doc_a']}.*")), "held"
    ex = rt.load_policy(ROOT / "config" / "finops" / "retention" / "example-seven-years.yaml")
    assert ex.statement.keep_days == 2557 and ex.sheets.keep_days == 365


def test_events_written_before_digests_are_reported_not_silently_kept(tmp_path: Path) -> None:
    db = Database(tmp_path / "f.sqlite3")
    with db.tx() as c:
        db.append_event(c, "recon", "workspace:1", "dev:pat", "decision", {"note": "new style"})
    raw = sqlite3.connect(tmp_path / "f.sqlite3", isolation_level=None)  # an old-style row, as written before today
    raw.execute("DROP TRIGGER audit_no_update")
    raw.execute("UPDATE audit_events SET payload_sha = ''")
    raw.close()
    db2 = Database(tmp_path / "f.sqlite3")
    with db2.tx() as c:
        c.execute("INSERT INTO erasures (engine, unit, reason, requested_by, requested_at) VALUES ('recon','workspace:1','t','x','t')")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE audit_events SET payload='{\"erased\": true}'")
