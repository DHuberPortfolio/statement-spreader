"""Synthetic invoices, purchase orders and receipts with known answers.

The generator writes the vendor master, POs and receipts as CSV, each invoice as HTML in one of
three layouts (printed to PDF by headless Edge, the way the statement corpus is) or as
structured JSON, and an answer key: every header field as printed, every line, the PO and PO
lines it belongs to, the reason codes a correct engine must raise, and whether the invoice
should be eligible without a person. The key is decided while generating, never computed by
the engine being graded.

The inbox order matters (a duplicate comes after its original; a second partial invoice after
the first), so the key is an ordered list.
"""

from __future__ import annotations

import csv
import html
import io
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

VENDORS = ["Northwind Traders", "Contoso Supply", "Fabrikam Tools", "Tailspin Freight", "Adventure Works",
           "Wide World Importers", "Litware Labs", "Proseware Inc", "Lucerne Publishing", "Fourth Coffee",
           "Coho Vineyard", "Alpine Ski House"]
GOODS = ["Steel bracket 40mm", "Shipping cartons, bundle of 25", "Safety gloves, size L", "LED panel 600x600",
         "Hydraulic hose 2m", "Printer toner, black", "Cable ties, pack of 100", "Pallet wrap film", "Copy paper, case",
         "Torque wrench 1/2in", "Hard hat, white", "Extension cord 15m", "Label printer rolls", "Bolt set M8",
         "Air filter 20x25", "Floor cleaner 5L"]
SERVICES = ["Consulting services (hours)", "Equipment maintenance visit", "Software subscription, monthly",
            "Training session (hours)"]
MIX = {"clean": 14, "service_2way": 4, "sequential": 3, "over_receipt": 3, "missing_receipt": 3, "price_over": 3,
       "price_within_tol": 3, "po_not_found": 2, "no_po_ref": 2, "closed_po": 2, "vendor_mismatch": 2, "line_math": 3,
       "total_math": 2, "tax_wrong": 2, "tax_unverified": 2, "exact_dup": 3, "same_file_again": 1, "possible_dup": 2,
       "similar_distinct": 2, "bank_changed": 3, "bank_unverified": 2, "vendor_alias": 2, "multipage": 2, "json_clean": 3}
EXPECT = {  # reason codes a correct engine must raise (at least these), and whether it may pass untouched
    "clean": ([], True), "service_2way": ([], True), "sequential": ([], True), "over_receipt": (["QTY_EXCEEDS_RECEIVED"], False),
    "missing_receipt": (["MISSING_RECEIPT"], False), "price_over": (["PRICE_OVER_PO"], False), "price_within_tol": ([], True),
    "po_not_found": (["PO_NOT_FOUND"], False), "no_po_ref": (["NO_PO_REFERENCE"], False), "closed_po": (["PO_NOT_OPEN"], False),
    "vendor_mismatch": (["VENDOR_MISMATCH"], False), "line_math": (["LINE_EXTENSION_MISMATCH"], False),
    "total_math": (["TOTAL_MISMATCH"], False), "tax_wrong": (["TAX_MISMATCH"], False), "tax_unverified": (["TAX_UNVERIFIED"], False),
    "exact_dup": (["EXACT_DUPLICATE"], False), "same_file_again": (["EXACT_DUPLICATE"], False),
    "possible_dup": (["POSSIBLE_DUPLICATE"], False), "similar_distinct": ([], True), "bank_changed": (["BANK_DETAILS_CHANGED"], False),
    "bank_unverified": (["BANK_DETAILS_UNVERIFIED"], False), "vendor_alias": ([], True), "multipage": ([], True), "json_clean": ([], True),
}
BUYER = ["Example Buyer Co.", "Accounts Payable", "500 Commerce Way", "Springfield, ST 00000"]
CSS = """body{font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#111;margin:28px}
h1{font-size:20px;margin:0}.title{font-size:22px;font-weight:bold;letter-spacing:2px}
table{border-collapse:collapse}td,th{padding:4px 10px;text-align:left;vertical-align:top}
.items{width:100%;margin-top:18px}.items th{border-bottom:1px solid #444}.num{text-align:right}
.items thead{display:table-header-group}.totals td{padding:3px 10px}.muted{color:#555}
.hdr td{padding:2px 14px 2px 0}.footer{margin-top:24px;font-size:10px}"""


