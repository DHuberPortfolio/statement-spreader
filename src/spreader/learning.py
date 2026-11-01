"""What a statement reviewer's decisions say about the rules that produced the spread (DECISIONS D40).

Pure functions of the stored run, so the service writes them as decisions happen and scripts/export_outcomes.py can
rebuild them from the audit log. See finops.core.outcomes for where they go and how calibration reads them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from finops.core.outcomes import Outcome

from .contracts import RowMapping, Spread, StatementRow, StatementType

# Paths whose result is not a value placed on a line (scripts/calibrate.py), and the reviewer's own remembered mapping
# (counting it would only confirm the reviewer's earlier decision to themself).
NOT_JUDGED = {"none", "structure.cross_line_subtotal", "structure.ignored_section", "memory"}


def _power_of_ten(a: Decimal, b: Decimal) -> bool:
    if not a or not b:
        return False
    r = abs(a / b) if abs(a) > abs(b) else abs(b / a)
    return any(abs(r - Decimal(10) ** k) <= Decimal("0.001") * Decimal(10) ** k for k in range(1, 10))


def approval_outcomes(spread: Spread, state: dict[str, Any], refs: dict[str, Any], actor: str, at: str,
                      line_statement: dict[str, StatementType]) -> list[Outcome]:
    """At approval: rows the reviewer left alone were placed right; each statement's unit was right unless a value in
    it was corrected by a power of ten. Rows on lines whose value was corrected are not judged (the reading or the
    mapping may have been wrong)."""
    overrides = state.get("overrides", {})
    corrected = {k.split("@", 1)[0] for k in overrides}
    out: list[Outcome] = []
    for skey, res in spread.statements.items():
        rows = {r.index: r for r in res.table.rows}
        for m in res.mappings:
            if not m.canonical or m.excluded or (m.rule or "") in NOT_JUDGED or m.canonical in corrected:
                continue
            out.append(Outcome(engine="statements", method=m.rule or m.method.value, right=True, how="approved_unchanged",
                               subject=_subject(skey, rows.get(m.row_index), m), decided_by=actor, decided_at=at,
                               refs={**refs, "statement": skey, "row": m.row_index, "line": m.canonical,
                                     "label": rows[m.row_index].label_clean if m.row_index in rows else ""}))
        scaled = [k for k, o in overrides.items()
                  if line_statement.get(k.split("@", 1)[0]) is StatementType(skey) and o.get("previous") is not None
                  and _power_of_ten(Decimal(str(o["value"])), Decimal(str(o["previous"])))]
        s = res.table.scale
        out.append(Outcome(engine="units", method=s.rule, right=not scaled, how="corrected" if scaled else "approved_unchanged",
                           subject=f"{skey.replace('_', ' ')} unit: {s.multiplier:,}", decided_by=actor, decided_at=at,
                           refs={**refs, "statement": skey, "multiplier": s.multiplier, "corrected": scaled[:5]}))
    return out


def remap_outcome(skey: str, row: StatementRow, mapping: RowMapping | None, new_line: str, actor: str, at: str,
                  refs: dict[str, Any]) -> Outcome | None:
    """A reviewer moved a row to another line (or excluded it): the rule that placed it was wrong. None when the row
    had no placement to judge, or was moved to where it already was."""
    if mapping is None or not mapping.canonical or (mapping.rule or "") in NOT_JUDGED or mapping.canonical == new_line:
        return None
    return Outcome(engine="statements", method=mapping.rule or mapping.method.value, right=False,
                   how="excluded" if not new_line else "remapped", subject=_subject(skey, row, mapping),
                   decided_by=actor, decided_at=at,
                   refs={**refs, "statement": skey, "row": row.index, "line": mapping.canonical, "moved_to": new_line,
                         "label": row.label_clean})


def _subject(skey: str, row: StatementRow | None, m: RowMapping) -> str:
    label = row.label if row is not None else f"row {m.row_index}"
    return f"{skey.replace('_', ' ')}: '{label}' -> {m.canonical}"
