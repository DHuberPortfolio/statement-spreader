"""The processing pipeline: document in, spread out, every stage timed.

    read -> lay out tables -> pick the statements -> structure -> map -> assemble
         -> derive -> check -> ratios -> review

It is a pure function of (document bytes, profile, reviewer memory, optional model): running it
twice on the same inputs gives the same spread. Persistence, retries and idempotency live in
store.py and service.py, outside this function.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .checks import add_derived, run_checks, run_ratios
from .contracts import DocumentIR, SourceFormat, Spread, StatementResult, StatementType
from .detect import classify
from .layout import lay_out
from .mapping import Memory, ModelMapper, map_table
from .profile import Profile
from .review import attach_flags, build_review
from .spread import assemble_statement, merge_periods
from .structure import build_statement, harmonize_periods

LAYOUT_TOLERANCE = {SourceFormat.HTML: 0.0, SourceFormat.XLSX: 0.0, SourceFormat.PDF: 2.0}


@dataclass
class StageTimer:
    timings: dict[str, float] = field(default_factory=dict)
    _start: float = 0.0

    def __enter__(self) -> StageTimer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, name: str, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            self.timings[name] = round(self.timings.get(name, 0.0) + (time.perf_counter() - t0) * 1000, 2)


def pick_statements(doc: DocumentIR, profile: Profile, timer: StageTimer) -> dict[StatementType, tuple]:
    """Lay out every table and keep the best-scoring one per statement type."""
    best: dict[StatementType, tuple] = {}
    tol = LAYOUT_TOLERANCE[doc.format]
    for table in doc.tables:
        layout = timer.run("layout", lay_out, table, tol)
        det = timer.run("classify", classify, layout, table, profile)
        if det is None:
            continue
        cur = best.get(det.statement)
        if cur is None or det.score > cur[2].score:
            best[det.statement] = (table, layout, det)
    return best


def spread_document(doc: DocumentIR, profile: Profile, memory: Memory | None = None,
                    model: ModelMapper | None = None) -> tuple[Spread, dict[str, float]]:
    timer = StageTimer()
    picked = pick_statements(doc, profile, timer)
    statements: dict[str, StatementResult] = {}
    values = []
    built = {stype: timer.run("structure", build_statement, table, layout, stype, doc.doc_id, det.score)
             for stype, (table, layout, det) in picked.items()}
    harmonize_periods(list(built.values()))
    for stype, st in built.items():
        mappings = timer.run("map", map_table, st, profile, memory, model)
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
    review = timer.run("review", build_review, statements, values, checks, profile)
    attach_flags(values, review)

    order = {ln: i for i, ln in enumerate(profile.lines)}
    values.sort(key=lambda v: (order.get(v.line, 999), v.period))
    spread = Spread(doc_id=doc.doc_id, profile_id=profile.id, profile_version=f"{profile.version}+{profile.content_hash}",
                    statements=statements, periods=periods, values=values, checks=checks, ratios=ratios,
                    review=review, warnings=list(doc.warnings))
    return spread, timer.timings
