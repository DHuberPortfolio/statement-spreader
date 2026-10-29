"""HTTP API (FastAPI). Thin: validation and HTTP status codes here, all logic in service.py.

Run locally:  .venv/Scripts/python -m uvicorn spreader.api:app --port 8765

Boundaries, stated plainly:
- Every /api route needs a signed-in user with the route's permission (auth_api.py, DECISIONS D43). The
  actor in the audit log is the identity the server established, never a name the client sends.
- Documents never come back as raw HTML (that would run a filing's markup in the browser). The
  evidence view gets the parsed table as text cells, or a rendered PNG of a PDF page.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .contracts import RowRole
from .export import to_csv, to_json, to_xlsx
from .ingest import MAX_BYTES
from .service import ActionError, SeparationError, Service, StaleError
from .store import Store, now

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SPREADER_DATA", ROOT / "var"))
WEB_DIST = ROOT / "web" / "dist"
REPORTS = ROOT / "eval" / "reports"

app = FastAPI(title="Statement Spreader", version=__version__)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("SPREADER_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)  # blocks DNS-rebinding hosts


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):  # type: ignore[no-untyped-def]
    """A web page on another site must not be able to drive this API from the reviewer's browser.

    Writes must come from this app's own origin (or from a non-browser client, which sends no
    Origin), and JSON bodies must be declared as JSON (a cross-site form cannot send that
    without a preflight the server never approves).
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        host = request.headers.get("host", "")
        if site == "cross-site" or (origin and origin.split("://", 1)[-1] != host):
            return JSONResponse(status_code=403, content={"error": "Cross-site request refused"})
        ctype = request.headers.get("content-type", "")
        if not ctype.startswith(("application/json", "multipart/form-data")):
            return JSONResponse(status_code=415, content={"error": "Send JSON (application/json) or a file upload"})
    return await call_next(request)
_service: Service | None = None


def service() -> Service:
    global _service
    if _service is None:
        from .llm import configured_model, shadow_model
        from .profile import load_profile

        model, model_id = configured_model()
        shadow, shadow_id = shadow_model()  # SPREADER_MODEL_ROLE=shadow: a hidden second opinion (D52)
        profile = load_profile(os.environ["SPREADER_PROFILE"]) if os.environ.get("SPREADER_PROFILE") else None
        _service = Service(Store(DATA_DIR / "spreader.sqlite3"), profile=profile, model=model, model_id=model_id,
                           shadow=shadow, shadow_id=shadow_id)
    return _service


def set_service(svc: Service) -> None:
    """Tests use this to point the API at a temporary store."""
    global _service
    _service = svc


def _actor() -> str:
    """The signed-in principal's name for the audit log (auth_api established it; nothing the client sends
    can change it)."""
    from finops.core.identity import current

    return current().actor


# Statement actions: what each one needs, on top of signing in (auth_api refines the route by action here).
ACTION_PERMISSION = {"correct_value": "edit", "remap_row": "edit", "exclude_row": "edit", "resolve_item": "review",
                     "approve": "approve", "reopen": "approve"}


@app.exception_handler(ActionError)
async def _action_error(_: Request, exc: ActionError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})


def _run_payload(view: Any) -> dict[str, Any]:
    svc = service()
    spread = view.spread
    out: dict[str, Any] = {"run": view.run, "spread": json.loads(spread.model_dump_json()) if spread else None}
    if spread is not None:
        out["lines"] = {ln.id: {"label": ln.label, "kind": ln.kind, "critical": ln.critical,
                                "statement": svc.profile.line_statement[ln.id].value}
                        for ln in svc.profile.lines.values()}
        out["summary"] = {
            "values": len(spread.values),
            "auto_accepted": sum(1 for v in spread.values if not v.flags),
            "open_blockers": sum(1 for i in spread.review if not i.resolved and i.severity.value == "blocker"),
            "open_warnings": sum(1 for i in spread.review if not i.resolved and i.severity.value == "warning"),
            "checks_passed": sum(1 for c in spread.checks if c.status.value == "pass"),
            "checks_failed": sum(1 for c in spread.checks if c.status.value == "fail"),
            "checks_skipped": sum(1 for c in spread.checks if c.status.value == "skipped"),
        }
    doc = svc.store.document(view.run["document_id"])
    out["document"] = dict(doc) if doc else None
    out["corrected_after_review"] = [{**c, "approved_label": _line_label(c["approved_line"]),
                                      "correct_label": _line_label(c["correct_line"])}
                                     for c in svc.corrections(int(view.run["id"]))]
    return out


