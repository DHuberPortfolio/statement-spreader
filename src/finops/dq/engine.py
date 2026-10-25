"""The data-quality gate: source rows in, accepted / review / rejected records out, each with its reasons.

Order of work, all deterministic:
1. Read each source file with its row numbers; refuse a file missing a mapped column (naming it).
2. Map every row into the canonical record: normalise, translate codes, parse types. Every change from the cell
   as read is recorded (field, before, after, step), so a person can see exactly what the gate did.
3. Field checks (required, type, pattern, range), then the dataset's rules, record by record.
4. Dataset checks: keys, duplicates, references to other datasets, group consistency, outliers, and changes to
   controlled fields against the last accepted snapshot.
5. Decide: any "reject" issue -> rejected; else any "review" issue -> review; else accepted. A person's earlier
   decisions are replayed: a release holds only while the record and its issues are unchanged.

The gate never edits the source and never loads anything itself: it writes the accepted records for the next system
to load, and a quarantine report for people.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, PrivateAttr
from rapidfuzz import fuzz

from finops.core.fingerprint import content_hash
from finops.core.policy import Finding
from finops.core.tabular import TableError, read_table

from .config import DatasetSpec, FieldSpec, Rule, SourceSpec

ENGINE_VERSION = "dq-1"
Decision = Literal["accepted", "review", "rejected", "duplicate"]


class GateInputError(ValueError):
    """A whole file cannot be gated (unreadable, or a mapped column is missing)."""


class Issue(BaseModel):
    code: str
    severity: Literal["reject", "review", "info"]
    field: str | None = None
    message: str
    related: list[str] = []  # other record ids involved (duplicates, conflicts, groups)


class Change(BaseModel):
    field: str
    before: str
    after: str
    step: str


class Record(BaseModel):
    id: str
    source: str
    source_label: str
    file: str
    row: int
    sheet: str | None = None
    original: dict[str, str]
    canonical: dict[str, str]
    changes: list[Change] = []
    issues: list[Issue] = []
    invalid_fields: list[str] = []  # fields that could not be read: later checks do not repeat that as "empty"
    decision: Decision = "accepted"
    decided_by: str = "rules"  # "rules" or the person whose release/rejection decided it
    duplicate_of: str | None = None

    def key(self, spec: DatasetSpec) -> tuple[str, ...]:
        return tuple(self.canonical.get(k, "") for k in spec.key)

    def review_fingerprint(self) -> str:
        """What a release was given for: the record's content and its review issues. Either changing voids it."""
        return content_hash([self.canonical, sorted((i.code, i.field or "") for i in self.issues if i.severity == "review")])


class GateResult(BaseModel):
    dataset: str
    engine_version: str = ENGINE_VERSION
    config_version: str = ""
    records: list[Record]
    columns: list[str]  # canonical field order, the export's header
    carried_forward: list[dict[str, str]] = []  # last accepted versions exported in place of held records
    missing_from_source: list[str] = []  # keys in the last accepted snapshot that no source contains now
    withheld: list[str] = []  # held keys whose last accepted version was not carried forward (the new one stops them)
    warnings: list[str] = []
    # Unmasked canonical values, by record id: in memory only, never serialised (bank details stay out of the
    # database and the API). The export of accepted records reads them; a stored result is re-gated to export.
    _real: dict[str, dict[str, str]] = PrivateAttr(default_factory=dict)
    _carried_real: list[dict[str, str]] = PrivateAttr(default_factory=list)  # carried_forward, unmasked

    def counts(self) -> dict[str, int]:
        out = {"accepted": 0, "review": 0, "rejected": 0, "duplicate": 0}
        for r in self.records:
            out[r.decision] += 1
        return out


@dataclass
class Decisions:
    """A person's standing decisions, replayed on every run (from the service's append-only table)."""
    releases: dict[str, tuple[str, str, str]] = field(default_factory=dict)  # record id -> (fingerprint, actor, note)
    rejections: dict[str, tuple[str, str]] = field(default_factory=dict)  # record id -> (actor, note)
    corrections: dict[str, dict[str, tuple[str, str, str]]] = field(default_factory=dict)  # id -> field -> (value, actor, reason)


