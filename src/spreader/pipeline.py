"""The processing pipeline: document in, spread out, every stage timed.

    read -> lay out tables -> pick the statements -> structure -> map -> assemble
         -> derive -> check -> ratios -> review

It is a pure function of (document bytes, profile, reviewer memory, optional model): running it
twice on the same inputs gives the same spread. Persistence, retries and idempotency live in
store.py and service.py, outside this function.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .checks import add_derived, run_checks, run_ratios
from .company import CompanyContext, compare_with_approved
from .units import resolve_units
from .contracts import DocumentIR, SourceFormat, Spread, StatementResult, StatementType
from .detect import classify
from .layout import lay_out
from .mapping import Memory, ModelMapper, map_table
from .profile import Profile
from .review import attach_flags, build_review
from .second_reader import TagFact
from .second_reader import compare as compare_tags
from .spread import assemble_statement, merge_periods
from .structure import build_statement, harmonize_periods

_T = TypeVar("_T")

LAYOUT_TOLERANCE = {SourceFormat.HTML: 0.0, SourceFormat.XLSX: 0.0, SourceFormat.PDF: 2.0}
# The registrant's own, unconsolidated statements (SEC Schedule I/II): never the borrower's financial statements.
_PARENT_ONLY = re.compile(r"condensed financial information of (the )?registrant|parent company only|registrant only|"
                          r"\(parent company\)", re.I)
_NOT_PRIMARY = re.compile(r"pro\s*forma|unaudited|segment|quarterly|selected financial|summary|condensed consolidating|"
                          r"supplementary|non-gaap|illustrative", re.I)


@dataclass
class StageTimer:
    timings: dict[str, float] = field(default_factory=dict)
    _start: float = 0.0

    def __enter__(self) -> StageTimer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, name: str, fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            self.timings[name] = round(self.timings.get(name, 0.0) + (time.perf_counter() - t0) * 1000, 2)


# Rows only a holding company's own statements have: they mark a parent-only table even when the "parent company only"
# heading is pages above it (Hancock Whitney's "Condensed Statements of Cash Flows", found in D57: chosen over the
# consolidated statement, its figures added up, and three wrong values per year went out without review).
_PARENT_ROWS = re.compile(r"dividends? received from (?:bank |banking )?subsidiar|"
                          r"equity in (?:the )?undistributed (?:net )?(?:earnings|income|loss)\w* of (?:bank |banking )?subsidiar|"
                          r"investments? in (?:and advances to )?(?:bank |banking |consolidated )?subsidiar|"
                          r"advances (?:to|from) subsidiar|dividends? from (?:bank |banking )?subsidiar", re.I)


def is_parent_only(table: Any, layout: Any) -> bool:
    """The registrant's own (unconsolidated) statement: by its heading or by rows only a parent company prints."""
    if _PARENT_ONLY.search(layout.title_text + " " + table.context[-200:]):
        return True
    labels = " | ".join(" ".join(t.text for t in r.tokens[:1]) for r in table.rows)
    return bool(_PARENT_ROWS.search(labels))


def pick_statements(doc: DocumentIR, profile: Profile, timer: StageTimer) -> dict[StatementType, tuple]:
    """Lay out every table and keep the best-scoring one per statement type."""
    best: dict[StatementType, tuple] = {}
    rivals: dict[StatementType, list[tuple]] = {}
    tol = LAYOUT_TOLERANCE[doc.format]
    for table in doc.tables:
        layout = timer.run("layout", lay_out, table, tol)
        det = timer.run("classify", classify, layout, table, profile)
        if det is None:
            continue
        title = (layout.title_text + " " + table.context[-200:]).lower()
        if _NOT_PRIMARY.search(title):
            det.score -= 6  # a pro forma, unaudited, segment or quarterly table is not the primary statement
        if is_parent_only(table, layout):
            det.score -= 20  # the parent company's own statement: any consolidated candidate wins over it (D57)
        rivals.setdefault(det.statement, []).append((table, layout, det))
        cur = best.get(det.statement)
        if cur is None or det.score > cur[2].score:
            best[det.statement] = (table, layout, det)
    for stype, cands in rivals.items():
        chosen = best[stype]
        close = [c for c in cands if c[0] is not chosen[0] and c[2].score >= chosen[2].score - 3]
        if close:
            chosen[0].__dict__.setdefault("_rivals", [c[0].index for c in close])
    return best