def _line_label(line: str | None) -> str:
    if not line or line == "none":
        return "left off the spread"
    ln = service().profile.lines.get(line)
    return ln.label if ln else line


# ---- the learning period: a senior rules on disagreements (D53, D54) ----

RECENT_RULINGS = 200  # rulings listed on the senior's page; older ones stay in the report and the export


def _a_is_analyst(disagreement_id: int) -> bool:
    """Which of the two answers is shown as A: fixed per disagreement, unrelated to whose it is."""
    return hashlib.sha256(f"disagreement:{disagreement_id}".encode()).digest()[0] % 2 == 0


def _disagreement_view(d: dict[str, Any], blind: bool) -> dict[str, Any]:
    first, second = ("analyst", "model") if _a_is_analyst(d["id"]) else ("model", "analyst")
    line_of = {"analyst": d["analyst_line"], "model": d["model_line"]}
    rulable = d["status"] in {"open", "analyst_stands"}
    out = {k: d[k] for k in ("id", "run_id", "statement", "label", "section", "approved_at", "due_at", "status",
                             "verdict", "reason", "note", "ruled_by", "ruled_at")}
    doc = service().store.document(d["document_id"])
    out["document"] = doc["filename"] if doc else None
    out["answers"] = [{"key": k, "line": line_of[who], "label": _line_label(line_of[who]),
                       **({} if blind and rulable else {"who": who})} for k, who in (("a", first), ("b", second))]
    out["correct_line"] = d["correct_line"]
    out["correct_label"] = _line_label(d["correct_line"]) if d["correct_line"] else None
    if not (blind and rulable):
        out["approved_by"] = d["approved_by"]
    return out


@app.get("/api/disagreements")
def disagreements() -> dict[str, Any]:
    from .shadow import REASONS, blind_ruling, review_days

    svc = service()
    blind = blind_ruling()
    rows = svc.disagreements()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    # Everything still to rule on, and the most recent rulings: the full history is in the go-live report and export.
    rulable = [r for r in rows if r["status"] in {"open", "analyst_stands"}]
    ruled = [r for r in rows if r["status"] == "ruled"][-RECENT_RULINGS:]
    return {
        "items": [_disagreement_view(r, blind) for r in rulable + ruled],
        "recent_rulings_shown": len(ruled),
        "counts": counts, "reasons": REASONS, "review_days": review_days(), "blind": blind,
        "lines": {k.value: [{"id": ln.id, "label": ln.label} for ln in s.lines] for k, s in svc.profile.statements.items()},
    }


@app.post("/api/disagreements/{disagreement_id}/rule")
async def rule(disagreement_id: int, request: Request) -> dict[str, Any]:
    """body: {"choice": "a" | "b" | "neither", "correct_line": <line id or "none">, "reason": <key>, "note": "..."}"""
    from .shadow import blind_ruling

    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Body must be JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    choice = str(body.get("choice", ""))
    if choice not in {"a", "b", "neither"}:
        raise HTTPException(400, "choice is a, b or neither")
    a_is_analyst = _a_is_analyst(disagreement_id)
    verdict = "neither" if choice == "neither" else ("analyst" if (choice == "a") == a_is_analyst else "model")
    try:
        d = await run_in_threadpool(service().rule, disagreement_id, verdict, _actor(), str(body.get("reason", "")),
                                    str(body.get("note", "")), body.get("correct_line"))
    except SeparationError as exc:
        raise HTTPException(403, str(exc)) from exc
    return _disagreement_view(d, blind_ruling())


@app.get("/api/learning/report")
def learning_report() -> dict[str, Any]:
    """Whether the model is ready to go live, and the evidence (D55). Settles overdue disagreements first."""
    from .teaching import golive_report

    svc = service()
    svc.settle_overdue()
    return golive_report(svc.store)


@app.get("/api/health")
def health() -> dict[str, Any]:
    svc = service()
    return {"ok": True, "version": __version__, "profile": f"{svc.profile.id} {svc.profile.version}", "model": svc.model_id}


