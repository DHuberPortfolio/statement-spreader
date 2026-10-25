"""Reconciliation settings: how to read each source, what counts as a match, what needs a person.

Everything company-specific lives in a YAML profile (config/finops/recon/*.yaml); this module
only defines and validates the shape. Column names are never guessed: a profile names each
column it uses, and a file missing one of them is refused with the column's name.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from finops.core.money import Tolerance

AUTO_RULES = {"reference", "unique_amount_date", "assignment", "one_to_many", "many_to_one"}


class SourceSpec(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")  # short id used in record ids, e.g. "bank"
    label: str  # what a person calls it, e.g. "Bank statement"
    id_field: str | None = None  # the source's own transaction id, if it has one
    date_field: str
    amount_field: str | None = None  # one signed column ...
    inflow_field: str | None = None  # ... or two columns: money in (deposits, debits to cash)
    outflow_field: str | None = None  # and money out (withdrawals, credits to cash)
    amount_sign: Literal["as_is", "negate"] = "as_is"  # negate when the file's sign is the opposite of ours
    # A negative number inside a money-in or money-out column: "refuse" (an unreadable row, the default),
    # "magnitude" (the column decides the direction), or "reverse" (a negative deposit is money out).
    negative_in_columns: Literal["refuse", "magnitude", "reverse"] = "refuse"
    reference_field: str | None = None
    description_field: str | None = None
    counterparty_field: str | None = None
    currency_field: str | None = None
    date_formats: list[str] = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%m/%d/%y"]
    sheet: str | None = None

    @model_validator(mode="after")
    def _amount_columns(self) -> SourceSpec:
        two = self.inflow_field is not None and self.outflow_field is not None
        if (self.amount_field is None) == (not two):
            raise ValueError("give either amount_field, or both inflow_field and outflow_field")
        return self

    def required_columns(self) -> list[str]:
        cols = [self.date_field, self.amount_field, self.inflow_field, self.outflow_field, self.id_field,
                self.reference_field, self.description_field, self.counterparty_field, self.currency_field]
        return [c for c in cols if c]


class ReferenceRules(BaseModel):
    strip_prefixes: list[str] = ["INV", "CHK", "CHECK", "REF", "NO"]
    strip_leading_zeros: bool = True
    min_length: int = Field(default=2, ge=1)


class GroupRule(BaseModel):
    """One record on one side equal to the sum of several on the other (batch deposit, split settlement)."""

    enabled: bool = True
    max_items: int = Field(default=4, ge=2, le=6)
    max_candidates: int = Field(default=40, ge=2, le=80)  # nearest by date; exact sums search all of them


class MatchingRules(BaseModel):
    date_window_days: int = Field(default=5, ge=0, le=60)
    reference_date_window_days: int = Field(default=45, ge=0, le=365)  # a cheque can clear weeks later
    amount_tolerance: Tolerance = Tolerance()  # amounts this close are equal (default: to the cent)
    review_tolerance: Tolerance = Tolerance(abs=Decimal("50"), pct=Decimal("0.05"))  # beyond equal, up to this: proposed with the difference
    description_similarity: int = Field(default=85, ge=50, le=100)  # 0-100, for pairing without a reference
    # Amount and date alone are weak evidence (equal amounts recur). When true, an amount-and-date pairing is
    # automatic only if a second signal agrees: the party names, or the references (allowing a typo).
    require_corroboration: bool = True
    strategy: Literal["component", "greedy"] = "component"
    auto_accept: list[str] = sorted(AUTO_RULES)
    # A rule on auto_accept settles a match without a person only if its measured precision clears this bar (the
    # 95% lower bound, config/calibration/recon.json, finops.core.policy). A rule never measured is proposed.
    auto_accept_min_precision: float = Field(default=0.98, ge=0.5, le=1.0)
    one_to_many: GroupRule = GroupRule()
    many_to_one: GroupRule = GroupRule()
    references: ReferenceRules = ReferenceRules()

    @model_validator(mode="after")
    def _known_rules(self) -> MatchingRules:
        unknown = set(self.auto_accept) - AUTO_RULES
        if unknown:
            raise ValueError(f"auto_accept has unknown rules {sorted(unknown)}; known: {sorted(AUTO_RULES)}")
        return self


class ExceptionRules(BaseModel):
    fee_keywords: list[str] = ["service fee", "service charge", "monthly fee", "wire fee", "bank fee", "interest",
                               "overdraft", "maintenance fee"]
    timing_days: int = Field(default=4, ge=0)  # unmatched right-side items this close to the period end are timing differences
    duplicate_date_days: int = Field(default=3, ge=0)
    reversal_days: int = Field(default=10, ge=0)


class ReconProfile(BaseModel):
    id: str
    name: str
    version: str = "1"
    currency: str = "USD"  # used when a source has no currency column
    left: SourceSpec
    right: SourceSpec
    matching: MatchingRules = MatchingRules()
    exceptions: ExceptionRules = ExceptionRules()

    @model_validator(mode="after")
    def _names_differ(self) -> ReconProfile:
        if self.left.name == self.right.name:
            raise ValueError("left and right sources need different names")
        return self
