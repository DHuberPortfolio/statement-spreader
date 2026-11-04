"""Confirmations from approved work outside the document (D61).

- prior: the value equals the company's approved spread for the same line and period (spreader.company), within the
  rounding both carry. Each annual report reprints last year's numbers, and a person approved those a year ago, so from
  a borrower's second year most prior-year columns are confirmed this way.
- label: every printed row behind the value carries a label that has been placed on that line, and approved unchanged,
  in at least SPREADER_LABEL_RECORD_DOCS other documents (7 by default) and never moved by a reviewer. It vouches for the
  line, not for the table the number came from (EIG's revenue, read from the wrong table under a perfect label, is why
  a check must still be one of the two confirmations). Never on a catch-all line ("other_*").

Each counts as one confirmation in review.unconfirmed_items. Measured on the dev sets before building (D61).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from finops.core.outcomes import Outcome

from .company import CompanyContext, value_tolerance
from .contracts import Confirmation, SpreadValue, StatementResult
from .echo import is_catch_all
from .profile import Profile


def record_docs_required() -> int:
    """SPREADER_LABEL_RECORD_DOCS: how many other documents must have approved a label's placement unchanged before it
    counts as a confirmation. 7 by default (on the dev sets 5 let a wrong value through, 7 none); 0 turns it off."""
    raw = os.environ.get("SPREADER_LABEL_RECORD_DOCS", "7").strip()
    if not raw.isdigit() or int(raw) > 1000:
        raise ValueError(f"SPREADER_LABEL_RECORD_DOCS must be a whole number from 0 to 1000, not {raw!r}")
    return int(raw)


@dataclass
class LabelRecord:
    """(statement, cleaned label, line) -> the documents where a reviewer approved that placement unchanged, and those
    where a reviewer moved it. Built from reviewer outcomes (spreader.learning) or, for evaluation, from answer keys."""

    right: dict[tuple[str, str, str], set[str]] = field(default_factory=dict)
    wrong: dict[tuple[str, str, str], set[str]] = field(default_factory=dict)

    def add(self, key: tuple[str, str, str], document: str, ok: bool) -> None:
        (self.right if ok else self.wrong).setdefault(key, set()).add(document)

    def vouches(self, key: tuple[str, str, str], document: str, needed: int) -> int:
        """The number of other documents that approved this placement, or 0 when too few did or any moved it."""
        if self.wrong.get(key, set()) - {document}:
            return 0
        n = len(self.right.get(key, set()) - {document})
        return n if needed and n >= needed else 0


def record_from_outcomes(outcomes: Iterable[Outcome]) -> LabelRecord:
    rec = LabelRecord()
    for o in outcomes:
        r = o.refs
        if o.engine == "statements" and r.get("label") and r.get("statement") and r.get("line") and r.get("document"):
            rec.add((r["statement"], r["label"], r["line"]), str(r["document"]), o.right)
    return rec


def find_confirmations(doc_id: str, statements: dict[str, StatementResult], values: list[SpreadValue], profile: Profile,
                       company: CompanyContext | None = None, record: LabelRecord | None = None) -> list[Confirmation]:
    out: list[Confirmation] = []
    needed = record_docs_required() if record is not None else 0
    for v in values:
        if v.value is None:
            continue
        skey = profile.line_statement[v.line].value
        res = statements.get(skey)
        if company is not None and (a := company.approved.get((v.period, v.line))) is not None:
            mult = Decimal(res.table.scale.multiplier) if res is not None else Decimal(1)
            if abs(v.value - a.value) <= value_tolerance(v, mult) + a.tolerance:
                who = f"{a.approved_by}, {a.approved_at[:10]}" if a.approved_by and a.approved_at else "an earlier approval"
                out.append(Confirmation(line=v.line, period=v.period, value=v.value, source="prior",
                                        detail=f"Equals the company's approved spread ({who})."))
        # Never on a catch-all line, as for echoes (D60): the label can be right while the line collects the wrong rows
        # (Old Dominion's other current assets, YETI's other non-operating income on the holdout).
        if needed and res is not None and v.source_rows and not is_catch_all(v.line):
            rows = {r.index: r for r in res.table.rows}
            labels = [rows[i].label_clean for i in v.source_rows if i in rows]
            counts = [record.vouches((skey, lab, v.line), doc_id, needed) for lab in labels]  # type: ignore[union-attr]
            if labels and all(counts):
                out.append(Confirmation(line=v.line, period=v.period, value=v.value, source="label",
                                        detail=f"'{labels[0]}' has been placed on this line and approved unchanged in "
                                               f"{min(counts)} other documents, and never moved."))
    return out
