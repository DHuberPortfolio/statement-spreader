"""Invoice arithmetic, checked by code and never "corrected".

A difference is reported with both numbers and the evidence; the extracted amounts stay exactly
as printed. Tax is checked only under a known rule (a rate printed on the invoice, or the
vendor master's rate); otherwise it is TAX_UNVERIFIED, because tax depends on jurisdiction,
product category and exemptions this application does not know.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from finops.core.exceptions import ExceptionItem, Severity, exception_id
from finops.core.money import round_cents

from .config import APPolicy
from .master import Vendor
from .model import Invoice

REQUIRED = {"vendor_name": "vendor name", "invoice_number": "invoice number", "invoice_date": "invoice date", "total": "total"}


def exc(inv: Invoice, code: str, sev: Severity, title: str, detail: str, key: str = "", evidence: dict[str, Any] | None = None,
        action: str = "") -> ExceptionItem:
    return ExceptionItem(id=exception_id("invoice", code, [inv.doc_id, key]), engine="invoice", code=code, severity=sev,
                         title=title, detail=detail, subjects=[f"invoice:{inv.doc_id[:12]}"], evidence=evidence or {},
                         suggested_action=action)


def m(x: Decimal | None) -> str:
    return "missing" if x is None else f"{x:,.2f}"


def validate(inv: Invoice, policy: APPolicy, vendor: Vendor | None) -> tuple[list[ExceptionItem], list[dict[str, Any]]]:
    out: list[ExceptionItem] = []
    checks: list[dict[str, Any]] = []
    tol = policy.arithmetic_tolerance

    def check(name: str, ok: bool | None, detail: str) -> None:
        checks.append({"name": name, "status": "skipped" if ok is None else ("pass" if ok else "fail"), "detail": detail})

    missing = [label for k, label in REQUIRED.items() if inv.get(k) in (None, "")]
    if missing:
        out.append(exc(inv, "MISSING_FIELD", Severity.BLOCKER, f"Could not read: {', '.join(missing)}",
                       f"The {', '.join(missing)} could not be read from {inv.file}. Nothing was filled in.",
                       ",".join(missing), {"missing": missing, "notes": inv.extraction_notes},
                       "Enter the value from the document (the original stays on record), or reject the invoice."))
    if not inv.lines:
        out.append(exc(inv, "NO_LINE_ITEMS", Severity.BLOCKER, "No line items were read",
                       "No item table was read, so nothing can be matched to a purchase order. " + " ".join(inv.extraction_notes),
                       action="Check the document; it may be a scan or an unusual layout."))

    line_sum = Decimal(0)
    complete = True
    for ln in inv.lines:
        q = ln.quantity.value if ln.quantity else None
        p = ln.unit_price.value if ln.unit_price else None
        a = ln.amount.value if ln.amount else None
        if a is None:
            complete = False
            out.append(exc(inv, "LINE_INCOMPLETE", Severity.BLOCKER, f"Line {ln.index}: no amount", f"Line {ln.index} "
                           f"('{ln.description.value}') has no readable amount.", f"l{ln.index}"))
            continue
        line_sum += a
        if q is None or p is None:
            # Without both, neither the line's arithmetic nor its PO price and quantity can be checked.
            absent = " and ".join(x for x, v in (("quantity", q), ("unit price", p)) if v is None)
            out.append(exc(inv, "LINE_INCOMPLETE", Severity.BLOCKER, f"Line {ln.index}: no readable {absent}",
                           f"Line {ln.index} ('{ln.description.value}') shows {m(a)} but no readable {absent}, so it cannot "
                           "be checked against the purchase order.", f"l{ln.index}q",
                           action="Enter the quantity and unit price from the document, or ask the vendor."))
            check(f"Line {ln.index}: quantity x price = amount", None, f"{absent} not readable")
            continue
        expected = round_cents(q * p)
        ok = abs(expected - a) <= tol
        check(f"Line {ln.index}: quantity x price = amount", ok, f"{q} x {m(p)} = {m(expected)}; printed {m(a)}")
        if not ok:
            out.append(exc(inv, "LINE_EXTENSION_MISMATCH", Severity.BLOCKER, f"Line {ln.index}: {q} x {m(p)} is not {m(a)}",
                           f"Line {ln.index} ('{ln.description.value}'): {q} x {m(p)} = {m(expected)}, but the invoice prints "
                           f"{m(a)} (difference {m(a - expected)}).", f"l{ln.index}",
                           {"expected": str(expected), "printed": str(a)}, "Ask the vendor for a corrected invoice."))

    subtotal = inv.get("subtotal")
    if subtotal is not None and complete and inv.lines:
        ok = abs(subtotal - line_sum) <= tol
        check("Lines add up to the subtotal", ok, f"lines {m(line_sum)}; subtotal {m(subtotal)}")
        if not ok:
            out.append(exc(inv, "SUBTOTAL_MISMATCH", Severity.BLOCKER, f"Lines add to {m(line_sum)}, subtotal says {m(subtotal)}",
                           f"The {len(inv.lines)} lines add up to {m(line_sum)}; the printed subtotal is {m(subtotal)} "
                           f"(difference {m(subtotal - line_sum)}).", "", {"lines": str(line_sum), "subtotal": str(subtotal)},
                           "Check for a missing or extra line; ask for a corrected invoice."))
    base = subtotal if subtotal is not None else (line_sum if complete and inv.lines else None)

    tax, freight, discount = inv.get("tax"), inv.get("freight") or Decimal(0), inv.get("discount") or Decimal(0)
    printed_rate = inv.get("tax_rate")
    master_rate = vendor.tax_rate if policy.tax.use_vendor_rate and vendor is not None else None
    rate, rate_source = printed_rate, "printed on the invoice"
    if master_rate is not None:
        rate, rate_source = master_rate, "from the vendor master"  # the trusted rate wins over the vendor's claim
        if printed_rate is not None and printed_rate != master_rate:
            out.append(exc(inv, "TAX_RATE_MISMATCH", Severity.BLOCKER,
                           f"Invoice prints a {printed_rate * 100:g}% tax rate; the vendor master has {master_rate * 100:g}%",
                           "The rate on the invoice differs from the vendor master's. The tax was checked at the master's rate.",
                           "", {"printed_rate": str(printed_rate), "master_rate": str(master_rate)},
                           "Confirm the applicable rate; update the vendor master only through its change process."))
    elif printed_rate is not None and tax:
        out.append(exc(inv, "TAX_UNVERIFIED", Severity.WARNING, f"Tax rate {printed_rate * 100:g}% is the vendor's own claim",
                       "The arithmetic was checked at the printed rate, but no trusted rate (vendor master) confirms it.",
                       "rate", {"printed_rate": str(printed_rate)}, "Confirm the rate with your tax rules."))
    if base is not None and rate is not None:
        taxable = base + (freight if policy.tax.freight_taxable else Decimal(0))
        expected = round_cents(taxable * rate)
        printed = tax or Decimal(0)
        ok = abs(expected - printed) <= tol
        check("Tax = rate x taxable amount", ok, f"{rate * 100:g}% ({rate_source}) of {m(taxable)} = {m(expected)}; printed {m(tax)}")
        if not ok:
            out.append(exc(inv, "TAX_MISMATCH", Severity.BLOCKER, f"Tax should be {m(expected)}, invoice says {m(tax)}",
                           f"At {rate * 100:g}% ({rate_source}) on {m(taxable)} the tax is {m(expected)}; the invoice charges "
                           f"{m(tax)}.", "", {"expected": str(expected), "printed": str(tax), "rate": str(rate)},
                           "Confirm the applicable rate and exemptions; ask for a corrected invoice if it is wrong."))
    elif tax:
        check("Tax = rate x taxable amount", None, "no rate printed and none in the vendor master")
        out.append(exc(inv, "TAX_UNVERIFIED", Severity.WARNING, f"Tax of {m(tax)} could not be checked",
                       "No tax rate is printed and the vendor master has none, so the tax was not verified. It was not "
                       "assumed right or wrong.", "", {"tax": str(tax)}, "Confirm the tax with your tax rules."))

    total = inv.get("total")
    if total is not None and base is not None:
        expected = base + (tax or Decimal(0)) + freight - discount
        ok = abs(expected - total) <= tol
        check("Subtotal + tax + freight - discount = total", ok,
              f"{m(base)} + {m(tax or Decimal(0))} + {m(freight)} - {m(discount)} = {m(expected)}; printed {m(total)}")
        if not ok:
            out.append(exc(inv, "TOTAL_MISMATCH", Severity.BLOCKER, f"Total should be {m(expected)}, invoice says {m(total)}",
                           f"{m(base)} + tax {m(tax or Decimal(0))} + freight {m(freight)} - discount {m(discount)} = {m(expected)}, "
                           f"but the invoice total is {m(total)} (difference {m(total - expected)}).", "",
                           {"expected": str(expected), "printed": str(total)}, "Ask the vendor for a corrected invoice."))

    if freight > policy.matching.max_unmatched_freight:
        out.append(exc(inv, "FREIGHT_NOT_ON_PO", Severity.WARNING, f"Freight of {m(freight)} is not on the purchase order",
                       f"The invoice charges {m(freight)} freight; purchase orders here carry no freight line (allowed without "
                       f"one: {m(policy.matching.max_unmatched_freight)}).", "header",
                       action="Confirm the freight terms with purchasing."))
    if discount < 0:
        out.append(exc(inv, "NEGATIVE_DISCOUNT", Severity.BLOCKER, f"A negative discount ({m(discount)}) is a surcharge",
                       "A discount below zero raises the total; it is not on the purchase order.", "discount",
                       action="Ask the vendor what the charge is."))
    elif discount > 0:
        checks.append({"name": "Discount", "status": "pass", "detail": f"{m(discount)} off; lowers the amount payable"})

    d1, d2 = inv.get("invoice_date"), inv.get("due_date")
    if d1 and d2 and d2 < d1:
        out.append(exc(inv, "DATE_INCONSISTENT", Severity.WARNING, "Due date is before the invoice date",
                       f"Invoice date {d1}, due date {d2}.", "", action="Check the dates with the vendor."))
    if inv.get("currency") is None:
        out.append(exc(inv, "CURRENCY_UNKNOWN", Severity.WARNING, "No currency on the invoice",
                       "Neither a currency code nor a currency sign was read.", action="Confirm the currency."))
    return out, checks
