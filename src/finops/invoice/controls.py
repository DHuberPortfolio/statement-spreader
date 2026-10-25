"""Duplicate detection, vendor checks and the bank-detail control.

Duplicates, beyond the invoice number alone:
  EXACT_DUPLICATE     the same file again; or the same vendor, invoice number (normalised:
                      INV-000123 = 123) and total
  POSSIBLE_DUPLICATE  same vendor and number with a different total (a re-issue or a mistake);
                      same number and total under a different vendor (an alias problem); same
                      vendor and total within the window under a different number
Neither rejects anything: both stop the invoice from being eligible until a person decides.

Bank details: an invoice that shows payment details different from the vendor master's trusted
baseline is a BANK_DETAILS_CHANGED blocker (a common invoice-fraud pattern). With no baseline,
BANK_DETAILS_UNVERIFIED: the details cannot be verified, and the outcome says exactly that.
Only the masked number (****1234) is ever shown. Resolving either needs independent
verification by a different person (see service.py); this software never changes vendor bank
details, never pays, and never states that fraud has been ruled out.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from rapidfuzz import fuzz

from finops.core.exceptions import ExceptionItem, Severity

from .config import APPolicy
from .master import Master, normalize_number
from .matching import History
from .model import Invoice
from .validate import exc, m


def duplicates(inv: Invoice, vendor_id: str | None, history: History, policy: APPolicy) -> tuple[list[ExceptionItem], list[str]]:
    out: list[ExceptionItem] = []
    hits: list[str] = []
    num = normalize_number(inv.get("invoice_number"))
    total = inv.get("total")
    d = inv.get("invoice_date")
    for h in history.invoices:
        if h["doc_id"] == inv.doc_id:
            out.append(exc(inv, "EXACT_DUPLICATE", Severity.BLOCKER, "This exact file was submitted before",
                           f"The same file (fingerprint {inv.doc_id[:12]}) was processed before as invoice {h['number_raw']}.",
                           h["doc_id"], {"other": h["doc_id"]}, "Do not process it again."))
            hits.append(h["doc_id"])
            continue
        same_vendor = vendor_id is not None and h["vendor_id"] == vendor_id
        same_num = bool(num) and h["number"] == num
        h_total = Decimal(str(h["total"])) if h["total"] is not None else None  # stored outcomes give text back
        same_total = total is not None and h_total is not None and h_total == Decimal(str(total))
        days = abs((date.fromisoformat(d) - date.fromisoformat(h["date"])).days) if d and h["date"] else None
        code, why = None, ""
        if same_vendor and same_num and same_total:
            code, why = "EXACT_DUPLICATE", f"same vendor, invoice number ({inv.get('invoice_number')} = {h['number_raw']}) and total {m(total)}"
        elif same_vendor and same_num:
            code, why = "POSSIBLE_DUPLICATE", f"same vendor and invoice number, but total {m(total)} vs {m(h_total)}"
        elif same_num and same_total:
            code, why = "POSSIBLE_DUPLICATE", "same invoice number and total under a different vendor record"
        elif same_vendor and same_total and days is not None and days <= policy.duplicates.window_days:
            code, why = "POSSIBLE_DUPLICATE", f"same vendor and total {m(total)}, {days} days apart, different numbers"
        if code:
            hits.append(h["doc_id"])
            out.append(exc(inv, code, Severity.BLOCKER,
                           "Already invoiced: do not pay twice" if code == "EXACT_DUPLICATE" else "Possible duplicate invoice",
                           f"Compared with invoice {h['number_raw']} processed earlier: {why}.", h["doc_id"],
                           {"other": h["doc_id"], "other_number": h["number_raw"]},
                           "Do not pay twice. Reject this one if it is the same invoice; if it is a separate charge, "
                           "record why."))
    return out, hits


def vendor_and_bank(inv: Invoice, vendor_id: str | None, how: str, why: str, master: Master) -> tuple[list[ExceptionItem], list[dict]]:
    out: list[ExceptionItem] = []
    checks: list[dict] = []
    if vendor_id is None:
        out.append(exc(inv, "VENDOR_UNKNOWN", Severity.BLOCKER, "Vendor not recognised", f"{why}.",
                       action="Match the vendor by hand, or start the vendor onboarding process."))
    else:
        v = master.vendors[vendor_id]
        checks.append({"name": "Vendor identified", "status": "pass", "detail": f"{v.name} ({vendor_id}): {why}"})
        if how == "fuzzy":
            out.append(exc(inv, "VENDOR_INFERRED", Severity.WARNING, f"Vendor taken to be {v.name}", f"{why}; this is a close "
                           "spelling, not an exact name or alias.", action="Confirm the vendor, then add the spelling as an alias."))
        if v.status.lower() not in ("active", ""):
            out.append(exc(inv, "VENDOR_INACTIVE", Severity.BLOCKER, f"{v.name} is {v.status} in the vendor master",
                           f"Vendor {vendor_id} has status '{v.status}'.", action="Check with vendor management."))
    if vendor_id is not None and how == "tax_id" and inv.get("vendor_name"):
        v = master.vendors[vendor_id]
        printed = str(inv.get("vendor_name"))
        best = max(fuzz.token_set_ratio(printed.lower(), x.lower()) for x in [v.name] + v.aliases)
        if best < 85:
            out.append(exc(inv, "VENDOR_IDENTITY_CONFLICT", Severity.BLOCKER, "Vendor name and tax id disagree",
                           f"The tax id printed is {v.name}'s, but the name printed is '{printed}' ({best:.0f}/100 alike). "
                           "A borrowed tax id is a known impersonation pattern.", "identity",
                           {"printed_name": printed, "tax_id_vendor": v.name}, "Confirm who issued the invoice before anything else."))
    hidden = inv.fields.get("hidden_text")
    if hidden is not None:
        out.append(exc(inv, "HIDDEN_TEXT", Severity.WARNING, "The document contains text a reader may not see",
                       f"{hidden.value} piece(s) of white or tiny text: {hidden.note}. Tiny text was ignored; white text was "
                       "read in case it sits on a dark band. Check the values against what the page visibly shows.", "hidden",
                       action="Compare the extracted values with the visible page."))
    conflict = inv.fields.get("bank_account_conflict")
    if conflict is not None:
        out.append(exc(inv, "BANK_DETAILS_CONFLICT", Severity.BLOCKER, "The invoice shows more than one bank account",
                       f"Accounts printed: {conflict.note}. Only one can be right.", "conflict",
                       action="Treat as suspicious; verify through the vendor-change process."))
    total = inv.get("total")
    negative_qty = any(ln.quantity is not None and ln.quantity.value is not None and ln.quantity.value < 0 for ln in inv.lines)
    if (total is not None and total <= 0) or negative_qty:
        out.append(exc(inv, "CREDIT_NOTE", Severity.WARNING, "Looks like a credit note, not an invoice",
                       f"Total {m(total)}{' and a negative quantity' if negative_qty else ''}. Credit notes are not matched or "
                       "settled by this engine.", "credit", action="Route to the credit-note process."))
    fpr = inv.get("bank_fingerprint")
    shown = inv.get("bank_account")
    if fpr is None:
        checks.append({"name": "Payment details on the invoice", "status": "skipped",
                       "detail": "The invoice shows no bank account; payment would use the vendor master."})
        return out, checks
    vb = master.vendors.get(vendor_id) if vendor_id else None
    if vb is None or vb.bank_fingerprint is None:
        out.append(exc(inv, "BANK_DETAILS_UNVERIFIED", Severity.BLOCKER, "Bank details on the invoice cannot be verified",
                       f"The invoice shows account {shown}, and {'the vendor is unknown' if vb is None else 'the vendor master has no trusted bank details for ' + vb.name}. "
                       "There is nothing trusted to compare it with.", "unverified", {"invoice_account": shown},
                       "Verify the details through your vendor-onboarding process (an independent call-back), "
                       "never through contact details on this invoice or its email."))
        checks.append({"name": "Payment details match the vendor master", "status": "skipped", "detail": "no trusted baseline"})
    elif fpr != vb.bank_fingerprint or (inv.get("routing_fingerprint") and vb.routing_fingerprint
                                        and inv.get("routing_fingerprint") != vb.routing_fingerprint):
        out.append(exc(inv, "BANK_DETAILS_CHANGED", Severity.BLOCKER, "Payment details differ from the vendor master",
                       f"The invoice asks for payment to account {shown}; the vendor master has {vb.bank_masked} for {vb.name}. "
                       "Changed bank details on an invoice are a common fraud pattern. Nothing has been changed and nothing "
                       "will be paid by this system.", "changed", {"invoice_account": shown, "master_account": vb.bank_masked},
                       "Call the vendor on a number from the vendor master or contract (not from this invoice or its "
                       "email) and update master data only through the vendor-change process, by someone else."))
        checks.append({"name": "Payment details match the vendor master", "status": "fail",
                       "detail": f"invoice {shown} vs master {vb.bank_masked}"})
    else:
        checks.append({"name": "Payment details match the vendor master", "status": "pass", "detail": f"both {vb.bank_masked}"})
    return out, checks