@dataclass
class SourceInput:
    source: str  # a source id from the dataset spec
    name: str
    data: bytes


# -- field parsing ---------------------------------------------------------------------------------------------------

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")
_SEPARATORS = re.compile(r"[\s\-]")
_SCIENTIFIC = re.compile(r"[+-]?\d(?:[.,]\d+)?[eE][+-]?\d+")
_FORMULA_START = ("=", "+", "-", "@")
_TRUE = {"yes", "y", "true", "t", "1"}
_FALSE = {"no", "n", "false", "f", "0"}


def mask(value: str) -> str:
    v = re.sub(r"\s", "", value or "")
    return f"****{v[-4:]}" if len(v) > 4 else ("****" if v else "")


def aba_ok(digits: str) -> bool:
    """US routing number checksum: 3(d1+d4+d7) + 7(d2+d5+d8) + (d3+d6+d9) is a multiple of 10."""
    if not re.fullmatch(r"\d{9}", digits):
        return False
    d = [int(c) for c in digits]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


def _normalise(text: str, steps: Sequence[str]) -> str:
    t = text
    for s in steps:
        if s == "trim":
            t = t.strip()
        elif s == "collapse_spaces":
            t = re.sub(r"\s+", " ", t)
        elif s == "upper":
            t = t.upper()
        elif s == "lower":
            t = t.lower()
        elif s == "digits_only":
            # Only separators go: "1234 5678" and "1234-5678" are 12345678. Anything else stays, so "6.70913E+11"
            # (Excel's scientific notation, digits already lost) fails the field's format instead of becoming 67091311.
            t = _SEPARATORS.sub("", t)
        elif s == "ein" and re.fullmatch(r"\d{2}-?\d{7}", re.sub(r"[\s.]", "", t)):
            d = re.sub(r"\D", "", t)
            t = f"{d[:2]}-{d[2:]}"
        elif s == "strip_punctuation_ends":
            t = t.strip(" .,;:")
    return t


def _parse_date(text: str, formats: list[str]) -> tuple[date | None, list[date]]:
    """(the date, every distinct date the formats give). Two different dates means the text is ambiguous."""
    t = text.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", t):
        t = t[:10]
    found: list[date] = []
    for f in formats:
        try:
            d = datetime.strptime(t, f).date()
        except ValueError:
            continue
        if d not in found:
            found.append(d)
    return (found[0] if len(found) == 1 else None), found


_STRICT_NUMBER = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+-]?\.\d+")


def _number(text: str) -> Decimal | None:
    """A plain number: digits, a sign, a decimal point and US thousands separators, nothing else. Stricter than the
    statement reader on purpose: "NET 45 EOM" is not 45 (end-of-month terms are different terms) and "€1,250" on a
    USD order is not 1250. A source that always prints a symbol says so in its configuration (strip_patterns)."""
    t = text.strip()
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t = t[1:-1].strip()
    if not _STRICT_NUMBER.fullmatch(t):
        return None
    v = Decimal(t.replace(",", ""))
    return -v if neg else v


def _fmt_decimal(v: Decimal) -> str:
    s = format(v.normalize(), "f")
    return s if s not in {"-0", ""} else "0"


@dataclass
class _Parsed:
    text: str = ""  # canonical text ("" when empty or unreadable)
    value: Any = None  # typed value for comparisons
    issues: list[Issue] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)


