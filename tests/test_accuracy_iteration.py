"""Behaviour added in the accuracy iteration (2026-10-24, late afternoon): multi-seed and messy-data findings.

Reconciliation: amount and date alone never auto-match (a name or reference must agree); evidence that identifies one
partner settles mixed components; truncated and abbreviated bank names are recognised; late-clearing payments
are proposed. Invoices: label-looking values ("PO 4516") are read as values; overlapping column wording
("Item" as code or description) is disambiguated.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from finops.core.config import load_config
from finops.invoice.config import APPolicy
from finops.invoice.extract import _label_patterns, _value_like
from finops.recon.config import ReconProfile
from finops.recon.engine import reconcile
from finops.recon.matcher import names_agree
from finops.recon.model import MatchStatus

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml"
BANK = "Transaction ID,Posted Date,Description,Reference,Withdrawals,Deposits,Currency\n"
GL = "Entry No,Date,Memo,Ref,Counterparty,Debit,Credit,Currency\n"


def rec(b: str, g: str):  # type: ignore[no-untyped-def]
    p, v = load_config(ReconProfile, RECON)
    return reconcile("b.csv", (BANK + b).encode(), "g.csv", (GL + g).encode(), p, v)


def test_amount_and_date_alone_are_only_proposed() -> None:
    res = rec("B1,03/10/2026,CARD SETTLEMENT,,,2000.00,USD\n", "J1,2026-03-08,Customer receipt,,Northwind Traders,2000.00,,USD\n")
    (g,) = res.groups
    assert g.status is MatchStatus.PROPOSED and "Only the amount and date agree" in g.explanation[0]
    res = rec("B1,03/10/2026,ACH CREDIT NORTHWIND TRADERS,,,2000.00,USD\n",
              "J1,2026-03-08,Customer receipt,,Northwind Traders,2000.00,,USD\n")
    assert res.groups[0].status is MatchStatus.AUTO


@pytest.mark.parametrize("bank_name,ledger_name", [("FOU", "FOURTH COFFEE"), ("GUS MR", "GUS MOREAU"),
                                                   ("NRTHWND TRDRS", "NORTHWIND TRADERS"),
                                                   ("NORTHWIND TRADERS PPD ID", "NORTHWIND TRADERS")])
def test_bank_mangled_names_still_agree(bank_name: str, ledger_name: str) -> None:
    assert names_agree(bank_name, ledger_name)


def test_different_names_do_not_agree() -> None:
    assert not names_agree("ACME", "BETA CORP") and not names_agree("ZETA HOLDINGS", "ACME")


def test_payroll_burst_pairs_by_name_even_among_other_equal_amounts() -> None:
    names = ["Ana Lopez", "Ben Carter", "Chloe Kim"]
    b = "".join(f"B{i},03/10/2026,ACH DEBIT {n.upper()} PAYROLL,,1250.00,,USD\n" for i, n in enumerate(names)) + \
        "B9,03/11/2026,DEPOSIT,,,1250.00,USD\n"
    g = "".join(f"J{i},2026-03-10,Payroll - {n},,{n},,1250.00,USD\n" for i, n in enumerate(names)) + \
        "J9,2026-03-09,Customer receipt,,Contoso,1250.00,,USD\n"
    res = rec(b, g)
    auto = {tuple(x.left + x.right) for x in res.groups if x.status is MatchStatus.AUTO}
    assert auto == {(f"bank:B{i}", f"ledger:J{i}") for i in range(3)}
    assert all(x.status is MatchStatus.PROPOSED for x in res.groups if "bank:B9" in x.left)


def test_late_clearing_payment_without_reference_is_proposed() -> None:
    res = rec("B1,03/25/2026,ACH CREDIT LITWARE LABS,,,812.40,USD\n", "J1,2026-03-05,Customer receipt,,Litware Labs,812.40,,USD\n")
    (g,) = res.groups
    assert g.rule == "late_by_name" and g.status is MatchStatus.PROPOSED
    assert any(e.code == "LATE_MATCH" for e in res.exceptions)


def test_a_record_claimed_by_a_partial_reference_is_not_auto_matched_elsewhere() -> None:
    res = rec("B1,03/21/2026,ACH CREDIT PROSEWARE INC,INV-1156,,2000.00,USD\n",
              "J1,2026-03-19,Customer receipt,,Proseware Inc,2000.00,,USD\nJ2,2026-03-18,Customer receipt,INV-1156,Proseware Inc,4000.00,,USD\n")
    assert not any(x.status is MatchStatus.AUTO for x in res.groups)


def test_label_looking_values_are_values() -> None:
    pats = _label_patterns(load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "default-ap.yaml")[0])
    for text in ("PO 4516", "PO#4516", "P.O. 4516", "INV-007001", "4516"):
        assert _value_like(text, pats), text
    for text in ("PO Number:", "Date", "Purchase Order"):
        assert not _value_like(text, pats), text


MESSY = ROOT / "eval" / "invoice" / "messy-31"


@pytest.mark.skipif(not (MESSY / "truth.json").exists(), reason="messy invoice set not generated")
def test_messy_mixed_layout_set_reads_exactly_with_the_combined_wording() -> None:
    from finops.invoice.evaluate import evaluate_set

    r = evaluate_set(MESSY, load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "example-all-known-wording.yaml")[0])
    assert r["rates"]["false_touchless"].n == 0
    assert r["rates"]["header_fields"].value == 1.0 and r["rates"]["line_items"].value == 1.0
    truth = json.loads((MESSY / "truth.json").read_text(encoding="utf-8"))
    # the set really exercises 3-decimal prices (the case a generator bug once hid)
    assert any("." in ln["unit_price"] and len(ln["unit_price"].split(".")[1]) == 3 for d in truth["inbox"] for ln in d["lines"])
    assert all(Decimal(ln["quantity"]) > 0 for d in truth["inbox"] for ln in d["lines"])
