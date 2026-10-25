"""Master data the invoice engine checks against: vendors, purchase orders, goods receipts.

Loaded from CSV exports (the file-based connector). A deployment swaps this module's loader for
an ERP adapter that returns the same objects; nothing else changes. Bank account numbers from
the vendor master are turned into a keyed fingerprint and the last four digits at load time;
the full number is not kept in memory past loading, written to the database, or logged.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rapidfuzz import fuzz

from finops.core.tabular import read_table

PREFIXES = ("INVOICE", "INV", "PO", "NO", "NUMBER")


def normalize_number(text: str | None) -> str:
    """Document numbers as people mistype them: INV-000123, inv 123, #123 -> 123."""
    t = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    for p in PREFIXES:
        if t.startswith(p) and len(t) > len(p) and t[len(p)].isdigit():
            t = t[len(p):]
            break
    return t.lstrip("0") or t if t.isdigit() else t


class BankFingerprinter:
    """Keyed hash (HMAC-SHA256) of a normalised account number + routing code.

    A plain hash of a 10-digit account number can be reversed by trying every number; a keyed
    one cannot without the key, which lives in a local file outside the repository.
    """

    def __init__(self, key: bytes):
        self.key = key

    @classmethod
    def from_file(cls, path: Path) -> BankFingerprinter:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(os.urandom(32))
        return cls(path.read_bytes())

    @staticmethod
    def digits(account: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (account or "").upper())

    def digest(self, kind: str, value: str) -> str:
        """Keyed digest of one normalised value; `kind` keeps an account and a routing code with the same digits apart."""
        return hmac.new(self.key, f"{kind}|{self.digits(value)}".encode(), hashlib.sha256).hexdigest()[:32]

    @staticmethod
    def mask(account: str) -> str:
        d = BankFingerprinter.digits(account)
        return f"****{d[-4:]}" if len(d) >= 4 else "****"


_DIGIT_RUN = re.compile(r"\d(?:[ -]?\d){5,}")
_BANK_WORDS = re.compile(r"account|acct|a/c|iban|routing|\baba\b|sort\s*code|swift|\bbic\b|beneficiary", re.I)


def mask_digits(text: str) -> str:
    """Every run of 6+ digits (spaces and hyphens allowed inside) becomes ****1234."""
    return _DIGIT_RUN.sub(lambda m: "****" + re.sub(r"\D", "", m.group())[-4:], text)


def mask_if_bank(text: str) -> str:
    """Mask digit runs in text that talks about bank details; leave invoice and PO numbers alone elsewhere."""
    return mask_digits(text) if _BANK_WORDS.search(text or "") else text


@dataclass
class Vendor:
    id: str
    name: str
    aliases: list[str]
    tax_id: str
    tax_rate: Decimal | None
    bank_fingerprint: str | None
    bank_masked: str | None
    status: str
    routing_fingerprint: str | None = None


@dataclass
class POLine:
    line_no: int
    item_code: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    receipt_required: bool


@dataclass
class PurchaseOrder:
    number: str
    vendor_id: str
    status: str  # open | closed | cancelled
    currency: str
    lines: dict[int, POLine] = field(default_factory=dict)


@dataclass
class Receipt:
    id: str
    po_number: str
    line_no: int
    quantity: Decimal
    date: date | None
    status: str  # accepted | rejected