def parse_field(name: str, raw: str, spec: FieldSpec, source: SourceSpec) -> _Parsed:
    out = _Parsed()
    shown = mask(raw) if spec.sensitive else raw

    def change(after: str, step: str, before: str) -> None:
        if after != before:
            out.changes.append(Change(field=name, before=mask(before) if spec.sensitive else before,
                                      after=mask(after) if spec.sensitive else after, step=step))

    t = raw
    for a, b in source.replace.get(name, {}).items():
        t = t.replace(a, b)
    if name in source.strip_patterns:
        t = re.sub(source.strip_patterns[name], "", t, flags=re.I)
    change(t, f"{source.label} format rule", raw)
    if _SCIENTIFIC.fullmatch(t.strip()) and (spec.type in ("string", "aba_routing")):
        out.issues.append(Issue(code="SCIENTIFIC_NOTATION", severity="reject", field=name,
                                message=f"{name} '{shown}' is in scientific notation: a spreadsheet rounded the number and its "
                                        "last digits are lost; export the column as text"))
        return out
    n = _normalise(t, spec.normalize)
    change(n, "normalised (" + ", ".join(spec.normalize) + ")", t)
    t = n
    vmap = {k.strip().lower(): v for k, v in source.value_maps.get(name, {}).items()}
    if t.lower() in vmap:
        mapped = vmap[t.lower()]
        change(mapped, f"code mapped by the {source.label} value map", t)
        t = mapped
    if not t:
        if spec.required:
            out.issues.append(Issue(code="MISSING_REQUIRED", severity="reject", field=name, message=f"{name} is required but empty"))
        return out
    if spec.type == "string":
        out.text, out.value = t, t
    elif spec.type in ("integer", "decimal"):
        s = t
        if s.endswith("%"):
            s = s[:-1].strip()
        v = _number(s)
        if v is None:
            out.issues.append(Issue(code="INVALID_NUMBER", severity="reject", field=name, message=f"{name} '{shown}' is not a number"))
            return out
        if name in source.decimal_scale:
            v = v * source.decimal_scale[name]
        if spec.type == "integer":
            if v != v.to_integral_value():
                out.issues.append(Issue(code="INVALID_NUMBER", severity="reject", field=name, message=f"{name} '{shown}' is not a whole number"))
                return out
            v = Decimal(int(v))
        out.text, out.value = _fmt_decimal(v), v
        change(out.text, "read as a number", t)
        if spec.min is not None and v < spec.min or spec.max is not None and v > spec.max:
            out.issues.append(Issue(code="OUT_OF_RANGE", severity="reject", field=name,
                                    message=f"{name} {out.text} is outside {spec.min if spec.min is not None else '...'}"
                                            f" to {spec.max if spec.max is not None else '...'}"))
        return out
    elif spec.type == "date":
        d, found = _parse_date(t, source.date_formats)
        if d is None and len(found) > 1:
            out.issues.append(Issue(code="AMBIGUOUS_DATE", severity="review", field=name,
                                    message=f"{name} '{t}' reads as {' or '.join(x.isoformat() for x in found)} under this source's date formats"))
            return out
        if d is None:
            out.issues.append(Issue(code="INVALID_DATE", severity="reject", field=name,
                                    message=f"{name} '{t}' is not a date in any of this source's formats ({', '.join(source.date_formats)})"))
            return out
        out.text, out.value = d.isoformat(), d
        change(out.text, "read as a date", t)
        return out
    elif spec.type == "enum":
        hit = next((v for v in spec.values if v.lower() == t.lower()), None)
        if hit is None:
            out.issues.append(Issue(code="INVALID_VALUE", severity="reject", field=name,
                                    message=f"{name} '{t}' is not one of: {', '.join(spec.values)}"))
            return out
        out.text, out.value = hit, hit
        change(hit, "matched to an allowed value", t)
        return out
    elif spec.type == "email":
        e = t.lower()
        if not _EMAIL.fullmatch(e):
            out.issues.append(Issue(code="INVALID_EMAIL", severity="reject", field=name, message=f"{name} '{t}' is not an e-mail address"))
            return out
        out.text, out.value = e, e
        change(e, "lower-cased", t)
        return out
    elif spec.type == "aba_routing":
        digits = _SEPARATORS.sub("", t)
        if not aba_ok(digits):
            out.issues.append(Issue(code="INVALID_ROUTING", severity="reject", field=name,
                                    message=f"{name} {mask(digits) if spec.sensitive else digits} is not a valid US routing number (nine digits with a checksum)"))
            return out
        out.text, out.value = digits, digits
        change(digits, "digits only", t)
        return out
    elif spec.type == "bool":
        if t.lower() in _TRUE:
            out.text, out.value = "yes", True
        elif t.lower() in _FALSE:
            out.text, out.value = "no", False
        else:
            out.issues.append(Issue(code="INVALID_VALUE", severity="reject", field=name, message=f"{name} '{t}' is not yes or no"))
            return out
        change(out.text, "read as yes/no", t)
        return out
    if spec.max_length and len(out.text) > spec.max_length:
        out.issues.append(Issue(code="TOO_LONG", severity="reject", field=name,
                                message=f"{name} is {len(out.text)} characters; the limit is {spec.max_length}"))
    if spec.pattern and out.text and not re.fullmatch(spec.pattern, out.text):
        out.issues.append(Issue(code="INVALID_FORMAT", severity="reject", field=name,
                                message=f"{name} '{mask(out.text) if spec.sensitive else out.text}' does not have the expected format"))
    return out


