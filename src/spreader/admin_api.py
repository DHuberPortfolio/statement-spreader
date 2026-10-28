"""Retention, erasure and legal holds over HTTP (admin permission; DECISIONS D46, finops.core.retention).

The same operations as `spreader retention ...` on the command line. Everything is recorded in the platform audit
chain under the signed-in administrator.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from finops.core import retention as rt
from finops.core.identity import current

router = APIRouter(prefix="/api/admin")
POLICY = Path(__file__).resolve().parents[2] / "config" / "finops" / "retention" / "default.yaml"


def platform() -> rt.Platform:
    from finops.api import db
    from finops.core.outcomes import directory

    from .api import DATA_DIR, service

    return rt.Platform(store=service().store, db=db(), data_dir=DATA_DIR, outcomes_dir=directory())


def policy() -> rt.RetentionPolicy:
    return rt.load_policy(os.environ.get("FINOPS_RETENTION_POLICY") or POLICY)


class ErasureRequest(BaseModel):
    engine: str
    unit: str
    reason: str


class HoldRequest(BaseModel):
    engine: str
    unit: str
    reason: str


class Release(BaseModel):
    note: str


def _fail(exc: rt.RetentionError) -> HTTPException:
    return HTTPException(409 if isinstance(exc, rt.HoldError) else 400, str(exc))


@router.get("/retention")
def retention_plan() -> dict[str, Any]:
    """What the policy would erase now, what is held, and erasures that did not finish."""
    return rt.run(platform(), policy(), current().actor, apply=False)


@router.post("/retention/run")
def retention_run() -> dict[str, Any]:
    return rt.run(platform(), policy(), current().actor, apply=True)


@router.get("/erasures")
def erasures() -> dict[str, Any]:
    p = platform()
    return {"statement": [dict(r) for r in p.store.query("SELECT * FROM erasures ORDER BY requested_at")],
            "platform": [dict(r) for r in p.db.query("SELECT * FROM erasures ORDER BY requested_at")],
            "incomplete": rt.incomplete(p)}


@router.post("/erasures")
def erase(body: ErasureRequest) -> dict[str, Any]:
    try:
        return {"erased": True, "counts": rt.erase(platform(), body.engine, body.unit, body.reason, current().actor)}
    except rt.RetentionError as exc:
        raise _fail(exc) from exc


@router.get("/holds")
def list_holds() -> list[dict[str, Any]]:
    return rt.holds(platform().db, active_only=False)


@router.post("/holds")
def place(body: HoldRequest) -> dict[str, Any]:
    try:
        return {"id": rt.place_hold(platform().db, body.engine, body.unit, body.reason, current().actor)}
    except rt.RetentionError as exc:
        raise _fail(exc) from exc


@router.post("/holds/{hold_id}/release")
def release(hold_id: int, body: Release) -> dict[str, Any]:
    try:
        rt.release_hold(platform().db, hold_id, current().actor, body.note)
    except rt.RetentionError as exc:
        raise _fail(exc) from exc
    return {"released": hold_id}
