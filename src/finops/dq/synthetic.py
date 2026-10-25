"""Synthetic vendor and purchase-order exports with known answers, for measuring the data-quality gate.

The generator decides the truth first (clean canonical vendors), then writes them the way two different systems
would (a procurement portal CSV and a legacy ERP workbook), then injects faults. Every source row gets a label: its
case, the decision the gate should reach, and the reason code(s) it should give. Three kinds of rows:

- clean: must be accepted.
- legit_*: unusual but valid (a foreign vendor with no US tax id, a card-paid vendor with no bank details, two real
  companies with similar names, an EIN typed without its hyphen...). These measure false quarantines.
- faults: definite errors (must be rejected) and suspicious records (must go to review), each with its code.

One legit case is expected to be quarantined: a company whose name starts with "@". The formula-injection check sends
it to review; it is included so the cost of that check is measured, not hidden.
"""

from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from openpyxl import Workbook

from finops.core.fingerprint import stable_xlsx

PORTAL_HEADER = ["Supplier ID", "Supplier Name", "Also Known As", "EIN", "Sales Tax %", "Bank Acct", "ABA", "Status",
                 "Country", "Contact Email", "Terms (days)", "Onboarded"]
ERP_HEADER = ["VENDOR_NO", "VENDOR_NAME", "ALT_NAMES", "TAX_ID", "VAT_RATE", "BANK_ACCOUNT", "ROUTING", "STAT", "CTRY",
              "EMAIL", "CCY", "PAY_TERMS", "CREATED"]
CANON_VENDOR = ["vendor_id", "name", "aliases", "tax_id", "tax_rate", "bank_account", "routing_number", "status", "country",
                "email", "currency", "payment_terms_days", "onboarded_date"]
PO_HEADER = ["PO_NUMBER", "VENDOR_NO", "PO_STATUS", "CCY", "LINE", "ITEM", "ITEM_DESC", "QTY", "UNIT_PRICE", "GR_REQUIRED"]

FIRST = ["Northwind", "Contoso", "Fabrikam", "Tailspin", "Adventure", "Alpine", "Coho", "Proseware", "Litware", "Wingtip",
         "Woodgrove", "Lucerne", "Fourth Coffee", "Blue Yonder", "Humongous", "Trey", "Graphic Design", "Wide World",
         "Relecloud", "Bellows", "Datum", "Southridge", "Margie", "Consolidated", "Pinecrest", "Riverbend", "Ironclad",
         "Summit", "Harbor", "Meridian", "Granite", "Evergreen", "Silverline", "Redwood", "Lakeside", "Brightwater"]
SECOND = ["Traders", "Supply", "Logistics", "Industries", "Foods", "Systems", "Partners", "Freight", "Labs", "Works",
          "Metals", "Packaging", "Electric", "Chemicals", "Textiles", "Analytics"]
COUNTRY_NAMES = {"US": ["USA", "United States", "US"], "CA": ["Canada", "CA"], "GB": ["United Kingdom", "GB"], "DE": ["Germany"],
                 "MX": ["Mexico"]}
CURRENCY = {"US": "USD", "CA": "CAD", "GB": "GBP", "DE": "EUR", "MX": "MXN"}
ITEMS = {"OFF-100": ("Copy paper, case", 42), "OFF-210": ("Printer toner, black", 280), "SAF-121": ("Safety gloves, size L", 25),
         "SAF-300": ("Hard hat", 31), "IT-550": ("Laptop dock", 189), "IT-900": ("Rack server", 7400),
         "PKG-010": ("Pallet wrap", 19), "PKG-200": ("Shipping boxes, 100", 64), "MRO-77": ("Bearing assembly", 115),
         "LAB-12": ("Reagent kit", 960)}


def aba_check_digit(first8: str) -> str:
    d = [int(c) for c in first8]
    s = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5])
    return str((10 - s % 10) % 10)


@dataclass
class Vendor:
    vendor_id: str
    name: str
    aliases: list[str]
    tax_id: str
    tax_rate: str  # canonical fraction text, "" if none
    bank_account: str
    routing_number: str
    status: str
    country: str
    email: str
    payment_terms_days: int
    onboarded: date

    def canonical(self) -> dict[str, str]:
        return {"vendor_id": self.vendor_id, "name": self.name, "aliases": ";".join(self.aliases), "tax_id": self.tax_id,
                "tax_rate": self.tax_rate, "bank_account": self.bank_account, "routing_number": self.routing_number,
                "status": self.status, "country": self.country, "email": self.email, "currency": CURRENCY[self.country],
                "payment_terms_days": str(self.payment_terms_days), "onboarded_date": self.onboarded.isoformat()}