# -- record rules ----------------------------------------------------------------------------------------------------

def _applies(rule: Rule, canon: dict[str, str]) -> bool:
    for f, vals in rule.when.equals.items():
        if canon.get(f, "").lower() not in {v.lower() for v in vals}:
            return False
    return all(canon.get(f, "") for f in rule.when.present)


def _cmp(a: Any, op: str, b: Any) -> bool:
    return {"<": a < b, "<=": a <= b, "==": a == b, ">=": a >= b, ">": a > b, "!=": a != b}[op]


def check_rules(spec: DatasetSpec, canon: dict[str, str], typed: dict[str, Any], invalid: frozenset[str] = frozenset()) -> list[Issue]:
    """`invalid`: fields whose value could not be read. They already carry their own reason, so a rule does not
    report them again as empty (one bad routing number is one problem, not three)."""
    out: list[Issue] = []
    for rule in spec.rules:
        if not _applies(rule, canon):
            continue
        failed: list[str] = []
        failed += [f"{f} is empty" for f in rule.require if not canon.get(f) and f not in invalid]
        if rule.require_one_of and not any(canon.get(f) or f in invalid for f in rule.require_one_of):
            failed.append(f"none of {', '.join(rule.require_one_of)} is filled")
        failed += [f"{f} must be empty" for f in rule.forbid if canon.get(f)]
        failed += [f"{f} has the wrong format" for f, p in rule.pattern.items() if canon.get(f) and not re.fullmatch(p, canon[f])]
        if rule.compare:
            a, op, b = rule.compare
            if typed.get(a) is not None and typed.get(b) is not None:
                try:
                    if not _cmp(typed[a], op, typed[b]):
                        failed.append(f"{a} {op} {b} does not hold ({canon[a]} vs {canon[b]})")
                except TypeError:
                    failed.append(f"{a} and {b} cannot be compared")
        if failed:
            out.append(Issue(code=rule.id.upper(), severity=rule.severity, message=f"{rule.message} ({'; '.join(failed)})"))
    return out


# -- the gate --------------------------------------------------------------------------------------------------------

def _read_source(spec: DatasetSpec, inp: SourceInput) -> tuple[SourceSpec, list[Any]]:
    if inp.source not in spec.sources:
        raise GateInputError(f"'{inp.source}' is not a source of {spec.name} (sources: {', '.join(spec.sources)})")
    src = spec.sources[inp.source]
    try:
        header, rows = read_table(inp.name, inp.data, src.sheet, find_formulas=True)
    except TableError as exc:
        raise GateInputError(str(exc)) from exc
    missing = sorted({c for c in src.columns.values() if c not in header})
    if missing:
        raise GateInputError(f"{inp.name} ({src.label}) has no column {', '.join(repr(m) for m in missing)}; "
                             f"its columns are {', '.join(repr(h) for h in header if h)}")
    return src, rows


