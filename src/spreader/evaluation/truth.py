"""The answer-key format every evaluation source produces.

A key describes what a correct spread of one document contains:

- spread: the value of each canonical line in each period, as an analyst would spread it
  (cost lines positive, cash outflows negative, money in units of currency after scaling).
- cells: optional, finer truth about individual printed numbers (which row, which period,
  which value, which line it feeds) for measuring extraction and source attribution.
- expect_review: kinds of review items that MUST be raised (for adversarial documents: no unit
  statement -> "assumed_scale"; a total that does not add up -> "footing" or "failed_check").
- unknown_lines: lines the key cannot judge (e.g. a company-specific XBRL tag that maps to no
  template line); spread values on these lines are not scored as right or wrong.

Values are strings of exact decimals so a key file round-trips without float error.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field


class TruthValue(BaseModel):
    statement: str  # income_statement | balance_sheet | cash_flow
    line: str  # canonical line id
    period: str  # period key, e.g. "2025-12-31/12M" or "2025-12-31/I"
    value: Decimal
    precision: Decimal = Decimal(1)  # the value is right to within half of this (the printed rounding)


class TruthCell(BaseModel):
    statement: str
    row_label: str  # the printed label of the row
    period: str
    value: Decimal  # the printed number after scaling, with the sign as printed
    line: str | None = None  # the canonical line the row feeds (None: no template line)
    role: str = "detail"  # detail | total | component (inside a total feeding the same line)
    xpath: str | None = None  # HTML only: the table cell the number is printed in (for attribution)


class AnswerKey(BaseModel):
    document: str  # file name of the document this key is for
    source: str  # "sec" | "synthetic"
    description: str = ""
    periods: list[str] = Field(default_factory=list)
    spread: list[TruthValue] = Field(default_factory=list)
    cells: list[TruthCell] = Field(default_factory=list)
    expect_review: list[str] = Field(default_factory=list)
    forbid_values: list[TruthValue] = Field(default_factory=list)  # values that must NOT appear (e.g. hidden rows)
    unknown_lines: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)  # e.g. ["adversarial", "no-unit-statement"]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> AnswerKey:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
