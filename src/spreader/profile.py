"""Loading and validating a spread profile (config/profiles/*.yaml).

A profile is the part a new organisation edits: its template lines, the labels that map to
them, its checks and ratios. It is validated on load so a typo fails loudly at start-up rather
than producing a quietly wrong spread.
"""

from __future__ import annotations

import fnmatch
import hashlib
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from . import formulas
from .contracts import StatementType, ValueUnit
from .numbers import clean_label

PROFILE_DIR = Path(__file__).resolve().parents[2] / "config" / "profiles"

KINDS = {"income", "cost", "result", "either", "asset", "liability", "equity", "flow", "per_share", "shares"}


class SectionRule(BaseModel):
    section: list[str]
    labels: list[str]
    confidence: float | None = None  # for a catch-all ("*") rule; default 0.75


class LineDef(BaseModel):
    id: str
    label: str
    kind: str
    critical: bool = False
    aliases: list[str] = Field(default_factory=list)
    sections: list[SectionRule] = Field(default_factory=list)
    parts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _kind(self) -> LineDef:
        if self.kind not in KINDS:
            raise ValueError(f"line {self.id}: unknown kind '{self.kind}'")
        self.aliases = [clean_label(a) if "*" not in a else a.lower() for a in self.aliases]
        return self

    @property
    def unit(self) -> ValueUnit:
        if self.kind == "per_share":
            return ValueUnit.PER_SHARE
        if self.kind == "shares":
            return ValueUnit.SHARES
        return ValueUnit.MONEY


class DetectDef(BaseModel):
    must_any: list[str]
    also_any: list[str] = Field(default_factory=list)
    exclude_any: list[str] = Field(default_factory=list)


class StatementDef(BaseModel):
    title: str
    detect: DetectDef
    lines: list[LineDef]
    # Sections whose rows are disclosures, not part of the statement ("Supplemental cash flow
    # disclosure"): their rows are excluded on purpose and said so.
    ignore_sections: list[str] = Field(default_factory=list)


class DerivedDef(BaseModel):
    line: str
    expr: str
    requires: list[str] = Field(default_factory=list)
    skip_check: str | None = None


class CheckDef(BaseModel):
    id: str
    statement: StatementType
    title: str
    lhs: str
    rhs: str
    severity: str = "blocker"
    relative_tolerance: float | None = None
    note: str = ""


class RatioDef(BaseModel):
    id: str
    label: str
    expr: str
    format: str = "times"
    note: str = ""


class Profile(BaseModel):
    id: str
    version: str
    title: str
    statements: dict[StatementType, StatementDef]
    derived: list[DerivedDef] = Field(default_factory=list)
    checks: list[CheckDef] = Field(default_factory=list)
    ratios: list[RatioDef] = Field(default_factory=list)
    content_hash: str = ""

    @model_validator(mode="after")
    def _validate(self) -> Profile:
        ids: set[str] = set()
        for st in self.statements.values():
            for line in st.lines:
                if line.id in ids:
                    raise ValueError(f"line id '{line.id}' is defined twice")
                ids.add(line.id)
        for st in self.statements.values():
            for line in st.lines:
                bad = [p for p in line.parts if p not in ids]
                if bad:
                    raise ValueError(f"line {line.id}: parts {bad} are not lines")
        exprs: list[tuple[str, str]] = []
        exprs += [(f"derived {d.line}", d.expr) for d in self.derived]
        exprs += [(f"check {c.id}", c.lhs) for c in self.checks] + [(f"check {c.id}", c.rhs) for c in self.checks]
        exprs += [(f"ratio {r.id}", r.expr) for r in self.ratios]
        for where, expr in exprs:
            unknown = formulas.names(expr) - ids
            if unknown:
                raise ValueError(f"{where}: unknown line(s) {sorted(unknown)} in '{expr}'")
        for d in self.derived:
            if d.line not in ids:
                raise ValueError(f"derived line '{d.line}' is not a line")
        check_ids = {c.id for c in self.checks}
        for d in self.derived:
            if d.skip_check and d.skip_check not in check_ids:
                raise ValueError(f"derived {d.line}: skip_check '{d.skip_check}' is not a check")
        return self

    @cached_property
    def lines(self) -> dict[str, LineDef]:
        return {line.id: line for st in self.statements.values() for line in st.lines}

    @cached_property
    def line_statement(self) -> dict[str, StatementType]:
        return {line.id: stype for stype, st in self.statements.items() for line in st.lines}


def matches(pattern: str, label: str) -> bool:
    if "*" in pattern:
        return fnmatch.fnmatchcase(label, pattern)
    return label == pattern


def load_profile(path: str | Path | None = None) -> Profile:
    p = Path(path) if path else PROFILE_DIR / "us-commercial.yaml"
    raw = p.read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{p} is not a profile")
    profile = Profile.model_validate(data)
    profile.content_hash = hashlib.sha256(raw).hexdigest()[:12]
    return profile


def list_profiles() -> list[Path]:
    return sorted(PROFILE_DIR.glob("*.yaml"))
