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
    # Hand-set confidence for a catch-all ("*") rule. No longer used: every rule's confidence is measured
    # (config/calibration/statements.json, finops.core.policy). Kept so existing overlays still load.
    confidence: float | None = None


class LineDef(BaseModel):
    id: str
    label: str
    kind: str
    critical: bool = False
    # An "either" line that a statement printing costs in parentheses also prints as a deduction
    # (income tax): flipped with the costs, so a tax expense is positive and a benefit negative.
    deduction: bool = False
    aliases: list[str] = Field(default_factory=list)
    sections: list[SectionRule] = Field(default_factory=list)
    parts: list[str] = Field(default_factory=list)
    total_aliases: list[str] = Field(default_factory=list)  # only for rows that foot as totals

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
    # "confirm": the check only ever confirms. A pass counts toward a value's confirmations; a failure raises no review
    # item, because a sum of detail lines fails whenever one printed row is left unplaced, which says nothing against
    # the lines it did find (D62).
    role: str = "flag"


class RatioDef(BaseModel):
    id: str
    label: str
    expr: str
    format: str = "times"
    note: str = ""
    # A covenant or policy limit. A computed value outside it raises a review item; a value that
    # cannot be computed raises one too, because an unknown covenant is not a passed covenant.
    min: float | None = None
    max: float | None = None


class Profile(BaseModel):
    id: str
    version: str
    title: str
    statements: dict[StatementType, StatementDef]
    derived: list[DerivedDef] = Field(default_factory=list)
    checks: list[CheckDef] = Field(default_factory=list)
    ratios: list[RatioDef] = Field(default_factory=list)
    # Checks and ratios of the base template that do not hold for this kind of company, with the reason (D50):
    # "check:is_gross_profit" -> "Banks do not report cost of sales". Shown, never silently dropped.
    not_applicable: dict[str, str] = Field(default_factory=dict)
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


def _overlay(base: dict, over: dict) -> dict:
    """Apply an organisation's overlay to a base profile.

    The overlay can: rename and re-version the profile; add lines an industry needs (`add_lines:
    {statement: [line, ...]}`: a bank's loans and deposits, an insurer's premiums); add aliases or
    section rules to existing lines (`add_aliases: {line_id: [...]}`, `add_sections: {line_id: [...]}`);
    append checks, derived lines and ratios; and replace a ratio or check with the same id. It cannot
    delete template lines, so every organisation's spread stays comparable with the base template.
    A check or ratio that does not hold for the kind of company is declared `not_applicable: {checks: {id: reason},
    ratios: {id: reason}}`: it stops running and the profile says why (D50). An unknown id is an error.
    """
    import copy

    out = copy.deepcopy(base)
    for k in ("id", "version", "title"):
        if k in over:
            out[k] = over[k]
    existing = {ln["id"] for st in out["statements"].values() for ln in st["lines"]}
    for stype, new_lines in (over.get("add_lines") or {}).items():
        if stype not in out["statements"]:
            raise ValueError(f"overlay: add_lines names unknown statement '{stype}'")
        for ln in new_lines:
            if ln.get("id") in existing:
                raise ValueError(f"overlay: add_lines would redefine the template line '{ln.get('id')}'")
            existing.add(ln["id"])
        out["statements"][stype] = {**out["statements"][stype], "lines": list(out["statements"][stype]["lines"]) + list(new_lines)}
    lines = {ln["id"]: ln for st in out["statements"].values() for ln in st["lines"]}
    for line_id, aliases in (over.get("add_aliases") or {}).items():
        if line_id not in lines:
            raise ValueError(f"overlay: add_aliases names unknown line '{line_id}'")
        lines[line_id]["aliases"] = list(lines[line_id].get("aliases", [])) + list(aliases)
    for line_id, rules in (over.get("add_sections") or {}).items():
        if line_id not in lines:
            raise ValueError(f"overlay: add_sections names unknown line '{line_id}'")
        lines[line_id]["sections"] = list(lines[line_id].get("sections", [])) + list(rules)
    for stype, extra in (over.get("add_detect") or {}).items():
        if stype not in out["statements"]:
            raise ValueError(f"overlay: add_detect names unknown statement '{stype}'")
        det = dict(out["statements"][stype]["detect"])
        for k in ("must_any", "also_any"):
            det[k] = list(det.get(k, [])) + list(extra.get(k, []))
        out["statements"][stype] = {**out["statements"][stype], "detect": det}
    for key in ("checks", "ratios", "derived"):
        merged = {(d.get("id") or d.get("line")): d for d in out.get(key, [])}
        for d in over.get(key, []) or []:
            merged[d.get("id") or d.get("line")] = d
        out[key] = list(merged.values())
    na = over.get("not_applicable") or {}
    unknown_kinds = set(na) - {"checks", "ratios"}
    if unknown_kinds:
        raise ValueError(f"overlay: not_applicable takes checks and ratios, not {sorted(unknown_kinds)}")
    declared = dict(out.get("not_applicable", {}))
    for key in ("checks", "ratios"):
        reasons = na.get(key) or {}
        have = {d.get("id") for d in out.get(key, [])}
        missing = set(reasons) - have
        if missing:
            raise ValueError(f"overlay: not_applicable names {key} that do not exist: {sorted(missing)}")
        for cid, why in reasons.items():
            if not str(why).strip():
                raise ValueError(f"overlay: not_applicable {key} '{cid}' needs a reason")
            declared[f"{key[:-1]}:{cid}"] = str(why).strip()
        out[key] = [d for d in out.get(key, []) if d.get("id") not in reasons]
    gone = set(na.get("checks") or {})
    for d in out.get("derived", []):  # a derived line no longer needs to skip a check that does not run
        if d.get("skip_check") in gone:
            d.pop("skip_check")
    out["not_applicable"] = declared
    return out


def load_profile(path: str | Path | None = None) -> Profile:
    """Load a profile. A profile with `extends: <file>` is an overlay on that base profile."""
    p = Path(path) if path else PROFILE_DIR / "us-commercial.yaml"
    raw = p.read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{p} is not a profile")
    digest = hashlib.sha256(raw)
    if "extends" in data:
        base_path = (p.parent / str(data["extends"])).resolve()
        if base_path.parent != p.parent.resolve():
            raise ValueError("overlay: 'extends' must name a profile in the same folder")
        base_raw = base_path.read_bytes()
        digest.update(base_raw)
        data = _overlay(yaml.safe_load(base_raw), data)
    profile = Profile.model_validate(data)
    profile.content_hash = digest.hexdigest()[:12]
    return profile


def list_profiles() -> list[Path]:
    return sorted(PROFILE_DIR.glob("*.yaml"))