@app.get("/api/profile")
def profile() -> dict[str, Any]:
    p = service().profile
    return {
        "id": p.id, "version": p.version, "hash": p.content_hash, "title": p.title,
        "statements": {k.value: {"title": s.title, "lines": [{"id": ln.id, "label": ln.label, "kind": ln.kind,
                                                               "critical": ln.critical} for ln in s.lines]}
                       for k, s in p.statements.items()},
        "checks": [c.model_dump() for c in p.checks],
        "ratios": [r.model_dump() for r in p.ratios],
        "derived": [d.model_dump() for d in p.derived],
        "not_applicable": p.not_applicable,
    }


@app.get("/api/documents")
def documents() -> list[dict[str, Any]]:
    return service().documents()


@app.post("/api/documents")
async def upload(file: UploadFile = File(...), company_id: str | None = Form(default=None)) -> dict[str, Any]:
    """company_id: the organisation's identifier for the company (an SEC filing defaults to its CIK); a company's
    documents share its approved spreads and confirmed mappings (spreader.company)."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_BYTES // 1_000_000} MB")
    doc, view = await run_in_threadpool(service().upload, file.filename or "document", data, _actor(), company_id)
    return await run_in_threadpool(_run_payload, view)


@app.get("/api/outcomes")
def outcomes_summary() -> dict[str, Any]:
    """What reviewers' decisions have recorded for calibration so far (finops.core.outcomes, D40)."""
    from finops.core.outcomes import summary

    return summary()


@app.get("/api/companies")
def companies() -> list[dict[str, Any]]:
    return service().companies()


@app.post("/api/documents/{doc_id}/company")
async def set_company(doc_id: str, request: Request) -> dict[str, Any]:
    """Says which company an uploaded document is about; the document is re-run with that company's approvals."""
    if not re.fullmatch(r"[0-9a-f]{64}", doc_id):
        raise HTTPException(404, "Unknown document")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Body must be JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    view = await run_in_threadpool(service().set_company, doc_id, str(body.get("company_id", "")), _actor())
    return await run_in_threadpool(_run_payload, view)


