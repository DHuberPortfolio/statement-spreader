"""An industry-aware ontology: what a printed label means in the language of the company's own industry (D67).

The template has about 80 lines. Filers have thousands of wordings, and the same words mean different things by industry.
A flat list of synonyms cannot hold that, so a term here is a concept with a context:

- ``family``: the broad idea it belongs to. Lease operating expenses (energy), property operating expenses (real estate) and
  utility operating expenses all sit in the family ``operating_expense``, but stay three separate concepts.
- ``destination``: the template line it rolls up to, if any. The detail survives on the mapping as ``concept``.
- ``role``: ``line`` is a row of a statement. ``disclosure`` is a measure a statement may print but which is not a line of it
  (funds from operations, occupancy, reserves): it is recognised so it is never pushed onto a line.
- ``statement``, ``side``, ``sections``, ``not_when``: where the words mean this and where they do not.
- ``industries`` on the file: a concept only applies when the document shows that it is in one of them.

The industry comes from the document: its own rows carry the signature terms of its trade, and it takes at least two different
ones to count. A bank's "rental income" is not a landlord's.

Files live in config/ontology, one per industry. A group's fields are defaults for the concepts inside it.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

from .numbers import clean_label
from .profile import matches

ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "config" / "ontology"

ROLES = {"line", "disclosure"}
STATEMENTS = {"income_statement", "balance_sheet", "cash_flow", "any"}
SIDES = {"asset", "liability", "equity"}
UNITS = {"currency", "per_share", "per_unit", "shares", "percent", "ratio", "volume", "count", "days", "area", "text"}
SIGNS = {"as_printed", "positive", "negative", "contra"}  # contra: deducted from the line it feeds, however it is printed
REVIEW = {"calibrated", "always"}  # always: the words are ambiguous, so a person sees it however well the rule is measured
_COST_HEADING = re.compile(r"\bcosts?\b|\bexpenses?\b")
SIGNATURE_MIN = 2  # distinct signature concepts before a document counts as being in an industry


class Concept(BaseModel):
    id: str
    label: str  # 1 canonical concept
    industry: str  # 2
    family: str  # the broad idea: separate concepts share it without being merged
    statement: str = "any"  # 3
    role: str = "line"
    destination: list[str] = Field(default_factory=list)  # 4 first line the profile has; current/noncurrent choose by section
    current: str | None = None
    noncurrent: str | None = None
    in_cash_flow: str | None = None  # the line it feeds when the same words appear on the cash flow statement
    synonyms: list[str] = Field(default_factory=list)  # 5
    not_when: list[str] = Field(default_factory=list)  # label patterns that look alike and mean something else
    sections: list[str] = Field(default_factory=list)  # only under these section headers, when set
    side: str | None = None  # the balance sheet side it can sit on
    related: list[str] = Field(default_factory=list)  # 6
    context: str = ""  # 7
    unit: str = "currency"  # 8
    sign: str = "as_printed"  # 9
    part_of: str | None = None  # 10 a part of this line: it cannot be larger than the line
    review: str = "calibrated"  # 11
    source: str = ""  # 12
    signature: bool = False  # seeing it is evidence of the industry
    overrides_alias: bool = False  # in its industry, this meaning beats the general alias for the same words

    @model_validator(mode="after")
    def _valid(self) -> Concept:
        if self.role not in ROLES:
            raise ValueError(f"{self.id}: role {self.role}")
        if self.statement not in STATEMENTS:
            raise ValueError(f"{self.id}: statement {self.statement}")
        if self.side and self.side not in SIDES:
            raise ValueError(f"{self.id}: side {self.side}")
        if self.unit not in UNITS or self.sign not in SIGNS or self.review not in REVIEW:
            raise ValueError(f"{self.id}: unit, sign or review")
        if self.role == "line" and not (self.destination or self.current or self.noncurrent):
            raise ValueError(f"{self.id}: a line needs a destination")
        if self.role == "disclosure" and (self.destination or self.current or self.noncurrent):
            raise ValueError(f"{self.id}: a disclosure has no destination")
        if not self.source:
            raise ValueError(f"{self.id}: every concept says where it came from")
        for s in self.synonyms + self.not_when:
            if "*" not in s and s != clean(s):
                raise ValueError(f"{self.id}: '{s}' is not in cleaned form")
        return self

    @property
    def terms(self) -> list[str]:
        """Every wording: the label with and without its abbreviation, the abbreviation alone, and the synonyms."""
        base = re.sub(r"\s*\([^)]*\)", "", self.label)
        short = re.findall(r"\(([^)]*)\)", self.label)
        return [clean(base), *(clean(s) for s in short), *self.synonyms]


def clean(label: str) -> str:
    """The same cleaning a row label gets, so a term and a printed row compare as equals."""
    return clean_label(label)


@dataclass(frozen=True)
class Match:
    concept: Concept
    destination: str | None  # None for a disclosure, or a line this profile lacks


class Ontology:
    def __init__(self, concepts: list[Concept]):
        self.concepts = concepts
        self.by_id = {c.id: c for c in concepts}
        if len(self.by_id) != len(concepts):
            raise ValueError("duplicate concept id")
        self._exact: dict[str, list[Concept]] = {}
        self._wild: list[tuple[str, Concept]] = []
        for c in concepts:
            for t in c.terms:
                if "*" in t:
                    self._wild.append((t, c))
                else:
                    self._exact.setdefault(t, []).append(c)

    def signatures(self, labels: list[str]) -> dict[str, int]:
        """How many different signature concepts of each industry these labels hold."""
        found: dict[str, set[str]] = {}
        for lab in set(labels):
            for c in self._hits(lab):
                if c.signature:
                    found.setdefault(c.industry, set()).add(c.id)
        return {k: len(v) for k, v in found.items()}

    def industries(self, labels: list[str]) -> frozenset[str]:
        """The industries a document's own rows show it to be in. It can be several: a utility with a gas business."""
        return frozenset(k for k, n in self.signatures(labels).items() if n >= SIGNATURE_MIN)

    def _hits(self, label: str) -> list[Concept]:
        return list(self._exact.get(label, [])) + [c for p, c in self._wild if matches(p, label)]

    def candidates(self, label: str, statement: str, sections: list[str], industries: frozenset[str],
                   wrong_side: frozenset[str] = frozenset()) -> list[Concept]:
        """Concepts these words can mean here: right statement, side, section and industry, and not excluded."""
        out = []
        for c in self._hits(label):
            if c.industry != "cross_industry" and c.industry not in industries:
                continue
            if c.statement not in ("any", statement) and not (statement == "cash_flow" and c.in_cash_flow):
                continue
            if c.side and c.side in wrong_side:
                continue
            if c.sections and not any(matches(s, sec) for s in c.sections for sec in sections):
                continue
            if any(matches(p, label) for p in c.not_when):
                continue
            if c.family == "revenue" and any(_COST_HEADING.search(s) for s in sections):
                continue  # "Subscription" under "Cost of revenue" is a cost of subscriptions
            out.append(c)
        return out

    def resolve(self, c: Concept, sections: list[str], lines: set[str], statement: str = "") -> str | None:
        """The template line a concept feeds in this profile, in this place on the statement."""
        if c.role == "disclosure":
            return None
        if statement == "cash_flow" and c.in_cash_flow:
            return c.in_cash_flow if c.in_cash_flow in lines else None
        in_current = any("current" in s and not re.search(r"\bnon ?current\b|long term", s) for s in sections)
        in_noncurrent = any(re.search(r"\bnon ?current\b|long term", s) for s in sections)
        if c.current and in_current and c.current in lines:
            return c.current
        if c.noncurrent and (in_noncurrent or not in_current) and c.noncurrent in lines:
            return c.noncurrent
        return next((d for d in c.destination if d in lines), None)

    def match(self, label: str, statement: str, sections: list[str], industries: frozenset[str], lines: set[str],
              wrong_side: frozenset[str] = frozenset()) -> Match | None:
        """One clear meaning, or None. Concepts that disagree on where the row goes are not a match: a person decides."""
        hits = self.candidates(label, statement, sections, industries, wrong_side)
        if not hits:
            return None
        # A concept of the document's own industry says more than a cross-industry one.
        own = [c for c in hits if c.industry != "cross_industry"]
        hits = own or hits
        places = {self.resolve(c, sections, lines, statement) for c in hits}
        if len(places) != 1:
            return None
        return Match(hits[0], places.pop())