class _Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.vendors: list[dict[str, str]] = []
        self.items: dict[str, list[tuple[str, str, Decimal, bool]]] = {}
        self.po_rows: list[dict[str, str]] = []
        self.receipt_rows: list[dict[str, str]] = []
        self.docs: list[dict[str, Any]] = []
        self.npo = 4500
        self.ninv = 7000
        self.nrec = 900
        for i, name in enumerate(VENDORS):
            vid = f"V{100 + i}"
            rate = self.r.choice(["0.0825", "0.07", "0.06", "", ""]) if i % 4 else ""
            acct = "" if i in (5, 9) else f"{self.r.randint(10**11, 10**12 - 1)}"
            self.vendors.append({"vendor_id": vid, "name": name, "aliases": f"{name} Inc.;{name.upper()} LLC",
                                 "tax_id": f"{self.r.randint(10, 99)}-{self.r.randint(1000000, 9999999)}", "tax_rate": rate,
                                 "bank_account": acct, "routing_number": f"0{self.r.randint(10**7, 10**8 - 1)}" if acct else "",
                                 "status": "active"})
            catalog = []
            for k, g in enumerate(self.r.sample(GOODS, 4)):
                catalog.append((f"{name[:3].upper()}-{100 + k * 7}", g, Decimal(self.r.randint(150, 40000)) / 100, True))
            s = self.r.choice(SERVICES)
            catalog.append((f"{name[:3].upper()}-SVC", s, Decimal(self.r.choice([95, 120, 150, 175, 450])), False))
            self.items[vid] = catalog

    def vendor(self, with_rate: bool | None = None, with_bank: bool = True) -> dict[str, str]:
        pool = [v for v in self.vendors if (with_rate is None or bool(v["tax_rate"]) == with_rate) and (bool(v["bank_account"]) == with_bank)]
        return self.r.choice(pool)

    def po(self, v: dict[str, str], n_lines: int, services: bool = False, status: str = "open", lots: int = 0) -> dict[str, Any]:
        self.npo += 1
        number = f"PO-{self.npo}"
        cat = [c for c in self.items[v["vendor_id"]] if (not c[3]) == services]
        if lots:  # a long order (multi-page invoices): distinct numbered lots of the vendor's goods
            cat = [(f"{v['name'][:3].upper()}-L{n:02d}", f"{GOODS[n % len(GOODS)]} (lot {n})",
                    Decimal(self.r.randint(150, 9000)) / 100, True) for n in range(1, lots + 1)]
            n_lines = lots
        lines = []
        for ln, (code, desc, price, receipt) in enumerate(self.r.sample(cat, min(n_lines, len(cat))), start=1):
            qty = Decimal(self.r.choice([2, 4, 5, 8, 10, 12, 20, 24, 40]))
            lines.append({"line_no": ln, "item_code": code, "description": desc, "quantity": qty, "unit_price": price, "receipt": receipt})
            self.po_rows.append({"po_number": number, "vendor_id": v["vendor_id"], "status": status, "currency": "USD",
                                 "line_no": str(ln), "item_code": code, "description": desc, "quantity": str(qty),
                                 "unit_price": str(price), "receipt_required": "yes" if receipt else "no"})
        return {"number": number, "vendor": v, "lines": lines}

    def receive(self, po: dict[str, Any], share: Decimal = Decimal(1), skip: bool = False) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for ln in po["lines"]:
            if not ln["receipt"] or skip:
                continue
            self.nrec += 1
            rid = f"GR-{self.nrec}"
            qty = (ln["quantity"] * share).to_integral_value()
            self.receipt_rows.append({"receipt_id": rid, "po_number": po["number"], "line_no": str(ln["line_no"]),
                                      "quantity_received": str(qty), "received_date": "2026-03-02", "status": "accepted"})
            out[ln["line_no"]] = [rid]
        return out


