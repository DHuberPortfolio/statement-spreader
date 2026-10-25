"""One invoice in, one outcome out: extract -> correct (if a person did) -> validate -> match ->
duplicates -> vendor and bank controls -> status.

The statuses are kept apart on purpose (see model.Outcome): an invoice can read perfectly,
add up, match its PO and still be blocked by a bank-detail change. Eligibility is the most this
software ever grants; authorization is always "not_authorized".

Touchless means: eligible, with no exception above "info", no human correction and no resolved
exception. Any human touch, recorded or not avoidable, makes it not touchless.
"""

from __future__ import annotations

import time
from typing import Any

from finops import __version__
from finops.core.exceptions import ExceptionStatus, Resolution, Severity

from .config import APPolicy
from .controls import duplicates, vendor_and_bank
from .extract import extract
from .master import BankFingerprinter, Master
from .matching import History, match
from .model import FieldValue, Origin, Outcome
from .validate import validate

ENGINE_VERSION = f"invoice-{__version__}"
CORRECTABLE = {"vendor_name", "invoice_number", "invoice_date", "due_date", "po_number", "currency", "subtotal", "tax",
               "freight", "discount", "total", "terms"}


def process(file_name: str, data: bytes, policy: APPolicy, master: Master, history: History, fp: BankFingerprinter,
            corrections: dict[str, dict[str, Any]] | None = None, resolutions: dict[str, Resolution] | None = None) -> Outcome:
    t0 = time.perf_counter()
    inv = extract(file_name, data, policy, fp)
    t_ext = time.perf_counter()
    for name, c in (corrections or {}).items():
        if name not in CORRECTABLE:
            continue
        old = inv.fields.get(name)
        inv.fields[name] = FieldValue(value=c["value"], origin=Origin.HUMAN, evidence=old.evidence if old else None,
                                      original=old.value if old else None, corrected_by=c["actor"], note=c.get("note", ""))

    vendor_id, how, why = master.resolve_vendor(inv.get("vendor_name"), inv.get("vendor_tax_id"))
    if vendor_id:
        inv.fields["vendor_id"] = FieldValue(value=vendor_id, origin=Origin.INFERRED if how == "fuzzy" else Origin.NORMALIZED,
                                             note=why)
    vendor = master.vendors.get(vendor_id) if vendor_id else None
    exceptions, checks = validate(inv, policy, vendor)
    po_number, line_matches, m_exc, m_status, m_checks = match(inv, vendor_id, master, policy, history)
    d_exc, dup_of = duplicates(inv, vendor_id, history, policy)
    v_exc, v_checks = vendor_and_bank(inv, vendor_id, how, why, master)
    exceptions += m_exc + d_exc + v_exc
    checks += m_checks + v_checks

    resolutions = resolutions or {}
    seen: set[str] = set()
    final = []
    for e in exceptions:
        if e.id in seen:
            continue
        seen.add(e.id)
        if e.id in resolutions:
            e = e.model_copy(update={"status": ExceptionStatus.RESOLVED, "resolution": resolutions[e.id]})
        final.append(e)
    open_ = [e for e in final if e.status is ExceptionStatus.OPEN]
    if any(e.resolution is not None and e.resolution.action == "rejected" for e in final):
        eligibility = "rejected"  # a person rejected it: it stays rejected whatever else is resolved
    elif any(e.severity is Severity.BLOCKER for e in open_):
        eligibility = "blocked"
    elif any(e.severity is Severity.WARNING for e in open_):
        eligibility = "needs_review"
    else:
        eligibility = "eligible_for_approval"
    human = any(f.origin is Origin.HUMAN for f in inv.fields.values()) or any(e.status is ExceptionStatus.RESOLVED for e in final)
    required_missing = any(e.code == "MISSING_FIELD" for e in final)
    validation = "fail" if any(e.code in {"LINE_EXTENSION_MISMATCH", "SUBTOTAL_MISMATCH", "TAX_MISMATCH", "TOTAL_MISMATCH"}
                               for e in final) else ("partial" if any(c["status"] == "skipped" for c in checks) else "pass")
    sev = {Severity.BLOCKER: 0, Severity.WARNING: 1, Severity.INFO: 2}
    final.sort(key=lambda e: (e.status is not ExceptionStatus.OPEN, sev[e.severity], e.code))
    return Outcome(invoice=inv, vendor_id=vendor_id, po_number=po_number,
                   extraction="incomplete" if required_missing or not inv.lines else "complete",
                   validation=validation, matching=m_status, eligibility=eligibility,
                   touchless=eligibility == "eligible_for_approval" and not human, exceptions=final,
                   line_matches=line_matches, checks=checks, duplicate_of=dup_of,
                   timings_ms={"extract": round((t_ext - t0) * 1000, 1), "total": round((time.perf_counter() - t0) * 1000, 1)})


def history_entry(o: Outcome) -> dict[str, Any]:
    """What later invoices need to know about this one.

    Its quantities count against the PO unless it was rejected or is an open exact duplicate: an invoice held for
    review still reserves what it bills, so a second invoice cannot pass on the same goods while the first waits.
    """
    from .master import normalize_number

    inv = o.invoice
    open_exact = any(e.code == "EXACT_DUPLICATE" and e.status is ExceptionStatus.OPEN for e in o.exceptions)
    counted = o.eligibility != "rejected" and not open_exact
    lines = [(o.po_number, lm.po_line, lm.invoiced) for lm in o.line_matches if o.po_number and lm.po_line and lm.invoiced]
    return {"doc_id": inv.doc_id, "vendor_id": o.vendor_id, "number": normalize_number(inv.get("invoice_number")),
            "number_raw": inv.get("invoice_number"), "total": inv.get("total"), "date": inv.get("invoice_date"),
            "po": o.po_number, "lines": lines, "counted": counted}