@dataclass
class Row:
    source: str  # portal | erp
    cells: dict[str, Any]
    case: str
    expect: str  # accepted | review | rejected | duplicate
    codes: list[str] = field(default_factory=list)


@dataclass
class SyntheticSet:
    portal_csv: bytes
    erp_xlsx: bytes
    previous_csv: bytes  # last month's accepted vendor master (canonical)
    po_csv: bytes
    vendor_truth: list[dict[str, Any]]  # one per source row: source, row (1-based, header = 1), case, expect, codes
    po_truth: list[dict[str, Any]]


class _Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.used_names: set[str] = set()
        self.used_eins: set[str] = set()
        self.used_accounts: set[str] = set()
        self.next_id = 100

    def name(self) -> str:
        for _ in range(1000):
            n = f"{self.r.choice(FIRST)} {self.r.choice(SECOND)}"
            if n not in self.used_names and not any(n.split()[0] == u.split()[0] and n.split()[-1] == u.split()[-1] for u in self.used_names):
                self.used_names.add(n)
                return n
        raise RuntimeError("ran out of names")

    def ein(self) -> str:
        while True:
            e = f"{self.r.randint(10, 99)}-{self.r.randint(1000000, 9999999)}"
            if e not in self.used_eins:
                self.used_eins.add(e)
                return e

    def account(self) -> str:
        while True:
            a = str(self.r.randint(10 ** 9, 10 ** 12 - 1))
            if a not in self.used_accounts:
                self.used_accounts.add(a)
                return a

    def routing(self) -> str:
        first8 = f"0{self.r.randint(1000000, 9999999)}" if self.r.random() < 0.4 else str(self.r.randint(10000000, 32999999))
        return first8 + aba_check_digit(first8)

    def vendor(self, country: str = "US", status: str = "active") -> Vendor:
        vid = f"V{self.next_id}"
        self.next_id += 1
        name = self.name()
        us = country == "US"
        base = name.split()[0]
        return Vendor(vid, name, [f"{name} Inc.", f"{name.upper()} LLC"] if self.r.random() < 0.6 else [],
                      self.ein() if us else "", self.r.choice(["", "0.0825", "0.07", "0.06"]) if us else "",
                      self.account(), self.routing() if us else "", status, country,
                      f"ap@{base.lower().replace(' ', '')}{self.r.randint(1, 99)}.example.com",
                      self.r.choice([0, 15, 30, 30, 45, 60]), date(2020, 1, 1) + timedelta(days=self.r.randint(0, 2200)))


def portal_cells(v: Vendor, r: random.Random) -> dict[str, Any]:
    pct = "" if not v.tax_rate else f"{float(v.tax_rate) * 100:g}"
    return {"Supplier ID": v.vendor_id, "Supplier Name": v.name, "Also Known As": ";".join(v.aliases), "EIN": v.tax_id,
            "Sales Tax %": pct, "Bank Acct": v.bank_account, "ABA": v.routing_number,
            "Status": {"active": "A", "inactive": "I", "blocked": "B"}[v.status], "Country": r.choice(COUNTRY_NAMES[v.country]),
            "Contact Email": v.email, "Terms (days)": str(v.payment_terms_days), "Onboarded": v.onboarded.strftime("%m/%d/%Y")}


def erp_cells(v: Vendor, r: random.Random) -> dict[str, Any]:
    created: Any = v.onboarded if r.random() < 0.5 else v.onboarded.strftime("%d.%m.%Y")
    return {"VENDOR_NO": v.vendor_id, "VENDOR_NAME": v.name, "ALT_NAMES": "|".join(v.aliases), "TAX_ID": v.tax_id,
            "VAT_RATE": v.tax_rate, "BANK_ACCOUNT": v.bank_account, "ROUTING": v.routing_number,
            "STAT": {"active": "ACTIVE", "inactive": "INACTIVE", "blocked": "HOLD"}[v.status], "CTRY": v.country,
            "EMAIL": v.email, "CCY": CURRENCY[v.country], "PAY_TERMS": f"NET{v.payment_terms_days}", "CREATED": created}


