"""HTTP routes for the reconciliation and invoice engines, mounted into the existing app.

Same boundaries as the statement engine's API (spreader/api.py): local, no sign-in, the
signed-in user's identity from auth_api (DECISIONS D43), cross-site writes refused by the app's
middleware. Errors a reviewer can act on come back as 400 {"error": "..."}.

Sample data: the "sample" routes load the synthetic sets (eval/), so the workflows can be tried
without any real financial data.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUpload

from finops.core.audit import Database
from finops.core.identity import require
from spreader.export import _safe_text as safe  # text that starts with = + - @ is written as plain text

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter(prefix="/api/finops")
_db: Database | None = None
_recon = None
_invoice = None
MAX_UPLOAD = 25 * 1024 * 1024


def _data_dir() -> Path:
    from spreader.api import DATA_DIR

    return DATA_DIR


def db() -> Database:
    global _db
    if _db is None:
        _db = Database(_data_dir() / "finops.sqlite3")
    return _db


def recon() -> Any:
    global _recon
    if _recon is None:
        from finops.recon.service import ReconService

        _recon = ReconService(db(), _data_dir() / "finops-files", ROOT / "config" / "finops" / "recon")
    return _recon


def invoices() -> Any:
    global _invoice
    if _invoice is None:
        from finops.invoice.service import InvoiceService

        _invoice = InvoiceService(
            db(), _data_dir() / "finops-files" / "invoices",
            Path(os.environ.get("FINOPS_AP_POLICY", ROOT / "config" / "finops" / "invoice" / "default-ap.yaml")),
            Path(os.environ.get("FINOPS_MASTER_DIR", ROOT / "eval" / "invoice" / "dev" / "master")),
            _data_dir() / "bank-fingerprint.key")
    return _invoice


_dq = None


def dq() -> Any:
    global _dq
    if _dq is None:
        from finops.dq.service import DQService

        _dq = DQService(db(), _data_dir() / "finops-files" / "dq", ROOT / "config" / "finops" / "dq")
    return _dq


_sheets = None


def sheets() -> Any:
    global _sheets
    if _sheets is None:
        from finops.sheets.service import SheetsService

        _sheets = SheetsService(db(), _data_dir() / "finops-files" / "sheets",
                                Path(os.environ.get("FINOPS_SHEETS_CONFIG", ROOT / "config" / "finops" / "sheets" / "default.yaml")))
    return _sheets


def configure(database: Database, recon_service: Any = None, invoice_service: Any = None, dq_service: Any = None,
              sheets_service: Any = None) -> None:
    """Tests point the routes at temporary services."""
    global _db, _recon, _invoice, _dq, _sheets
    _db, _recon, _invoice, _dq, _sheets = database, recon_service, invoice_service, dq_service, sheets_service


def attachment(name: str) -> str:
    """A download header that a file name cannot break: letters, digits, dot, dash and underscore only."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "export"
    return f'attachment; filename="{safe_name[:120]}"'


def _actor() -> str:
    from finops.core.identity import current

    return current().actor


async def _read(f: UploadFile) -> tuple[str, bytes]:
    data = await f.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"{f.filename} is larger than {MAX_UPLOAD // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(400, f"{f.filename} is empty")
    return f.filename or "upload", data


class Note(BaseModel):
    note: str = ""


class GroupAction(Note):
    group_id: str


class ManualMatch(Note):
    left: list[str]
    right: list[str]


class Resolve(Note):
    exception_id: str
    action: str


class Correction(Note):
    field: str
    value: str


class NewWorkspace(BaseModel):
    name: str
    profile: str = "bank-vs-gl.yaml"


# -- overview ------------------------------------------------------------------------------------

@router.get("/overview")
def overview() -> dict[str, Any]:
    ws = recon().workspaces()
    inv = invoices().inbox()
    return {
        "engines": [
            {"id": "statements", "name": "Financial statement spreading", "path": "/", "status": "available"},
            {"id": "recon", "name": "Reconciliation and exceptions", "path": "/recon", "workspaces": len(ws)},
            {"id": "invoices", "name": "Invoice intake and three-way matching", "path": "/invoices", "invoices": len(inv),
             "blocked": sum(1 for i in inv if i["eligibility"] == "blocked")},
        ],
        "authorization": "This software never approves or pays anything. Its best status is 'eligible for approval'.",
    }


# -- reconciliation ------------------------------------------------------------------------------

@router.get("/recon/profiles")
def recon_profiles() -> list[dict[str, str]]:
    return recon().profiles()


