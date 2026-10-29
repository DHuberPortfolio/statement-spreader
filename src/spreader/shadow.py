"""The model's hidden second opinion during a learning period (DECISIONS D52).

With SPREADER_MODEL_ROLE=shadow the model takes no part in spreading. After a run succeeds, the model is asked
independently where every labelled row belongs, as if no rule had placed it, and its answer is stored next to the
platform's placement in `shadow_opinions`. Nothing here changes a run, a spread, a review item or the run's
idempotency key, and analysts are never shown the opinions: seeing them would anchor the decisions they are meant
to be compared with. Later steps compare them with what the analyst approved and send disagreements to a reviewer.

The model sees what it sees in the cascade (llm/local.py): labels and section headers, never numbers.
"""

from __future__ import annotations

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


def summary(opinions: list[Opinion]) -> dict[str, Any]:
    counts = {"rows": len(opinions), "agree": 0, "disagree": 0, "no_answer": 0}
    for o in opinions:
        counts[o.outcome] += 1
    return counts