def cells(source: str, v: Vendor, r: random.Random) -> dict[str, Any]:
    return portal_cells(v, r) if source == "portal" else erp_cells(v, r)


# Field -> the column each source uses for it, for injecting faults by canonical name.
COL = {"portal": dict(zip(CANON_VENDOR[:10] + ["payment_terms_days", "onboarded_date"],
                          ["Supplier ID", "Supplier Name", "Also Known As", "EIN", "Sales Tax %", "Bank Acct", "ABA", "Status",
                           "Country", "Contact Email", "Terms (days)", "Onboarded"], strict=True)),
       "erp": dict(zip(CANON_VENDOR, ERP_HEADER[:10] + ["CCY", "PAY_TERMS", "CREATED"], strict=True))}


def generate(seed: int, clean: int = 70, per_fault: int = 2, per_legit: int = 2) -> SyntheticSet:
    g = _Gen(seed)
    r = g.r
    rows: list[Row] = []
    previous: list[dict[str, str]] = []
    vendors_for_po: list[Vendor] = []
    inactive_vendors: list[Vendor] = []
    unusual = ["Société Générale d'Équipement & Fils", "O'Brien-Hughes & Partners (Holdings)", "Müller Bürobedarf GmbH & Co. KG",
               "A&B Klein-Østergaard ApS", "Ünal Tekstil Sanayi ve Ticaret"]
    r.shuffle(unusual)

    def src() -> str:
        return "portal" if r.random() < 0.55 else "erp"

    def add(v: Vendor, case: str, expect: str, codes: list[str] | None = None, source: str | None = None,
            edit: dict[str, Any] | None = None, in_previous: bool = True) -> Row:
        s = source or src()
        c = cells(s, v, r)
        for f, val in (edit or {}).items():
            c[COL[s][f]] = val
        row = Row(s, c, case, expect, codes or [])
        rows.append(row)
        if in_previous and r.random() < 0.85:
            previous.append(v.canonical())
        return row

    for _ in range(clean):
        country = r.choices(["US", "CA", "GB", "DE", "MX"], [80, 7, 6, 4, 3])[0]
        status = r.choices(["active", "inactive", "blocked"], [88, 9, 3])[0]
        v = g.vendor(country, status)
        add(v, "clean", "accepted")
        if status == "active":
            vendors_for_po.append(v)
        elif status == "inactive":
            inactive_vendors.append(v)

    # -- legitimate oddities: must be accepted -------------------------------------------------------------------------
    for i in range(per_legit):
        v = g.vendor(r.choice(["CA", "GB", "DE"]))
        v.tax_id = r.choice(["", f"GB{r.randint(100000000, 999999999)}", f"DE{r.randint(100000000, 999999999)}"])
        add(v, "legit_foreign_no_ein", "accepted")
        v = g.vendor("US")
        v.bank_account, v.routing_number = "", ""
        add(v, "legit_no_bank_card_paid", "accepted")
        v = g.vendor("GB")
        v.name = unusual[i % len(unusual)]
        g.used_names.add(v.name)
        add(v, "legit_unusual_name", "accepted", in_previous=False)
        a = g.vendor("US")
        b = g.vendor("US")
        b.name = a.name.split()[0] + " " + a.name.split()[1] + "s"  # Contoso Supply / Contoso Supplys: two companies, two EINs
        g.used_names.add(b.name)
        add(a, "legit_similar_name_distinct", "accepted")
        add(b, "legit_similar_name_distinct", "accepted")
        v = g.vendor("US")
        s = src()
        add(v, "legit_ein_without_hyphen", "accepted", source=s, edit={"tax_id": v.tax_id.replace("-", "")})
        v = g.vendor("US")
        s = "portal"
        add(v, "legit_messy_spacing_and_codes", "accepted", source=s,
            edit={"name": f"  {v.name}   ", "status": " a ", "country": " usa "})
        v = g.vendor("US")
        v.payment_terms_days = 0
        add(v, "legit_immediate_terms", "accepted")
        v = g.vendor("US", "inactive")
        v.email = ""
        add(v, "legit_inactive_without_email", "accepted")
        v = g.vendor("US")
        v.tax_rate = "0.0825"
        add(v, "legit_percent_sign", "accepted", source="portal", edit={"tax_rate": "8.25%"})
    v = g.vendor("US")
    v.name = "@Home Supply"
    g.used_names.add(v.name)
    add(v, "legit_name_starts_with_at", "accepted")  # valid: the gate is expected to hold it (the formula check's cost)

    # -- definite errors: must be rejected -----------------------------------------------------------------------------
    def fault(case: str, codes: list[str], edit: dict[str, Any], expect: str = "rejected", source: str | None = None,
              country: str = "US") -> None:
        v = g.vendor(country)
        add(v, case, expect, codes, source=source, edit=edit)

    for _ in range(per_fault):
        fault("missing_name", ["MISSING_REQUIRED"], {"name": ""})
        fault("missing_id", ["MISSING_REQUIRED"], {"vendor_id": ""})
        fault("short_ein", ["US_VENDOR_NEEDS_EIN"], {"tax_id": f"{r.randint(10, 99)}-{r.randint(1000, 99999)}"})
        fault("missing_ein", ["US_VENDOR_NEEDS_EIN"], {"tax_id": ""})
        v = g.vendor("US")
        bad = v.routing_number[:8] + str((int(v.routing_number[8]) + 3) % 10)
        add(v, "bad_routing_checksum", "rejected", ["INVALID_ROUTING"], edit={"routing_number": bad})
        fault("bank_without_routing", ["US_BANK_NEEDS_ROUTING"], {"routing_number": ""})
        fault("routing_without_account", ["ROUTING_NEEDS_ACCOUNT"], {"bank_account": ""})
        fault("invalid_email", ["INVALID_EMAIL"], {"email": r.choice(["ap at example.com", "billing@", "accounts@@x.com"])})
        fault("terms_out_of_range", ["OUT_OF_RANGE"], {"payment_terms_days": r.choice(["365", "-5"])}, source="portal")
        fault("unknown_status", ["INVALID_VALUE"], {"status": "Z"}, source="portal")
        fault("bad_date", ["INVALID_DATE"], {"onboarded_date": r.choice(["31/31/2024", "yesterday", "2024-13-40"])}, source="portal")
        fault("tax_rate_not_number", ["INVALID_NUMBER"], {"tax_rate": "eight"}, source="portal")
        fault("bad_account_number", ["INVALID_FORMAT"], {"bank_account": r.choice(["12AB34", "12345"])})
        fault("unknown_country", ["INVALID_VALUE"], {"country": "Narnia"}, source="portal")
        v = g.vendor("US")
        v.routing_number = "0" + v.routing_number[1:8]
        v.routing_number += aba_check_digit(v.routing_number)
        add(v, "routing_leading_zero_lost", "rejected", ["INVALID_ROUTING"], source="erp",
            edit={"routing_number": int(v.routing_number)})  # a number cell: Excel dropped the leading zero

    # -- suspicious: must go to review ---------------------------------------------------------------------------------
    for _ in range(per_fault):
        fault("formula_in_name", ["FORMULA_LIKE_TEXT"], {"name": '=HYPERLINK("http://x.example/pay","Click")'}, expect="review")
        a = g.vendor("US")
        b = g.vendor("US")
        b.tax_id = a.tax_id
        add(a, "same_tax_id_pair", "review", ["SAME_TAX_ID"])
        add(b, "same_tax_id_pair", "review", ["SAME_TAX_ID"], in_previous=False)
        a = g.vendor("US")
        b = g.vendor("US")
        b.bank_account, b.routing_number = a.bank_account, a.routing_number
        add(a, "shared_bank_pair", "review", ["SHARED_BANK_ACCOUNT"])
        add(b, "shared_bank_pair", "review", ["SHARED_BANK_ACCOUNT"], in_previous=False)
        a = g.vendor("GB")
        b = g.vendor("GB")
        b.name = a.name + " Ltd"
        g.used_names.add(b.name)
        add(a, "similar_name_pair", "review", ["SIMILAR_NAME"])
        add(b, "similar_name_pair", "review", ["SIMILAR_NAME"], in_previous=False)
        v = g.vendor("US")
        twin = Vendor(**{**v.__dict__, "bank_account": g.account()})
        twin.aliases = list(v.aliases)
        add(v, "conflicting_key_pair", "review", ["CONFLICTING_KEY"], source="portal")
        add(twin, "conflicting_key_pair", "review", ["CONFLICTING_KEY", "CONTROLLED_FIELD_CHANGED"], source="erp", in_previous=False)
        rows[-1].codes = ["CONFLICTING_KEY"]
        v = g.vendor("US")
        previous.append(v.canonical())
        v.bank_account, v.routing_number = g.account(), g.routing()
        add(v, "bank_changed_since_last_load", "review", ["CONTROLLED_FIELD_CHANGED"], in_previous=False)
        v = g.vendor("US")
        v.email = ""
        add(v, "active_without_email", "review", ["ACTIVE_VENDOR_NEEDS_CONTACT"])
        v = g.vendor("US")
        add(v, "unsaved_formula_in_optional_field", "review", ["FORMULA_WITHOUT_VALUE"], source="erp",
            edit={"aliases": '=B2&" Inc."'})  # a real formula cell, saved by a program, so it has no value
    for _ in range(per_fault):
        v = g.vendor("US")
        add(v, "exact_duplicate_first", "accepted", source="portal")
        add(v, "exact_duplicate_repeat", "duplicate", ["DUPLICATE_ROW"], source="erp", in_previous=False)
        vendors_for_po.append(v)

    r.shuffle(rows)
    portal = [x for x in rows if x.source == "portal"]
    erp = [x for x in rows if x.source == "erp"]
    truth = [{"source": "portal", "row": i + 2, "case": x.case, "expect": x.expect, "codes": x.codes} for i, x in enumerate(portal)]
    truth += [{"source": "erp", "row": i + 2, "case": x.case, "expect": x.expect, "codes": x.codes} for i, x in enumerate(erp)]

    pbuf = io.StringIO()
    w = csv.DictWriter(pbuf, fieldnames=PORTAL_HEADER, lineterminator="\n")
    w.writeheader()
    for x in portal:
        w.writerow(x.cells)
    wb = Workbook()
    ws = wb.active
    ws.title = "Vendors"
    ws.append(ERP_HEADER)
    for x in erp:
        ws.append([x.cells[h] for h in ERP_HEADER])
        for col, h in enumerate(ERP_HEADER, start=1):  # text columns stay text, as a careful export keeps them
            cell = ws.cell(row=ws.max_row, column=col)
            if h in ("BANK_ACCOUNT", "ROUTING", "TAX_ID", "VENDOR_NO") and isinstance(x.cells[h], str):
                cell.number_format = "@"
            if isinstance(x.cells[h], str) and x.cells[h].startswith("=") and x.case != "unsaved_formula_in_optional_field":
                cell.data_type = "s"  # exported text that merely starts with "=", not a formula
    erp_bytes = stable_xlsx(wb)  # same seed, same bytes (the evaluation manifests hash them)
    prev_buf = io.StringIO()
    w = csv.DictWriter(prev_buf, fieldnames=CANON_VENDOR, lineterminator="\n")
    w.writeheader()
    for p in sorted(previous, key=lambda p: p["vendor_id"]):
        w.writerow(p)
    po_csv, po_truth = _purchase_orders(r, vendors_for_po, inactive_vendors)
    return SyntheticSet(pbuf.getvalue().encode(), erp_bytes, prev_buf.getvalue().encode(), po_csv, truth, po_truth)


