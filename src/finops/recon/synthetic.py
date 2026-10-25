"""Synthetic bank-vs-ledger pairs with known answers and deliberately injected problems.

The generator decides what is true (which records belong together, which have no counterpart,
which exception each problem should raise) while it writes the files. The answer key is
therefore independent of the matcher: nothing in it is computed by the code being graded.

Scenario kinds (per 100 "scale"):
  ref_1to1         same reference both sides, formatted differently (INV-000123 vs 123)   auto
  noref_1to1       no reference, unique amount, 0-4 days apart                            auto
  late_clearing    same reference, the bank clears 10-30 days later                       auto
  batch_ref        one deposit = 2-4 ledger receipts, all with the deposit reference     auto
  split_ref        2-3 bank settlements = one ledger entry, same reference                auto
  batch_noref      one deposit = 2-3 receipts, nothing ties them but the sum              review
  fee_deducted     bank received the ledger amount less a fee, same reference             review + AMOUNT_DIFFERENCE
  keying_error     same reference, digits transposed on one side                          review + AMOUNT_DIFFERENCE
  duplicate_ledger the ledger posted the same receipt twice                               review + POSSIBLE_DUPLICATE
  ambiguous_twins  one bank line, two ledger lines with its amount and no reference      review + AMBIGUOUS_CANDIDATES
  near_miss_ref    a reference match plus a same-amount decoy dated closer                auto (decoy UNMATCHED)
  reversal         a deposit returned by the bank; the ledger has only the receipt         auto + REVERSAL
  bank_fee         a bank charge with no ledger entry                                     UNRECORDED_FEE
  outstanding      a ledger payment in the last days of the period                        TIMING_DIFFERENCE
  missing_ledger   a bank line with no ledger entry                                       UNMATCHED
  missing_bank     a ledger entry with no bank line, mid-period                           UNMATCHED
  noref_late       the same payment, no reference, 7-9 days apart (outside the window)    review (a known miss)
  currency_mismatch same reference and number, EUR on one side, USD on the other          CURRENCY_MISMATCH
  coincidental_sum a deposit with no ledger entry that equals the sum of two unrelated
                   receipts                                                               nothing may be auto-matched
  partial_payment  the ledger expects the full receipt, the bank received 30-70% of it,
                   same reference                                                         review + PARTIAL_MATCH
"""

from __future__ import annotations

import csv
import io
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

MIX = {"ref_1to1": 34, "noref_1to1": 20, "late_clearing": 3, "batch_ref": 5, "split_ref": 3, "batch_noref": 3,
       "fee_deducted": 4, "keying_error": 2, "duplicate_ledger": 3, "ambiguous_twins": 3, "near_miss_ref": 3,
       "reversal": 3, "bank_fee": 3, "outstanding": 4, "missing_ledger": 2, "missing_bank": 2, "noref_late": 2,
       "currency_mismatch": 1, "coincidental_sum": 2, "partial_payment": 2}

PARTIES = ["Northwind Traders", "Contoso Supply", "Fabrikam Tools", "Tailspin Freight", "Adventure Works",
           "Wide World Importers", "Litware Labs", "Proseware Inc", "Lucerne Publishing", "Margie Travel",
           "Fourth Coffee", "Coho Vineyard", "Alpine Ski House", "Blue Yonder Air", "Trey Research",
           "Woodgrove Services", "Humongous Insurance", "Datum Corp", "Graphic Design Inst", "Southridge Video"]

BANK_COLS = ["Transaction ID", "Posted Date", "Description", "Reference", "Withdrawals", "Deposits", "Currency"]
GL_COLS = ["Entry No", "Date", "Memo", "Ref", "Counterparty", "Debit", "Credit", "Currency"]


# Messy mode only: what real bank exports do to the same transactions.
MESSY_MIX = {"payroll_burst": 3, "ref_typo": 3}
PAYEES = ["Ana Lopez", "Ben Carter", "Chloe Kim", "Dev Patel", "Eli Novak", "Fatima Khan", "Gus Moreau", "Hana Sato"]

ROUND_AMOUNTS = [100, 150, 200, 250, 300, 500, 750, 1000, 1200, 1500, 2000, 2500, 5000]


