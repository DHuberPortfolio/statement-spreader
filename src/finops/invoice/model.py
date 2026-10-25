"""The canonical invoice and the outcome of processing one.

Every value says where it came from (Origin) and, when read from a page, exactly where (Evidence).
A human correction never overwrites: the field keeps its original value and evidence beside the
corrected one.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field as PField

from finops.core.exceptions import ExceptionItem


class Origin(str, Enum):
    EXTRACTED = "extracted"  # read from the document as printed
    NORMALIZED = "normalized"  # read, then put in standard form (a date, a vendor id from an exact alias)
    COMPUTED = "computed"  # calculated by this application
    INFERRED = "inferred"  # chosen with uncertainty (a fuzzy vendor name, a PO line by description)
    HUMAN = "human"  # entered or corrected by a reviewer


class Evidence(BaseModel):
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    text: str = ""  # as printed (bank account numbers are masked even here)
    pointer: str | None = None  # JSON pointer for structured input


class FieldValue(BaseModel):
    value: Any
    origin: Origin
    evidence: Evidence | None = None
    original: Any = None  # the value before a human correction
    corrected_by: str | None = None
    note: str = ""


class InvoiceLine(BaseModel):
    index: int
    item_code: FieldValue | None = None
    description: FieldValue
    quantity: FieldValue | None = None
    unit_price: FieldValue | None = None
    amount: FieldValue | None = None


class Invoice(BaseModel):
    doc_id: str
    file: str
    format: str  # pdf | json
    pages: int = 1
    fields: dict[str, FieldValue] = PField(default_factory=dict)
    lines: list[InvoiceLine] = PField(default_factory=list)
    extraction_notes: list[str] = PField(default_factory=list)

    def get(self, name: str) -> Any:
        f = self.fields.get(name)
        return None if f is None else f.value


class LineMatch(BaseModel):
    invoice_line: int
    po_line: int | None
    method: str  # item_code | description | none
    ordered: str | None = None
    received: str | None = None
    previously_invoiced: str | None = None
    invoiced: str | None = None
    po_price: str | None = None
    invoice_price: str | None = None
    receipts: list[str] = PField(default_factory=list)
    receipt_required: bool = True
    notes: list[str] = PField(default_factory=list)


class Outcome(BaseModel):
    """Separate dimensions, on purpose: passing one says nothing about the next."""

    invoice: Invoice
    vendor_id: str | None
    po_number: str | None
    extraction: str  # complete | incomplete
    validation: str  # pass | fail | partial
    matching: str  # matched | partial | unmatched | not_attempted
    eligibility: str  # eligible_for_approval | needs_review | blocked
    authorization: str = "not_authorized"  # approval and payment happen in the ERP, by authorised people
    touchless: bool = False
    exceptions: list[ExceptionItem] = PField(default_factory=list)
    line_matches: list[LineMatch] = PField(default_factory=list)
    checks: list[dict[str, Any]] = PField(default_factory=list)
    duplicate_of: list[str] = PField(default_factory=list)
    timings_ms: dict[str, float] = PField(default_factory=dict)