def _purchase_orders(r: random.Random, active: list[Vendor], inactive: list[Vendor]) -> tuple[bytes, list[dict[str, Any]]]:
    """Purchase-order lines against vendors the gate accepts, plus labelled faults."""
    lines: list[tuple[dict[str, Any], str, str, list[str]]] = []  # cells, case, expect, codes
    po_no = 4500
    items = list(ITEMS)

    def po(vendor: Vendor, n_lines: int, case: str = "clean", expect: str = "accepted", codes: list[str] | None = None) -> list[dict[str, Any]]:
        nonlocal po_no
        po_no += 1
        out = []
        for ln in range(1, n_lines + 1):
            item = r.choice(items)
            desc, base = ITEMS[item]
            c = {"PO_NUMBER": f"PO-{po_no}", "VENDOR_NO": vendor.vendor_id, "PO_STATUS": r.choice(["O", "O", "O", "C"]),
                 "CCY": CURRENCY[vendor.country], "LINE": str(ln), "ITEM": item, "ITEM_DESC": desc,
                 "QTY": str(r.randint(1, 40)), "UNIT_PRICE": f"{base * r.uniform(0.95, 1.05):.2f}", "GR_REQUIRED": r.choice(["Y", "Y", "N"])}
            out.append(c)
            lines.append((c, case, expect, list(codes or [])))
        # every line of one PO shares its status
        for c in out:
            c["PO_STATUS"] = out[0]["PO_STATUS"]
        return out

    for _ in range(45):
        po(r.choice(active), r.randint(1, 4))
    for _ in range(2):
        # unknown vendor; zero quantity; negative price; bad line number; missing item; bad receipt flag; bad PO number
        c = po(r.choice(active), 1, "unknown_vendor", "rejected", ["UNKNOWN_REFERENCE"])[0]
        c["VENDOR_NO"] = "V99999"
        po(r.choice(active), 1, "zero_quantity", "rejected", ["OUT_OF_RANGE"])[0]["QTY"] = "0"
        po(r.choice(active), 1, "negative_price", "rejected", ["OUT_OF_RANGE"])[0]["UNIT_PRICE"] = "-12.50"
        po(r.choice(active), 1, "bad_line_number", "rejected", ["INVALID_NUMBER"])[0]["LINE"] = "1a"
        po(r.choice(active), 1, "missing_item", "rejected", ["MISSING_REQUIRED"])[0]["ITEM"] = ""
        po(r.choice(active), 1, "bad_receipt_flag", "rejected", ["INVALID_VALUE"])[0]["GR_REQUIRED"] = "maybe"
        po(r.choice(active), 1, "bad_po_number", "rejected", ["INVALID_FORMAT"])[0]["PO_NUMBER"] = f"P{r.randint(100, 999)}"
        # one PO, two currencies: every line is wrong to load
        cs = po(r.choice([v for v in active if v.country == "US"]), 3, "mixed_currency_po", "rejected", ["GROUP_INCONSISTENT"])
        cs[-1]["CCY"] = "EUR"
        # a typed extra zero: ten times the item's usual price
        c = po(r.choice(active), 1, "price_ten_times", "review", ["OUTLIER"])[0]
        c["UNIT_PRICE"] = f"{float(c['UNIT_PRICE']) * 10:.2f}"
        # the same line twice with different quantities
        c = po(r.choice(active), 1, "conflicting_line_pair", "review", ["CONFLICTING_KEY"])[0]
        d = dict(c)
        d["QTY"] = str(int(c["QTY"]) + 5)
        lines.append((d, "conflicting_line_pair", "review", ["CONFLICTING_KEY"]))
        # the same line twice, identical
        c = po(r.choice(active), 1, "exact_duplicate_first")[0]
        lines.append((dict(c), "exact_duplicate_repeat", "duplicate", ["DUPLICATE_ROW"]))
        if inactive:
            po(r.choice(inactive), 1, "vendor_not_active", "review", ["REFERENCE_STATUS"])
    # legit: a consistently expensive item is not an outlier
    for _ in range(2):
        v = r.choice(active)
        cs = po(v, 2, "legit_expensive_item")
        for c in cs:
            c["ITEM"], c["ITEM_DESC"] = "IT-900", ITEMS["IT-900"][0]
            c["UNIT_PRICE"] = f"{7400 * r.uniform(0.97, 1.03):.2f}"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=PO_HEADER, lineterminator="\n")
    w.writeheader()
    order = list(range(len(lines)))
    r.shuffle(order)
    truth = []
    seen_dupes: set[tuple[str, ...]] = set()
    for i, k in enumerate(order):
        c, case, expect, codes = lines[k]
        if case.startswith("exact_duplicate"):  # whichever copy comes first in the file is the one loaded
            sig = tuple(str(c[h]) for h in PO_HEADER)
            case, expect, codes = (("exact_duplicate_repeat", "duplicate", ["DUPLICATE_ROW"]) if sig in seen_dupes
                                   else ("exact_duplicate_first", "accepted", []))
            seen_dupes.add(sig)
        w.writerow(c)
        truth.append({"source": "erp", "row": i + 2, "case": case, "expect": expect, "codes": codes})
    return buf.getvalue().encode(), truth