class _Gen:
    def __init__(self, seed: int, start: date, end: date, round_share: float = 0.0, messy: bool = False):
        self.round_share = round_share
        self.messy = messy
        self.r = random.Random(seed)
        self.start, self.end = start, end
        self.bank: list[dict[str, str]] = []
        self.gl: list[dict[str, str]] = []
        self.groups: list[dict[str, Any]] = []
        self.exceptions: list[dict[str, Any]] = []
        self.no_counterpart: list[dict[str, str]] = []
        self.amounts: set[Decimal] = set()
        self.nb = 0
        self.ng = 0
        self.nref = 1000

    def amount(self, lo: int = 50, hi: int = 25000) -> Decimal:
        if self.round_share and self.r.random() < self.round_share:
            # Real books repeat round amounts (rent, retainers, subscriptions): collisions on purpose.
            fits = [a for a in ROUND_AMOUNTS if lo <= a <= hi] or [lo]
            return Decimal(self.r.choice(fits))
        while True:
            a = Decimal(self.r.randint(lo * 100, hi * 100)) / 100
            if a not in self.amounts:
                self.amounts.add(a)
                return a

    def day(self, lo: int = 1, hi: int | None = None) -> date:
        last = (self.end - self.start).days
        return self.start + timedelta(days=self.r.randint(lo - 1, min(hi or last + 1, last + 1) - 1))

    def ref(self, prefix: str) -> tuple[str, str]:
        self.nref += 1
        n = self.nref
        styles = [(f"{prefix}-{n:06d}", f"{n}"), (f"{prefix}{n}", f"{prefix}-{n}"), (f"{prefix} {n}", f"{prefix} {n:07d}")]
        return self.r.choice(styles)

    def garble(self, desc: str, ref: str) -> tuple[str, str]:
        """Messy mode: banks truncate, abbreviate and pad descriptions, and drop or mistype references."""
        x = self.r.random()
        if x < 0.12:
            desc = desc[:18]
        elif x < 0.24:
            words = desc.split()
            desc = " ".join(w if len(w) <= 4 else w[0] + "".join(c for c in w[1:] if c not in "AEIOU") for w in words)
        elif x < 0.36:
            desc = f"{desc} PPD ID {self.r.randint(10**9, 10**10 - 1)}"
        elif x < 0.42:
            desc = desc.lower()
        if ref and self.r.random() < 0.12:
            ref = ""
        return desc, ref

    def b(self, d: date, amt: Decimal, desc: str, ref: str = "", cur: str = "USD") -> str:
        if self.messy:
            desc, ref = self.garble(desc, ref)
        self.nb += 1
        tid = f"BK-{self.nb:05d}"
        self.bank.append({"Transaction ID": tid, "Posted Date": d.strftime("%m/%d/%Y"), "Description": desc, "Reference": ref,
                          "Withdrawals": f"{-amt:,.2f}" if amt < 0 else "", "Deposits": f"{amt:,.2f}" if amt > 0 else "",
                          "Currency": cur})
        return f"bank:{tid}"

    def g(self, d: date, amt: Decimal, memo: str, party: str, ref: str = "", cur: str = "USD") -> str:
        self.ng += 1
        eid = f"JE-{10000 + self.ng}"
        self.gl.append({"Entry No": eid, "Date": d.isoformat(), "Memo": memo, "Ref": ref, "Counterparty": party,
                        "Debit": f"{amt:.2f}" if amt > 0 else "", "Credit": f"{-amt:.2f}" if amt < 0 else "",
                        "Currency": cur})
        return f"ledger:{eid}"

    def pair_text(self, inflow: bool) -> tuple[str, str, str]:
        p = self.r.choice(PARTIES)
        if inflow:
            return f"ACH CREDIT {p.upper()}", f"Customer receipt - {p}", p
        return f"ACH DEBIT {p.upper()}", f"Vendor payment - {p}", p

    def group(self, kind: str, left: list[str], right: list[str], expect: str, alt: list[list[str]] | None = None) -> None:
        self.groups.append({"kind": kind, "left": sorted(left), "right": sorted(right), "expect": expect,
                            "alternatives": [sorted(a) for a in (alt or [])]})

    def exc(self, kind: str, code: str, any_of: list[str], also: list[str] | None = None) -> None:
        """`also`: other reason codes that are an equally right answer for this problem."""
        self.exceptions.append({"kind": kind, "code": code, "codes": [code] + (also or []), "any_of": sorted(any_of)})

    def alone(self, kind: str, rid: str) -> None:
        self.no_counterpart.append({"kind": kind, "id": rid})

    # -- scenarios -----------------------------------------------------------------------------

    def ref_1to1(self, gap_lo: int = 0, gap_hi: int = 3, kind: str = "ref_1to1") -> None:
        inflow = self.r.random() < 0.5
        amt = self.amount() * (1 if inflow else -1)
        d_gl = self.day(1, 24 if gap_hi <= 3 else 8)
        d_bank = min(d_gl + timedelta(days=self.r.randint(gap_lo, gap_hi)), self.end)
        bref, gref = self.ref("INV" if inflow else "CHK")
        bdesc, memo, party = self.pair_text(inflow)
        self.group(kind, [self.b(d_bank, amt, bdesc, bref)], [self.g(d_gl, amt, memo, party, gref)], "auto")

    def late_clearing(self) -> None:
        self.ref_1to1(10, 20, "late_clearing")

    def noref_1to1(self) -> None:
        inflow = self.r.random() < 0.5
        amt = self.amount() * (1 if inflow else -1)
        d_gl = self.day(1, 24)
        d_bank = d_gl + timedelta(days=self.r.randint(0, 4))
        bdesc, memo, party = self.pair_text(inflow)
        self.group("noref_1to1", [self.b(d_bank, amt, bdesc)], [self.g(d_gl, amt, memo, party)], "auto")

    def batch(self, with_ref: bool) -> None:
        k = self.r.randint(2, 4 if with_ref else 3)
        parts = [self.amount(100, 4000) for _ in range(k)]
        d_bank = self.day(4, 25)
        ref = f"DEP-{self.r.randint(10000, 99999)}" if with_ref else ""
        right = []
        for a in parts:
            p = self.r.choice(PARTIES)
            right.append(self.g(d_bank - timedelta(days=self.r.randint(0, 2)), a, f"Customer receipt - {p}", p, ref))
        total = sum(parts, Decimal(0))
        self.amounts.add(total)
        left = [self.b(d_bank, total, "BRANCH DEPOSIT" if with_ref else "DEPOSIT", ref)]
        self.group("batch_ref" if with_ref else "batch_noref", left, right, "auto" if with_ref else "review")

    def split_ref(self) -> None:
        k = self.r.randint(2, 3)
        parts = [self.amount(200, 6000) for _ in range(k)]
        d = self.day(2, 22)
        ref = f"STL-{self.r.randint(10000, 99999)}"
        left = [self.b(d + timedelta(days=i), a, "CARD SETTLEMENT", ref) for i, a in enumerate(parts)]
        total = sum(parts, Decimal(0))
        self.amounts.add(total)
        right = [self.g(d, total, "Card sales settlement", "Card processor", ref)]
        self.group("split_ref", left, right, "auto")

    def fee_deducted(self) -> None:
        amt = self.amount(1000, 20000)
        fee = Decimal(self.r.choice([15, 20, 25, 30, 35]))
        d_gl = self.day(1, 22)
        bref, gref = self.ref("INV")
        p = self.r.choice(PARTIES)
        bk = self.b(d_gl + timedelta(days=self.r.randint(1, 3)), amt - fee, f"WIRE IN {p.upper()}", bref)
        r = self.g(d_gl, amt, f"Customer receipt - {p}", p, gref)
        self.group("fee_deducted", [bk], [r], "review")
        self.exc("fee_deducted", "AMOUNT_DIFFERENCE", [bk, r])

    def keying_error(self) -> None:
        while True:
            amt = self.amount(1000, 9999)
            s = f"{amt:.2f}"
            i = self.r.randint(0, 2)
            swapped = Decimal(s[:i] + s[i + 1] + s[i] + s[i + 2:])
            if swapped != amt and abs(swapped - amt) <= Decimal("50") and abs(swapped - amt) <= amt * Decimal("0.05"):
                break
        d = self.day(1, 22)
        bref, gref = self.ref("INV")
        bdesc, memo, party = self.pair_text(True)
        bk = self.b(d + timedelta(days=1), amt, bdesc, bref)
        r = self.g(d, swapped, memo, party, gref)
        self.group("keying_error", [bk], [r], "review")
        self.exc("keying_error", "AMOUNT_DIFFERENCE", [bk, r])

    def duplicate_ledger(self) -> None:
        amt = self.amount(100, 5000)
        d = self.day(1, 22)
        p = self.r.choice(PARTIES)
        ref = f"INV-{self.r.randint(100000, 999999)}"
        bk = self.b(d + timedelta(days=1), amt, f"ACH CREDIT {p.upper()}", ref)
        x = self.g(d, amt, f"Customer receipt - {p}", p, ref)
        y = self.g(d, amt, f"Customer receipt - {p}", p, ref)
        self.group("duplicate_ledger", [bk], [x], "review", alt=[[y]])
        self.exc("duplicate_ledger", "POSSIBLE_DUPLICATE", [x, y])

    def ambiguous_twins(self) -> None:
        amt = self.amount(100, 3000)
        d = self.day(4, 22)
        bk = self.b(d, amt, "DEPOSIT")
        x = self.g(d - timedelta(days=1), amt, "Customer receipt", self.r.choice(PARTIES))
        y = self.g(d - timedelta(days=2), amt, "Customer receipt", self.r.choice(PARTIES))
        self.group("ambiguous_twins", [bk], [x], "review", alt=[[y]])
        self.exc("ambiguous_twins", "AMBIGUOUS_CANDIDATES", [bk])

    def near_miss_ref(self) -> None:
        amt = self.amount(200, 8000)
        d = self.day(5, 22)
        bref, gref = self.ref("INV")
        p, q = self.r.sample(PARTIES, 2)
        bk = self.b(d, amt, f"ACH CREDIT {p.upper()}", bref)
        x = self.g(d - timedelta(days=3), amt, f"Customer receipt - {p}", p, gref)
        y = self.g(d, amt, f"Customer receipt - {q}", q)
        self.group("near_miss_ref", [bk], [x], "auto")
        self.alone("near_miss_ref", y)
        self.exc("near_miss_ref", "UNMATCHED", [y])

    def reversal(self) -> None:
        amt = self.amount(200, 5000)
        d = self.day(1, 18)
        p = self.r.choice(PARTIES)
        ref = f"CK-{self.r.randint(10000, 99999)}"
        bk = self.b(d, amt, f"MOBILE DEPOSIT {p.upper()}", ref)
        r = self.g(d, amt, f"Customer receipt - {p}", p, ref)
        back = self.b(d + timedelta(days=self.r.randint(2, 6)), -amt, "RETURNED ITEM NSF", ref)
        self.group("reversal", [bk], [r], "auto")
        self.alone("reversal", back)
        self.exc("reversal", "REVERSAL", [back])

    def bank_fee(self) -> None:
        desc = self.r.choice(["MONTHLY SERVICE FEE", "WIRE FEE", "ACCOUNT MAINTENANCE FEE", "OVERDRAFT CHARGE"])
        bk = self.b(self.day(1, 30), -Decimal(self.r.choice([12, 15, 25, 30, 45])) - Decimal(self.r.randint(0, 99)) / 100, desc)
        self.alone("bank_fee", bk)
        self.exc("bank_fee", "UNRECORDED_FEE", [bk])

    def outstanding(self) -> None:
        last = (self.end - self.start).days + 1
        bdesc, memo, party = self.pair_text(False)
        _, gref = self.ref("CHK")
        r = self.g(self.day(last - 2, last), -self.amount(), memo, party, gref)
        self.alone("outstanding", r)
        self.exc("outstanding", "TIMING_DIFFERENCE", [r])

    def missing_ledger(self) -> None:
        bdesc, _, _ = self.pair_text(self.r.random() < 0.5)
        bk = self.b(self.day(2, 24), self.amount() * (1 if "CREDIT" in bdesc else -1), bdesc)
        self.alone("missing_ledger", bk)
        self.exc("missing_ledger", "UNMATCHED", [bk])

    def missing_bank(self) -> None:
        inflow = self.r.random() < 0.5
        _, memo, party = self.pair_text(inflow)
        r = self.g(self.day(2, 20), self.amount() * (1 if inflow else -1), memo, party)
        self.alone("missing_bank", r)
        self.exc("missing_bank", "UNMATCHED", [r])

    def noref_late(self) -> None:
        inflow = self.r.random() < 0.5
        amt = self.amount() * (1 if inflow else -1)
        d = self.day(1, 15)
        bdesc, memo, party = self.pair_text(inflow)
        bk = self.b(d + timedelta(days=self.r.randint(7, 9)), amt, bdesc)
        r = self.g(d, amt, memo, party)
        self.group("noref_late", [bk], [r], "review")

    def currency_mismatch(self) -> None:
        amt = self.amount(500, 9000)
        d = self.day(1, 22)
        bref, gref = self.ref("INV")
        bdesc, memo, party = self.pair_text(True)
        bk = self.b(d + timedelta(days=1), amt, bdesc, bref, cur="EUR")
        r = self.g(d, amt, memo, party, gref, cur="USD")
        self.alone("currency_mismatch", bk)
        self.alone("currency_mismatch", r)
        self.exc("currency_mismatch", "CURRENCY_MISMATCH", [bk, r])

    def coincidental_sum(self) -> None:
        a, b = self.amount(300, 3000), self.amount(300, 3000)
        d = self.day(5, 20)
        bk = self.b(d, a + b, "DEPOSIT")
        self.amounts.add(a + b)
        x = self.g(d - timedelta(days=1), a, "Customer receipt", self.r.choice(PARTIES))
        y = self.g(d - timedelta(days=2), b, "Customer receipt", self.r.choice(PARTIES))
        for rid in (bk, x, y):
            self.alone("coincidental_sum", rid)
        # The point of this case is that nothing is auto-matched: leaving the deposit unmatched,
        # or proposing the coincidental sum with its "a sum can match by coincidence" warning,
        # both put it in front of a person.
        self.exc("coincidental_sum", "UNMATCHED", [bk], also=["PROPOSED_GROUP", "AMBIGUOUS_CANDIDATES"])

    def payroll_burst(self) -> None:
        """Several payments of the same round amount on the same day to different people: only names tell them apart."""
        amt = -Decimal(self.r.choice([1250, 1500, 2000, 2400]))
        d = self.day(5, 22)
        for payee in self.r.sample(PAYEES, self.r.randint(3, 5)):
            bk = self.b(d + timedelta(days=self.r.randint(0, 1)), amt, f"ACH DEBIT {payee.upper()} PAYROLL")
            r = self.g(d, amt, f"Payroll - {payee}", payee)
            self.group("payroll_burst", [bk], [r], "auto")

    def ref_typo(self) -> None:
        """The bank's copy of the reference has two digits swapped: no longer equal, so other evidence must carry it."""
        inflow = self.r.random() < 0.5
        amt = self.amount() * (1 if inflow else -1)
        d = self.day(1, 22)
        self.nref += 1
        n = f"{self.nref:06d}"
        typo = n[:-2] + n[-1] + n[-2] if n[-1] != n[-2] else n[:-1] + str((int(n[-1]) + 1) % 10)
        bdesc, memo, party = self.pair_text(inflow)
        self.group("ref_typo", [self.b(d + timedelta(days=1), amt, bdesc, f"INV-{typo}")],
                   [self.g(d, amt, memo, party, f"INV-{n}")], "auto")

    def partial_payment(self) -> None:
        amt = self.amount(2000, 20000)
        paid = (amt * Decimal(self.r.choice([30, 40, 50, 60, 70])) / 100).quantize(Decimal("0.01"))
        d = self.day(1, 20)
        bref, gref = self.ref("INV")
        bdesc, memo, party = self.pair_text(True)
        bk = self.b(d + timedelta(days=self.r.randint(1, 4)), paid, bdesc, bref)
        r = self.g(d, amt, memo, party, gref)
        self.group("partial_payment", [bk], [r], "review")
        self.exc("partial_payment", "PARTIAL_MATCH", [bk, r])


