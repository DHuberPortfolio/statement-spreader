"""Data contracts shared by every stage.

The pipeline is a chain of typed hand-offs:

    bytes -> DocumentIR (tables of positioned tokens, each with a SourceRef)
          -> StatementTable (rows with parsed values per period)
          -> RowMapping (which canonical line each row feeds)
          -> Spread (one value per canonical line and period, with its provenance and status)
          -> CheckResult / ReviewItem (what passed, what failed, what a person must look at)

Money is Decimal end to end. A float can turn 0.1 + 0.2 into 0.30000000000000004; a spread
that is off by a fraction of a cent fails an equality check for no real reason.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    HTML = "html"
    PDF = "pdf"
    XLSX = "xlsx"


class SourceRef(BaseModel):
    """Where a piece of text came from, precise enough to show it to a person."""

    doc_id: str
    format: SourceFormat
    table: int
    row: int
    page: int | None = None  # PDF, 1-based
    bbox: tuple[float, float, float, float] | None = None  # PDF points: x0, top, x1, bottom
    sheet: str | None = None  # Excel
    cell: str | None = None  # Excel A1 reference
    xpath: str | None = None  # HTML element path
    text: str  # the text exactly as found
    ocr_confidence: float | None = None  # set only when the text was read by OCR from a scan (lowest word score, 0..1)


class Token(BaseModel):
    """A piece of text in a table row and its horizontal extent.

    x0/x1 are in the format's own unit: grid columns for HTML and Excel, points for PDF.
    Only their order and overlap matter, so the layout code works the same for all three.
    """

    text: str
    x0: float
    x1: float
    ref: SourceRef


class RawRow(BaseModel):
    index: int
    tokens: list[Token]
    indent: float = 0.0  # visual indentation in points (0 when unknown)
    bold: bool = False


class RawTable(BaseModel):
    index: int
    rows: list[RawRow]
    context: str = ""  # text just before the table: its title and unit statement
    page: int | None = None


class DocumentIR(BaseModel):
    doc_id: str  # sha256 of the file's bytes
    filename: str
    format: SourceFormat
    tables: list[RawTable]
    warnings: list[str] = Field(default_factory=list)
    preface: str = ""  # visible text before the first table (a filing's cover page)
    unit_statements: list[str] = Field(default_factory=list)  # units stated for the whole document (detect.py, D39)


class StatementType(str, Enum):
    INCOME = "income_statement"
    BALANCE = "balance_sheet"
    CASH_FLOW = "cash_flow"


class Period(BaseModel):
    """A column of a statement."""

    key: str  # e.g. "2025-09-27/12M" or "2025-09-27/I" (instant)
    end: str  # ISO date
    months: int | None  # duration in months; None for a balance-sheet instant
    label: str  # the header text it was read from
    assumed: list[str] = Field(default_factory=list)  # anything the system had to assume (sent to review)
    notes: list[str] = Field(default_factory=list)  # how it was read, when not from the column header alone


class ValueUnit(str, Enum):
    MONEY = "money"
    SHARES = "shares"
    PER_SHARE = "per_share"
    PERCENT = "percent"


class Scale(BaseModel):
    multiplier: int  # 1, 1_000, 1_000_000, 1_000_000_000
    evidence: str  # the words it was read from, or why it was assumed
    assumed: bool = False  # True: a person confirms it before approval (no rule cleared the bar)
    # The rule that set it (spreader.units; calibrated in config/calibration/units.json): scale.table (a unit statement
    # at the table, any wording, "(In U.S. dollars)" included), scale.document (one stated for the whole document),
    # scale.sibling (the other statements' printed unit), scale.conflict, scale.none (nothing found).
    rule: str = "scale.table"
    confidence: float | None = None  # the rule's measured lower bound (None: never measured)
    currency: str | None = None  # ISO code when the document names one ("EUR"); None when it names none
    currency_evidence: str = ""


class ParsedValue(BaseModel):
    raw: str  # the cell text, including any "$" or ")" merged from neighbours
    displayed: Decimal | None  # the number as shown, sign included; None when blank or not a number
    negative_display: bool = False  # shown in parentheses or with a minus
    dash: bool = False  # shown as a dash: nothing to report (read as zero)
    ref: SourceRef | None = None
    note: str | None = None  # why it could not be read, when it could not


class RowRole(str, Enum):
    HEADER = "header"  # a section title with no values ("Operating expenses:")
    DETAIL = "detail"
    TOTAL = "total"  # equals the sum of rows above it (found by footing, not by its label alone)


class StatementRow(BaseModel):
    index: int  # row index within the source table
    label: str  # the label as found
    label_clean: str  # lower case, footnote markers and punctuation removed
    section: str = ""  # nearest header above it ("operating expenses")
    indent: float = 0.0
    bold: bool = False
    unit: ValueUnit = ValueUnit.MONEY
    values: dict[str, ParsedValue] = Field(default_factory=dict)  # period key -> value
    role: RowRole = RowRole.DETAIL
    children: list[int] = Field(default_factory=list)  # for totals: the row indexes it sums
    label_ref: SourceRef | None = None


class StatementTable(BaseModel):
    doc_id: str
    table_index: int
    statement: StatementType
    title: str
    periods: list[Period]
    scale: Scale
    share_scale: Scale | None = None  # "shares in thousands"
    rows: list[StatementRow]
    detection_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class MapMethod(str, Enum):
    ALIAS = "alias"  # the profile's alias list
    MEMORY = "memory"  # a reviewer's earlier decision for this label
    FUZZY = "fuzzy"  # close spelling of an alias
    STRUCTURE = "structure"  # implied by position (a total of mapped rows, a header's children)
    MODEL = "model"  # a language model's suggestion
    HUMAN = "human"  # a reviewer's decision on this run
    NONE = "none"


class RowMapping(BaseModel):
    row_index: int
    canonical: str | None  # canonical line id, or None when unmapped / excluded
    method: MapMethod
    confidence: float  # 0..1
    excluded: bool = False  # deliberately left out (e.g. a memo line)
    candidates: list[tuple[str, float]] = Field(default_factory=list)
    reason: str = ""
    rule: str = ""  # the exact path that placed the row (calibration is per rule: finops.core.policy)


class ValueStatus(str, Enum):
    """What kind of fact a spread value is. Shown on every value in the interface."""

    EXTRACTED = "extracted"  # read from one source cell, no change but the declared scale
    NORMALIZED = "normalized"  # read from the source, then transformed (sign flipped, summed rows)
    CALCULATED = "calculated"  # computed by code from other spread values (not in the source)
    AI_MAPPED = "ai_mapped"  # from the source, but a model chose which line it belongs to
    HUMAN = "human"  # corrected or approved by a reviewer
    ASSUMED = "assumed"  # depends on something the system had to assume (e.g. no unit statement)
    MISSING = "missing"  # not found


class ProvenanceStep(BaseModel):
    """One step from source text to spread value, in plain words."""

    kind: str  # read | scale | sign | sum | map | calculate | correct
    detail: str


class SpreadValue(BaseModel):
    line: str  # canonical line id
    period: str  # period key
    value: Decimal | None
    status: ValueStatus
    confidence: float = 1.0
    source_rows: list[int] = Field(default_factory=list)
    refs: list[SourceRef] = Field(default_factory=list)
    steps: list[ProvenanceStep] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)  # ids of review items touching this value


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"  # an input was missing


class CheckResult(BaseModel):
    id: str
    title: str
    period: str
    status: CheckStatus
    lhs: Decimal | None = None
    rhs: Decimal | None = None
    difference: Decimal | None = None
    tolerance: Decimal | None = None
    lines: list[str] = Field(default_factory=list)
    explanation: str = ""


class ReviewKind(str, Enum):
    UNMAPPED_ROW = "unmapped_row"
    LOW_CONFIDENCE = "low_confidence"
    FAILED_CHECK = "failed_check"
    FOOTING = "footing"  # a total in the document does not equal its rows
    ASSUMED_SCALE = "assumed_scale"
    ASSUMED_PERIOD = "assumed_period"
    MISSING_STATEMENT = "missing_statement"
    CONFLICT = "conflict"  # two rows give different values for one line
    SUSPICIOUS = "suspicious"  # passes the checks but looks wrong (scale, sign)
    UNREADABLE = "unreadable"
    PRIOR_PERIOD = "prior_period"  # differs from the company's approved spread for the same period (spreader.company)
    SECOND_READER = "second_reader"  # the cell's inline XBRL tag disagrees with the printed number (opt-in, D37)
    CURRENCY = "currency"  # not the profile's currency, or statements in different currencies (spreader.units, D39)


class Severity(str, Enum):
    BLOCKER = "blocker"  # the spread must not be approved until resolved
    WARNING = "warning"
    INFO = "info"


class ReviewItem(BaseModel):
    id: str  # stable within a run, e.g. "check:bs_balance:2025-09-27/I"
    kind: ReviewKind
    severity: Severity
    statement: StatementType | None = None
    message: str
    lines: list[str] = Field(default_factory=list)
    rows: list[int] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)
    resolved: bool = False
    resolution: str | None = None


class StatementResult(BaseModel):
    table: StatementTable
    mappings: list[RowMapping]


class RatioResult(BaseModel):
    id: str
    label: str
    period: str
    value: Decimal | None
    format: str  # percent | times | days | money
    formula: str
    inputs: dict[str, Decimal | None] = Field(default_factory=dict)
    reason: str | None = None  # why it is not computable
    note: str = ""


class Spread(BaseModel):
    """Everything one run produced for one document."""

    doc_id: str
    profile_id: str
    profile_version: str
    statements: dict[str, StatementResult] = Field(default_factory=dict)  # by StatementType value
    periods: list[Period] = Field(default_factory=list)
    values: list[SpreadValue] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    ratios: list[RatioResult] = Field(default_factory=list)
    review: list[ReviewItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    company_id: str | None = None
    company_version: str | None = None  # what the run remembered about the company (spreader.company)
    second_reader_items: list[ReviewItem] = Field(default_factory=list)  # opt-in XBRL comparison (spreader.second_reader)
    prior_items: list[ReviewItem] = Field(default_factory=list)  # differences from approved spreads, kept apart:
    # the review is rebuilt after every correction, and these come from the company's history, not from the document

    def value(self, line: str, period: str) -> SpreadValue | None:
        for v in self.values:
            if v.line == line and v.period == period:
                return v
        return None
