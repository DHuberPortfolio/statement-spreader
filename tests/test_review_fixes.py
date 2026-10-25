"""Regression tests for the independent red-team review of the platform (2026-10-24, afternoon).

Each test reproduces a finding the reviewer demonstrated against the earlier code; the finding number is
in the test name. They fail on that code and pass on the fix.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from finops.core.audit import Database
from finops.core.config import load_config
from finops.core.exceptions import is_person, same_person
from finops.core.tabular import TableError, read_table
from finops.invoice.config import APPolicy
from finops.invoice.controls import duplicates
from finops.invoice.engine import process
from finops.invoice.extract import BANK_ANYWHERE, _label_patterns, _match_label
from finops.invoice.master import BankFingerprinter, Vendor, load_master, mask_digits
from finops.invoice.matching import History
from finops.invoice.model import Evidence, FieldValue, Invoice, InvoiceLine, Origin
from finops.invoice.service import ActionError, InvoiceService
from finops.invoice.validate import validate
from finops.recon.config import ReconProfile
from finops.recon.engine import Decisions, reconcile
from finops.recon.model import MatchStatus
from finops.recon.service import ReconService

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "eval" / "invoice" / "dev"
POLICY = ROOT / "config" / "finops" / "invoice" / "default-ap.yaml"
RECON = ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml"
FIX = ROOT / "tests" / "fixtures" / "invoices"
pytestmark = pytest.mark.skipif(not (DEV / "truth.json").exists(), reason="synthetic invoices not generated")


@pytest.fixture(scope="module")
def env():  # type: ignore[no-untyped-def]
    policy = load_config(APPolicy, POLICY)[0]
    fp = BankFingerprinter(b"k")
    return policy, load_master(DEV / "master", policy.master_data.model_dump(), fp), fp


def base_json() -> dict:
    truth = json.loads((DEV / "truth.json").read_text(encoding="utf-8"))
    d = next(x for x in truth["inbox"] if x["layout"] == "json")
    return json.loads((DEV / d["file"]).read_text(encoding="utf-8"))


def run(env, body: dict, history: History | None = None):  # type: ignore[no-untyped-def]
    policy, master, fp = env
    return process("x.json", json.dumps(body).encode(), policy, master, history or History(), fp)


def codes(o) -> set[str]:  # type: ignore[no-untyped-def]
    return {e.code for e in o.exceptions}


def fv(v):  # type: ignore[no-untyped-def]
    return FieldValue(value=v, origin=Origin.EXTRACTED, evidence=Evidence(text=str(v)))


def simple_invoice(**fields) -> Invoice:  # type: ignore[no-untyped-def]
    inv = Invoice(doc_id="d" * 64, file="x", format="json",
                  lines=[InvoiceLine(index=1, description=fv("Widget"), quantity=fv(Decimal("2")), unit_price=fv(Decimal("50.00")),
                                     amount=fv(Decimal("100.00")))])
    base = {"vendor_name": "V", "invoice_number": "A1", "invoice_date": "2026-03-03", "currency": "USD",
            "subtotal": Decimal("100.00"), "total": Decimal("100.00")}
    for k, v in {**base, **fields}.items():
        if v is not None:
            inv.fields[k] = fv(v)
    return inv


VENDOR = Vendor(id="V1", name="V", aliases=[], tax_id="", tax_rate=Decimal("0.0825"), bank_fingerprint=None, bank_masked=None,
                status="active")


# -- invoices ------------------------------------------------------------------------------------

def test_f1_a_line_without_unit_price_cannot_go_through(env) -> None:  # type: ignore[no-untyped-def]
    body = base_json()
    body["lines"][0].pop("unit_price")
    body["lines"][0]["amount"] = str(Decimal(body["lines"][0]["amount"]) * 10)
    o = run(env, body)
    assert "LINE_INCOMPLETE" in codes(o) and not o.touchless and o.eligibility == "blocked"
    for bad in ("NaN", "9E+999999", "ten"):
        body = base_json()
        body["lines"][0]["quantity"] = bad
        o = run(env, body)
        assert "LINE_INCOMPLETE" in codes(o) and not o.touchless


def test_f2_printed_tax_rate_cannot_override_the_vendor_master(env) -> None:  # type: ignore[no-untyped-def]
    policy = env[0]
    inv = simple_invoice(tax=Decimal("0.25"), tax_rate=Decimal("0.0025"), total=Decimal("100.25"))
    out, _ = validate(inv, policy, VENDOR)
    assert {"TAX_RATE_MISMATCH", "TAX_MISMATCH"} <= {e.code for e in out}  # and the tax is checked at 8.25%
    out, _ = validate(simple_invoice(tax=Decimal("50.00"), tax_rate=Decimal("0.5"), total=Decimal("150.00")), policy,
                      VENDOR.__class__(**{**VENDOR.__dict__, "tax_rate": None}))
    assert "TAX_UNVERIFIED" in {e.code for e in out}  # a rate nobody trusted is only the vendor's claim


def test_f3_header_freight_and_negative_discount_are_checked(env) -> None:  # type: ignore[no-untyped-def]
    policy = env[0]
    out, _ = validate(simple_invoice(freight=Decimal("500"), total=Decimal("600.00")), policy, None)
    assert "FREIGHT_NOT_ON_PO" in {e.code for e in out}
    out, _ = validate(simple_invoice(discount=Decimal("-500"), total=Decimal("600.00")), policy, None)
    assert "NEGATIVE_DISCOUNT" in {e.code for e in out}


@pytest.fixture()
def svc(tmp_path: Path) -> InvoiceService:
    return InvoiceService(Database(tmp_path / "f.sqlite3"), tmp_path / "files", POLICY, DEV / "master", tmp_path / "key")


def test_f4_a_held_invoice_reserves_its_quantity(svc: InvoiceService) -> None:
    a = base_json()
    a["freight"] = "10.00"
    a["total"] = str(Decimal(a["total"]) + 10)
    ra = svc.upload("a.json", json.dumps(a).encode(), "dana")
    assert ra["outcome"]["eligibility"] == "needs_review"
    b = base_json()
    b["invoice_number"] = "B-" + str(b["invoice_number"])
    rb = svc.upload("b.json", json.dumps(b).encode(), "dana")
    assert {"QTY_EXCEEDS_RECEIVED", "QTY_EXCEEDS_ORDERED"} & {e["code"] for e in rb["outcome"]["exceptions"]}
    # rejecting A releases its quantity, and B is re-checked without anyone reprocessing it by hand
    e = next(x for x in ra["outcome"]["exceptions"] if x["code"] == "FREIGHT_NOT_ON_PO")
    r = svc.resolve(ra["document"]["doc_id"], e["id"], "rejected", "Duplicate of B with freight added.", "dana")
    assert r["outcome"]["eligibility"] == "rejected"
    later = svc.get(rb["document"]["doc_id"])["outcome"]
    assert not {"QTY_EXCEEDS_RECEIVED", "QTY_EXCEEDS_ORDERED"} & {x["code"] for x in later["exceptions"]}


def test_f5_more_bank_label_wordings_are_read() -> None:
    pats = _label_patterns(load_config(APPolicy, POLICY)[0])
    for text in ("Bank Account: 4402118890123", "Account: 4402118890123", "A/C No. 4402118890123",
                 "Beneficiary account 4402118890123"):
        hit = _match_label(text, pats)
        anywhere = BANK_ANYWHERE[0][1].search(text)
        assert (hit and hit[0] == "bank_account") or anywhere, text
    assert _match_label("Accounts Payable", pats) is None


def test_f6_f7_conflict_needs_another_person_and_rejection_sticks(svc: InvoiceService) -> None:
    r = svc.upload("two.pdf", (FIX / "two-accounts.pdf").read_bytes(), "alice")
    did = r["document"]["doc_id"]
    e = next(x for x in r["outcome"]["exceptions"] if x["code"] == "BANK_DETAILS_CONFLICT")
    with pytest.raises(ActionError):
        svc.resolve(did, e["id"], "explained", "fine.", "alice")
    with pytest.raises(ActionError, match="someone other"):
        svc.resolve(did, e["id"], "verified_independently", "Called the vendor on the master number today.", "Alice.")
    with pytest.raises(ActionError, match="Describe"):
        svc.resolve(did, e["id"], "verified_independently", "x" * 20, "lee")
    r2 = svc.resolve(did, e["id"], "rejected", "Two accounts printed; refused.", "alice")
    assert r2["outcome"]["eligibility"] == "rejected" and not r2["outcome"]["touchless"]


def test_f8_account_numbers_are_masked_wherever_they_appear(env, svc: InvoiceService) -> None:  # type: ignore[no-untyped-def]
    assert mask_digits("Account 9999-8888-7777") == "Account ****7777"
    body = base_json()
    body["terms"] = "Net 30, pay to Account No: 4402118890123"
    o = run(env, body)
    assert "4402118890123" not in o.model_dump_json()
    r = svc.upload("t.json", json.dumps(body).encode(), "dana")
    svc.correct(r["document"]["doc_id"], "terms", "Net 30", "As printed, without the bank text.", "dana")
    assert "4402118890123" not in json.dumps(svc.events(r["document"]["doc_id"]))


def test_f9_duplicate_totals_compare_as_numbers(env) -> None:  # type: ignore[no-untyped-def]
    policy = env[0]
    inv = simple_invoice(invoice_number="NEW-2", total=Decimal("604.20"))
    h = History(invoices=[{"doc_id": "x", "vendor_id": "V1", "number": "OLD1", "number_raw": "OLD-1", "total": "604.2",
                           "date": "2026-03-02", "po": None, "lines": [], "counted": True}])
    found, _ = duplicates(inv, "V1", h, policy)
    assert [e.code for e in found] == ["POSSIBLE_DUPLICATE"]


def test_f10_a_change_to_an_earlier_invoice_rechecks_later_ones(svc: InvoiceService) -> None:
    p = base_json()
    q = base_json()
    q["invoice_number"] = "Q-77"
    q["invoice_date"] = "2026-05-20"
    for ln in q["lines"]:
        ln["quantity"] = "1"
        ln["amount"] = ln["unit_price"]
    q["subtotal"] = str(sum(Decimal(ln["amount"]) for ln in q["lines"]))
    q["tax"] = None
    q["total"] = q["subtotal"]
    rp = svc.upload("p.json", json.dumps(p).encode(), "dana")
    rq = svc.upload("q.json", json.dumps(q).encode(), "dana")
    assert not {"POSSIBLE_DUPLICATE", "EXACT_DUPLICATE"} & {e["code"] for e in rq["outcome"]["exceptions"]}
    svc.correct(rp["document"]["doc_id"], "invoice_number", "Q-77", "As printed on the original.", "dana")
    later = svc.get(rq["document"]["doc_id"])["outcome"]
    assert {"POSSIBLE_DUPLICATE", "EXACT_DUPLICATE"} & {e["code"] for e in later["exceptions"]}


def test_f11_malformed_input_is_refused_cleanly(svc: InvoiceService) -> None:
    for body in ({**base_json(), "invoice_number": {"a": 1}}, {**base_json(), "vendor": "just a name"}):
        with pytest.raises(ActionError):
            svc.upload("bad.json", json.dumps(body).encode(), "dana")
    with pytest.raises(ActionError):
        svc.upload("deep.json", b"[" * 100_000, "dana")
    assert svc.inbox() == []  # nothing half-registered
    r = svc.upload("ok.json", json.dumps(base_json()).encode(), "dana")
    for bad in ("NaN", "sNaN", "Infinity", "1e400"):
        with pytest.raises(ActionError):
            svc.correct(r["document"]["doc_id"], "total", bad, "From the document.", "dana")
    with pytest.raises(TableError):
        read_table("x.csv", b'a,b\n"' + b"x" * 200_000 + b'",1\n')


def test_f17_named_people_only() -> None:
    for name in ("System.", "AI assistant", "Claude Code", "local_user", "local-user", "gpt-4o", "", "  ", "x"):
        assert not is_person(name), name
    assert is_person("Dana Smith") and is_person("lee")
    assert same_person("alice.", " Alice ") and not same_person("alice", "alicia")


# -- reconciliation ------------------------------------------------------------------------------

BANK = "Transaction ID,Posted Date,Description,Reference,Withdrawals,Deposits,Currency\n"
GL = "Entry No,Date,Memo,Ref,Counterparty,Debit,Credit,Currency\n"


def rec(b: str, g: str, profile: ReconProfile | None = None, decisions: Decisions | None = None):  # type: ignore[no-untyped-def]
    p, v = (profile, "t") if profile else load_config(ReconProfile, RECON)
    return reconcile("b.csv", (BANK + b).encode(), "g.csv", (GL + g).encode(), p, v, decisions)


def test_f12_currency_in_the_amount_cell_is_honoured() -> None:
    res = rec("B1,03/05/2026,X,,,EUR 7829.48,\n", "J1,2026-03-05,X,,P,7829.48,,USD\n")
    assert res.records["bank:B1"].currency == "EUR" and not any(g.status is MatchStatus.AUTO for g in res.groups)
    res = rec("B1,03/05/2026,X,,,EUR 7829.48,USD\n", "J1,2026-03-05,X,,P,7829.48,,USD\n")
    assert "bank:B1" not in res.records and any(e.code == "INVALID_RECORD" for e in res.exceptions)


def test_f13_a_negative_deposit_is_not_silently_flipped() -> None:
    res = rec("B1,03/05/2026,RETURNED,,,-3437.96,USD\n", "J1,2026-03-05,X,,P,3437.96,,USD\n")
    assert "bank:B1" not in res.records and res.groups == []
    p, _ = load_config(ReconProfile, RECON)
    rev = p.model_copy(update={"left": p.left.model_copy(update={"negative_in_columns": "reverse"})})
    res = rec("B1,03/05/2026,RETURNED,,,-3437.96,USD\n", "J1,2026-03-05,X,,P,3437.96,,USD\n", rev)
    assert res.records["bank:B1"].amount == Decimal("-3437.96") and res.groups == []


def test_f14_contradicting_names_are_not_matched_automatically() -> None:
    res = rec("B1,03/10/2026,ACH CREDIT ACME,,,1000.00,USD\nB2,03/12/2026,ACH CREDIT BETA,,,1000.00,USD\n",
              "J1,2026-03-10,Customer receipt,,Beta Corp,1000.00,,USD\nJ2,2026-03-12,Customer receipt,,Acme Inc,1000.00,,USD\n")
    for g in res.groups:
        if g.status is MatchStatus.AUTO:
            names = {res.records[m].description.split()[-1].upper() for m in g.left} | \
                    {res.records[m].counterparty.split()[0].upper() for m in g.right}
            assert len(names) == 1, g  # an automatic pair names one party
    res = rec("B1,03/10/2026,ACH CREDIT ACME,,,1000.00,USD\n", "J1,2026-03-10,Customer receipt,,Zeta Holdings,1000.00,,USD\n")
    assert res.groups[0].status is MatchStatus.PROPOSED and any(e.code == "NAME_MISMATCH" for e in res.exceptions)


def test_f15_rejecting_one_candidate_does_not_make_the_other_certain() -> None:
    b = "B1,03/10/2026,DEPOSIT,,,500.00,USD\n"
    g = "J1,2026-03-09,Receipt,,P,500.00,,USD\nJ2,2026-03-08,Receipt,,Q,500.00,,USD\n"
    first = rec(b, g)
    prop = first.groups[0]
    d = Decisions(rejected=[{"members": prop.left + prop.right,
                             "hashes": {m: first.records[m].content_hash for m in prop.left + prop.right}}])
    again = rec(b, g, decisions=d)
    assert again.groups and all(x.status is MatchStatus.PROPOSED for x in again.groups)


def test_f16_each_invalidated_decision_is_its_own_exception() -> None:
    d = Decisions(accepted=[
        {"decision_id": 1, "left": ["bank:GONE1"], "right": ["ledger:GONE2"], "hashes": {}, "actor": "erin", "note": "", "kind": "manual"},
        {"decision_id": 2, "left": ["bank:GONE3"], "right": ["ledger:GONE4"], "hashes": {}, "actor": "frank", "note": "", "kind": "manual"}])
    res = rec("B1,03/10/2026,X,,,1.00,USD\n", "J1,2026-03-10,X,,P,2.00,,USD\n", decisions=d)
    inv = [e for e in res.exceptions if e.code == "DECISION_INVALIDATED"]
    assert len(inv) == 2 and len({e.id for e in inv}) == 2


def test_f17_amount_differences_beyond_a_cent_are_found() -> None:
    res = rec("B1,03/10/2026,WIRE IN NORTHWIND TRADERS,,,990.00,USD\n",
              "J1,2026-03-09,Customer receipt - Northwind Traders,,Northwind Traders,1000.00,,USD\n")
    assert [(g.rule, g.status) for g in res.groups] == [("amount_difference", MatchStatus.PROPOSED)]


def test_f17_older_files_again_give_a_run_that_can_be_decided_on(tmp_path: Path) -> None:
    svc = ReconService(Database(tmp_path / "r.sqlite3"), tmp_path / "files", RECON.parent)
    wid = svc.create_workspace("t", "bank-vs-gl.yaml", "dana")
    a = ("b.csv", (BANK + "B1,03/10/2026,X,,,1.00,USD\n").encode())
    b = ("b.csv", (BANK + "B1,03/10/2026,X,,,2.00,USD\n").encode())
    g = ("g.csv", (GL + "J1,2026-03-10,X,,P,1.00,,USD\n").encode())
    svc.run(wid, "dana", a, g)
    svc.run(wid, "dana", b, g)
    back = svc.run(wid, "dana", a, g)
    assert back["run"]["is_latest"] and back["run"]["error"] is None


def test_hypothesis_two_decisions_at_once_on_one_run_cannot_both_land(tmp_path: Path) -> None:
    svc = ReconService(Database(tmp_path / "r.sqlite3"), tmp_path / "files", RECON.parent)
    wid = svc.create_workspace("t", "bank-vs-gl.yaml", "dana")
    from finops.recon.service import ActionError as ReconActionError

    r = svc.run(wid, "dana", ("b.csv", (BANK + "B1,03/10/2026,DEPOSIT,,,500.00,USD\n").encode()),
                ("g.csv", (GL + "J1,2026-03-09,R,,P,500.00,,USD\nJ2,2026-03-08,R,,Q,500.00,,USD\n").encode()))
    rid, prop = r["run"]["id"], next(g for g in r["result"]["groups"] if g["status"] == "proposed")
    real_run = svc.run
    svc.run = lambda *a, **k: {}  # type: ignore[method-assign]  # the first request has not produced its new run yet
    svc.accept(rid, prop["id"], "dana")
    with pytest.raises(ReconActionError, match="out of date"):
        svc.reject(rid, prop["id"], "lee")
    svc.run = real_run  # type: ignore[method-assign]


def test_hypothesis_a_credit_note_cannot_free_up_po_quantity() -> None:
    h = History(invoices=[{"doc_id": "cn", "vendor_id": "V1", "number": "CN1", "number_raw": "CN-1", "total": "-400",
                           "date": "2026-03-02", "po": "PO-1", "lines": [("PO-1", 1, "-8")], "counted": True},
                          {"doc_id": "a", "vendor_id": "V1", "number": "A1", "number_raw": "A-1", "total": "400",
                           "date": "2026-03-01", "po": "PO-1", "lines": [("PO-1", 1, "8")], "counted": True}])
    assert h.invoiced("PO-1", 1, "new") == Decimal("8")