def _csv(cols: list[str], rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def generate(seed: int, scale: int = 100, start: date = date(2026, 3, 1), end: date = date(2026, 3, 31),
             round_share: float = 0.0, messy: bool = False) -> tuple[bytes, bytes, dict[str, Any]]:
    """Return (bank.csv, ledger.csv, truth). Rows are sorted by date, like real exports.

    round_share > 0 draws that share of amounts from a short list of round numbers, so equal
    amounts collide the way they do in real books (the stress set).
    """
    g = _Gen(seed, start, end, round_share, messy)
    mix = {**MIX, **MESSY_MIX} if messy else MIX
    plan = [k for k, n in mix.items() for _ in range(max(1, round(n * scale / 100)))]
    g.r.shuffle(plan)
    for kind in plan:
        getattr(g, kind)() if kind not in ("batch_ref", "batch_noref") else g.batch(kind == "batch_ref")
    g.bank.sort(key=lambda r: (r["Posted Date"][6:] + r["Posted Date"][:5], r["Transaction ID"]))
    g.gl.sort(key=lambda r: (r["Date"], r["Entry No"]))
    truth = {"seed": seed, "scale": scale, "round_share": round_share, "messy": messy, "period": [start.isoformat(), end.isoformat()], "mix": MIX,
             "groups": g.groups, "exceptions": g.exceptions, "no_counterpart": g.no_counterpart}
    return _csv(BANK_COLS, g.bank), _csv(GL_COLS, g.gl), truth


def write_case(directory: Path, seed: int, scale: int = 100) -> None:
    bank, gl, truth = generate(seed, scale)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bank.csv").write_bytes(bank)
    (directory / "ledger.csv").write_bytes(gl)
    (directory / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