def _build(spec: DatasetSpec, sid: str, src: SourceSpec, row: Any, rid: str, decisions: Decisions) -> tuple[Record, dict[str, Any]]:
    original = {k: v for k, v in row.values.items() if k != "__extra__"}
    canon: dict[str, str] = {}
    typed: dict[str, Any] = {}
    issues: list[Issue] = []
    changes: list[Change] = []
    fixes = decisions.corrections.get(rid, {})
    for name, fspec in spec.fields.items():
        if name in fixes:
            value, actor, reason = fixes[name]
            before = original.get(src.columns.get(name, ""), src.defaults.get(name, ""))
            changes.append(Change(field=name, before=mask(before) if fspec.sensitive else before,
                                  after=mask(value) if fspec.sensitive else value, step=f"corrected by {actor}: {reason}"))
            raw = value
        elif name in src.columns:
            raw = original.get(src.columns[name], "")
        else:
            raw = src.defaults.get(name, "")
            if raw:
                changes.append(Change(field=name, before="", after=raw, step=f"default for {src.label}"))
        p = parse_field(name, raw, fspec, src)
        canon[name], typed[name] = p.text, p.value
        issues += p.issues
        changes += p.changes
        if (spec.formula_like_text and fspec.type == "string" and p.text.startswith(_FORMULA_START)
                and _number(p.text) is None):
            issues.append(Issue(code="FORMULA_LIKE_TEXT", severity=spec.formula_like_text, field=name,
                                message=f"{name} starts with '{p.text[0]}': a spreadsheet would run it as a formula"))
    for name, column in src.columns.items():
        if column in row.formulas:
            issues.append(Issue(code="FORMULA_WITHOUT_VALUE", severity="review", field=name,
                                message=f"{name} ({column}) holds a spreadsheet formula with no saved result, so it reads as empty; "
                                        "export values, or open and save the file in Excel"))
    if "__extra__" in row.values:
        issues.append(Issue(code="EXTRA_CELLS", severity="review", message="the row has more cells than the header has columns"))
    invalid = frozenset(i.field for i in issues if i.field and i.severity == "reject" and not canon.get(i.field))
    issues += check_rules(spec, canon, typed, invalid)
    rec = Record(id=rid, source=sid, source_label=src.label, file=row.ref.file, row=row.ref.row, sheet=row.ref.sheet,
                 original={k: (mask(v) if _sensitive_column(spec, src, k) else v) for k, v in original.items()},
                 canonical=canon, changes=changes, issues=issues, invalid_fields=sorted(invalid))
    return rec, typed


def _sensitive_column(spec: DatasetSpec, src: SourceSpec, column: str) -> bool:
    return any(spec.fields[f].sensitive for f, c in src.columns.items() if c == column)


def gate(spec: DatasetSpec, inputs: list[SourceInput], references: dict[str, tuple[str, bytes]] | None = None,
         previous: tuple[str, bytes] | None = None, decisions: Decisions | None = None, config_version: str = "") -> GateResult:
    decisions = decisions or Decisions()
    records: list[Record] = []
    typed_of: dict[str, dict[str, Any]] = {}
    real: dict[str, dict[str, str]] = {}  # unmasked canonical values of sensitive fields, for comparisons only
    seen: dict[str, int] = defaultdict(int)
    for inp in inputs:
        src, rows = _read_source(spec, inp)
        for row in rows:
            base = content_hash([spec.id, inp.source, sorted(row.values.items())], 16)
            seen[base] += 1
            rid = base if seen[base] == 1 else f"{base}-{seen[base]}"
            rec, typed = _build(spec, inp.source, src, row, rid, decisions)
            records.append(rec)
            typed_of[rid] = typed
            real[rid] = dict(rec.canonical)
    for rec in records:  # what people see: sensitive canonical values masked
        rec.canonical = {k: (mask(v) if spec.fields[k].sensitive else v) for k, v in rec.canonical.items()}

    result = GateResult(dataset=spec.id, config_version=config_version, records=records, columns=list(spec.fields))
    _keys(spec, records, real)
    live = [r for r in records if r.decision != "duplicate"]
    _duplicates(spec, live, real)
    _references(spec, live, real, references or {}, result)
    _groups(spec, live, real)
    _outliers(spec, live, typed_of)
    prev_rows = _previous(spec, previous, result) if previous else {}
    if spec.change_control and prev_rows:
        _changes(spec, live, real, prev_rows)
    for rec in live:
        _decide(rec, decisions)
    if prev_rows and spec.carry_forward.enabled:
        stop = {f: {v.lower() for v in vals} for f, vals in spec.carry_forward.never_when.items()}
        held: dict[tuple[str, ...], list[Record]] = defaultdict(list)
        for r in live:
            if r.decision in ("review", "rejected"):
                held[tuple(real[r.id].get(k, "") for k in spec.key)].append(r)
        accepted = {tuple(real[r.id].get(k, "") for k in spec.key) for r in live if r.decision == "accepted"}
        for k, row in sorted(prev_rows.items()):
            if k not in held or k in accepted:
                continue
            if any(real[r.id].get(f, "").lower() in vals for r in held[k] for f, vals in stop.items()):
                result.withheld.append("/".join(k))  # the held version stops the record: do not revive the old one
            else:
                result._carried_real.append(row)
                result.carried_forward.append({c: (mask(v) if spec.fields[c].sensitive else v) for c, v in row.items()})
        present = {tuple(real[r.id].get(k, "") for k in spec.key) for r in live}
        result.missing_from_source = ["/".join(k) for k in sorted(prev_rows) if k not in present]
    result._real = real
    return result


