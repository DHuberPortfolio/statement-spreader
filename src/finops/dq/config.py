"""Data-quality gate settings: the canonical record, how each source system maps into it, and the rules.

One YAML file describes one dataset (vendors, purchase orders, journal lines...). Nothing is guessed at run time:
every source names the column behind each canonical field, and a file missing one of them is refused with its name.
Rules are a closed set of deterministic checks (below); there is no expression language to get wrong or exploit.

Severities: "reject" means the record is definitely wrong and must be corrected (in the source, or by a named person
here, with a reason); "review" means it may be right but needs a person before it moves on. Accepted records are the
only ones exported for loading.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FieldType = Literal["string", "integer", "decimal", "date", "enum", "email", "aba_routing", "bool"]
Normalizer = Literal["trim", "collapse_spaces", "upper", "lower", "digits_only", "ein", "strip_punctuation_ends"]
Severity = Literal["reject", "review"]


class FieldSpec(BaseModel):
    type: FieldType = "string"
    required: bool = False
    pattern: str | None = None  # the normalised value must match all of it (re.fullmatch)
    values: list[str] = []  # enum: the allowed canonical values
    min: Decimal | None = None  # integer/decimal: inclusive bounds
    max: Decimal | None = None
    max_length: int | None = None
    normalize: list[Normalizer] = ["trim", "collapse_spaces"]
    sensitive: bool = False  # masked (last four characters) in reports, logs and the review screen
    description: str = ""

    @model_validator(mode="after")
    def _check(self) -> FieldSpec:
        if self.type == "enum" and not self.values:
            raise ValueError("an enum field needs its allowed values")
        if self.pattern:
            re.compile(self.pattern)
        return self


class SourceSpec(BaseModel):
    label: str  # what a person calls the system, e.g. "Procurement portal export"
    columns: dict[str, str]  # canonical field -> the source's column name
    defaults: dict[str, str] = {}  # canonical field -> a constant, for fields this source does not have
    value_maps: dict[str, dict[str, str]] = {}  # canonical field -> {source value (case-insensitive): canonical}
    replace: dict[str, dict[str, str]] = {}  # canonical field -> {text: replacement}, e.g. aliases split by "|" -> ";"
    strip_patterns: dict[str, str] = {}  # canonical field -> a regex removed (case-insensitive), e.g. "^NET\s*" in NET30
    date_formats: list[str] = ["%Y-%m-%d"]
    decimal_scale: dict[str, Decimal] = {}  # canonical field -> multiplier, e.g. a percent column to a fraction: 0.01
    sheet: str | None = None

    @model_validator(mode="after")
    def _check(self) -> SourceSpec:
        for p in self.strip_patterns.values():
            re.compile(p)
        return self


class When(BaseModel):
    """A rule applies only to records where each named field has one of the listed values (canonical, compared
    case-insensitively), and where each field in `present` is filled."""
    equals: dict[str, list[str]] = {}
    present: list[str] = []


class Rule(BaseModel):
    """One record-level check. Each part present must hold: `require` fields filled, `forbid` fields empty,
    `pattern` values matching, `compare` true. Any failure raises the rule's code."""
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    severity: Severity = "reject"
    message: str
    when: When = When()
    require: list[str] = []
    require_one_of: list[str] = []
    forbid: list[str] = []
    pattern: dict[str, str] = {}
    compare: tuple[str, Literal["<", "<=", "==", ">=", ">", "!="], str] | None = None

    @model_validator(mode="after")
    def _check(self) -> Rule:
        if not (self.require or self.require_one_of or self.forbid or self.pattern or self.compare):
            raise ValueError(f"rule {self.id} checks nothing")
        for p in self.pattern.values():
            re.compile(p)
        return self


class DuplicateCheck(BaseModel):
    """Records with the same value(s) in `fields` but different keys. exact: equal normalised values; fuzzy: names
    that read alike (token-set similarity >= threshold) within the same `block_on` values. `unless_different`
    clears a pair whose listed fields are both filled and differ: two similar names with different tax ids are two
    companies. Duplicates are flagged for a person, never merged."""
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    fields: list[str]
    match: Literal["exact", "fuzzy"] = "exact"
    threshold: int = Field(default=92, ge=80, le=100)
    block_on: list[str] = []
    unless_different: list[str] = []
    # exact: the fields that must be filled for two records to be compared (default: all of `fields`). An account
    # number with no routing number (most countries) still matches another account number with none.
    required: list[str] | None = None
    severity: Severity = "review"
    message: str