def spread_document(doc: DocumentIR, profile: Profile, memory: Memory | None = None,
                    model: ModelMapper | None = None, company: CompanyContext | None = None,
                    tags: dict[str, list[TagFact]] | None = None) -> tuple[Spread, dict[str, float]]:
    """tags: the opt-in second reader's inline XBRL facts by cell (spreader.second_reader); None leaves it off."""
    timer = StageTimer()
    picked = pick_statements(doc, profile, timer)
    statements: dict[str, StatementResult] = {}
    values = []
    built = {stype: timer.run("structure", build_statement, table, layout, stype, doc.doc_id, det.score)
             for stype, (table, layout, det) in picked.items()}
    for stype, (table, layout, _det) in picked.items():
        if is_parent_only(table, layout):
            # Found on a 10-K whose consolidated statements are in an exhibit: the only balance sheet in the document was
            # the parent company's own, and it was spread as if it were the group's (IMPROVEMENT_LOG #23).
            built[stype].warnings.append(
                f"PARENT_ONLY: the only {stype.value.replace('_', ' ')} found is the registrant's own (parent company, "
                "unconsolidated) statement, not the consolidated one; the consolidated statements may be in an exhibit.")
        rival_ids = table.__dict__.get("_rivals")
        if rival_ids:
            built[stype].warnings.append(
                f"COMPETING_TABLE: another table (table {', '.join(str(i + 1) for i in rival_ids)}) also looks like the "
                f"{stype.value.replace('_', ' ')}; the pipeline used table {table.index + 1}. Confirm it is the audited "
                "primary statement.")
    harmonize_periods(list(built.values()), doc.preface)
    contexts = {stype: [layout.title_text + " " + layout.header_label_text,
                        " ".join(" ".join(t.text for t in r.tokens) for r in layout.header_rows), table.context[-400:]]
                for stype, (table, layout, _det) in picked.items()}
    resolve_units(built, contexts, doc.unit_statements)
    for stype, st in built.items():
        mappings = timer.run("map", map_table, st, profile, memory, model, company.mappings if company else None)
        statements[stype.value] = StatementResult(table=st, mappings=mappings)
        values.extend(timer.run("assemble", assemble_statement, st, mappings, profile))

    tables = [r.table for r in statements.values()]
    periods = merge_periods(tables)
    period_keys = {StatementType(k): {p.key for p in r.table.periods} for k, r in statements.items()}
    scales = {StatementType(k): r.table.scale.multiplier for k, r in statements.items()}

    derived, skip = timer.run("derive", add_derived, values, periods, profile, period_keys)
    values.extend(derived)
    checks = timer.run("check", run_checks, values, periods, profile, period_keys, scales, skip)
    ratios = timer.run("ratios", run_ratios, values, periods, profile)
    review = timer.run("review", build_review, statements, values, checks, profile, ratios)
    prior: list = []
    if company and company.approved:
        partial = Spread(doc_id=doc.doc_id, profile_id=profile.id, profile_version="", statements=statements,
                         periods=periods, values=values)
        # Only the statements' own headings and labels: the cover page's boilerplate ("new or revised financial
        # accounting standards") made every filing look restated.
        text = " ".join([*(p.label for r in statements.values() for p in r.table.periods),
                         *(row.label for r in statements.values() for row in r.table.rows)])
        prior = timer.run("company", compare_with_approved, partial, company, profile, text)
    second: list = []
    if tags:
        partial = Spread(doc_id=doc.doc_id, profile_id=profile.id, profile_version="", statements=statements,
                         periods=periods, values=values)
        second = timer.run("second_reader", compare_tags, partial, tags).items
    attach_flags(values, review + prior + second)

    order = {ln: i for i, ln in enumerate(profile.lines)}
    values.sort(key=lambda v: (order.get(v.line, 999), v.period))
    spread = Spread(doc_id=doc.doc_id, profile_id=profile.id, profile_version=f"{profile.version}+{profile.content_hash}",
                    statements=statements, periods=periods, values=values, checks=checks, ratios=ratios,
                    review=review + prior + second, warnings=list(doc.warnings), prior_items=prior,
                    second_reader_items=second,
                    company_id=company.company_id if company else None,
                    company_version=company.version if company else None)
    return spread, timer.timings