def accepted_rows(result: GateResult) -> list[dict[str, str]]:
    """The records to load: accepted ones with their real (unmasked) values, then any carried-forward last accepted
    versions of held records. One row per key."""
    real = result._real
    if not real and result.records:
        raise ValueError("this result's values are not in memory; re-run the gate to export it")
    out: list[dict[str, str]] = []
    for r in result.records:
        if r.decision == "accepted":
            out.append({c: real[r.id].get(c, "") for c in result.columns})
    out += [{c: row.get(c, "") for c in result.columns} for row in result._carried_real]
    return out


def _keys(spec: DatasetSpec, records: list[Record], real: dict[str, dict[str, str]]) -> None:
    by_key: dict[tuple[str, ...], list[Record]] = defaultdict(list)
    for r in records:
        k = tuple(real[r.id].get(f, "") for f in spec.key)
        if all(k):
            by_key[k].append(r)
    for k, group in by_key.items():
        if len(group) < 2:
            continue
        first = group[0]
        conflicting = [r for r in group[1:] if real[r.id] != real[first.id]]
        identical = [r for r in group[1:] if real[r.id] == real[first.id]]
        for r in identical:
            r.decision, r.duplicate_of = "duplicate", first.id
            r.issues.append(Issue(code="DUPLICATE_ROW", severity="info", message=f"same record as {first.source_label} row {first.row}; loaded once",
                                  related=[first.id]))
        if conflicting:
            ids = [first.id] + [r.id for r in conflicting]
            fields = sorted({f for r in conflicting for f in spec.fields if real[r.id].get(f) != real[first.id].get(f)})
            for r in [first] + conflicting:
                r.issues.append(Issue(code="CONFLICTING_KEY", severity="review",
                                      message=f"{'/'.join(spec.key)} {'/'.join(k)} appears {len(ids)} times with different "
                                              f"{', '.join(fields)}; which one is right is a person's call",
                                      related=[i for i in ids if i != r.id]))


