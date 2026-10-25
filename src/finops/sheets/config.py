"""The scanner's settings: what counts as a documented input, which constants are normal, how strict to be.

A company adapts the scanner here, not in code: its input-cell colour, the unit constants its models use, and the
severity of each finding kind (a team that links workbooks on purpose can make EXTERNAL_LINK an anomaly). Every
setting has a default, so an empty overlay that only says `extends: default.yaml` is valid.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["error", "risk", "anomaly"]

# What each finding kind means, and how sure the scanner is. "error": the workbook is broken whatever the intent.
# "risk": probably wrong, a person should look. "anomaly": worth knowing, often deliberate; not counted as a finding
# in the precision figures.
KINDS: dict[str, tuple[Severity, str]] = {
    "REF_ERROR": ("error", "Formula contains #REF! (a deleted row, column or sheet)"),
    "MISSING_SHEET": ("error", "Formula refers to a worksheet that does not exist"),
    "UNKNOWN_NAME": ("error", "Formula uses a name that is not defined in the workbook"),
    "BROKEN_NAME": ("error", "Defined name points at #REF! or a missing sheet"),
    "CIRCULAR_REFERENCE": ("error", "Cells depend on themselves"),
    "TEXT_NUMBER_IN_SUM": ("error", "Number stored as text inside a range that is added up: the total skips it"),
    "CACHED_ERROR": ("error", "The cell shows an error value"),
    "INCONSISTENT_FORMULA": ("risk", "Formula differs from the same formula on both sides of it"),
    "HARDCODED_OVERRIDE": ("risk", "Typed number in the middle of a formula-driven run"),
    "SUM_OMITS_ROW": ("risk", "Total stops short of a number that belongs to its block"),
    "DOUBLE_COUNT": ("risk", "Total adds a subtotal together with the items it already includes"),
    "EXTERNAL_LINK": ("risk", "Formula reads another workbook"),
    "HARDCODED_PLUG": ("risk", "Formula adds or subtracts a typed number to referenced values"),
    "CACHED_NA": ("risk", "The cell shows #N/A"),
    "DOCUMENTED_OVERRIDE": ("anomaly", "Typed number in a formula run, marked as an input or explained in a comment"),
    "PATTERN_BREAK": ("anomaly", "Formula differs from its neighbours but matches the cells across from it"),
    "CONSTANT_IN_FORMULA": ("anomaly", "Typed rate or factor inside a formula"),
    "VOLATILE_REFERENCE": ("anomaly", "INDIRECT or OFFSET: what the formula reads cannot be traced without calculating"),
    "HIDDEN_SHEET": ("anomaly", "Hidden worksheet that visible formulas read"),
    "UNPARSEABLE_FORMULA": ("anomaly", "The scanner could not read this formula"),
}


class ScanSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = "default"
    name: str = "Default spreadsheet checks"
    # Limits: a file beyond them is refused with a message, never half-scanned.
    max_file_mb: float = Field(default=25, gt=0)
    max_uncompressed_mb: float = Field(default=400, gt=0)
    max_cells: int = Field(default=2_000_000, gt=0)
    max_expanded_references: int = Field(default=3_000_000, gt=0)  # dependency tracing stops (and says so) beyond this
    # Runs: a cell is compared with its neighbours only when at least this many cells around it agree (and always
    # at least one on each side). 2 lets a three-year forecast row (E, F, G) be checked.
    min_run: int = Field(default=2, ge=2)
    max_odd_group: int = Field(default=2, ge=1)  # up to this many adjacent odd cells are still reported one by one
    # Documented inputs: a typed number in a formula run is not a risk when it carries one of these font colours
    # (aRGB, as Excel stores them) or a cell comment.
    input_font_colors: list[str] = Field(default_factory=lambda: ["FF0000FF"])
    comment_documents_override: bool = True
    # Constants that are normal inside formulas: units and calendar factors.
    allowed_addends: list[float] = Field(default_factory=lambda: [0.0, 1.0])
    allowed_multipliers: list[float] = Field(default_factory=lambda: [float(x) for x in (
        -1, 0, 1, 2, 3, 4, 6, 7, 10, 12, 24, 52, 60, 100, 360, 365, 366, 1000, 1_000_000, 0.5, 0.01, 0.001)])
    year_range: tuple[int, int] = (1990, 2100)
    aggregate_functions: list[str] = Field(default_factory=lambda: [
        "SUM", "SUBTOTAL", "AGGREGATE", "AVERAGE", "MIN", "MAX", "PRODUCT", "SUMPRODUCT", "SUMIF", "SUMIFS",
        "AVERAGEIF", "AVERAGEIFS"])
    volatile_functions: list[str] = Field(default_factory=lambda: ["INDIRECT", "OFFSET"])
    severity: dict[str, Severity] = Field(default_factory=dict)  # per-kind override, e.g. EXTERNAL_LINK: anomaly

    def severity_of(self, kind: str) -> Severity:
        return self.severity.get(kind, KINDS[kind][0])
