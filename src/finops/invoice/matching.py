"""Purchase-order and goods-receipt matching, at header and line level.

Header: the PO named on the invoice must exist, be open, belong to the same vendor and use the
same currency. Lines: each invoice line is tied to a PO line by item code, else (if unique and
clearly best) by description; quantities are checked cumulatively, so a second invoice against
the same PO line counts what was already invoiced; prices are checked against the PO price
under the policy's tolerance.

A receipt shows that goods were received, not that they were accepted as fit for use; rejected
receipts are not counted. A PO line marked receipt_required = no (services) is matched two-way,
and the outcome says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz

from finops.core.exceptions import ExceptionItem, Severity

from .config import APPolicy
from .master import Master, PurchaseOrder, normalize_number
from .model import Invoice, InvoiceLine, LineMatch
from .validate import exc, m


@dataclass
class History:
    """Invoices processed before this one: for duplicates and for quantities already invoiced."""

    invoices: list[dict] = field(default_factory=list)  # {doc_id, vendor_id, number, total, date, po, lines:[(po, line, qty)], counted}

    def invoiced(self, po: str, line_no: int, exclude_doc: str) -> Decimal:
        key = normalize_number(po)
        # Only positive quantities count: a credit note is not matched here, so it cannot free up PO quantity.
        return sum((max(Decimal(q), Decimal(0)) for h in self.invoices if h["counted"] and h["doc_id"] != exclude_doc
                    for p, ln, q in h["lines"] if normalize_number(p) == key and ln == line_no), Decimal(0))


def _po_line(inv_line: InvoiceLine, po: PurchaseOrder, policy: APPolicy) -> tuple[int | None, str, str]:
    ic = inv_line.item_code
    code = normalize_number(str(ic.value)) if ic is not None and ic.value else ""
    if code:
        hits = [ln.line_no for ln in po.lines.values() if normalize_number(ln.item_code) == code]
        if len(hits) == 1:
            return hits[0], "item_code", f"item code {ic.value if ic else code}"
    desc = str(inv_line.description.value or "")
    scored = sorted(((fuzz.token_set_ratio(desc.lower(), ln.description.lower()), ln.line_no) for ln in po.lines.values()), reverse=True)
    if scored and scored[0][0] >= policy.matching.description_similarity and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 5):
        return scored[0][1], "description", f"description '{desc}' is like PO line '{po.lines[scored[0][1]].description}' ({scored[0][0]:.0f}/100)"
    return None, "none", "no PO line has this item code or a clearly similar description"


def match(inv: Invoice, vendor_id: str | None, master: Master, policy: APPolicy, history: History
          ) -> tuple[str | None, list[LineMatch], list[ExceptionItem], str, list[dict]]:
    """Returns (PO number, line matches, exceptions, status, checks)."""
    out: list[ExceptionItem] = []
    checks: list[dict] = []
    ref = inv.get("po_number")
    if not ref:
        open_pos = sorted(p.number for p in master.pos.values() if p.vendor_id == vendor_id and p.status == "open")
        out.append(exc(inv, "NO_PO_REFERENCE", Severity.BLOCKER, "No purchase order number on the invoice",
                       "The invoice names no PO, so it cannot be matched. " +
                       (f"The vendor's open POs: {', '.join(open_pos)}." if open_pos else "The vendor has no open PO."),
                       evidence={"open_pos": open_pos}, action="Ask the requester for the PO, or route it as a non-PO invoice."))
        return None, [], out, "unmatched", checks
    po = master.pos.get(normalize_number(str(ref)))
    if po is None:
        out.append(exc(inv, "PO_NOT_FOUND", Severity.BLOCKER, f"PO {ref} is not in the purchase-order data",
                       f"No purchase order {ref} exists (searched as {normalize_number(str(ref))}).", str(ref),
                       action="Check the PO number with the requester or vendor."))
        return None, [], out, "unmatched", checks
    header_ok = True
    if po.status != "open":
        header_ok = False
        out.append(exc(inv, "PO_NOT_OPEN", Severity.BLOCKER, f"PO {po.number} is {po.status}",
                       f"Purchase order {po.number} has status '{po.status}'; invoices against it are not eligible.", po.number,
                       action="Confirm with purchasing whether the PO should be reopened."))
    if vendor_id is not None and po.vendor_id != vendor_id:
        header_ok = False
        out.append(exc(inv, "VENDOR_MISMATCH", Severity.BLOCKER, f"PO {po.number} belongs to another vendor",
                       f"The invoice is from {master.vendors[vendor_id].name if vendor_id in master.vendors else vendor_id}; "
                       f"PO {po.number} was issued to {master.vendors[po.vendor_id].name if po.vendor_id in master.vendors else po.vendor_id}.",
                       po.number, action="Check which vendor actually supplied the goods."))
    cur = inv.get("currency")
    if cur and cur != po.currency:
        header_ok = False
        out.append(exc(inv, "CURRENCY_MISMATCH", Severity.BLOCKER, f"Invoice in {cur}, PO in {po.currency}",
                       f"The PO was issued in {po.currency}; the invoice is in {cur}.", po.number))
    checks.append({"name": "PO exists, is open, same vendor and currency", "status": "pass" if header_ok else "fail",
                   "detail": f"PO {po.number} ({po.status}, vendor {po.vendor_id}, {po.currency})"})

    results: list[LineMatch] = []
    used: set[int] = set()
    tol_q = policy.matching.quantity_tolerance
    ptol = policy.matching.price_tolerance
    all_ok = header_ok
    for ln in inv.lines:
        qty = ln.quantity.value if ln.quantity else None
        price = ln.unit_price.value if ln.unit_price else None
        no, method, why = _po_line(ln, po, policy)
        if no is not None and no in used:
            no, method, why = None, "none", f"PO line {no} is already matched to another line of this invoice"
        lm = LineMatch(invoice_line=ln.index, po_line=no, method=method, invoiced=str(qty) if qty is not None else None,
                       invoice_price=str(price) if price is not None else None, notes=[why])
        results.append(lm)
        if no is None:
            all_ok = False
            is_freight = any(w in str(ln.description.value).lower() for w in ("freight", "shipping", "delivery"))
            code = "FREIGHT_NOT_ON_PO" if is_freight else "UNMATCHED_LINE"
            out.append(exc(inv, code, Severity.BLOCKER if not is_freight else Severity.WARNING,
                           f"Line {ln.index} is not on PO {po.number}", f"'{ln.description.value}': {why}.", f"l{ln.index}",
                           action="Confirm the charge with purchasing; it may need a PO change."))
            continue
        used.add(no)
        pl = po.lines[no]
        lm.ordered, lm.po_price, lm.receipt_required = str(pl.quantity), str(pl.unit_price), pl.receipt_required
        if method == "description":
            lm.notes.append("Matched by description, not by item code: the pairing is inferred.")
        if qty is None or price is None:
            all_ok = False  # validate.py raises LINE_INCOMPLETE; nothing can be checked against the PO
            lm.notes.append("Quantity or unit price not readable: not checked against the PO.")
            continue
        prev = history.invoiced(po.number, no, inv.doc_id)
        lm.previously_invoiced = str(prev)
        cumulative = prev + qty
        if cumulative > pl.quantity + tol_q:
            all_ok = False
            out.append(exc(inv, "QTY_EXCEEDS_ORDERED", Severity.BLOCKER, f"Line {ln.index}: invoiced more than ordered",
                           f"PO line {no} ordered {pl.quantity}; already invoiced {prev}; this invoice {qty}; total {cumulative}.",
                           f"l{ln.index}", {"ordered": str(pl.quantity), "previously_invoiced": str(prev), "this": str(qty)},
                           "Pay only up to the ordered quantity or get a PO change."))
        if pl.receipt_required:
            recs = [r for r in master.receipts_for(po.number, no) if r.status == "accepted"]
            received = sum((r.quantity for r in recs), Decimal(0))
            lm.received, lm.receipts = str(received), [r.id for r in recs]
            if not recs:
                all_ok = False
                out.append(exc(inv, "MISSING_RECEIPT", Severity.BLOCKER, f"Line {ln.index}: nothing received yet",
                               f"PO line {no} ('{pl.description}') has no accepted goods receipt.", f"l{ln.index}",
                               action="Wait for the receipt, or confirm delivery with the requester."))
            elif cumulative > received + tol_q:
                all_ok = False
                out.append(exc(inv, "QTY_EXCEEDS_RECEIVED", Severity.BLOCKER, f"Line {ln.index}: invoiced {cumulative}, received {received}",
                               f"PO line {no}: received {received} ({', '.join(lm.receipts)}); invoiced so far {prev} plus {qty} on "
                               f"this invoice = {cumulative}.", f"l{ln.index}",
                               {"received": str(received), "previously_invoiced": str(prev), "this": str(qty)},
                               "Hold until the rest is received, or pay only what was received."))
        else:
            lm.notes.append("No goods receipt required for this PO line (service): matched two-way, invoice to PO.")
        if price is not None and not ptol.within(pl.unit_price, price, base=pl.unit_price):
            if price > pl.unit_price:
                all_ok = False
                out.append(exc(inv, "PRICE_OVER_PO", Severity.BLOCKER, f"Line {ln.index}: price {m(price)} above PO {m(pl.unit_price)}",
                               f"PO line {no} price {m(pl.unit_price)}; invoice {m(price)} ({(price / pl.unit_price - 1) * 100:.1f}% "
                               f"higher; tolerance {ptol.describe()}).", f"l{ln.index}",
                               {"po_price": str(pl.unit_price), "invoice_price": str(price)}, "Get a credit note or a PO price change."))
            else:
                lm.notes.append(f"Price {m(price)} is below the PO price {m(pl.unit_price)}.")
    status = "matched" if all_ok and results else ("partial" if any(r.po_line for r in results) else "unmatched")
    return po.number, results, out, status, checks