@dataclass
class Master:
    vendors: dict[str, Vendor]
    pos: dict[str, PurchaseOrder]  # by normalised PO number
    receipts: list[Receipt]

    def receipts_for(self, po: str, line_no: int) -> list[Receipt]:
        return [r for r in self.receipts if normalize_number(r.po_number) == normalize_number(po) and r.line_no == line_no]

    def resolve_vendor(self, name: str | None, tax_id: str | None) -> tuple[str | None, str, str]:
        """(vendor id, how, why). how: tax_id | name | alias | fuzzy | none."""
        if tax_id:
            t = re.sub(r"[^0-9A-Z]", "", tax_id.upper())
            hits = [v for v in self.vendors.values() if v.tax_id and re.sub(r"[^0-9A-Z]", "", v.tax_id.upper()) == t]
            if len(hits) == 1:
                return hits[0].id, "tax_id", f"tax id {tax_id} is {hits[0].name}'s"
        if not name:
            return None, "none", "no vendor name was read"
        n = _norm_name(name)
        exact = [v for v in self.vendors.values() if _norm_name(v.name) == n]
        if len(exact) == 1:
            return exact[0].id, "name", f"'{name}' is the vendor master name"
        alias = [v for v in self.vendors.values() if any(_norm_name(a) == n for a in v.aliases)]
        if len(alias) == 1:
            return alias[0].id, "alias", f"'{name}' is a listed alias of {alias[0].name}"
        scored = sorted(((max([fuzz.token_set_ratio(n, _norm_name(x)) for x in [v.name] + v.aliases]), v.id)
                         for v in self.vendors.values()), reverse=True)
        if scored and scored[0][0] >= 92 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 8):
            return scored[0][1], "fuzzy", f"'{name}' is spelled like {self.vendors[scored[0][1]].name} ({scored[0][0]:.0f}/100)"
        return None, "none", f"'{name}' is not a known vendor or alias"


def _norm_name(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|company|the|limited|gmbh|plc)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _dec(text: str, what: str, where: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"{where}: {what} '{text}' is not a number") from exc


def load_master(directory: Path, files: dict[str, str], fp: BankFingerprinter) -> Master:
    def table(name: str, required: list[str]) -> list[dict[str, str]]:
        path = directory / name
        header, rows = read_table(path.name, path.read_bytes())
        missing = [c for c in required if c not in header]
        if missing:
            raise ValueError(f"{name} has no column {', '.join(missing)}")
        return [{**r.values, "__row__": str(r.ref.row)} for r in rows]

    vendors: dict[str, Vendor] = {}
    for r in table(files["vendors"], ["vendor_id", "name", "aliases", "tax_id", "tax_rate", "bank_account", "routing_number", "status"]):
        acct = r["bank_account"].strip()
        vendors[r["vendor_id"]] = Vendor(
            id=r["vendor_id"], name=r["name"], aliases=[a.strip() for a in r["aliases"].split(";") if a.strip()],
            tax_id=r["tax_id"], tax_rate=_dec(r["tax_rate"], "tax_rate", f"vendors row {r['__row__']}") if r["tax_rate"].strip() else None,
            bank_fingerprint=fp.digest("account", acct) if acct else None,
            bank_masked=fp.mask(acct) if acct else None, status=r["status"] or "active",
            routing_fingerprint=fp.digest("routing", r["routing_number"]) if r["routing_number"].strip() else None)
    pos: dict[str, PurchaseOrder] = {}
    for r in table(files["purchase_orders"], ["po_number", "vendor_id", "status", "currency", "line_no", "item_code",
                                              "description", "quantity", "unit_price", "receipt_required"]):
        key = normalize_number(r["po_number"])
        po = pos.setdefault(key, PurchaseOrder(r["po_number"], r["vendor_id"], r["status"].lower(), r["currency"].upper()))
        where = f"purchase_orders row {r['__row__']}"
        po.lines[int(r["line_no"])] = POLine(int(r["line_no"]), r["item_code"], r["description"],
                                             _dec(r["quantity"], "quantity", where), _dec(r["unit_price"], "unit_price", where),
                                             r["receipt_required"].strip().lower() not in ("no", "false", "0", "n"))
    receipts = []
    for r in table(files["receipts"], ["receipt_id", "po_number", "line_no", "quantity_received", "received_date", "status"]):
        d = r["received_date"].strip()
        receipts.append(Receipt(r["receipt_id"], r["po_number"], int(r["line_no"]),
                                _dec(r["quantity_received"], "quantity_received", f"receipts row {r['__row__']}"),
                                date.fromisoformat(d) if d else None, (r["status"] or "accepted").lower()))
    return Master(vendors, pos, receipts)
