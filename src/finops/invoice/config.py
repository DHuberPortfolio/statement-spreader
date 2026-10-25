"""Accounts-payable policy: tolerances, tax rules, duplicate rules, what may pass without a person.

A company adapts these in config/finops/invoice/*.yaml. Nothing here is a universal truth about
tax or matching: the defaults are explicit, conservative and meant to be replaced.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from finops.core.money import Tolerance


class TaxPolicy(BaseModel):
    # Tax is checked only when its rule is known: a rate printed on the invoice, or a rate in the
    # vendor master. Anything else is TAX_UNVERIFIED, never assumed correct or incorrect.
    freight_taxable: bool = False
    use_vendor_rate: bool = True


class MatchPolicy(BaseModel):
    price_tolerance: Tolerance = Tolerance(abs=Decimal("0.05"), pct=Decimal("0.01"), combine="max")
    quantity_tolerance: Decimal = Decimal("0")  # units an invoice may exceed the received quantity by
    description_similarity: int = Field(default=88, ge=60, le=100)
    max_unmatched_freight: Decimal = Decimal("0")  # freight above this with no PO freight line is an exception


class DuplicatePolicy(BaseModel):
    window_days: int = Field(default=14, ge=0)  # same vendor + same amount within this many days: possible duplicate


class MasterData(BaseModel):
    vendors: str = "vendors.csv"
    purchase_orders: str = "purchase_orders.csv"
    receipts: str = "receipts.csv"


class APPolicy(BaseModel):
    id: str
    name: str
    version: str = "1"
    base_currency: str = "USD"
    date_formats: list[str] = ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"]
    arithmetic_tolerance: Decimal = Decimal("0.01")
    master_data: MasterData = MasterData()
    tax: TaxPolicy = TaxPolicy()
    matching: MatchPolicy = MatchPolicy()
    duplicates: DuplicatePolicy = DuplicatePolicy()
    # Extra label wording per field, for a vendor or country whose invoices say it differently.
    extra_labels: dict[str, list[str]] = Field(default_factory=dict)
    # Extra item-table column headings (description, quantity, unit_price, amount, item_code).
    extra_columns: dict[str, list[str]] = Field(default_factory=dict)