@router.get("/recon/workspaces")
def recon_workspaces() -> list[dict[str, Any]]:
    return recon().workspaces()


@router.post("/recon/workspaces")
def recon_create(body: NewWorkspace) -> dict[str, Any]:
    return {"id": recon().create_workspace(body.name, body.profile, _actor())}


@router.post("/recon/workspaces/{wid}/run")
async def recon_run(wid: int, left: UploadFile | None = File(default=None), right: UploadFile | None = File(default=None)) -> dict[str, Any]:
    lf = await _read(left) if left else None
    rf = await _read(right) if right else None
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(recon().run, wid, _actor(), lf, rf)


@router.post("/recon/workspaces/{wid}/sample")
def recon_sample(wid: int) -> dict[str, Any]:
    from finops.recon.synthetic import generate

    bank, ledger, _ = generate(7, 60)
    return recon().run(wid, _actor(), ("sample-bank.csv", bank), ("sample-ledger.csv", ledger))


@router.get("/recon/runs/{run_id}")
def recon_get(run_id: int) -> dict[str, Any]:
    return recon().get_run(run_id)


@router.post("/recon/runs/{run_id}/accept")
def recon_accept(run_id: int, body: GroupAction) -> dict[str, Any]:
    return recon().accept(run_id, body.group_id, _actor(), body.note)


@router.post("/recon/runs/{run_id}/reject")
def recon_reject(run_id: int, body: GroupAction) -> dict[str, Any]:
    return recon().reject(run_id, body.group_id, _actor(), body.note)


@router.post("/recon/runs/{run_id}/manual")
def recon_manual(run_id: int, body: ManualMatch) -> dict[str, Any]:
    return recon().manual_match(run_id, body.left, body.right, _actor(), body.note)


@router.post("/recon/runs/{run_id}/resolve")
def recon_resolve(run_id: int, body: Resolve) -> dict[str, Any]:
    return recon().resolve(run_id, body.exception_id, body.action, _actor(), body.note)


@router.get("/recon/workspaces/{wid}/events")
def recon_events(wid: int) -> list[dict[str, Any]]:
    return recon().events(wid)


@router.get("/recon/runs/{run_id}/export.csv")
def recon_export(run_id: int) -> Response:
    """One row per record: its match (or none), the match status and rule, and its open exceptions."""
    res = recon().result(run_id)
    gof = res.group_of()
    exc: dict[str, list[str]] = {}
    for e in res.exceptions:
        for s in e.subjects:
            exc.setdefault(s, []).append(f"{e.code} ({e.status.value})")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["record", "source", "file", "row", "date", "amount", "currency", "reference", "description", "match_id",
                "match_status", "rule", "decided_by", "exceptions"])
    for t in sorted(res.records.values(), key=lambda t: (t.source, t.date, t.id)):
        g = gof.get(t.id)
        w.writerow([safe(t.id), t.source, safe(t.file), t.row, t.date.isoformat(), str(t.amount), t.currency, safe(t.reference),
                    safe(t.description), g.id if g else "", g.status.value if g else "unmatched", g.rule if g else "",
                    safe(g.decided_by) if g else "", "; ".join(exc.get(t.id, []))])
    body = buf.getvalue()
    wid = db().query("SELECT workspace_id FROM recon_runs WHERE id = ?", (run_id,))
    with db().tx() as c:  # data leaving the platform is recorded under the person who took it
        db().append_event(c, "recon", f"workspace:{wid[0]['workspace_id'] if wid else '?'}", _actor(), "exported",
                          {"run": run_id, "rows": len(res.records)})
    return Response(body, media_type="text/csv", headers={"Content-Disposition": attachment(f"reconciliation-run{run_id}.csv")})


# -- invoices --------------------------------------------------------------------------------------

@router.get("/invoices")
def invoice_list() -> list[dict[str, Any]]:
    return invoices().inbox()


@router.post("/invoices")
async def invoice_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    name, data = await _read(file)
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(invoices().upload, name, data, _actor())


@router.post("/invoices/sample")
def invoice_sample() -> dict[str, Any]:
    """Load the synthetic dev inbox, in order (only meaningful with the default sample master data)."""
    d = ROOT / "eval" / "invoice" / "dev"
    truth = json.loads((d / "truth.json").read_text(encoding="utf-8"))
    n = 0
    for doc in truth["inbox"]:
        invoices().upload(Path(doc["file"]).name, (d / doc["file"]).read_bytes(), _actor())
        n += 1
    return {"submitted": n}


