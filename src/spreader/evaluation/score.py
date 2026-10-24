"""Grading a spread against an answer key.

Every truth value ends in exactly one bucket:

    correct, auto-accepted        right and no review item on it
    correct, sent to review       right, but a person was asked to look (an unnecessary review)
    wrong, sent to review         caught: a person will see it before it is used
    wrong, auto-accepted          SILENT ERROR: wrong and nothing says so
    missing, flagged              the line is absent and the run says rows were left unplaced
                                  or a check failed for that period
    missing, silent               the line is absent and nothing says so (a silent omission)

The silent error rate is (wrong, auto-accepted) / (all values that were auto-accepted): of what
would go out without a person looking, the share that is wrong. It is the same definition as
the workflow-eval-harness uses, so the two can be compared.

Wrong values are also classified by kind, because each kind has a different fix:
scale (off by a power of ten), sign, period (the value of another period), and value/mapping.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from ..contracts import CheckStatus, ReviewKind, Severity, Spread, ValueStatus
from .truth import AnswerKey, TruthValue


@dataclass
class ValueOutcome:
    line: str
    period: str
    truth: Decimal
    predicted: Decimal | None
    bucket: str  # correct_auto | correct_review | wrong_review | wrong_auto | missing_flagged | missing_silent
    kind: str = ""  # for wrong: scale | sign | period | value
    status: str = ""  # the predicted value's status
    flags: list[str] = field(default_factory=list)


@dataclass
class CellOutcome:
    row_label: str
    period: str
    truth: Decimal
    found: bool
    value_ok: bool
    period_ok: bool
    line_truth: str | None
    line_pred: str | None
    mapping_ok: bool | None  # None when the key cannot judge the mapping


@dataclass
class DocScore:
    document: str
    source: str
    values: list[ValueOutcome] = field(default_factory=list)
    cells: list[CellOutcome] = field(default_factory=list)
    expected_review_missing: list[str] = field(default_factory=list)
    forbidden_present: list[str] = field(default_factory=list)
    statements_found: list[str] = field(default_factory=list)
    error: str | None = None

    def counts(self) -> Counter[str]:
        return Counter(v.bucket for v in self.values)


def _tolerance(t: TruthValue, n_rows: int) -> Decimal:
    return t.precision * Decimal(max(1, n_rows)) / Decimal(2) + Decimal("0.0000001")


def _kind(pred: Decimal, truth: Decimal, others: list[Decimal]) -> str:
    if truth != 0 and pred != 0:
        ratio = abs(pred / truth)
        for k in (Decimal(1000), Decimal("0.001"), Decimal(1000000), Decimal("0.000001"), Decimal(10), Decimal("0.1")):
            if abs(ratio - k) / k < Decimal("0.01"):
                return "scale"
        if abs(pred + truth) <= abs(truth) * Decimal("0.0001"):
            return "sign"
    if any(abs(pred - o) <= abs(o) * Decimal("0.0001") for o in others if o != truth):
        return "period"
    return "value"


def score(spread: Spread, key: AnswerKey) -> DocScore:
    ds = DocScore(document=key.document, source=key.source, statements_found=list(spread.statements))
    pred = {(v.line, v.period): v for v in spread.values}
    truth_by_line: dict[str, dict[str, Decimal]] = {}
    for t in key.spread:
        truth_by_line.setdefault(t.line, {})[t.period] = t.value

    open_items = [i for i in spread.review if not i.resolved and i.severity is not Severity.INFO]
    flagged_periods_unmapped: dict[str, set[str]] = {}
    for it in open_items:
        if it.kind in {ReviewKind.UNMAPPED_ROW, ReviewKind.FAILED_CHECK, ReviewKind.MISSING_STATEMENT, ReviewKind.UNREADABLE,
                       ReviewKind.FOOTING} and it.statement is not None:
            flagged_periods_unmapped.setdefault(it.statement.value, set()).update(it.periods or ["*"])

    for t in key.spread:
        v = pred.get((t.line, t.period))
        if v is None or v.value is None:
            fl = flagged_periods_unmapped.get(t.statement, set())
            bucket = "missing_flagged" if (t.period in fl or "*" in fl) else "missing_silent"
            ds.values.append(ValueOutcome(t.line, t.period, t.value, None, bucket))
            continue
        n_terms = 3 if v.status is ValueStatus.CALCULATED else len(v.source_rows)
        ok = abs(v.value - t.value) <= _tolerance(t, n_terms)
        auto = not v.flags
        if ok:
            bucket = "correct_auto" if auto else "correct_review"
            kind = ""
        else:
            bucket = "wrong_auto" if auto else "wrong_review"
            kind = _kind(v.value, t.value, list(truth_by_line.get(t.line, {}).values()))
        ds.values.append(ValueOutcome(t.line, t.period, t.value, v.value, bucket, kind, v.status.value, list(v.flags)))

    # Cell level (when the key has cell truth with source locations).
    if key.cells:
        by_xpath: dict[str, tuple[str, str, Decimal | None, str | None]] = {}
        for skey, res in spread.statements.items():
            mapping_of = {m.row_index: m for m in res.mappings}
            mult = res.table.scale.multiplier
            for r in res.table.rows:
                m = mapping_of.get(r.index)
                for pk, pv in r.values.items():
                    if pv.ref and pv.ref.xpath and pv.displayed is not None:
                        unit_mult = 1 if r.unit.value in {"per_share", "percent"} else (
                            res.table.share_scale.multiplier if r.unit.value == "shares" and res.table.share_scale else mult)
                        by_xpath[pv.ref.xpath] = (skey, pk, pv.displayed * unit_mult, m.canonical if m else None)
        for c in key.cells:
            if c.role == "component" or c.xpath is None:
                continue
            got = by_xpath.get(c.xpath)
            if got is None:
                ds.cells.append(CellOutcome(c.row_label, c.period, c.value, False, False, False, c.line, None, None))
                continue
            _, pk, val, line = got
            value_ok = val is not None and abs(val - c.value) <= max(abs(c.value) * Decimal("0.000001"), Decimal("0.5"))
            mapping_ok = None if c.line is None else (line == c.line or _equivalent(line, c.line))
            ds.cells.append(CellOutcome(c.row_label, c.period, c.value, True, value_ok, pk == c.period, c.line, line, mapping_ok))

    kinds = {i.kind.value for i in spread.review}
    ds.expected_review_missing = [k for k in key.expect_review if k not in kinds]
    for f in key.forbid_values:
        v = pred.get((f.line, f.period))
        if v is not None and v.value is not None and abs(v.value - f.value) <= _tolerance(f, 1):
            ds.forbidden_present.append(f"{f.line} {f.period}")
    return ds


_EQUIV = [{"net_income", "net_income_parent"}, {"total_equity", "total_equity_parent"}]


def _equivalent(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return any(a in s and b in s for s in _EQUIV if s)


@dataclass
class Summary:
    documents: int
    buckets: Counter[str]
    kinds: Counter[str]
    cells: dict[str, tuple[int, int]]  # metric -> (ok, total)


def summarize(scores: list[DocScore]) -> Summary:
    buckets: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    cell = {"found": [0, 0], "value": [0, 0], "period": [0, 0], "mapping": [0, 0]}
    for s in scores:
        buckets.update(s.counts())
        kinds.update(v.kind for v in s.values if v.kind)
        for c in s.cells:
            cell["found"][1] += 1
            cell["found"][0] += int(c.found)
            if c.found:
                cell["value"][1] += 1
                cell["value"][0] += int(c.value_ok)
                cell["period"][1] += 1
                cell["period"][0] += int(c.period_ok)
                if c.mapping_ok is not None:
                    cell["mapping"][1] += 1
                    cell["mapping"][0] += int(c.mapping_ok)
    return Summary(len(scores), buckets, kinds, {k: (v[0], v[1]) for k, v in cell.items()})


def check_pass_rate(spreads: list[Spread]) -> tuple[int, int]:
    n = sum(1 for sp in spreads for c in spread_checks(sp) if c.status is not CheckStatus.SKIPPED)
    ok = sum(1 for sp in spreads for c in spread_checks(sp) if c.status is CheckStatus.PASS)
    return ok, n


def spread_checks(sp: Spread):  # type: ignore[no-untyped-def]
    return sp.checks