def _money(x: Decimal) -> str:
    return f"{x:,.2f}"


def _price(x: Decimal) -> str:
    """A unit price as the key records it: 2 decimals, or 3 when it has them (the page must match the key)."""
    return f"{x:,.3f}" if x != x.quantize(Decimal("0.01")) else f"{x:,.2f}"


def _date_text(d: date, layout: str) -> str:
    return {"A": d.strftime("%B %d, %Y").replace(" 0", " "), "B": d.strftime("%m/%d/%Y"), "C": d.strftime("%d %b %Y").lstrip("0"),
            "D": d.strftime("%d %B %Y"), "E": d.strftime("%B %d, %Y").replace(" 0", " ")}[layout]


def render_html(doc: dict[str, Any]) -> str:
    L = doc["layout"]
    e = html.escape
    lines = doc["lines"]
    inv_date, due = date.fromisoformat(doc["invoice_date"]), date.fromisoformat(doc["due_date"])
    vendor_block = f"<h1>{e(doc['vendor_name'])}</h1><div class='muted'>12 Supplier Road, Industry City</div>"
    if doc.get("tax_id"):
        vendor_block += f"<div class='muted'>Tax ID: {e(doc['tax_id'])}</div>"
    bill = "<div><b>Bill To:</b><br>" + "<br>".join(e(x) for x in BUYER) + "</div>"
    if L == "A":
        cols = [("Item", "code"), ("Description", "desc"), ("Qty", "qty"), ("Unit Price", "price"), ("Amount", "amount")]
        head = (f"<table style='width:100%'><tr><td>{vendor_block}</td><td style='text-align:right'><div class='title'>INVOICE</div></td></tr></table>"
                "<table class='hdr' style='margin-top:12px'>"
                f"<tr><td>Invoice No:</td><td>{e(doc['invoice_number'])}</td></tr>"
                f"<tr><td>Invoice Date:</td><td>{_date_text(inv_date, L)}</td></tr>"
                f"<tr><td>Due Date:</td><td>{_date_text(due, L)}</td></tr>"
                + (f"<tr><td>PO Number:</td><td>{e(doc['po_number'])}</td></tr>" if doc.get("po_number") else "")
                + f"<tr><td>Terms:</td><td>{e(doc['terms'])}</td></tr></table><div style='margin-top:12px'>{bill}</div>")
    elif L == "B":
        cols = [("Description", "desc"), ("Quantity", "qty"), ("Rate", "price"), ("Line Total", "amount")]
        cells = [("Invoice #", doc["invoice_number"]), ("Date", _date_text(inv_date, L)), ("Due Date", _date_text(due, L))]
        if doc.get("po_number"):
            cells.append(("Purchase Order", doc["po_number"]))
        head = ("<div class='title'>INVOICE</div>" + vendor_block.replace("<div class='muted'>Tax ID", "<div class='x' style='display:none'>Tax ID")
                + "<table class='hdr' style='margin-top:14px'><tr>" + "".join(f"<td><b>{e(a)}</b></td>" for a, _ in cells)
                + "</tr><tr>" + "".join(f"<td>{e(b)}</td>" for _, b in cells) + f"</tr></table><div style='margin-top:12px'>{bill}</div>")
    elif L == "D":  # never used in dev/holdout: other wording everywhere, to test what the extractor has not seen
        cols = [("Code", "code"), ("Item", "desc"), ("Units", "qty"), ("Unit Cost", "price"), ("Net", "amount")]
        head = (f"<div style='text-align:center'>{vendor_block}<div class='title' style='margin-top:8px'>TAX INVOICE</div></div>"
                "<table class='hdr' style='margin-top:12px'>"
                f"<tr><td>Document No.</td><td>{e(doc['invoice_number'])}</td><td>Document Date</td><td>{_date_text(inv_date, L)}</td></tr>"
                + (f"<tr><td>Customer Order</td><td>{e(doc['po_number'])}</td>" if doc.get("po_number") else "<tr><td></td><td></td>")
                + f"<td>Payment Due</td><td>{_date_text(due, L)}</td></tr>"
                f"<tr><td>Terms of Payment</td><td>{e(doc['terms'])}</td></tr></table><div style='margin-top:12px'>{bill}</div>")
    elif L == "E":  # a second unseen layout, kept for testing the label-suggestion method without tuning on it
        cols = [("Ref", "code"), ("Particulars", "desc"), ("Qty", "qty"), ("Each", "price"), ("Line Value", "amount")]
        head = (f"<table style='width:100%'><tr><td>{vendor_block}</td><td style='text-align:right'>"
                "<table class='hdr' style='margin-left:auto'>"
                f"<tr><td>Our Ref.</td><td>{e(doc['invoice_number'])}</td></tr>"
                f"<tr><td>Dated</td><td>{_date_text(inv_date, L)}</td></tr>"
                + (f"<tr><td>Your Ref.</td><td>{e(doc['po_number'])}</td></tr>" if doc.get("po_number") else "")
                + f"<tr><td>Conditions</td><td>{e(doc['terms'])}</td></tr>"
                f"<tr><td>Settle By</td><td>{_date_text(due, L)}</td></tr></table></td></tr></table>"
                f"<div style='margin-top:12px'>{bill}</div>")
    else:
        cols = [("SKU", "code"), ("Description", "desc"), ("Qty", "qty"), ("Price", "price"), ("Total", "amount")]
        head = (f"<table style='width:100%'><tr><td>{vendor_block}<div style='margin-top:10px'>{bill}</div></td>"
                "<td style='text-align:right'><table class='hdr' style='margin-left:auto'>"
                f"<tr><td>Bill No.</td><td>{e(doc['invoice_number'])}</td></tr>"
                f"<tr><td>Issue Date</td><td>{_date_text(inv_date, L)}</td></tr>"
                + (f"<tr><td>Your Order No.</td><td>{e(doc['po_number'])}</td></tr>" if doc.get("po_number") else "")
                + f"<tr><td>Payment Terms</td><td>{e(doc['terms'])}</td></tr>"
                f"<tr><td>Date Due</td><td>{_date_text(due, L)}</td></tr></table></td></tr></table>")
    rows = []
    for ln in lines:
        vals = {"code": ln.get("item_code", ""), "desc": ln["description"], "qty": f"{ln['quantity']}",
                "price": _price(Decimal(ln["unit_price"])), "amount": _money(Decimal(ln["amount"]))}
        rows.append("<tr>" + "".join(f"<td class='{'num' if k in ('qty', 'price', 'amount') else ''}'>{e(vals[k])}</td>" for _, k in cols) + "</tr>")
    table = ("<table class='items'><thead><tr>" + "".join(f"<th class='{'num' if k in ('qty', 'price', 'amount') else ''}'>{e(h)}</th>" for h, k in cols)
             + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
    tot = [("Subtotal", doc["subtotal"])]
    if doc.get("tax") is not None:
        tot.append((f"Sales Tax ({Decimal(doc['tax_rate_printed']) * 100:g}%)" if doc.get("tax_rate_printed") else "Tax", doc["tax"]))
    if doc.get("freight"):
        tot.append(("Shipping", doc["freight"]))
    if L == "D":
        tot = [("Net Total" if a == "Subtotal" else a, b) for a, b in tot]
    if L == "E":
        tot = [("Goods Value" if a == "Subtotal" else a, b) for a, b in tot]
    tot.append(({"A": "Total Due", "B": "Total", "C": "Amount Due", "D": "Gross Total", "E": "Balance Payable"}[L], doc["total"]))
    cur = "USD " if L in ("C", "D") else "$"
    totals = ("<table class='totals' style='margin-left:auto;margin-top:10px'>"
              + "".join(f"<tr><td>{e(a)}</td><td class='num'>{cur}{_money(Decimal(b))}</td></tr>" for a, b in tot) + "</table>")
    footer = "<div class='footer'>Please pay by the due date. Thank you for your business.</div>"
    if doc.get("bank_account"):
        footer += (f"<div class='footer'>Remit by ACH to First Example Bank &nbsp; Account No: {e(doc['bank_account'])}"
                   f" &nbsp; Routing No: {e(doc['routing_number'])}</div>")
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{head}{table}{totals}{footer}</body></html>"


def _messy_po(g: _Gen, po: str | None, messy: bool) -> str | None:
    if not messy or not po or g.r.random() >= 0.4:
        return po
    n = po.split("-")[-1]
    return g.r.choice([f"PO#{n}", n, f"PO {n}", f"P.O. {n}"])


def build(seed: int = 21, layouts: str = "ABC", messy: bool = False) -> dict[str, Any]:
    """messy: print references the ways real suppliers do (PO#4501, a bare 4501, lower-case or spaced invoice
    numbers) and use prices with 3 decimals; the answer key records exactly what is printed."""
    g = _Gen(seed)
    plan = [k for k, n in MIX.items() for _ in range(n)]
    g.r.shuffle(plan)
    inbox: list[dict[str, Any]] = []
    later: list[dict[str, Any]] = []
    base_day = date(2026, 3, 3)

    def invoice(kind: str, v: dict[str, str], po: dict[str, Any] | None, picks: list[tuple[dict[str, Any], Decimal]],
                layout: str | None = None, **over: Any) -> dict[str, Any]:
        g.ninv += 1
        lay = layout if layout and layout in layouts else g.r.choice(layouts)
        lines = []
        for ln, qty in picks:
            price = Decimal(over.get("price_factor", 1)) * ln["unit_price"]
            price = price.quantize(Decimal("0.001") if messy and g.r.random() < 0.25 else Decimal("0.01"))
            amount = (price * qty).quantize(Decimal("0.01"))
            lines.append({"item_code": ln["item_code"] if lay != "B" else "", "description": ln["description"],
                          "quantity": str(qty), "unit_price": str(price), "amount": str(amount), "po_line": ln["line_no"] if po else None})
        if over.get("line_error"):
            lines[0]["amount"] = str(Decimal(lines[0]["amount"]) + Decimal("10.00"))
        subtotal = sum((Decimal(x["amount"]) for x in lines), Decimal(0))
        rate = Decimal(v["tax_rate"]) if v["tax_rate"] else None
        tax = (subtotal * rate).quantize(Decimal("0.01")) if rate is not None else None
        if over.get("tax_unverified"):
            tax = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
        if over.get("tax_error") and tax is not None:
            tax += Decimal("4.17")
        total = subtotal + (tax or Decimal(0))
        if over.get("total_error"):
            total += Decimal("100.00")
        d = base_day + timedelta(days=g.r.randint(0, 20) + over.get("day_shift", 0))
        number = over.get("number") or f"INV-{g.ninv:06d}"
        if messy and not over.get("number") and g.r.random() < 0.3:
            number = g.r.choice([f"inv {g.ninv:06d}", f"INV {g.ninv}", f"{g.ninv:06d}"])
        doc = {"id": f"inv-{len(inbox) + len(later) + 1:03d}-{kind}", "kind": kind, "layout": lay if kind != "json_clean" else "json",
               "vendor_id": v["vendor_id"], "vendor_name": over.get("vendor_name", v["name"]),
               "tax_id": None if lay == "B" or over.get("no_tax_id") else v["tax_id"],
               "invoice_number": number, "invoice_date": d.isoformat(), "due_date": (d + timedelta(days=30)).isoformat(),
               "terms": "Net 30", "po_number": _messy_po(g, over.get("po_number", po["number"] if po else None), messy),
               "currency": "USD",
               "lines": lines, "subtotal": str(subtotal), "tax": str(tax) if tax is not None else None,
               "tax_rate_printed": str(rate) if rate is not None and lay == "A" else None, "freight": None, "total": str(total),
               "bank_account": over.get("bank_account", v["bank_account"] if g.r.random() < 0.5 else ""),
               "routing_number": over.get("routing", v["routing_number"])}
        if not doc["bank_account"]:
            doc["routing_number"] = ""
        codes, touchless = EXPECT[kind]
        doc["expect"] = {"codes": codes, "touchless": touchless,
                         "po": (po["number"] if po and kind not in ("po_not_found", "no_po_ref") else None)}
        return doc

    for kind in plan:
        services = kind == "service_2way"
        if kind in ("tax_unverified",):
            v = g.vendor(with_rate=False)
        elif kind == "tax_wrong":
            v = g.vendor(with_rate=True)
        elif kind == "bank_unverified":
            v = g.vendor(with_bank=False)
        else:
            v = g.vendor(with_bank=True)
        po = g.po(v, 1 if services else g.r.randint(1, 3), services=services, status="closed" if kind == "closed_po" else "open",
                  lots=48 if kind == "multipage" else 0)
        share = Decimal("0.5") if kind == "over_receipt" else Decimal(1)
        g.receive(po, share, skip=kind == "missing_receipt")
        full = [(ln, ln["quantity"]) for ln in po["lines"]]
        if kind == "sequential":
            # A first delivery invoiced, then the rest: unequal parts, so the two invoices are not
            # the same amount (equal amounts within the window are a possible duplicate by policy).
            half = [(ln, max(Decimal(1), (ln["quantity"] / 3).to_integral_value())) for ln in po["lines"]]
            rest = [(ln, ln["quantity"] - max(Decimal(1), (ln["quantity"] / 3).to_integral_value())) for ln in po["lines"]]
            inbox.append(invoice(kind, v, po, half))
            later.append(invoice(kind, v, po, rest, day_shift=3))
            continue
        if kind == "multipage":
            lines = po["lines"]
            picks = [(ln, ln["quantity"]) for ln in lines]
            inbox.append(invoice(kind, v, po, picks, layout=g.r.choice([x for x in layouts if x != "B"] or list(layouts))))
            continue
        over: dict[str, Any] = {}
        if kind == "price_over":
            over["price_factor"] = "1.08"
        elif kind == "price_within_tol":
            over["price_factor"] = "1.005"
        elif kind == "po_not_found":
            over["po_number"] = f"PO-{g.r.randint(90000, 99999)}"
        elif kind == "no_po_ref":
            over["po_number"] = None
        elif kind == "vendor_mismatch":
            other = g.r.choice([x for x in g.vendors if x["vendor_id"] != v["vendor_id"] and x["bank_account"]])
            inbox.append(invoice(kind, other, po, full, bank_account=""))
            continue
        elif kind == "line_math":
            over["line_error"] = True
        elif kind == "total_math":
            over["total_error"] = True
        elif kind == "tax_wrong":
            over["tax_error"] = True
        elif kind == "tax_unverified":
            over["tax_unverified"] = True
        elif kind == "bank_changed":
            over["bank_account"] = f"{g.r.randint(10**11, 10**12 - 1)}"
        elif kind == "bank_unverified":
            over["bank_account"] = f"{g.r.randint(10**11, 10**12 - 1)}"
            over["routing"] = f"0{g.r.randint(10**7, 10**8 - 1)}"
        elif kind == "vendor_alias":
            over["vendor_name"] = g.r.choice(v["aliases"].split(";"))
            over["no_tax_id"] = True
        if kind in ("exact_dup", "possible_dup", "similar_distinct", "same_file_again"):
            first = invoice("clean", v, po, full, bank_account="")
            inbox.append(first)
            if kind == "same_file_again":
                later.append({**first, "id": first["id"] + "-again", "kind": kind, "same_file_as": first["id"],
                              "expect": {"codes": EXPECT[kind][0], "touchless": False, "po": first["po_number"]}})
                continue
            if kind == "exact_dup":
                num = first["invoice_number"].replace("INV-", g.r.choice(["", "INV ", "inv-0", "#"]))
                dup = invoice(kind, v, po, full, number=num, bank_account="")
                for k in ("invoice_date", "due_date", "lines", "subtotal", "tax", "total"):
                    dup[k] = first[k]
                later.append(dup)
            elif kind == "possible_dup":
                dup = invoice(kind, v, po, full, bank_account="")
                for k in ("lines", "subtotal", "tax", "total"):
                    dup[k] = first[k]
                dup["invoice_date"] = (date.fromisoformat(first["invoice_date"]) + timedelta(days=3)).isoformat()
                later.append(dup)
            else:
                po2 = g.po(v, 1)
                g.receive(po2)
                later.append(invoice(kind, v, po2, [(ln, ln["quantity"]) for ln in po2["lines"]], bank_account=""))
            continue
        doc = invoice(kind, v, po, full, layout="A" if kind == "tax_wrong" else None, **over)
        if kind == "json_clean":
            doc["layout"] = "json"
        inbox.append(doc)
    return {"seed": seed, "mix": MIX, "inbox": inbox + later, "vendors": g.vendors, "po_rows": g.po_rows, "receipt_rows": g.receipt_rows}


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def to_json_invoice(doc: dict[str, Any]) -> bytes:
    body = {"vendor": {"name": doc["vendor_name"], "tax_id": doc["tax_id"]}, "invoice_number": doc["invoice_number"],
            "invoice_date": doc["invoice_date"], "due_date": doc["due_date"], "po_number": doc["po_number"], "terms": doc["terms"],
            "currency": doc["currency"], "subtotal": doc["subtotal"], "tax": doc["tax"], "total": doc["total"],
            "lines": [{k: ln[k] for k in ("item_code", "description", "quantity", "unit_price", "amount")} for ln in doc["lines"]]}
    if doc.get("bank_account"):
        body["remit_to"] = {"account_number": doc["bank_account"], "routing_number": doc["routing_number"]}
    return json.dumps(body, indent=1).encode("utf-8")


def write(out: Path, seed: int = 21, edge: str | None = None, layouts: str = "ABC", messy: bool = False) -> dict[str, Any]:
    """Write master CSVs, invoices (PDF via headless Edge, or JSON) and truth.json to `out`."""
    from spreader.evaluation.synthetic import print_pdf

    data = build(seed, layouts, messy)
    master = out / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "vendors.csv").write_bytes(_csv(data["vendors"]))
    (master / "purchase_orders.csv").write_bytes(_csv(data["po_rows"]))
    (master / "receipts.csv").write_bytes(_csv(data["receipt_rows"]))
    docs = out / "invoices"
    docs.mkdir(parents=True, exist_ok=True)
    failures = []
    for doc in data["inbox"]:
        if doc.get("same_file_as"):
            doc["file"] = next(d["file"] for d in data["inbox"] if d["id"] == doc["same_file_as"])
            continue
        if doc["layout"] == "json":
            doc["file"] = f"invoices/{doc['id']}.json"
            (out / doc["file"]).write_bytes(to_json_invoice(doc))
            continue
        h = docs / f"{doc['id']}.html"
        h.write_text(render_html(doc), encoding="utf-8")
        doc["file"] = f"invoices/{doc['id']}.pdf"
        err = print_pdf(h, out / doc["file"], edge)
        if err:
            failures.append((doc["id"], err))
    truth = {k: v for k, v in data.items() if k in ("seed", "mix", "inbox")}
    truth["print_failures"] = failures
    (out / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
    return truth