class Reference(BaseModel):
    """`field` must name a record of another dataset (loaded from the file given at run time as `dataset`)."""
    field: str
    dataset: str
    key: str  # the column in the reference file
    severity: Severity = "reject"
    status_field: str | None = None  # optional: the reference record's status column ...
    allowed_status: list[str] = []  # ... must be one of these, else `status_severity`
    status_severity: Severity = "review"


class GroupConsistency(BaseModel):
    """Records sharing `group_by` must agree on `fields` (all lines of one purchase order: one vendor, one currency)."""
    group_by: list[str]
    fields: list[str]
    severity: Severity = "reject"


class Outlier(BaseModel):
    """A number far from its peers: |value - median| > factor x median absolute deviation, within `group_by`,
    when the group has at least `min_group` records. A typed extra zero is the classic case."""
    field: str
    group_by: list[str] = []
    factor: Decimal = Decimal(8)
    min_group: int = Field(default=4, ge=3)
    severity: Severity = "review"


class ChangeControl(BaseModel):
    """Fields that must not change silently against the last accepted snapshot (bank details, tax ids)."""
    fields: list[str]
    severity: Severity = "review"


class CarryForward(BaseModel):
    """While a record is held, its last accepted version goes out in its place (the business keeps working on data
    someone already checked), except when the held version says the record must stop: a vendor the source system
    blocked must not be revived from last month's file. Those keys are listed as withheld instead."""
    enabled: bool = True
    never_when: dict[str, list[str]] = {}


class DatasetSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    name: str
    key: list[str]  # the canonical fields that identify one record
    fields: dict[str, FieldSpec]
    sources: dict[str, SourceSpec]  # short source id -> how to read it
    rules: list[Rule] = []
    duplicates: list[DuplicateCheck] = []
    references: list[Reference] = []
    group_consistency: list[GroupConsistency] = []
    outliers: list[Outlier] = []
    change_control: ChangeControl | None = None
    carry_forward: CarryForward = CarryForward()
    formula_like_text: Severity | None = "review"  # text starting with = + - @ that is not a number

    @model_validator(mode="after")
    def _check(self) -> DatasetSpec:
        known = set(self.fields)

        def need(names: list[str] | tuple[str, ...], where: str) -> None:
            bad = [n for n in names if n not in known]
            if bad:
                raise ValueError(f"{where} names unknown field(s): {', '.join(bad)}")

        need(self.key, "key")
        for sid, s in self.sources.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,19}", sid):
                raise ValueError(f"source id '{sid}' must be short lowercase letters, digits or _")
            need(list(s.columns) + list(s.defaults) + list(s.value_maps) + list(s.replace) + list(s.strip_patterns)
                 + list(s.decimal_scale), f"source {sid}")
            unmapped = [f for f, spec in self.fields.items() if spec.required and f not in s.columns and f not in s.defaults]
            if unmapped:
                raise ValueError(f"source {sid} has no column for required field(s): {', '.join(unmapped)}")
        for r in self.rules:
            need(r.require + r.require_one_of + r.forbid + list(r.pattern) + list(r.when.equals) + r.when.present
                 + (list(r.compare[::2]) if r.compare else []), f"rule {r.id}")
        for d in self.duplicates:
            need(d.fields + d.block_on + d.unless_different + (d.required or []), f"duplicate check {d.id}")
            if d.required is not None and (not d.required or not set(d.required) <= set(d.fields)):
                raise ValueError(f"duplicate check {d.id}: `required` must name one or more of its `fields`")
        for ref in self.references:
            need([ref.field], f"reference to {ref.dataset}")
        for g in self.group_consistency:
            need(g.group_by + g.fields, "group consistency")
        for o in self.outliers:
            need([o.field] + o.group_by, "outlier check")
        if self.change_control:
            need(self.change_control.fields, "change control")
        need(list(self.carry_forward.never_when), "carry_forward")
        return self
