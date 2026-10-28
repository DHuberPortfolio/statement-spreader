"""The invoice inbox: uploads, processing, corrections, decisions and the audit trail.

- The same file uploaded twice is one invoice: the second upload is logged and returns the
  first record (it can never become a second payable). Re-typed duplicates are caught by the
  duplicate rules instead.
- Processing is idempotent: the key is (file, policy version, master-data fingerprint, engine
  version, decisions on this invoice, outcomes of earlier invoices it depends on).
- Corrections keep the extracted value: the engine records it as `original` next to the
  corrected one, and the correction itself is an append-only row and an audit event.
- Bank-detail exceptions can only be resolved as "verified_independently", with a note that
  says how, by someone other than the person who uploaded the invoice (segregation of duties).
  Resolving one never changes vendor master data.
- Nothing here approves or pays. The best status an invoice reaches is "eligible for approval".
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from finops.core.audit import Database, now
from finops.core.config import ConfigError, load_config
from finops.core.exceptions import (
    ExceptionStatus,
    Resolution,
    ResolutionError,
    check_resolution,
    is_person,
    same_person,
)
from finops.core.fingerprint import content_hash, sha256_bytes
from finops.core.vault import vault

from .config import APPolicy
from .engine import CORRECTABLE, ENGINE_VERSION, history_entry, process
from .master import BankFingerprinter, Master, load_master
from .matching import History
from .model import Outcome

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS inv_documents (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL, size INTEGER NOT NULL,
        uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS inv_outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL REFERENCES inv_documents(doc_id),
        run_key TEXT NOT NULL, policy_version TEXT NOT NULL, engine_version TEXT NOT NULL,
        created_at TEXT NOT NULL, actor TEXT NOT NULL, outcome TEXT NOT NULL)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS inv_outcomes_key ON inv_outcomes(doc_id, run_key)""",
    """CREATE TABLE IF NOT EXISTS inv_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
        actor TEXT NOT NULL, at TEXT NOT NULL)""",
    """CREATE TRIGGER IF NOT EXISTS inv_decisions_no_update BEFORE UPDATE ON inv_decisions
       BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS inv_decisions_no_delete BEFORE DELETE ON inv_decisions
       BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END""",
]
BANK_CODES = {"BANK_DETAILS_CHANGED", "BANK_DETAILS_UNVERIFIED", "BANK_DETAILS_CONFLICT", "VENDOR_IDENTITY_CONFLICT"}
RESOLUTIONS = {"explained", "corrected_by_vendor", "accept_variance", "confirmed_not_duplicate", "rejected"}
MONEY = {"subtotal", "tax", "freight", "discount", "total"}
DATES = {"invoice_date", "due_date"}


class ActionError(ValueError):
    pass