def _duplicates(spec: DatasetSpec, records: list[Record], real: dict[str, dict[str, str]]) -> None:
    for d in spec.duplicates:
        pairs: set[tuple[str, str]] = set()
        if d.match == "exact":
            groups: dict[tuple[str, ...], list[Record]] = defaultdict(list)
            must = d.fields if d.required is None else d.required
            for r in records:
                v = tuple(real[r.id].get(f, "").lower() for f in d.fields)
                if all(real[r.id].get(f, "") for f in must):
                    groups[v].append(r)
            for g in groups.values():
                for i, a in enumerate(g):
                    for b in g[i + 1:]:
                        pairs.add((a.id, b.id))
        else:
            blocks: dict[tuple[str, ...], list[Record]] = defaultdict(list)
            for r in records:
                blocks[tuple(real[r.id].get(f, "").lower() for f in d.block_on)].append(r)
            for g in blocks.values():
                names = [(r, " ".join(_name_tokens(real[r.id].get(f, "")) for f in d.fields)) for r in g]
                for i, (a, na) in enumerate(names):
                    for b, nb in names[i + 1:]:
                        if na and nb and fuzz.token_set_ratio(na, nb) >= d.threshold:
                            pairs.add((a.id, b.id))
        by_id = {r.id: r for r in records}
        for a_id, b_id in sorted(pairs):
            a, b = by_id[a_id], by_id[b_id]
            if a.key(spec) == b.key(spec) and all(a.key(spec)):
                continue  # same key: handled as a key conflict
            if any(real[a.id].get(f) and real[b.id].get(f) and real[a.id][f].lower() != real[b.id][f].lower()
                   for f in d.unless_different):
                continue
            for x, y in ((a, b), (b, a)):
                x.issues.append(Issue(code=d.id.upper(), severity=d.severity,
                                      message=f"{d.message}: {y.source_label} row {y.row} ({'/'.join(y.key(spec))})", related=[y.id]))


_LEGAL = re.compile(r"\b(inc|incorporated|llc|ltd|limited|co|corp|corporation|company|gmbh|plc|sa|ag|bv|the)\b")