@router.get("/invoices/export.csv")
def invoice_export() -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["doc_id", "file", "vendor", "vendor_id", "invoice_number", "currency", "total", "eligibility", "touchless", "open_exceptions"])
    for i in invoices().inbox():
        w.writerow([i["doc_id"][:12], safe(i["name"] or ""), safe(i["vendor"] or ""), i["vendor_id"],
                    safe(str(i["invoice_number"] or "")), safe(str(i["currency"] or "")), i["total"], i["eligibility"],
                    i["touchless"], "; ".join(i["open"])])
    with db().tx() as c:
        db().append_event(c, "invoice", "inbox", _actor(), "exported", {"kind": "inbox"})
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": attachment("invoices.csv")})


@router.get("/invoices/{doc_id}")
def invoice_get(doc_id: str) -> dict[str, Any]:
    return invoices().get(doc_id)


@router.post("/invoices/{doc_id}/reprocess")
def invoice_reprocess(doc_id: str) -> dict[str, Any]:
    return invoices().process(doc_id, _actor())


@router.post("/invoices/{doc_id}/correct")
def invoice_correct(doc_id: str, body: Correction) -> dict[str, Any]:
    return invoices().correct(doc_id, body.field, body.value, body.note, _actor())


@router.post("/invoices/{doc_id}/resolve")
def invoice_resolve(doc_id: str, body: Resolve) -> dict[str, Any]:
    if body.action == "verified_independently":  # accepting changed bank details is an approval (D43)
        require("approve")
    return invoices().resolve(doc_id, body.exception_id, body.action, body.note, _actor())


@router.get("/invoices/{doc_id}/events")
def invoice_events(doc_id: str) -> list[dict[str, Any]]:
    return invoices().events(doc_id)


# -- data-quality gate ---------------------------------------------------------------------------

class GateDecision(Note):
    record_id: str
    action: str  # release | reject | correct
    field: str | None = None
    value: str | None = None


@router.get("/dq/datasets")
def dq_datasets() -> list[dict[str, Any]]:
    return dq().datasets()


@router.get("/dq/runs")
def dq_runs() -> list[dict[str, Any]]:
    return dq().runs()


@router.post("/dq/runs")
async def dq_run(request: Request) -> dict[str, Any]:
    """Multipart form: `dataset` (a configuration file name), one file per source as `source_<id>`, optional
    `reference_<dataset>` files and an optional `previous` (the last accepted export)."""
    form = await request.form()
    dataset = str(form.get("dataset") or "")
    inputs: list[tuple[str, str, bytes]] = []
    refs: dict[str, tuple[str, bytes]] = {}
    previous = None
    for key, val in form.multi_items():
        if not isinstance(val, StarletteUpload):
            continue
        name, data = await _read(val)  # type: ignore[arg-type]
        if key.startswith("source_"):
            inputs.append((key[7:], name, data))
        elif key.startswith("reference_"):
            refs[key[10:]] = (name, data)
        elif key == "previous":
            previous = (name, data)
    from starlette.concurrency import run_in_threadpool

    run_id = await run_in_threadpool(dq().run, dataset, inputs, _actor(), refs, previous)
    return {"run": run_id}


@router.post("/dq/sample")
def dq_sample() -> dict[str, Any]:
    """The synthetic vendor and purchase-order exports (finops.dq.synthetic, seed 21): vendors from two systems
    against last month's accepted file, then purchase orders against the vendors this run accepted."""
    from finops.dq.synthetic import generate

    s = generate(21)
    actor = _actor()
    v = dq().run("vendors.yaml", [("portal", "sample-portal.csv", s.portal_csv), ("erp", "sample-erp.xlsx", s.erp_xlsx)], actor,
                 previous=("sample-last-accepted-vendors.csv", s.previous_csv))
    _, accepted = dq().export(v, "accepted", actor)
    p = dq().run("purchase_orders.yaml", [("erp", "sample-po.csv", s.po_csv)], actor, references={"vendors": ("vendors-accepted.csv", accepted)})
    return {"vendors": v, "purchase_orders": p}


@router.get("/dq/runs/{run_id}")
def dq_get(run_id: int) -> dict[str, Any]:
    return dq().get(run_id)


@router.post("/dq/runs/{run_id}/decide")
def dq_decide(run_id: int, body: GateDecision) -> dict[str, Any]:
    require({"release": "approve", "reject": "review", "correct": "edit"}.get(body.action, "edit"))
    return {"run": dq().decide(run_id, body.record_id, body.action, _actor(), body.note, body.field, body.value)}


