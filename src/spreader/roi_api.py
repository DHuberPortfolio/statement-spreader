"""ROI routes: timed work sessions, assumptions, and the ROI report.

Time is measured as active time: the browser sends heartbeats only while the tab is visible and
the person has interacted in the last minute, and the server caps each heartbeat at 30 seconds,
so leaving a tab open does not inflate a session.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from . import roi
from .store import now

router = APIRouter()
MAX_HEARTBEAT_SECONDS = 30.0
REPORTS = Path(__file__).resolve().parents[2] / "eval" / "reports"


def _svc():  # imported lazily to avoid a cycle with api.py
    from .api import _actor, service

    return service(), _actor


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Body must be JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    return body


@router.post("/api/sessions")
async def start_session(request: Request, x_actor: str | None = Header(default=None)) -> dict[str, Any]:
    svc, actor_of = _svc()
    b = await _body(request)
    mode = b.get("mode")
    if mode not in {"baseline", "assisted"}:
        raise HTTPException(400, "mode must be 'baseline' or 'assisted'")
    doc = svc.store.document(str(b.get("document_id", "")))
    if doc is None:
        raise HTTPException(404, "Unknown document")
    run_id = b.get("run_id")
    with svc.store.tx() as c:
        cur = c.execute("INSERT INTO work_sessions(document_id, run_id, mode, actor, started_at) VALUES (?,?,?,?,?)",
                        (doc["id"], run_id, mode, actor_of(x_actor), now()))
        sid = cur.lastrowid
        svc.store.log(c, "session_start", {"session": sid, "mode": mode}, actor_of(x_actor), run_id, doc["id"])
    return {"id": sid}


@router.post("/api/sessions/{sid}/heartbeat")
async def heartbeat(sid: int, request: Request) -> dict[str, Any]:
    svc, _ = _svc()
    b = await _body(request)
    try:
        delta = float(b.get("active_seconds", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "active_seconds must be a number") from exc
    delta = max(0.0, min(delta, MAX_HEARTBEAT_SECONDS))
    with svc.store.tx() as c:
        cur = c.execute("UPDATE work_sessions SET active_seconds = active_seconds + ? WHERE id=? AND ended_at IS NULL",
                        (delta, sid))
        if cur.rowcount != 1:
            raise HTTPException(409, "Session is unknown or already ended")
    row = svc.store.query("SELECT active_seconds FROM work_sessions WHERE id=?", (sid,))[0]
    return {"active_seconds": row["active_seconds"]}


@router.post("/api/sessions/{sid}/end")
async def end_session(sid: int, request: Request, x_actor: str | None = Header(default=None)) -> dict[str, Any]:
    svc, actor_of = _svc()
    b = await _body(request)
    rows = svc.store.query("SELECT * FROM work_sessions WHERE id=?", (sid,))
    if not rows:
        raise HTTPException(404, "Unknown session")
    s = rows[0]
    if s["ended_at"]:
        return dict(s)  # ending twice is harmless
    entered = b.get("values") if isinstance(b.get("values"), dict) else {}
    errors = checked = None
    if s["mode"] == "baseline" and entered and s["run_id"]:
        # Hand-keyed values are compared with the run's spread as the reviewer left it.
        view = svc.get(int(s["run_id"]))
        if view.spread is not None:
            index = {f"{v.line}@{v.period}": v.value for v in view.spread.values}
            errors = checked = 0
            for k, raw in entered.items():
                if k not in index or index[k] is None:
                    continue
                try:
                    val = Decimal(str(raw).replace(",", ""))
                except InvalidOperation:
                    val = None
                checked += 1
                if val is None or abs(val - index[k]) > max(abs(index[k]) * Decimal("0.0005"), Decimal(1)):
                    errors += 1
    with svc.store.tx() as c:
        c.execute("UPDATE work_sessions SET ended_at=?, corrections=?, values_entered=?, errors_found=?, values_checked=?, note=?"
                  " WHERE id=?", (now(), int(b.get("corrections", 0) or 0), len(entered) or int(b.get("values_entered", 0) or 0),
                                  errors, checked, str(b.get("note", ""))[:500], sid))
        svc.store.log(c, "session_end", {"session": sid, "active_seconds": s["active_seconds"], "errors_found": errors,
                                         "values_checked": checked}, actor_of(x_actor), s["run_id"], s["document_id"])
    return dict(svc.store.query("SELECT * FROM work_sessions WHERE id=?", (sid,))[0])


@router.get("/api/sessions")
def sessions() -> list[dict[str, Any]]:
    svc, _ = _svc()
    return [dict(r) for r in svc.store.query("SELECT * FROM work_sessions ORDER BY id DESC")]


def _assumptions(svc: Any) -> dict[str, tuple[float, str]]:
    stored = {r["key"]: r for r in svc.store.query("SELECT * FROM assumptions")}
    out: dict[str, tuple[float, str]] = {}
    for k, (v, _) in roi.DEFAULT_ASSUMPTIONS.items():
        if k in stored:
            out[k] = (float(stored[k]["value"]), "entered")
        else:
            out[k] = (v, "default")
    return out


@router.put("/api/roi/assumptions")
async def set_assumptions(request: Request, x_actor: str | None = Header(default=None)) -> dict[str, Any]:
    svc, actor_of = _svc()
    b = await _body(request)
    changed = {}
    with svc.store.tx() as c:
        for k, v in b.items():
            if k not in roi.DEFAULT_ASSUMPTIONS:
                raise HTTPException(400, f"Unknown assumption '{k}'")
            try:
                f = float(v)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, f"'{k}' must be a number") from exc
            if f < 0 or (k.endswith("_share") and f > 1) or f > 1e9:
                raise HTTPException(400, f"'{k}' is out of range")
            c.execute("INSERT OR REPLACE INTO assumptions(key, value, source, note, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
                      (k, str(f), "entered", None, now(), actor_of(x_actor)))
            changed[k] = f
        svc.store.log(c, "assumptions", changed, actor_of(x_actor))
    return report()


@router.get("/api/roi")
def report() -> dict[str, Any]:
    svc, _ = _svc()
    rows = svc.store.query("SELECT * FROM work_sessions WHERE ended_at IS NOT NULL")
    sessions = [roi.Session(mode=r["mode"], document_id=r["document_id"], active_seconds=r["active_seconds"],
                            corrections=r["corrections"], values_entered=r["values_entered"], errors_found=r["errors_found"],
                            values_checked=r["values_checked"]) for r in rows]
    compute = []
    for r in svc.store.query("SELECT timings FROM runs WHERE status='succeeded' AND timings IS NOT NULL"):
        t = json.loads(r["timings"])
        compute.append(sum(t.values()) / 1000)
    silent = None
    source = ""
    for name in ("latest-holdout", "latest-all", "latest-dev"):
        p = REPORTS / f"{name}.json"
        if p.exists():
            rep = json.loads(p.read_text())
            r = rep["rates"]["silent_error_rate"]
            silent = (int(r["n"]), int(r["d"]))
            source = f"evaluation '{rep['name']}', {rep['documents']} documents"
            break
    synthetic = any(r["note"] and "demo" in (r["note"] or "").lower() for r in rows)
    inp = roi.RoiInputs(assumptions=_assumptions(svc), sessions=sessions, compute_seconds=compute, silent_error=silent,
                        silent_error_source=source, synthetic_sessions=synthetic)
    out = roi.compute(inp).as_dict()
    out["sessions"] = {"baseline": sum(1 for s in sessions if s.mode == "baseline"),
                       "assisted": sum(1 for s in sessions if s.mode == "assisted")}
    return out