def _concepts(path: Path) -> list[Concept]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    industry = data["industry"]
    file_defaults = {k: v for k, v in data.items() if k not in {"industry", "groups", "title"}}
    out = []
    for group in data["groups"]:
        defaults = {**file_defaults, **{k: v for k, v in group.items() if k != "concepts"}}
        for raw in group["concepts"]:
            item = {"label": raw} if isinstance(raw, str) else raw
            merged = {**defaults, **item}
            if isinstance(merged.get("destination"), str):
                merged["destination"] = [merged["destination"]]
            merged.setdefault("id", re.sub(r"\s+", "_", clean(item["label"])))
            merged["id"] = f"{industry}.{merged['id']}"
            out.append(Concept(industry=industry, **merged))
    return out


def fingerprint() -> str:
    """Changes when any concept changes, so a document is spread again rather than a saved run reused."""
    digest = hashlib.sha256()
    for p in sorted(ONTOLOGY_DIR.glob("*.yaml")):
        digest.update(p.read_bytes())
    return digest.hexdigest()[:12]


@lru_cache(maxsize=1)
def load(directory: str | None = None) -> Ontology:
    if os.environ.get("SPREADER_ONTOLOGY") == "off":  # for a before-and-after measurement, and as an off switch
        return Ontology([])
    root = Path(directory) if directory else ONTOLOGY_DIR
    return Ontology([c for p in sorted(root.glob("*.yaml")) for c in _concepts(p)])