@router.get("/dq/runs/{run_id}/export/{kind}.csv")
def dq_export(run_id: int, kind: str) -> Response:
    name, body = dq().export(run_id, kind, _actor())
    return Response(body, media_type="text/csv", headers={"Content-Disposition": attachment(name)})


@router.get("/dq/datasets/{dataset_id}/events")
def dq_events(dataset_id: str) -> list[dict[str, Any]]:
    return dq().events(dataset_id)


# -- spreadsheet risk scanner ----------------------------------------------------------------------

class Review(Note):
    finding_id: str
    action: str  # confirm | dismiss


@router.get("/sheets/scans")
def sheets_scans() -> list[dict[str, Any]]:
    return sheets().scans()


@router.post("/sheets/scans")
async def sheets_scan(request: Request) -> dict[str, Any]:
    """Multipart form: `workbook`, an optional `previous` version and an optional `model` name."""
    form = await request.form()
    wb = form.get("workbook")
    if not isinstance(wb, StarletteUpload):
        raise HTTPException(400, "Attach the workbook as 'workbook'")
    name, data = await _read(wb)  # type: ignore[arg-type]
    prev_f = form.get("previous")
    previous = await _read(prev_f) if isinstance(prev_f, StarletteUpload) else None  # type: ignore[arg-type]
    from starlette.concurrency import run_in_threadpool

    scan_id = await run_in_threadpool(sheets().scan, name, data, _actor(), previous, str(form.get("model") or "") or None)
    return {"scan": scan_id}


@router.post("/sheets/sample")
def sheets_sample() -> dict[str, Any]:
    """A synthetic budget with planted problems (finops.sheets.synthetic, seed 41), then an edited version of a
    clean budget compared with its original."""
    from finops.sheets.synthetic import generate

    books, pairs = generate(41)
    actor = _actor()
    one = sheets().scan(books[0].name, books[0].data, actor)
    p = pairs[0]
    two = sheets().scan(p.after.name, p.after.data, actor, (p.before.name, p.before.data))
    return {"scans": [one, two]}


@router.get("/sheets/scans/{scan_id}")
def sheets_get(scan_id: int) -> dict[str, Any]:
    return sheets().get(scan_id)


@router.post("/sheets/scans/{scan_id}/review")
def sheets_review(scan_id: int, body: Review) -> dict[str, Any]:
    return sheets().review(scan_id, body.finding_id, body.action, _actor(), body.note)


@router.get("/sheets/scans/{scan_id}/export.csv")
def sheets_export(scan_id: int) -> Response:
    name, body = sheets().export(scan_id, _actor())
    return Response(body, media_type="text/csv", headers={"Content-Disposition": attachment(name)})


@router.get("/sheets/models/{model}/events")
def sheets_events(model: str) -> list[dict[str, Any]]:
    return sheets().events(model)


# -- ROI -----------------------------------------------------------------------------------------

_ASSUMPTIONS_SQL = """CREATE TABLE IF NOT EXISTS finops_assumptions (
    key TEXT PRIMARY KEY, value REAL NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL)"""


def _entered() -> dict[str, float]:
    with db().tx() as c:
        c.execute(_ASSUMPTIONS_SQL)
    return {r["key"]: float(r["value"]) for r in db().query("SELECT key, value FROM finops_assumptions")}


@router.get("/roi")
def roi() -> dict[str, Any]:
    from finops.roi import compute

    return compute(ROOT / "eval" / "reports", _entered())


@router.put("/roi/assumptions")
def roi_assumptions(body: dict[str, float]) -> dict[str, Any]:
    from finops.core.audit import now
    from finops.roi import DEFAULTS

    known = {k for g in DEFAULTS.values() for k in g}
    bad = [k for k in body if k not in known]
    if bad:
        raise HTTPException(400, f"Unknown assumption(s): {', '.join(bad)}")
    for k, v in body.items():
        if not (v >= 0) or (k == "cash_realization_share" and v > 1):
            raise HTTPException(400, f"{k} must be {'between 0 and 1' if k == 'cash_realization_share' else 'zero or more'}")
    _entered()
    with db().tx() as c:
        for k, v in body.items():
            c.execute("INSERT INTO finops_assumptions (key, value, actor, at) VALUES (?,?,?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value, actor = excluded.actor, at = excluded.at",
                      (k, float(v), _actor(), now()))
        db().append_event(c, "roi", "assumptions", _actor(), "assumptions_changed", dict(body))
    return roi()
