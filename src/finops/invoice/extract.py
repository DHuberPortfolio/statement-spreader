"""Reading an invoice: PDF text layer or structured JSON -> Invoice with field-level evidence.

PDF, in three passes over the words pdfplumber reports with their positions:

1. Lines and segments. Words on the same baseline form a line; a wide horizontal gap splits a
   line into segments (the cells a person sees).
2. The item table. A line whose segments name a description column, an amount column and a
   quantity or price column is the header; its segments define the columns. Following lines
   are items until a totals label; a line with only text continues the previous description;
   a repeated header on a later page is skipped, so multi-page tables read as one.
3. Labelled fields, outside the table. A segment that starts with a known label ("Invoice No",
   "PO Number", "Amount Due") takes its value from the rest of the segment, else the next
   segment on the line (unless that is another label), else the segment directly below (the
   labels-above-values layout). Layouts differ; label wording is configurable per company.

Nothing is guessed from position alone, and nothing is computed here: a missing total stays
missing (validation reports it), it is not filled in from the lines. Bank account numbers are
masked before they are stored anywhere, evidence text included.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from finops.core.fingerprint import sha256_bytes
from finops.core.money import parse_money

from .config import APPolicy
from .master import BankFingerprinter, mask_digits, mask_if_bank
from .model import Evidence, FieldValue, Invoice, InvoiceLine, Origin

GAP = 9.0  # points: a horizontal gap wider than this separates two cells

LABELS: list[tuple[str, str]] = [
    ("invoice_number", r"invoice\s*(?:no\.?|number|num\.?|#|id)|inv\.?\s*(?:no\.?|#)|bill\s*(?:no\.?|number)"),
    ("due_date", r"due\s*date|payment\s*due(?:\s*date)?|date\s*due"),
    ("invoice_date", r"invoice\s*date|date\s*of\s*issue|issue\s*date|bill\s*date|date"),
    ("po_number", r"(?:p\.?\s?o\.?|purchase\s*order)\s*(?:no\.?|number|#|ref(?:erence)?)?|your\s*order(?:\s*(?:no\.?|number|#))?|customer\s*po"),
    ("terms", r"(?:payment\s*)?terms"),
    ("currency", r"currency"),
    ("vendor_tax_id", r"tax\s*id|ein|tin|vat\s*(?:no\.?|number|reg(?:istration)?(?:\s*no\.?)?)"),
    ("bank_account", r"(?:beneficiary\s*|bank\s*)*(?:account|acct\.?|a/c)\s*(?:no\.?|number|#)?|iban"),
    ("routing_number", r"routing\s*(?:no\.?|number|#)?|aba(?:\s*(?:no\.?|number))?|sort\s*code|swift(?:\s*/\s*bic)?|bic"),
    ("subtotal", r"sub\s*-?\s*total"),
    ("tax", r"(?:sales\s*)?tax|vat|gst"),
    ("freight", r"freight|shipping(?:\s*(?:&|and)\s*handling)?|delivery"),
    ("discount", r"discount"),
    ("total", r"total\s*(?:due|amount(?:\s*due)?)|amount\s*due|balance\s*due|invoice\s*total|total"),
]
MONEY_FIELDS = {"subtotal", "tax", "freight", "discount", "total"}
DATE_FIELDS = {"invoice_date", "due_date"}
COLS = {
    "item_code": ("item code", "item no", "item #", "sku", "part no", "part #", "product code", "code", "item"),
    "description": ("description", "item description", "details", "service", "particulars"),
    "quantity": ("qty", "quantity", "units", "hours", "hrs"),
    "unit_price": ("unit price", "unit cost", "price", "rate"),
    "amount": ("amount", "line total", "extended", "ext. price", "total"),
}
BANK_ANYWHERE = [
    ("bank_account", re.compile(r"(?:account|acct\.?|a/c)\s*(?:no\.?|number|#)?\s*[:#.]?\s*([0-9][0-9 -]{5,}[0-9])", re.I)),
    ("routing_number", re.compile(r"(?:routing|aba|sort\s*code)\s*(?:no\.?|number|#)?\s*[:#]?\s*([0-9][0-9 -]{4,}[0-9])", re.I)),
]
SKIP = re.compile(r"^(page\s+\d+(\s+of\s+\d+)?|continued.*|thank you.*)$", re.I)
CURRENCY_SIGNS = {"€": "EUR", "£": "GBP"}


@dataclass
class Seg:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page: int

    def ev(self, text: str | None = None) -> Evidence:
        return Evidence(page=self.page, bbox=(round(self.x0, 1), round(self.top, 1), round(self.x1, 1), round(self.bottom, 1)),
                        text=mask_if_bank(text if text is not None else self.text))


@dataclass
class Line:
    page: int
    top: float
    segs: list[Seg]

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segs)


MIN_FONT = 3.0  # points: text smaller than this is not read by a person, so it is not read here either


def _white(color: Any) -> bool:
    if not isinstance(color, (tuple, list)) or not color:
        return False
    vals = [float(c) for c in color if isinstance(c, (int, float))]
    if len(vals) == 4:  # CMYK: white is no ink
        return all(v <= 0.03 for v in vals)
    return bool(vals) and all(v >= 0.97 for v in vals)


def pdf_lines(data: bytes, hidden: list[str] | None = None) -> tuple[list[Line], int]:
    """Lines of readable-size text. Tiny text is dropped; white text is kept (it may sit on a dark
    band) but reported in `hidden`, so a person can see what the page hides."""
    import pdfplumber

    out: list[Line] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, start=1):
            if hidden is not None:
                buf = ""
                for ch in page.chars:
                    if ch.get("size", 10) < MIN_FONT or _white(ch.get("non_stroking_color")):
                        buf += ch["text"]
                    elif buf.strip():
                        hidden.append(buf.strip())
                        buf = ""
                if buf.strip():
                    hidden.append(buf.strip())
            page = page.filter(lambda o: o.get("object_type") != "char" or o.get("size", 10) >= MIN_FONT)
            words = sorted(page.extract_words(x_tolerance=1.5, y_tolerance=2.5), key=lambda w: (w["top"], w["x0"]))
            rows: list[list[dict[str, Any]]] = []
            for w in words:
                if rows and abs(rows[-1][0]["top"] - w["top"]) <= 2.5:
                    rows[-1].append(w)
                else:
                    rows.append([w])
            for row in rows:
                row.sort(key=lambda w: w["x0"])
                segs: list[Seg] = []
                cur = [row[0]]
                for w in row[1:]:
                    if w["x0"] - cur[-1]["x1"] > GAP:
                        segs.append(_seg(cur, pno))
                        cur = [w]
                    else:
                        cur.append(w)
                segs.append(_seg(cur, pno))
                out.append(Line(pno, row[0]["top"], segs))
    return out, n


def _seg(words: list[dict[str, Any]], page: int) -> Seg:
    return Seg(" ".join(w["text"] for w in words), words[0]["x0"], words[-1]["x1"], min(w["top"] for w in words),
               max(w["bottom"] for w in words), page)


def _label_patterns(policy: APPolicy) -> list[tuple[str, re.Pattern[str]]]:
    out = []
    for name, rx in LABELS:
        extra = "|".join(re.escape(x) for x in policy.extra_labels.get(name, []))
        alt = f"{extra}|{rx}" if extra else rx
        # A label ends at a separator or the end ("PO Number:", "PO #", "Total"), so a value that merely
        # starts like a label ("PO-4501") is not mistaken for one.
        out.append((name, re.compile(rf"^(?:{alt})(?=$|[\s:#.(])\s*(?:\((?P<paren>[^)]*)\))?\s*[:#.]?\s*(?P<rest>.*)$", re.I)))
    return out


def _match_label(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> tuple[str, re.Match[str]] | None:
    for name, rx in patterns:
        m = rx.match(text.strip())
        if m:
            return name, m
    return None


def parse_date(text: str, formats: list[str]) -> str | None:
    t = re.sub(r"\s+", " ", text.strip().rstrip("."))
    for f in formats:
        try:
            return datetime.strptime(t, f).date().isoformat()
        except ValueError:
            continue
    return None


_PLAIN_NUMBER = re.compile(r"^-?\d{1,12}(?:\.\d{1,6})?$")


def _decimal(text: str) -> Decimal | None:
    """A plain quantity ("12", "2.5", "1,200"): no exponents, NaN or Infinity, at most 12 digits."""
    t = str(text).replace(",", "").strip()
    if not _PLAIN_NUMBER.match(t):
        return None
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


def _currency_in(text: str) -> str | None:
    m = re.search(r"\b(USD|EUR|GBP|CAD|AUD|CHF|JPY)\b", text.upper())
    if m:
        return m.group(1)
    for sign, code in CURRENCY_SIGNS.items():
        if sign in text:
            return code
    return None


def _column_type(text: str, extra: dict[str, list[str]] | None = None) -> str | None:
    t = text.lower().strip().rstrip(":")
    for name, words in (extra or {}).items():  # a company's own wording wins over the defaults
        if any(t == w.lower() for w in words):
            return name
    for name in ("description", "unit_price", "quantity", "amount", "item_code"):
        if any(t == k or t.startswith(k + " ") or t.endswith(" " + k) for k in COLS[name]):
            return name
    return None


def _table(lines: list[Line], patterns: list[tuple[str, re.Pattern[str]]], extra: dict[str, list[str]] | None = None
           ) -> tuple[list[dict[str, Any]], set[int], list[str]]:
    """Find the item table. Returns (rows, indices of lines it used, notes)."""
    notes: list[str] = []
    header_idx = None
    cols: list[tuple[str, Seg]] = []
    for i, ln in enumerate(lines):
        kinds = [(_column_type(s.text, extra), s) for s in ln.segs]
        found = {k for k, _ in kinds if k}
        if "description" in found and "amount" in found and ({"quantity", "unit_price"} & found):
            header_idx, cols = i, _disambiguate([(k, s) for k, s in kinds if k])
            break
    if header_idx is None:
        return [], set(), ["No item table header (description, quantity or price, amount) was found."]
    header_text = [s.text.lower() for _, s in cols]
    used = {header_idx}
    rows: list[dict[str, Any]] = []
    for i in range(header_idx + 1, len(lines)):
        ln = lines[i]
        if SKIP.match(ln.text.strip()):
            used.add(i)
            continue
        if [s.text.lower() for s in ln.segs] == header_text:
            used.add(i)  # the header repeated on a new page
            continue
        if len(ln.segs) <= 2 and _match_label(ln.segs[0].text, [p for p in patterns if p[0] in MONEY_FIELDS]):
            break  # a totals line (label + amount); an item named "Shipping cartons" has more cells
        cells: dict[str, Seg] = {}
        for s in ln.segs:
            best = min(cols, key=lambda c: (-_overlap(s, c[1]), abs((s.x0 + s.x1) / 2 - (c[1].x0 + c[1].x1) / 2)))
            if best[0] in cells:
                cells[best[0]] = Seg(cells[best[0]].text + " " + s.text, cells[best[0]].x0, s.x1, cells[best[0]].top,
                                     max(cells[best[0]].bottom, s.bottom), s.page)
            else:
                cells[best[0]] = s
        numeric = [k for k in ("quantity", "unit_price", "amount") if k in cells]
        if not numeric:
            if rows and "description" in cells:
                rows[-1]["description"].append(cells["description"])
                used.add(i)
                continue
            break
        rows.append({"page": ln.page, "cells": cells, "description": [cells["description"]] if "description" in cells else []})
        used.add(i)
    if not rows:
        notes.append("The item table has a header but no rows were read.")
    return rows, used, notes


def _disambiguate(cols: list[tuple[str, Seg]]) -> list[tuple[str, Seg]]:
    """Two description columns can come from overlapping wording (one supplier's "Item" is the description,
    another's is the product code). When a header has two, the one whose heading is a code word ("Item", "SKU",
    "Code") is the code column, and the other stays the description."""
    desc = [c for c in cols if c[0] == "description"]
    if len(desc) < 2:
        return cols
    code_words = set(COLS["item_code"])
    out = []
    for kind, seg in cols:
        if kind == "description" and seg.text.lower().strip().rstrip(":") in code_words and any(
                d[1] is not seg and d[1].text.lower().strip().rstrip(":") not in code_words for d in desc):
            kind = "item_code"
        out.append((kind, seg))
    return out


def _overlap(a: Seg, b: Seg) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))


def extract_pdf(file_name: str, data: bytes, policy: APPolicy, fp: BankFingerprinter) -> Invoice:
    hidden: list[str] = []
    lines, pages = pdf_lines(data, hidden)
    inv = Invoice(doc_id=sha256_bytes(data), file=file_name, format="pdf", pages=pages)
    if hidden:
        masked = [mask_digits(h)[:80] for h in hidden[:10]]
        inv.fields["hidden_text"] = FieldValue(value=len(hidden), origin=Origin.COMPUTED, note="; ".join(masked))
    if not lines:
        inv.extraction_notes.append("The PDF has no text layer (a scan?). Scanned invoices need OCR, which is not set up.")
        return inv
    patterns = _label_patterns(policy)
    rows, used, notes = _table(lines, patterns, policy.extra_columns)
    inv.extraction_notes += notes
    for n, r in enumerate(rows, start=1):
        c = r["cells"]
        desc_segs = r["description"]
        desc = " ".join(s.text for s in desc_segs).strip()
        line = InvoiceLine(index=n, description=FieldValue(value=desc, origin=Origin.EXTRACTED,
                                                           evidence=desc_segs[0].ev(desc) if desc_segs else None))
        if "item_code" in c:
            line.item_code = FieldValue(value=c["item_code"].text.strip(), origin=Origin.EXTRACTED, evidence=c["item_code"].ev())
        if "quantity" in c:
            q = _decimal(c["quantity"].text)
            line.quantity = FieldValue(value=q, origin=Origin.EXTRACTED, evidence=c["quantity"].ev())
        for k in ("unit_price", "amount"):
            if k in c:
                v, _ = parse_money(c[k].text)
                setattr(line, k, FieldValue(value=v, origin=Origin.EXTRACTED, evidence=c[k].ev()))
        inv.lines.append(line)

    claimed: set[int] = set()
    for i, ln in enumerate(lines):
        if i in used:
            continue
        for j, s in enumerate(ln.segs):
            hit = _match_label(s.text, patterns)
            if hit is None:
                continue
            name, m = hit
            if name in inv.fields:
                continue
            rest, ev_seg = m.group("rest").strip(), s
            if not rest:
                nxt = ln.segs[j + 1] if j + 1 < len(ln.segs) else None
                if nxt is not None and _value_like(nxt.text, patterns):
                    rest, ev_seg = nxt.text.strip(), nxt
                    claimed.add(id(nxt))
                else:
                    below = _below(lines, i, s, used, patterns)
                    if below is not None:
                        rest, ev_seg = below.text.strip(), below
            if not rest:
                continue
            _set_field(inv, name, rest, m.group("paren"), ev_seg, policy, fp)

    if "bank_account" not in inv.fields:  # remittance details are often mid-sentence: "... Account No: 1234 ..."
        for i, ln in enumerate(lines):
            if i in used:
                continue
            for name, rx in BANK_ANYWHERE:
                mm = rx.search(ln.text)
                if mm and name not in inv.fields:
                    seg = next((s for s in ln.segs if mm.group(1)[:4] in s.text), ln.segs[0])
                    _set_field(inv, name, mm.group(1).strip(), None, seg, policy, fp)

    accounts = {BankFingerprinter.digits(m.group(1)) for ln in lines for m in [BANK_ANYWHERE[0][1].search(ln.text)] if m}
    if len(accounts) > 1:
        inv.fields["bank_account_conflict"] = FieldValue(value=len(accounts), origin=Origin.COMPUTED,
                                                         note=", ".join(sorted(BankFingerprinter.mask(a) for a in accounts)))

    # The vendor is the first line of page 1 that is not the document title ("INVOICE", possibly
    # letter-spaced as "I N V O I C E") and not a label.
    first = next((ln for ln in lines if ln.page == 1 and not re.fullmatch(r"(tax)?invoice", re.sub(r"\s", "", ln.text), re.I)
                  and _match_label(ln.segs[0].text, patterns) is None), None)
    if first is not None:
        inv.fields["vendor_name"] = FieldValue(value=first.segs[0].text.strip(), origin=Origin.EXTRACTED, evidence=first.segs[0].ev())
    if "currency" not in inv.fields:
        for name in ("total", "subtotal"):
            f = inv.fields.get(name)
            if f and f.evidence:
                code = _currency_in(f.evidence.text)
                if code:
                    inv.fields["currency"] = FieldValue(value=code, origin=Origin.NORMALIZED, evidence=f.evidence)
                    break
        else:
            if any("$" in (f.evidence.text if f.evidence else "") for f in inv.fields.values()):
                inv.fields["currency"] = FieldValue(value=policy.base_currency, origin=Origin.INFERRED,
                                                    note=f"Only '$' is printed; taken as {policy.base_currency}.")
    return inv


def _value_like(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> bool:
    """Can this cell be the value of a label? Not if it is itself a label ("Date", "PO Number:"); yes if it only
    starts like one but carries the value ("PO 4516", "PO#4516", "P.O. 4516")."""
    hit = _match_label(text, patterns)
    if hit is None:
        return True
    rest = hit[1].group("rest")
    return bool(rest) and any(ch.isdigit() for ch in rest)


def _below(lines: list[Line], i: int, label: Seg, used: set[int], patterns: list[tuple[str, re.Pattern[str]]]) -> Seg | None:
    for k in range(i + 1, min(i + 3, len(lines))):
        if k in used or lines[k].page != label.page:
            continue
        for s in lines[k].segs:
            if _overlap(s, Seg("", label.x0 - 4, label.x1 + 40, 0, 0, 0)) > 0:
                return s if _value_like(s.text, patterns) else None
    return None


def _set_field(inv: Invoice, name: str, raw: str, paren: str | None, seg: Seg, policy: APPolicy, fp: BankFingerprinter) -> None:
    if name in MONEY_FIELDS:
        v, why = parse_money(raw)
        if v is None:
            inv.extraction_notes.append(f"{name}: '{raw}' is not an amount ({why}).")
            return
        inv.fields[name] = FieldValue(value=v, origin=Origin.EXTRACTED, evidence=seg.ev())
        if name == "tax":
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", f"{paren or ''} {seg.text}")
            if m:
                inv.fields["tax_rate"] = FieldValue(value=Decimal(m.group(1)) / 100, origin=Origin.EXTRACTED, evidence=seg.ev())
    elif name in DATE_FIELDS:
        iso = parse_date(raw, policy.date_formats)
        if iso is None:
            inv.extraction_notes.append(f"{name}: '{raw}' is not a date in a known format.")
            return
        inv.fields[name] = FieldValue(value=iso, origin=Origin.NORMALIZED, evidence=seg.ev(), original=raw)
    elif name in ("bank_account", "routing_number"):
        if len(BankFingerprinter.digits(raw)) < 6 or not any(ch.isdigit() for ch in raw):
            inv.extraction_notes.append(f"{name}: the text after the label is not an account number; ignored.")
            return
        masked = BankFingerprinter.mask(raw)
        inv.fields[name] = FieldValue(value=masked, origin=Origin.EXTRACTED, evidence=seg.ev(masked))
        if name == "bank_account":
            inv.fields["_bank_raw"] = FieldValue(value=raw, origin=Origin.EXTRACTED)  # removed by finish_bank()
        else:
            inv.fields["_routing_raw"] = FieldValue(value=raw, origin=Origin.EXTRACTED)
    elif name == "currency":
        inv.fields[name] = FieldValue(value=raw.strip().upper()[:3], origin=Origin.EXTRACTED, evidence=seg.ev())
    else:
        inv.fields[name] = FieldValue(value=mask_if_bank(raw.strip()), origin=Origin.EXTRACTED, evidence=seg.ev())


def finish_bank(inv: Invoice, fp: BankFingerprinter) -> None:
    """Replace the raw account number with its keyed fingerprint; the raw value never leaves this call."""
    raw = inv.fields.pop("_bank_raw", None)
    routing = inv.fields.pop("_routing_raw", None)
    if raw is not None:
        inv.fields["bank_fingerprint"] = FieldValue(value=fp.digest("account", str(raw.value)), origin=Origin.COMPUTED)
    if routing is not None:
        inv.fields["routing_fingerprint"] = FieldValue(value=fp.digest("routing", str(routing.value)), origin=Origin.COMPUTED)


def extract_json(file_name: str, data: bytes, policy: APPolicy, fp: BankFingerprinter) -> Invoice:
    """A structured invoice (an e-invoice export): fields are taken as given, with JSON pointers as evidence."""
    doc = json.loads(data.decode("utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("the JSON must be an object with the invoice's fields")
    for key in ("vendor", "remit_to"):
        if doc.get(key) is not None and not isinstance(doc.get(key), dict):
            raise ValueError(f"'{key}' must be an object")
    if doc.get("lines") is not None and (not isinstance(doc["lines"], list) or not all(isinstance(x, dict) for x in doc["lines"])):
        raise ValueError("'lines' must be a list of objects")
    inv = Invoice(doc_id=sha256_bytes(data), file=file_name, format="json")

    def put(name: str, value: Any, pointer: str, origin: Origin = Origin.EXTRACTED) -> None:
        if value in (None, ""):
            return
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            raise ValueError(f"{pointer} must be a single value, not {type(value).__name__}")
        value = mask_if_bank(value) if isinstance(value, str) else value
        inv.fields[name] = FieldValue(value=value, origin=origin, evidence=Evidence(pointer=pointer, text=mask_if_bank(str(value))))

    vendor = doc.get("vendor") or {}
    put("vendor_name", vendor.get("name"), "/vendor/name")
    put("vendor_tax_id", vendor.get("tax_id"), "/vendor/tax_id")
    for k in ("invoice_number", "po_number", "terms", "currency"):
        v = doc.get(k)
        put(k, v if v is None or isinstance(v, (str, dict, list)) else str(v), f"/{k}")
    for k in DATE_FIELDS:
        if doc.get(k):
            iso = parse_date(str(doc[k]), policy.date_formats + ["%Y-%m-%d"])
            if iso:
                put(k, iso, f"/{k}", Origin.NORMALIZED)
    for k in MONEY_FIELDS | {"tax_rate"}:
        if doc.get(k) is not None:
            if k == "tax_rate":
                v = _decimal(str(doc[k]))
            else:
                v, _ = parse_money(str(doc[k]))
            if v is None:
                inv.extraction_notes.append(f"/{k}: '{str(doc[k])[:40]}' is not a number; not read.")
            put(k, v, f"/{k}")
    remit = doc.get("remit_to") or {}
    if remit.get("account_number"):
        masked = BankFingerprinter.mask(str(remit["account_number"]))
        inv.fields["bank_account"] = FieldValue(value=masked, origin=Origin.EXTRACTED, evidence=Evidence(pointer="/remit_to/account_number", text=masked))
        inv.fields["bank_fingerprint"] = FieldValue(value=fp.digest("account", str(remit["account_number"])), origin=Origin.COMPUTED)
    if remit.get("routing_number"):
        inv.fields["routing_fingerprint"] = FieldValue(value=fp.digest("routing", str(remit["routing_number"])), origin=Origin.COMPUTED)
    for n, ln in enumerate(doc.get("lines") or [], start=1):
        p = f"/lines/{n - 1}"
        line = InvoiceLine(index=n, description=FieldValue(value=mask_if_bank(str(ln.get("description", ""))[:300]),
                                                           origin=Origin.EXTRACTED, evidence=Evidence(pointer=p + "/description")))
        if ln.get("item_code"):
            line.item_code = FieldValue(value=str(ln["item_code"]), origin=Origin.EXTRACTED, evidence=Evidence(pointer=p + "/item_code"))
        for k in ("quantity", "unit_price", "amount"):
            if ln.get(k) is not None:
                v = _decimal(str(ln[k])) if k == "quantity" else parse_money(str(ln[k]))[0]
                setattr(line, k, FieldValue(value=v, origin=Origin.EXTRACTED, evidence=Evidence(pointer=f"{p}/{k}", text=str(ln[k]))))
        inv.lines.append(line)
    return inv


def extract(file_name: str, data: bytes, policy: APPolicy, fp: BankFingerprinter) -> Invoice:
    name = file_name.lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        try:
            inv = extract_pdf(file_name, data, policy, fp)
        except Exception as exc:  # pdfminer raises many types for a damaged file
            if isinstance(exc, ValueError) and "readable" in str(exc):
                raise
            raise ValueError(f"{file_name} is not a readable PDF ({type(exc).__name__})") from exc
    elif name.endswith(".json"):
        try:
            inv = extract_json(file_name, data, policy, fp)
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError, RecursionError) as exc:
            raise ValueError(f"{file_name} is not a readable invoice JSON ({type(exc).__name__})") from exc
    else:
        raise ValueError(f"{file_name}: invoices are read from PDF (with a text layer) or JSON")
    finish_bank(inv, fp)
    return inv