class InvoiceService:
    def __init__(self, db: Database, files_dir: Path, policy_path: Path, master_dir: Path, key_path: Path):
        self.db = db
        self.files_dir = files_dir
        self.policy_path = policy_path
        self.master_dir = master_dir
        self.fp = BankFingerprinter.from_file(key_path)
        with db.tx() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    def _policy(self) -> tuple[APPolicy, str]:
        try:
            return load_config(APPolicy, self.policy_path)
        except ConfigError as exc:
            raise ActionError(f"The AP policy is invalid: {exc}") from exc

    def _master(self, policy: APPolicy) -> tuple[Master, str]:
        files = policy.master_data.model_dump()
        try:
            stamp = content_hash([sha256_bytes((self.master_dir / f).read_bytes()) for f in files.values()])
            return load_master(self.master_dir, files, self.fp), stamp
        except (OSError, ValueError) as exc:
            raise ActionError(f"Master data could not be read: {exc}") from exc

    # -- intake --------------------------------------------------------------------------------

    def upload(self, name: str, data: bytes, actor: str) -> dict[str, Any]:
        doc_id = sha256_bytes(data)
        existing = self.db.query("SELECT * FROM inv_documents WHERE doc_id = ?", (doc_id,))
        if not existing:  # refuse an unreadable file before it becomes an inbox row with no result
            policy, _ = self._policy()
            try:
                from .extract import extract

                extract(Path(name).name, data, policy, self.fp)
            except (ValueError, ArithmeticError, RecursionError, TypeError) as exc:
                raise ActionError(f"{Path(name).name}: {exc}"[:300]) from exc
        if existing:
            with self.db.tx() as c:
                self.db.append_event(c, "invoice", f"doc:{doc_id[:12]}", actor, "same_file_uploaded_again",
                                     {"name": Path(name).name, "first_uploaded_by": existing[0]["uploaded_by"]})
            return {**self.get(doc_id), "already_uploaded": True}
        vault().write(self.files_dir / doc_id, data)
        with self.db.tx() as c:
            c.execute("INSERT INTO inv_documents (doc_id, name, size, uploaded_by, uploaded_at) VALUES (?,?,?,?,?)",
                      (doc_id, Path(name).name[:200], len(data), actor, now()))
            self.db.append_event(c, "invoice", f"doc:{doc_id[:12]}", actor, "uploaded", {"name": Path(name).name, "size": len(data)})
        return {**self.process(doc_id, actor), "already_uploaded": False}

    def _decisions(self, doc_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, Resolution], int]:
        corrections: dict[str, dict[str, Any]] = {}
        resolutions: dict[str, Resolution] = {}
        rows = self.db.query("SELECT * FROM inv_decisions WHERE doc_id = ? ORDER BY id", (doc_id,))
        for r in rows:
            p = json.loads(r["payload"])
            if r["kind"] == "correct":
                corrections[p["field"]] = {"value": _typed(p["field"], p["value"]), "actor": r["actor"], "note": p.get("note", "")}
            elif r["kind"] == "resolve":
                resolutions[p["exception_id"]] = Resolution(action=p["action"], note=p.get("note", ""), actor=r["actor"], at=r["at"])
        return corrections, resolutions, len(rows)

    def _history(self, doc_id: str) -> History:
        seq = self.db.query("SELECT seq FROM inv_documents WHERE doc_id = ?", (doc_id,))[0]["seq"]
        h = History()
        for r in self.db.query("""SELECT o.outcome FROM inv_documents d JOIN inv_outcomes o ON o.doc_id = d.doc_id
                                  WHERE d.seq < ? AND o.id = (SELECT MAX(id) FROM inv_outcomes WHERE doc_id = d.doc_id)
                                  ORDER BY d.seq""", (seq,)):
            h.invoices.append(history_entry(Outcome.model_validate_json(r["outcome"])))
        return h

    def process(self, doc_id: str, actor: str) -> dict[str, Any]:
        doc = self.db.query("SELECT * FROM inv_documents WHERE doc_id = ?", (doc_id,))
        if not doc:
            raise ActionError("No such invoice")
        policy, version = self._policy()
        master, stamp = self._master(policy)
        corrections, resolutions, n_dec = self._decisions(doc_id)
        history = self._history(doc_id)
        key = content_hash([doc_id, version, stamp, ENGINE_VERSION, n_dec, history.invoices], 24)
        done = self.db.query("SELECT id FROM inv_outcomes WHERE doc_id = ? AND run_key = ?", (doc_id, key))
        if done:
            return {**self.get(doc_id), "reused": True}
        data = vault().read(self.files_dir / doc_id)
        try:
            outcome = process(doc[0]["name"], data, policy, master, history, self.fp, corrections, resolutions)
        except (ValueError, ArithmeticError, RecursionError, TypeError) as exc:
            raise ActionError(f"{doc[0]['name']}: {exc}"[:300]) from exc
        with self.db.tx() as c:
            c.execute("INSERT INTO inv_outcomes (doc_id, run_key, policy_version, engine_version, created_at, actor, outcome) "
                      "VALUES (?,?,?,?,?,?,?)", (doc_id, key, version, ENGINE_VERSION, now(), actor, outcome.model_dump_json()))
            self.db.append_event(c, "invoice", f"doc:{doc_id[:12]}", actor, "processed", {
                "eligibility": outcome.eligibility, "touchless": outcome.touchless, "matching": outcome.matching,
                "open_exceptions": [e.code for e in outcome.exceptions if e.status is ExceptionStatus.OPEN]})
        return {**self.get(doc_id), "reused": False}

    # -- reading -------------------------------------------------------------------------------

    def get(self, doc_id: str) -> dict[str, Any]:
        doc = self.db.query("SELECT * FROM inv_documents WHERE doc_id = ?", (doc_id,))
        if not doc:
            raise ActionError("No such invoice")
        o = self.db.query("SELECT * FROM inv_outcomes WHERE doc_id = ? ORDER BY id DESC LIMIT 1", (doc_id,))
        return {"document": dict(doc[0]), "outcome": json.loads(o[0]["outcome"]) if o else None,
                "processed_at": o[0]["created_at"] if o else None, "rejected": self._rejected(doc_id)}

    def _rejected(self, doc_id: str) -> bool:
        return any(json.loads(r["payload"]).get("action") == "rejected"
                   for r in self.db.query("SELECT payload FROM inv_decisions WHERE doc_id = ? AND kind = 'resolve'", (doc_id,)))

    def inbox(self) -> list[dict[str, Any]]:
        out = []
        for d in self.db.query("SELECT * FROM inv_documents ORDER BY seq DESC"):
            o = self.db.query("SELECT outcome FROM inv_outcomes WHERE doc_id = ? ORDER BY id DESC LIMIT 1", (d["doc_id"],))
            oc = json.loads(o[0]["outcome"]) if o else {}
            inv = oc.get("invoice", {}).get("fields", {})
            out.append({"doc_id": d["doc_id"], "name": d["name"], "uploaded_by": d["uploaded_by"], "uploaded_at": d["uploaded_at"],
                        "vendor": (inv.get("vendor_name") or {}).get("value"), "vendor_id": oc.get("vendor_id"),
                        "invoice_number": (inv.get("invoice_number") or {}).get("value"),
                        "total": (inv.get("total") or {}).get("value"), "currency": (inv.get("currency") or {}).get("value"),
                        "eligibility": "rejected" if self._rejected(d["doc_id"]) else oc.get("eligibility"),
                        "touchless": oc.get("touchless"),
                        "open": [e["code"] for e in oc.get("exceptions", []) if e["status"] == "open"]})
        return out

    def events(self, doc_id: str) -> list[dict[str, Any]]:
        return self.db.events("invoice", f"doc:{doc_id[:12]}")

    # -- decisions -------------------------------------------------------------------------------

    def _person(self, actor: str) -> None:
        if not is_person(actor):
            raise ActionError("A named reviewer must do this (set your name first); automated actors cannot.")

    def _decide(self, doc_id: str, kind: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        with self.db.tx() as c:
            c.execute("INSERT INTO inv_decisions (doc_id, kind, payload, actor, at) VALUES (?,?,?,?,?)",
                      (doc_id, kind, json.dumps(payload, default=str), actor, now()))
            self.db.append_event(c, "invoice", f"doc:{doc_id[:12]}", actor, f"decision_{kind}", payload)
        result = self.process(doc_id, actor)
        self._recheck_after(doc_id, actor)
        return result

    def _recheck_after(self, doc_id: str, actor: str) -> None:
        """A decision on one invoice can change what later invoices may bill (quantities, duplicates): re-check them.
        Processing is keyed on its inputs, so an invoice the decision does not affect is reused, not recomputed."""
        seq = self.db.query("SELECT seq FROM inv_documents WHERE doc_id = ?", (doc_id,))[0]["seq"]
        for r in self.db.query("SELECT doc_id FROM inv_documents WHERE seq > ? ORDER BY seq", (seq,)):
            self.process(r["doc_id"], actor)

    def correct(self, doc_id: str, field: str, value: str, note: str, actor: str) -> dict[str, Any]:
        self._person(actor)
        if field not in CORRECTABLE:
            raise ActionError(f"'{field}' cannot be corrected here; correctable: {', '.join(sorted(CORRECTABLE))}")
        try:
            typed = _typed(field, value)
        except ValueError as exc:
            raise ActionError(str(exc)) from exc
        if len(note.strip()) < 5:
            raise ActionError("Say where the corrected value comes from (e.g. 'as printed on page 1').")
        current = self.get(doc_id)["outcome"]
        old = ((current or {}).get("invoice", {}).get("fields", {}).get(field) or {}).get("value")
        return self._decide(doc_id, "correct", {"field": field, "value": str(typed), "was": old, "note": note.strip()}, actor)

    def resolve(self, doc_id: str, exception_id: str, action: str, note: str, actor: str) -> dict[str, Any]:
        cur = self.get(doc_id)
        oc = Outcome.model_validate(cur["outcome"]) if cur["outcome"] else None
        item = next((e for e in (oc.exceptions if oc else []) if e.id == exception_id), None)
        if item is None:
            raise ActionError("No such exception on this invoice")
        if item.status is not ExceptionStatus.OPEN:
            raise ActionError("This exception is already resolved")
        allowed = set(RESOLUTIONS)
        if item.code in BANK_CODES:
            allowed = {"verified_independently", "rejected"}
            if action == "verified_independently":
                if same_person(actor, cur["document"]["uploaded_by"]):
                    raise ActionError("This must be verified by someone other than the person who submitted the invoice.")
                if len(note.strip()) < 20 or len(re.findall(r"[A-Za-z]{2,}", note)) < 4:
                    raise ActionError("Describe the independent verification: who was called, on which number from the "
                                      "vendor master or contract, and when.")
        elif item.code == "EXACT_DUPLICATE":
            allowed = {"confirmed_not_duplicate", "rejected"}
        try:
            check_resolution(item, action, note, actor, allowed)
        except ResolutionError as exc:
            raise ActionError(str(exc)) from exc
        return self._decide(doc_id, "resolve", {"exception_id": item.id, "code": item.code, "action": action,
                                                "note": note.strip()}, actor)


def _typed(field: str, value: Any) -> Any:
    v = str(value).strip()
    if field in MONEY:
        try:
            d = Decimal(v.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"'{value}' is not an amount") from exc
        if not d.is_finite() or abs(d) >= Decimal("1e13"):
            raise ValueError(f"'{value}' is not an amount")
        return d
    if field in DATES:
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError as exc:
            raise ValueError(f"'{value}' is not a date (use YYYY-MM-DD)") from exc
    if not v:
        raise ValueError("A correction cannot be empty")
    return v[:200]
