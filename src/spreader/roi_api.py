"""ROI routes: timed work sessions, assumptions, and the ROI report.

Time is measured as active time: the browser sends heartbeats only while the tab is visible and
the person has interacted in the last minute, and the server caps each heartbeat at 30 seconds,
so leaving a tab open does not inflate a session.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from . import roi
from .store import now

router = APIRouter()
MAX_HEARTBEAT_SECONDS = 30.0
REPORTS = Path(__file__).resolve().parents[2] / "eval" / "reports"
MANIFEST = REPORTS.parent / "sec" / "manifest.json"


def silent_error_rate() -> tuple[tuple[int, int] | None, str]:
    """The tool's silent error rate for the ROI page, from the latest-* reports every full evaluation run writes.

    The holdout half (never tuned on) from whichever run measured it last, else the dev half, labelled as such. The
    page used to read latest-dev only, which named runs never refreshed, so it showed a figure from the first day."""
    def load(name: str) -> tuple[float, dict[str, Any]] | None:
        # "Which run is newer" comes from the time the report records; file times are arbitrary after a clone
        # (IMPROVEMENT_LOG O1). Reports from before provenance existed fall back to the file time.
        p = REPORTS / f"{name}.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        created = (data.get("provenance") or {}).get("created")
        return (datetime.fromisoformat(created).timestamp() if created else p.stat().st_mtime), data

    holdout: list[tuple[float, tuple[int, int], str]] = []
    if h := load("latest-holdout"):
        r = h[1]["rates"]["silent_error_rate"]
        holdout.append((h[0], (int(r["n"]), int(r["d"])), f"evaluation '{h[1]['name']}', {h[1]['documents']} holdout filings, never tuned on"))
    if (a := load("latest-all")) and MANIFEST.exists():
        split = {t: v.get("split") for t, v in json.loads(MANIFEST.read_text()).items()}
        docs = [d for d in a[1]["documents_detail"] if split.get(d["doc"].split(":", 1)[-1]) == "holdout"]
        wrong = sum(d["buckets"].get("wrong_auto", 0) for d in docs)
        auto = wrong + sum(d["buckets"].get("correct_auto", 0) for d in docs)
        crashed = sum(1 for d in docs if d.get("error"))
        if auto:
            holdout.append((a[0], (wrong, auto), f"holdout half of evaluation '{a[1]['name']}', {len(docs)} filings"
                            + (f" ({crashed} crashed)" if crashed else "") + ", never tuned on"))
    if holdout:
        _, rate, source = max(holdout, key=lambda x: x[0])
        return rate, source
    if d := load("latest-dev"):
        r = d[1]["rates"]["silent_error_rate"]
        return (int(r["n"]), int(r["d"])), f"evaluation '{d[1]['name']}', {d[1]['documents']} dev filings (tuned on)"
    return None, ""


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
async def start_session(request: Request) -> dict[str, Any]:
    svc, actor_of = _svc()
    b = await _body(request)
    mode = b.get("mode")
    if mode not in {"baseline", "assisted"}:
        raise HTTPException(400, "mode must be 'baseline' or 'assisted'")
    doc = svc.store.document(str(b.get("document_id", "")))
    if doc is None:
        raise HTTPException(404, "Unknown document")
    run_id = b.get("run_id")
    if run_id is not None:
        if not isinstance(run_id, int) or isinstance(run_id, bool):
            raise HTTPException(400, "run_id must be a run number")
        owner = svc.store.query("SELECT document_id FROM runs WHERE id=?", (run_id,))
        if not owner or owner[0]["document_id"] != doc["id"]:
            raise HTTPException(400, "That run does not belong to this document")
    with svc.store.tx() as c:
        cur = c.execute("INSERT INTO work_sessions(document_id, run_id, mode, actor, started_at) VALUES (?,?,?,?,?)",
                        (doc["id"], run_id, mode, actor_of(), now()))
        sid = cur.lastrowid
        svc.store.log(c, "session_start", {"session": sid, "mode": mode}, actor_of(), run_id, doc["id"])
    return {"id": sid}


@router.post("/api/sessions/{sid}/heartbeat")
async def heartbeat(sid: int, request: Request) -> dict[str, Any]:
    svc, _ = _svc()
    b = await _body(request)
    try:
        delta = float(b.get("active_seconds", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "active_seconds must be a number") from exc
    if not math.isfinite(delta):
        raise HTTPException(400, "active_seconds must be a finite number")
    delta = max(0.0, min(delta, MAX_HEARTBEAT_SECONDS))
    with svc.store.tx() as c:
        row = c.execute("SELECT started_at, active_seconds FROM work_sessions WHERE id=? AND ended_at IS NULL", (sid,)).fetchone()
        if row is None:
            raise HTTPException(409, "Session is unknown or already ended")
        elapsed = (datetime.now(UTC) - datetime.fromisoformat(row["started_at"])).total_seconds() + 1
        delta = max(0.0, min(delta, elapsed - row["active_seconds"]))  # active time cannot exceed clock time
        cur = c.execute("UPDATE work_sessions SET active_seconds = active_seconds + ? WHERE id=? AND ended_at IS NULL",
                        (delta, sid))
        if cur.rowcount != 1:
            raise HTTPException(409, "Session is unknown or already ended")
    row = svc.store.query("SELECT active_seconds FROM work_sessions WHERE id=?", (sid,))[0]
    return {"active_seconds": row["active_seconds"]}


@router.post("/api/sessions/{sid}/end")
async def end_session(sid: int, request: Request) -> dict[str, Any]:
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
        # Hand-keyed values are compared with the approved spread of the same document only; an
        # unapproved spread may hold the tool's own errors, which must not count against the person.
        view = svc.get(int(s["run_id"]))
        if view.run["document_id"] == s["document_id"] and view.run["state"].get("approved") and view.spread is not None:
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
                                         "values_checked": checked}, actor_of(), s["run_id"], s["document_id"])
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
async def set_assumptions(request: Request) -> dict[str, Any]:
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
            if not math.isfinite(f) or f < 0 or (k.endswith("_share") and f > 1) or f > 1e9:
                raise HTTPException(400, f"'{k}' is out of range")
            c.execute("INSERT OR REPLACE INTO assumptions(key, value, source, note, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
                      (k, str(f), "entered", None, now(), actor_of()))
            changed[k] = f
        svc.store.log(c, "assumptions", changed, actor_of())
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
    silent, source = silent_error_rate()
    synthetic = any(r["note"] and "demo" in (r["note"] or "").lower() for r in rows)
    inp = roi.RoiInputs(assumptions=_assumptions(svc), sessions=sessions, compute_seconds=compute, silent_error=silent,
                        silent_error_source=source, synthetic_sessions=synthetic)
    out = roi.compute(inp).as_dict()
    out["sessions"] = {"baseline": sum(1 for s in sessions if s.mode == "baseline"),
                       "assisted": sum(1 for s in sessions if s.mode == "assisted")}
    return out
