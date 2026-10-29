"""The model's hidden second opinion during a learning period (DECISIONS D52).

With SPREADER_MODEL_ROLE=shadow the model takes no part in spreading. After a run succeeds, the model is asked
independently where every labelled row belongs, as if no rule had placed it, and its answer is stored next to the
platform's placement in `shadow_opinions`. Nothing here changes a run, a spread, a review item or the run's
idempotency key, and analysts are never shown the opinions: seeing them would anchor the decisions they are meant
to be compared with.

When the analyst approves, every row where the model's opinion differs from the approved placement becomes a
disagreement (D53) waiting for a senior's ruling; after SPREADER_SHADOW_REVIEW_DAYS without one, the analyst's
answer stands. The ruling itself is the next step.

The model sees what it sees in the cascade (llm/local.py): labels and section headers, never numbers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import RowRole, Spread, StatementRow, StatementTable
from .mapping import _unit_ok
from .profile import LineDef, Profile


class Asker(Protocol):
    def ask(self, table: StatementTable, row: StatementRow, lines: list[LineDef]) -> str | None: ...


@dataclass(frozen=True)
class Opinion:
    statement: str
    row_index: int
    label: str
    section: str
    platform_line: str | None  # where the platform placed the row (None: unplaced or left out)
    platform_excluded: bool
    platform_rule: str
    model_line: str | None  # a line id, "none" (belongs nowhere), or None (no usable answer)

    @property
    def outcome(self) -> str:
        """agree | disagree | no_answer."""
        if self.model_line is None:
            return "no_answer"
        platform = self.platform_line if self.platform_line and not self.platform_excluded else "none"
        return "agree" if self.model_line == platform else "disagree"


def second_opinions(spread: Spread, profile: Profile, model: Asker) -> list[Opinion]:
    out: list[Opinion] = []
    for result in spread.statements.values():
        table = result.table
        lines = profile.statements[table.statement].lines
        placed = {m.row_index: m for m in result.mappings}
        for row in table.rows:
            if row.role is RowRole.HEADER or not row.label or row.index not in placed:
                continue
            m = placed[row.index]
            answer = model.ask(table, row, [ln for ln in lines if _unit_ok(ln, row)])
            out.append(Opinion(table.statement.value, row.index, row.label, row.section or "", m.canonical,
                               bool(m.excluded), m.rule or "", answer))
    return out


def share() -> float:
    """SPREADER_SHADOW_SHARE: the share of documents the model gives an opinion on (D53). 1 (every document) by
    default; a company that will not spend the GPU time on all of them sets a share, e.g. 0.2."""
    raw = os.environ.get("SPREADER_SHADOW_SHARE", "1")
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if not 0 < value <= 1:
        raise ValueError(f"SPREADER_SHADOW_SHARE must be a number above 0 and at most 1, not {raw!r}")
    return value


def in_sample(doc_id: str) -> bool:
    """Whether a document is in the sample. Decided by its id, so every run of one document is in or out together and
    the sample is random with respect to anything about the document's content or who spread it."""
    s = share()
    return s >= 1 or int(doc_id[:8], 16) / 0x1_0000_0000 < s


def review_days() -> int:
    """SPREADER_SHADOW_REVIEW_DAYS: how long a disagreement waits for a senior's ruling before the analyst's answer
    stands (D53). 14 by default."""
    raw = os.environ.get("SPREADER_SHADOW_REVIEW_DAYS", "14")
    if not raw.isdigit() or not 1 <= int(raw) <= 365:
        raise ValueError(f"SPREADER_SHADOW_REVIEW_DAYS must be a whole number of days from 1 to 365, not {raw!r}")
    return int(raw)


def _switch(name: str, default: str = "1") -> bool:
    raw = os.environ.get(name, default).strip().lower()
    if raw not in {"0", "1", "on", "off", "true", "false"}:
        raise ValueError(f"{name} must be 1 or 0 (on or off), not {raw!r}")
    return raw in {"1", "on", "true"}


def blind_ruling() -> bool:
    """SPREADER_BLIND_RULING: the senior sees the two answers as A and B, not which is the analyst's and which the
    model's, until they have ruled (D54). On by default: a ruling that knows the source can lean towards or against the
    model, and the go-live measure would then measure the senior's view of the model."""
    return _switch("SPREADER_BLIND_RULING")


def flag_corrected() -> bool:
    """SPREADER_FLAG_CORRECTED: when a senior rules the approved answer wrong, the spread shows "corrected after review"
    to its analyst (D54, Devin). On by default."""
    return _switch("SPREADER_FLAG_CORRECTED")


# Why a senior ruled as they did: a closed list, so the reasons can be counted (D54).
REASONS = {
    "unusual_wording": "The document words this line unusually",
    "industry_specific": "An industry-specific line",
    "judgement_call": "A judgement call; either could be defended",
    "analyst_slip": "The analyst missed it (rushed, or new to this kind of line)",
    "model_misread": "The model misread the context",
    "other": "Something else (say what in the note)",
}


def summary(opinions: list[Opinion]) -> dict[str, Any]:
    counts = {"rows": len(opinions), "agree": 0, "disagree": 0, "no_answer": 0}
    for o in opinions:
        counts[o.outcome] += 1
    return counts
