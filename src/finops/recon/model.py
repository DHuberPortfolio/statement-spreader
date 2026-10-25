"""The records and results a reconciliation run produces."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from finops.core.exceptions import ExceptionItem


class Txn(BaseModel):
    """One normalised transaction. The sign is always the company's: + money in, - money out."""

    id: str  # "<source>:<source id>" or "<source>:h<content hash>"
    source: str
    file: str
    row: int  # the row a person sees in the file (header = row 1)
    date: date
    amount: Decimal
    currency: str
    reference: str  # normalised ('' when none)
    description: str
    counterparty: str = ""
    raw: dict[str, str]  # the cells exactly as read
    content_hash: str  # changes when any normalised field changes; row order does not matter


class MatchStatus(str, Enum):
    AUTO = "auto_matched"  # the rules accepted it; no person involved
    ACCEPTED = "accepted"  # a person accepted it (a proposal or a manual match)
    PROPOSED = "proposed"  # the rules suggest it; a person must accept or reject


class MatchGroup(BaseModel):
    id: str
    left: list[str]
    right: list[str]
    rule: str  # reference | unique_amount_date | assignment | one_to_many | many_to_one | amount_difference | ambiguous | manual
    status: MatchStatus
    decided_by: str = "rules"
    note: str = ""
    difference: Decimal  # sum(left) - sum(right)
    date_gap_days: int
    explanation: list[str] = Field(default_factory=list)


class ReconResult(BaseModel):
    profile_id: str
    config_version: str
    engine_version: str
    left_name: str
    right_name: str
    left_label: str
    right_label: str
    period_end: date | None
    records: dict[str, Txn]
    groups: list[MatchGroup]
    exceptions: list[ExceptionItem]
    totals: dict[str, Any]
    checks: list[dict[str, Any]]
    timings_ms: dict[str, float] = Field(default_factory=dict)

    def group_of(self) -> dict[str, MatchGroup]:
        return {rid: g for g in self.groups for rid in g.left + g.right}