@app.post("/api/documents/{doc_id}/runs")
def rerun(doc_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", doc_id):
        raise HTTPException(404, "Unknown document")
    return _run_payload(service().run(doc_id, _actor()))


@app.get("/api/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    try:
        return _run_payload(service().get(run_id))
    except ActionError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/runs/{run_id}/actions")
async def act(run_id: int, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Body must be JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    from finops.core.identity import require

    require(ACTION_PERMISSION.get(str(body.get("type", "")), "edit"))
    from .auth_api import auth

    sod = auth().cfg.separation_of_duties
    try:
        view = await run_in_threadpool(service().act, run_id, body, _actor(),
                                       (sod.approver_not_uploader, sod.approver_not_corrector))
    except SeparationError as exc:
        raise HTTPException(403, str(exc)) from exc
    except StaleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await run_in_threadpool(_run_payload, view)


@app.get("/api/runs/{run_id}/events")
def events(run_id: int) -> list[dict[str, Any]]:
    try:
        service().get(run_id)
    except ActionError as exc:
        raise HTTPException(404, str(exc)) from exc
    return service().events(run_id)


@app.get("/api/runs/{run_id}/source/{statement}")
def source_table(run_id: int, statement: str) -> dict[str, Any]:
    """The statement as the pipeline read it: rows of text cells with their row index and role."""
    try:
        view = service().get(run_id)
    except ActionError as exc:
        raise HTTPException(404, str(exc)) from exc
    if view.spread is None or statement not in view.spread.statements:
        raise HTTPException(404, "No such statement in this run")
    res = view.spread.statements[statement]
    t = res.table
    mapping_of = {m.row_index: m for m in res.mappings}
    rows = []
    for r in t.rows:
        m = mapping_of.get(r.index)
        rows.append({
            "index": r.index, "label": r.label, "section": r.section, "indent": r.indent, "bold": r.bold,
            "role": r.role.value, "unit": r.unit.value, "children": r.children,
            "values": {k: {"raw": v.raw, "displayed": None if v.displayed is None else str(v.displayed),
                           "ref": v.ref.model_dump() if v.ref else None, "note": v.note} for k, v in r.values.items()},
            "mapping": m.model_dump() if m else None,
            "header": r.role is RowRole.HEADER,
        })
    return {"statement": statement, "title": t.title, "table_index": t.table_index, "scale": t.scale.model_dump(),
            "share_scale": t.share_scale.model_dump() if t.share_scale else None,
            "periods": [p.model_dump() for p in t.periods], "rows": rows, "warnings": t.warnings}


@app.get("/api/documents/{doc_id}/pages/{page}.png")
def page_image(doc_id: str, page: int) -> Response:
    svc = service()
    doc = svc.store.document(doc_id) if re.fullmatch(r"[0-9a-f]{64}", doc_id) else None
    if doc is None or doc["format"] != "pdf":
        raise HTTPException(404, "Not a PDF document")
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(svc.store.document_bytes(doc_id, "pdf"))
    try:
        if not 1 <= page <= len(pdf):
            raise HTTPException(404, "No such page")
        img = pdf[page - 1].render(scale=1.5).to_pil()
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "max-age=3600"})
    finally:
        pdf.close()


def _export_meta(view: Any) -> dict[str, Any]:
    doc = service().store.document(view.run["document_id"])
    approved = view.run["state"].get("approved")
    return {"run_id": view.run["id"], "filename": doc["filename"] if doc else "",
            "approved": f"yes, by {approved['by']} at {approved['at']}" if approved else None, "exported_at": now()}


@app.get("/api/runs/{run_id}/export.{fmt}")
def export(run_id: int, fmt: str) -> Response:
    svc = service()
    view = svc.get(run_id)
    if view.spread is None:
        raise HTTPException(409, "This run has no spread to export")
    meta = _export_meta(view)
    if fmt == "xlsx":
        body, media = to_xlsx(view.spread, svc.profile, meta), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif fmt == "csv":
        body, media = to_csv(view.spread, svc.profile), "text/csv"
    elif fmt == "json":
        body, media = to_json(view.spread, meta), "application/json"
    else:
        raise HTTPException(404, "Formats: xlsx, csv, json")
    with svc.store.tx() as c:
        svc.store.log(c, "export", {"format": fmt, "approved": bool(meta["approved"])}, _actor(), run_id,
                      view.run["document_id"])
    name = f"spread-run{run_id}.{fmt}"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/evaluation")
def evaluation() -> dict[str, Any]:
    """The saved evaluation reports (eval/reports/*.json), newest first."""
    reports = []
    for p in sorted(REPORTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            r = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        reports.append({k: r.get(k) for k in ("name", "documents", "crashed", "profile", "rates", "cells", "error_kinds",
                                              "buckets", "seconds")} | {"file": p.name})
    return {"reports": reports}


from . import roi_api  # noqa: E402  (registers the ROI routes)

app.include_router(roi_api.router)

from finops.api import router as finops_router  # noqa: E402  (reconciliation, invoice, data-quality and spreadsheet engines)
from finops.dq.service import ActionError as DQActionError  # noqa: E402
from finops.invoice.service import ActionError as InvoiceActionError  # noqa: E402
from finops.recon.service import ActionError as ReconActionError  # noqa: E402
from finops.sheets.service import ActionError as SheetsActionError  # noqa: E402

app.include_router(finops_router)

from finops.core.identity import AuthError, Forbidden  # noqa: E402

from . import auth_api  # noqa: E402

app.include_router(auth_api.router)

from . import admin_api  # noqa: E402

app.include_router(admin_api.router)
app.add_middleware(auth_api.AuthMiddleware)  # outermost: identity is settled before anything else runs


@app.exception_handler(AuthError)
async def _auth_error(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": str(exc), "sign_in": True})


from finops.core.vault import VaultError  # noqa: E402


@app.exception_handler(VaultError)
async def _vault_error(_: Request, exc: VaultError) -> JSONResponse:
    """A stored file that does not decrypt is never served or processed as if it were the original."""
    return JSONResponse(status_code=500, content={"error": f"A stored file could not be read: {exc}"})


@app.exception_handler(Forbidden)
async def _forbidden(_: Request, exc: Forbidden) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": str(exc)})


@app.get("/api/audit/verify")
def audit_verify() -> dict[str, Any]:
    """Recompute both audit chains and report the first entry that does not fit (needs the audit permission)."""
    from finops.api import db

    ok, first_bad = db().verify_chain()
    s_ok, s_bad = service().store.verify_chain()
    return {"platform": {"intact": ok, "first_bad_event": first_bad},
            "statements": {"intact": s_ok, "first_bad_event": s_bad}}


@app.exception_handler(ReconActionError)
@app.exception_handler(InvoiceActionError)
@app.exception_handler(DQActionError)
@app.exception_handler(SheetsActionError)
async def _finops_action_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")