def _name_tokens(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return re.sub(r"\s+", " ", _LEGAL.sub(" ", n)).strip()


def _references(spec: DatasetSpec, records: list[Record], real: dict[str, dict[str, str]],
                references: dict[str, tuple[str, bytes]], result: GateResult) -> None:
    for ref in spec.references:
        if ref.dataset not in references:
            result.warnings.append(f"No {ref.dataset} file was given, so {ref.field} was not checked against it")
            continue
        name, data = references[ref.dataset]
        try:
            header, rows = read_table(name, data)
        except TableError as exc:
            raise GateInputError(f"reference {ref.dataset}: {exc}") from exc
        if ref.key not in header:
            raise GateInputError(f"reference {ref.dataset} ({name}) has no column '{ref.key}'")
        status = {r.values.get(ref.key, "").strip(): r.values.get(ref.status_field or "", "").strip() for r in rows}
        for r in records:
            v = real[r.id].get(ref.field, "")
            if not v:
                continue
            if v not in status:
                r.issues.append(Issue(code="UNKNOWN_REFERENCE", severity=ref.severity, field=ref.field,
                                      message=f"{ref.field} {v} is not in {ref.dataset} ({name})"))
            elif ref.status_field and ref.allowed_status and status[v].lower() not in {s.lower() for s in ref.allowed_status}:
                r.issues.append(Issue(code="REFERENCE_STATUS", severity=ref.status_severity, field=ref.field,
                                      message=f"{ref.field} {v} is '{status[v] or 'blank'}' in {ref.dataset}"))


def _groups(spec: DatasetSpec, records: list[Record], real: dict[str, dict[str, str]]) -> None:
    for g in spec.group_consistency:
        groups: dict[tuple[str, ...], list[Record]] = defaultdict(list)
        for r in records:
            k = tuple(real[r.id].get(f, "") for f in g.group_by)
            if all(k):
                groups[k].append(r)
        for k, members in groups.items():
            for f in g.fields:
                vals = sorted({real[r.id].get(f, "") for r in members if real[r.id].get(f, "")})
                if len(vals) > 1:
                    for r in members:
                        r.issues.append(Issue(code="GROUP_INCONSISTENT", severity=g.severity, field=f,
                                              message=f"the {len(members)} records of {'/'.join(g.group_by)} {'/'.join(k)} "
                                                      f"disagree on {f}: {', '.join(vals)}",
                                              related=[m.id for m in members if m.id != r.id]))


def _outliers(spec: DatasetSpec, records: list[Record], typed: dict[str, dict[str, Any]]) -> None:
    for o in spec.outliers:
        groups: dict[tuple[str, ...], list[Record]] = defaultdict(list)
        for r in records:
            if isinstance(typed[r.id].get(o.field), Decimal):
                groups[tuple(r.canonical.get(f, "") for f in o.group_by)].append(r)
        for k, members in groups.items():
            if len(members) < o.min_group:
                continue
            vals = [typed[r.id][o.field] for r in members]
            med = Decimal(statistics.median(vals))
            mad = Decimal(statistics.median([abs(v - med) for v in vals]))
            spread = max(mad, abs(med) * Decimal("0.05"))
            if spread == 0:
                continue
            for r, v in zip(members, vals, strict=True):
                if abs(v - med) > o.factor * spread:
                    r.issues.append(Issue(code="OUTLIER", severity=o.severity, field=o.field,
                                          message=f"{o.field} {_fmt_decimal(v)} is far from the {len(members)} comparable records "
                                                  f"({'/'.join(k) or 'all'}: median {_fmt_decimal(med)})"))


def _previous(spec: DatasetSpec, previous: tuple[str, bytes], result: GateResult) -> dict[tuple[str, ...], dict[str, str]]:
    name, data = previous
    try:
        header, rows = read_table(name, data)
    except TableError as exc:
        raise GateInputError(f"last accepted snapshot: {exc}") from exc
    missing = [f for f in spec.key if f not in header]
    if missing:
        raise GateInputError(f"last accepted snapshot {name} has no key column {', '.join(missing)}")
    out = {}
    for r in rows:
        k = tuple(r.values.get(f, "") for f in spec.key)
        if all(k):
            out[k] = {c: r.values.get(c, "") for c in spec.fields}
    return out


def _changes(spec: DatasetSpec, records: list[Record], real: dict[str, dict[str, str]],
             prev: dict[tuple[str, ...], dict[str, str]]) -> None:
    assert spec.change_control
    for r in records:
        k = tuple(real[r.id].get(f, "") for f in spec.key)
        if k not in prev:
            continue
        for f in spec.change_control.fields:
            old, new = prev[k].get(f, ""), real[r.id].get(f, "")
            if old != new and f not in r.invalid_fields:
                s = spec.fields[f].sensitive
                r.issues.append(Issue(code="CONTROLLED_FIELD_CHANGED", severity=spec.change_control.severity, field=f,
                                      message=f"{f} changed from {(mask(old) if s else old) or 'blank'} to {(mask(new) if s else new) or 'blank'} "
                                              "since the last accepted load; confirm it with the counterparty through a known contact"))


def _decide(rec: Record, decisions: Decisions) -> None:
    sev = {i.severity for i in rec.issues}
    rec.decision = "rejected" if "reject" in sev else "review" if "review" in sev else "accepted"
    rec.decided_by = "rules"
    if rec.id in decisions.rejections and rec.decision != "accepted":
        rec.decision, rec.decided_by = "rejected", decisions.rejections[rec.id][0]
    elif rec.decision == "review" and rec.id in decisions.releases:
        fp, actor, _ = decisions.releases[rec.id]
        if fp == rec.review_fingerprint():
            rec.decision, rec.decided_by = "accepted", actor


DQ_ACTION = {"reject": "Correct the record in the source system (or here, with a reason) and run the gate again.",
             "review": "A named person releases it with a reason, or corrects it.",
             "info": "Nothing to do: recorded for the audit trail."}


def as_findings(result: GateResult) -> list[Finding]:
    """Every issue on every record in the shared shape (finops.core.policy). Values are the masked ones a report shows."""
    out = []
    for r in result.records:
        for i in r.issues:
            out.append(Finding(engine="dq", code=i.code, blocking=i.severity != "info", reason=i.message,
                               evidence={"source": r.source_label, "file": r.file, "row": r.row, "field": i.field,
                                         "related": i.related},
                               required_action=DQ_ACTION[i.severity], produced_by=f"dq check {i.code} ({result.dataset})",
                               subjects=[r.id, *i.related], severity=i.severity))
    return out
