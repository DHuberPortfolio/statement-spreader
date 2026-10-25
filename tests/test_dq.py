"""The data-quality gate (finops.dq): mapping two schemas into one record, every check, the controls on people's
decisions, and what it changes for the invoice engine downstream."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

import pytest
from openpyxl import Workbook

from finops.core.audit import Database
from finops.core.config import load_config
from finops.core.tabular import TableError, read_table
from finops.dq.config import DatasetSpec
from finops.dq.engine import SourceInput, aba_ok, accepted_rows, gate
from finops.dq.evaluate import hostile_inputs, run_report
from finops.dq.service import ActionError, DQService, quarantine_rows
from finops.dq.synthetic import ERP_HEADER, PORTAL_HEADER, aba_check_digit, generate

ROOT = Path(__file__).resolve().parents[1]
VENDORS = load_config(DatasetSpec, ROOT / "config" / "finops" / "dq" / "vendors.yaml")[0]
POS = load_config(DatasetSpec, ROOT / "config" / "finops" / "dq" / "purchase_orders.yaml")[0]
ROUTING = "09522824" + aba_check_digit("09522824")
ROUTING2 = "04117243" + aba_check_digit("04117243")


def portal(*rows: dict[str, str]) -> bytes:
    base = {"Supplier ID": "V100", "Supplier Name": "Northwind Traders", "Also Known As": "", "EIN": "98-8013380",
            "Sales Tax %": "8.25", "Bank Acct": "560269953287", "ABA": ROUTING, "Status": "A", "Country": "USA",
            "Contact Email": "ap@northwind.example.com", "Terms (days)": "30", "Onboarded": "03/14/2024"}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=PORTAL_HEADER, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({**base, **r})
    return buf.getvalue().encode()


def erp(*rows: dict[str, object]) -> bytes:
    base = {"VENDOR_NO": "V100", "VENDOR_NAME": "Northwind Traders", "ALT_NAMES": "", "TAX_ID": "98-8013380", "VAT_RATE": "0.0825",
            "BANK_ACCOUNT": "560269953287", "ROUTING": ROUTING, "STAT": "ACTIVE", "CTRY": "US", "EMAIL": "ap@northwind.example.com",
            "CCY": "USD", "PAY_TERMS": "NET30", "CREATED": "14.03.2024"}
    wb = Workbook()
    ws = wb.active
    ws.append(ERP_HEADER)
    for r in rows:
        ws.append([{**base, **r}[h] for h in ERP_HEADER])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run(*inputs: tuple[str, bytes], **kw):  # type: ignore[no-untyped-def]
    return gate(VENDORS, [SourceInput(s, f"{s}.{'xlsx' if s == 'erp' else 'csv'}", d) for s, d in inputs], **kw)


def by_name(result, name: str):  # type: ignore[no-untyped-def]
    return next(r for r in result.records if r.canonical.get("name") == name)


# -- mapping two schemas -----------------------------------------------------------------------------------------------

def test_two_schemas_map_to_one_record_and_an_identical_copy_loads_once() -> None:
    res = run(("portal", portal({})), ("erp", erp({})))
    first, second = res.records
    assert first.decision == "accepted" and second.decision == "duplicate" and second.duplicate_of == first.id
    assert first.canonical["tax_rate"] == "0.0825" and first.canonical["payment_terms_days"] == "30"
    assert first.canonical["onboarded_date"] == "2024-03-14" and first.canonical["country"] == "US"
    assert first.canonical["status"] == "active" and first.canonical["currency"] == "USD"
    assert len(accepted_rows(res)) == 1
    # every change from the cell as read is on record
    steps = {(c.field, c.step) for c in first.changes}
    assert ("country", "code mapped by the Procurement portal export value map") in steps


def test_normalisation_is_recorded_and_harmless_variants_are_accepted() -> None:
    res = run(("portal", portal({"Supplier Name": "  Northwind   Traders ", "Status": " a ", "Country": " usa ", "EIN": "988013380",
                                 "Contact Email": "AP@Northwind.Example.com", "Sales Tax %": "8.25%"})))
    r = res.records[0]
    assert r.decision == "accepted", r.issues
    assert (r.canonical["name"], r.canonical["tax_id"], r.canonical["email"], r.canonical["tax_rate"]) == (
        "Northwind Traders", "98-8013380", "ap@northwind.example.com", "0.0825")


# -- field and record checks -----------------------------------------------------------------------------------------

@pytest.mark.parametrize(("edit", "code"), [
    ({"Supplier Name": ""}, "MISSING_REQUIRED"),
    ({"ABA": ROUTING[:8] + str((int(ROUTING[8]) + 1) % 10)}, "INVALID_ROUTING"),
    ({"EIN": "98-80133"}, "US_VENDOR_NEEDS_EIN"),
    ({"ABA": ""}, "US_BANK_NEEDS_ROUTING"),
    ({"Bank Acct": ""}, "ROUTING_NEEDS_ACCOUNT"),
    ({"Contact Email": "ap at northwind"}, "INVALID_EMAIL"),
    ({"Terms (days)": "-5"}, "OUT_OF_RANGE"),
    ({"Status": "Z"}, "INVALID_VALUE"),
    ({"Onboarded": "31/31/2024"}, "INVALID_DATE"),
    ({"Sales Tax %": "eight"}, "INVALID_NUMBER"),
    ({"Bank Acct": "12AB34"}, "INVALID_FORMAT"),
])
def test_definite_errors_are_rejected_with_their_reason(edit: dict[str, str], code: str) -> None:
    r = run(("portal", portal(edit))).records[0]
    assert r.decision == "rejected" and code in {i.code for i in r.issues}


def test_excel_scientific_notation_is_rejected_not_turned_into_other_digits() -> None:
    """Found by the independent test set: '6.70913E+11' used to lose its '.' and 'E' and pass as account 67091311."""
    portal_row = run(("portal", portal({"Bank Acct": "6.70913E+11"}))).records[0]
    erp_row = run(("erp", erp({"BANK_ACCOUNT": "6.70913E+11"}))).records[0]
    for r in (portal_row, erp_row):
        assert r.decision == "rejected" and "SCIENTIFIC_NOTATION" in {i.code for i in r.issues}
    spaced = run(("portal", portal({"Bank Acct": "5602 6995-3287"}))).records[0]
    assert spaced.decision == "accepted"  # separators are still removed


@pytest.mark.parametrize(("terms", "ok"), [("NET30", True), ("Net 30", True), ("NET 45 EOM", False), ("NET30 USD", False),
                                           ("30 days", False), ("1,000", False)])
def test_numbers_are_plain_numbers(terms: str, ok: bool) -> None:
    """Found by the second independent set: 'NET 45 EOM' was read as 45 (the money parser took EOM for a currency)."""
    r = run(("erp", erp({"PAY_TERMS": terms}))).records[0]
    assert (r.decision == "accepted") is ok, (terms, r.issues)  # 1,000 days is a number, out of range


def test_a_currency_symbol_in_a_number_column_is_refused() -> None:
    res = gate(POS, [SourceInput("erp", "po.csv", po_csv({"UNIT_PRICE": "$1,250.00"}, {"LINE": "2", "UNIT_PRICE": "1,250.00"},
                                                        {"LINE": "3", "UNIT_PRICE": "(5.00)"}))],
               references={"vendors": ("vendors.csv", VENDOR_REF)})
    d = [(r.decision, r.canonical["unit_price"]) for r in res.records]
    assert d[0] == ("rejected", "") and d[1] == ("accepted", "1250") and d[2][0] == "rejected"  # a negative price is out of range


def test_us_rules_do_not_apply_abroad_and_card_paid_vendors_need_no_bank() -> None:
    res = run(("portal", portal({"Supplier ID": "V200", "Country": "Canada", "EIN": "", "ABA": "", "Supplier Name": "Maple Freight"},
                                {"Supplier ID": "V201", "Bank Acct": "", "ABA": "", "Supplier Name": "Card Paid Labs", "EIN": "12-3456789"})))
    assert [r.decision for r in res.records] == ["accepted", "accepted"], [r.issues for r in res.records]


def test_suspicious_records_go_to_review() -> None:
    res = run(("portal", portal(
        {"Supplier ID": "V300", "Supplier Name": '=HYPERLINK("http://x","pay")', "EIN": "11-1111111", "Bank Acct": "111111111"},
        {"Supplier ID": "V301", "Supplier Name": "Active No Mail", "Contact Email": "", "EIN": "22-2222222", "Bank Acct": "222222222"},
    )))
    assert {i.code for i in res.records[0].issues} == {"FORMULA_LIKE_TEXT"} and res.records[0].decision == "review"
    assert res.records[1].decision == "review" and "ACTIVE_VENDOR_NEEDS_CONTACT" in {i.code for i in res.records[1].issues}


def test_ambiguous_date_is_held_not_guessed() -> None:
    spec = VENDORS.model_copy(deep=True)
    spec.sources["portal"].date_formats = ["%m/%d/%Y", "%d/%m/%Y"]
    res = gate(spec, [SourceInput("portal", "p.csv", portal({"Onboarded": "03/04/2024"}, {"Supplier ID": "V101", "Onboarded": "13/04/2024",
                                                                                        "EIN": "11-2223334", "Bank Acct": "999888777"}))])
    assert res.records[0].decision == "review" and "AMBIGUOUS_DATE" in {i.code for i in res.records[0].issues}
    assert res.records[1].canonical["onboarded_date"] == "2024-04-13"


# -- dataset checks --------------------------------------------------------------------------------------------------

def test_duplicates_are_flagged_never_merged_and_similar_names_with_different_tax_ids_are_two_companies() -> None:
    res = run(("portal", portal(
        {"Supplier ID": "V100"},
        {"Supplier ID": "V101", "Supplier Name": "Northwind Trading Co", "EIN": "98-8013380", "Bank Acct": "333333333"},  # same EIN
        {"Supplier ID": "V102", "Supplier Name": "Other Name", "EIN": "44-4444444", "Bank Acct": "560269953287"},  # same bank
        {"Supplier ID": "V103", "Supplier Name": "Contoso Supply", "EIN": "55-5555555", "Bank Acct": "555555555"},
        {"Supplier ID": "V104", "Supplier Name": "Contoso Supplies", "EIN": "66-6666666", "Bank Acct": "666666666"},
    )))
    codes = {r.canonical["vendor_id"]: {i.code for i in r.issues} for r in res.records}
    assert "SAME_TAX_ID" in codes["V100"] and "SAME_TAX_ID" in codes["V101"]
    assert "SHARED_BANK_ACCOUNT" in codes["V100"] and "SHARED_BANK_ACCOUNT" in codes["V102"]
    assert codes["V103"] == set() and codes["V104"] == set()  # similar names, different EINs: accepted
    assert len(res.records) == 5  # nothing merged


def test_foreign_vendors_sharing_an_account_are_held_but_two_banks_are_two_accounts() -> None:
    """Found by probing: the shared-account check needed a routing number, which most countries do not have."""
    res = run(("portal", portal(
        {"Supplier ID": "V500", "Country": "Canada", "EIN": "", "ABA": "", "Bank Acct": "12345678", "Supplier Name": "Maple A"},
        {"Supplier ID": "V501", "Country": "Canada", "EIN": "", "ABA": "", "Bank Acct": "12345678", "Supplier Name": "Spruce B"},
        {"Supplier ID": "V502", "EIN": "11-1111111", "Bank Acct": "999999999", "Supplier Name": "First Bank Co"},
        {"Supplier ID": "V503", "EIN": "22-2222222", "Bank Acct": "999999999", "ABA": ROUTING2, "Supplier Name": "Other Bank Co"},
    )))
    d = {r.canonical["vendor_id"]: {i.code for i in r.issues} for r in res.records}
    assert "SHARED_BANK_ACCOUNT" in d["V500"] and "SHARED_BANK_ACCOUNT" in d["V501"]
    assert d["V502"] == set() and d["V503"] == set()  # same digits at two different banks


def test_similar_names_without_a_distinguishing_tax_id_are_held() -> None:
    res = run(("portal", portal({"Supplier ID": "V400", "Supplier Name": "Harbor Metals", "Country": "United Kingdom", "EIN": "", "ABA": ""},
                                {"Supplier ID": "V401", "Supplier Name": "Harbor Metals Ltd", "Country": "United Kingdom", "EIN": "",
                                 "ABA": "", "Bank Acct": "77777777"})))
    assert all("SIMILAR_NAME" in {i.code for i in r.issues} for r in res.records)


def test_one_key_two_versions_holds_both() -> None:
    res = run(("portal", portal({})), ("erp", erp({"BANK_ACCOUNT": "999999999"})))
    assert [r.decision for r in res.records] == ["review", "review"]
    assert all("CONFLICTING_KEY" in {i.code for i in r.issues} for r in res.records)
    assert accepted_rows(res) == []


def test_bank_change_is_held_and_the_last_accepted_version_is_carried_forward() -> None:
    prev = portal_snapshot([{"vendor_id": "V100", "bank_account": "560269953287", "routing_number": ROUTING, "tax_id": "98-8013380",
                             "name": "Northwind Traders"}, {"vendor_id": "V999", "name": "Gone Ltd"}])
    res = run(("portal", portal({"Bank Acct": "123123123", "ABA": ROUTING2})), previous=("prev.csv", prev))
    r = res.records[0]
    assert r.decision == "review"
    changed = [i for i in r.issues if i.code == "CONTROLLED_FIELD_CHANGED"]
    assert {i.field for i in changed} == {"bank_account", "routing_number"}
    assert "123123123" not in json.dumps(r.model_dump()) and "****3123" in changed[0].message  # masked on screen
    rows = accepted_rows(res)
    assert len(rows) == 1 and rows[0]["bank_account"] == "560269953287"  # last known good, not the new account
    assert res.missing_from_source == ["V999"]


def test_a_held_record_that_blocks_the_vendor_does_not_revive_the_old_version() -> None:
    """Blocked in the source system, and held for another reason: the old active version must not be loaded instead."""
    prev = portal_snapshot([{"vendor_id": "V100", "bank_account": "560269953287", "routing_number": ROUTING, "tax_id": "98-8013380",
                             "status": "active", "name": "Northwind Traders"}])
    res = run(("portal", portal({"Status": "B", "Contact Email": "not-an-email"})), previous=("prev.csv", prev))
    assert res.records[0].decision == "rejected"
    assert accepted_rows(res) == [] and res.withheld == ["V100"] and res.carried_forward == []


def portal_snapshot(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(VENDORS.fields), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in VENDORS.fields})
    return buf.getvalue().encode()


def po_csv(*lines: dict[str, str]) -> bytes:
    head = ["PO_NUMBER", "VENDOR_NO", "PO_STATUS", "CCY", "LINE", "ITEM", "ITEM_DESC", "QTY", "UNIT_PRICE", "GR_REQUIRED"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=head, lineterminator="\n")
    w.writeheader()
    for i, ln in enumerate(lines, start=1):
        w.writerow({"PO_NUMBER": "PO-4501", "VENDOR_NO": "V100", "PO_STATUS": "O", "CCY": "USD", "LINE": str(i), "ITEM": "OFF-100",
                    "ITEM_DESC": "Copy paper", "QTY": "5", "UNIT_PRICE": "42.00", "GR_REQUIRED": "Y", **ln})
    return buf.getvalue().encode()


VENDOR_REF = b"vendor_id,status\nV100,active\nV101,inactive\n"


def test_purchase_orders_reference_groups_and_outliers() -> None:
    res = gate(POS, [SourceInput("erp", "po.csv", po_csv(
        {}, {}, {}, {},  # four normal lines of one item: the price baseline
        {"PO_NUMBER": "PO-4502", "VENDOR_NO": "V555", "LINE": "1"},  # unknown vendor
        {"PO_NUMBER": "PO-4503", "VENDOR_NO": "V101", "LINE": "1"},  # inactive vendor
        {"PO_NUMBER": "PO-4504", "LINE": "1"}, {"PO_NUMBER": "PO-4504", "LINE": "2", "CCY": "EUR"},  # two currencies in one PO
        {"PO_NUMBER": "PO-4505", "LINE": "1", "UNIT_PRICE": "420.00"},  # a typed extra zero
    ))], references={"vendors": ("vendors.csv", VENDOR_REF)})
    d = {(r.canonical["po_number"], r.canonical["line_no"]): (r.decision, {i.code for i in r.issues}) for r in res.records}
    assert d[("PO-4501", "1")] == ("accepted", set())
    assert d[("PO-4502", "1")] == ("rejected", {"UNKNOWN_REFERENCE"})
    assert d[("PO-4503", "1")] == ("review", {"REFERENCE_STATUS"})
    assert d[("PO-4504", "1")][0] == d[("PO-4504", "2")][0] == "rejected"
    assert d[("PO-4505", "1")] == ("review", {"OUTLIER"})


def test_missing_reference_file_is_a_warning_not_a_silent_pass() -> None:
    res = gate(POS, [SourceInput("erp", "po.csv", po_csv({}))])
    assert res.warnings and "vendor_id was not checked" in res.warnings[0]


# -- what leaves the gate ---------------------------------------------------------------------------------------------

def test_exports_mask_bank_details_and_are_safe_to_open_in_a_spreadsheet() -> None:
    res = run(("portal", portal({"Supplier Name": "=cmd|' /C calc'!A0"}, {"Supplier ID": "V101", "EIN": "11-2223334",
                                                                          "Bank Acct": "444455556666", "Supplier Name": "Fine Co"})))
    q = quarantine_rows(res)
    flat = "\n".join(",".join(r) for r in q)
    assert "560269953287" not in flat and "****3287" in flat
    assert any(c.startswith("'=cmd") for row in q for c in row)  # escaped, so a spreadsheet shows it as text
    assert "560269953287" not in res.model_dump_json()  # stored results never hold a full account number
    assert [r["bank_account"] for r in accepted_rows(res)] == ["444455556666"]  # the load file has the real value


def test_hostile_files_are_refused_or_gated_never_crash() -> None:
    from finops.dq.engine import GateInputError

    for label, name, data in hostile_inputs(portal({})):
        try:
            gate(VENDORS, [SourceInput("portal", name, data)])
        except GateInputError:
            pass  # a clean refusal with a reason
        except Exception as exc:  # pragma: no cover - the assertion below names the file
            raise AssertionError(f"{label}: {type(exc).__name__}: {exc}") from exc


def test_reader_refuses_binary_and_flags_formulas_saved_without_a_value() -> None:
    with pytest.raises(TableError):
        read_table("x.csv", bytes(range(256)) * 10)  # used to crash (UnicodeDecodeError) for every engine
    wb = Workbook()
    ws = wb.active
    ws.append(["a", "b"])
    ws.append(["1", "=A2*2"])  # written by a program: no saved result
    buf = io.BytesIO()
    wb.save(buf)
    _, rows = read_table("f.xlsx", buf.getvalue(), find_formulas=True)
    assert rows[0].values["b"] == "" and rows[0].formulas == frozenset({"b"})
    _, rows = read_table("f.xlsx", buf.getvalue())
    assert rows[0].formulas == frozenset()  # off by default: the other engines read exactly as before


def test_aba_checksum() -> None:
    assert aba_ok(ROUTING) and aba_ok("011000015") and not aba_ok("011000016") and not aba_ok("12345678")


# -- the service: runs, decisions, controls ------------------------------------------------------------------------------

@pytest.fixture
def svc(tmp_path: Path) -> DQService:
    return DQService(Database(tmp_path / "f.sqlite3"), tmp_path / "files", ROOT / "config" / "finops" / "dq")


def test_rerunning_the_same_files_reuses_the_run(svc: DQService) -> None:
    a = svc.run("vendors.yaml", [("portal", "p.csv", portal({}))], "Alice Reviewer")
    b = svc.run("vendors.yaml", [("portal", "p.csv", portal({}))], "Alice Reviewer")
    assert a == b and len(svc.runs()) == 1
    assert any(e["kind"] == "run_reused" for e in svc.events("vendors"))


def test_release_correct_and_the_two_person_rule(svc: DQService) -> None:
    data = portal({"Contact Email": ""}, {"Supplier ID": "V101", "EIN": "12-345", "Bank Acct": "121212121", "Supplier Name": "Bad Ein Co"})
    run1 = svc.run("vendors.yaml", [("portal", "p.csv", data)], "Alice Reviewer")
    recs = {r["canonical"]["vendor_id"]: r for r in svc.get(run1)["result"]["records"]}
    held, bad = recs["V100"], recs["V101"]
    assert (held["decision"], bad["decision"]) == ("review", "rejected")
    with pytest.raises(ActionError, match="named reviewer"):
        svc.decide(run1, held["id"], "release", "AI assistant", "looks fine")
    with pytest.raises(ActionError, match="reason"):
        svc.decide(run1, held["id"], "release", "Alice Reviewer", "ok")
    with pytest.raises(ActionError, match="corrected"):
        svc.decide(run1, bad["id"], "release", "Alice Reviewer", "it is fine really")
    run2 = svc.decide(run1, held["id"], "release", "Alice Reviewer", "Called the vendor; no AP mailbox, pays by phone")
    with pytest.raises(ActionError, match="newer run"):
        svc.decide(run1, bad["id"], "correct", "Alice Reviewer", "typo in EIN", "tax_id", "12-3456789")
    run3 = svc.decide(run2, bad["id"], "correct", "Bob Clerk", "EIN from the W-9 on file", "tax_id", "12-3456789")
    recs3 = {r["canonical"]["vendor_id"]: r for r in svc.get(run3)["result"]["records"]}
    assert recs3["V100"]["decision"] == "accepted" and recs3["V100"]["decided_by"] == "Alice Reviewer"
    assert recs3["V101"]["decision"] == "accepted"  # corrected and now valid
    assert any("corrected by Bob Clerk" in c["step"] for c in recs3["V101"]["changes"])
    name, body = svc.export(run3, "accepted")
    assert body.count(b"\n") == 3 and b"12-3456789" in body
    # the decisions table refuses edits, so the history cannot be rewritten
    with pytest.raises(sqlite3.DatabaseError):
        svc.db.conn.execute("UPDATE dq_decisions SET actor = 'x'")


def test_whoever_corrected_a_held_record_cannot_release_it(svc: DQService) -> None:
    prev = portal_snapshot([{"vendor_id": "V100", "bank_account": "560269953287", "routing_number": ROUTING, "tax_id": "98-8013380"}])
    run1 = svc.run("vendors.yaml", [("portal", "p.csv", portal({"Contact Email": ""}))], "Alice Reviewer",
                   previous=("prev.csv", prev))
    rid = svc.get(run1)["result"]["records"][0]["id"]
    run2 = svc.decide(run1, rid, "correct", "Alice Reviewer", "new account per vendor letter", "bank_account", "999000111222")
    rec = svc.get(run2)["result"]["records"][0]
    assert rec["decision"] == "review" and "CONTROLLED_FIELD_CHANGED" in {i["code"] for i in rec["issues"]}
    with pytest.raises(ActionError, match="second person"):
        svc.decide(run2, rid, "release", "alice reviewer", "I confirmed it myself")
    run3 = svc.decide(run2, rid, "release", "Carol Controller", "Called the vendor on the number in the contract; confirmed")
    assert svc.get(run3)["result"]["records"][0]["decision"] == "accepted"
    events = json.dumps(svc.events("vendors"))
    assert "999000111222" not in events and "****1222" in events  # the audit log never holds the full number


def test_a_decision_racing_another_is_refused(svc: DQService) -> None:
    """Someone else's decision landed but its re-run has not finished: this run is already stale."""
    run1 = svc.run("vendors.yaml", [("portal", "p.csv", portal({"Contact Email": ""}))], "Alice Reviewer")
    rid = svc.get(run1)["result"]["records"][0]["id"]
    with svc.db.tx() as c:
        c.execute("INSERT INTO dq_decisions (dataset_id, run_id, record_id, kind, payload, actor, at) VALUES (?,?,?,?,?,?,?)",
                  ("vendors", run1, rid, "reject", json.dumps({"note": "duplicate of V7"}), "Bob Clerk", "now"))
    with pytest.raises(ActionError, match="a moment ago"):
        svc.decide(run1, rid, "release", "Alice Reviewer", "Confirmed by phone with the vendor")


def test_a_release_lapses_when_the_record_changes(svc: DQService) -> None:
    run1 = svc.run("vendors.yaml", [("portal", "p.csv", portal({"Contact Email": ""}))], "Alice Reviewer")
    rid = svc.get(run1)["result"]["records"][0]["id"]
    svc.decide(run1, rid, "release", "Alice Reviewer", "Confirmed by phone with the vendor")
    run3 = svc.run("vendors.yaml", [("portal", "p.csv", portal({"Contact Email": "", "Terms (days)": "45"}))], "Alice Reviewer")
    assert svc.get(run3)["result"]["records"][0]["decision"] == "review"  # different row: a new record, not released


# -- downstream: the invoice engine ------------------------------------------------------------------------------------

def _invoice_outcome(master_dir: Path, tmp_path: Path, account: str, routing: str):  # type: ignore[no-untyped-def]
    from finops.invoice.config import APPolicy
    from finops.invoice.engine import process
    from finops.invoice.master import BankFingerprinter, load_master
    from finops.invoice.matching import History

    policy, _ = load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "default-ap.yaml")
    fp = BankFingerprinter(b"k" * 32)
    master = load_master(master_dir, {"vendors": "vendors.csv", "purchase_orders": "purchase_orders.csv", "receipts": "receipts.csv"}, fp)
    doc = json.loads((ROOT / "eval" / "invoice" / "dev" / "invoices" / "inv-007-json_clean.json").read_text())
    doc["remit_to"] = {"account_number": account, "routing_number": routing}
    return process("inv.json", json.dumps(doc).encode(), policy, master, History(), fp)


def test_a_bank_change_in_the_source_system_no_longer_reaches_the_invoice_engine(tmp_path: Path) -> None:
    """Vendor-master fraud: someone changes Northwind's bank account in the source system, then invoices to it.
    Loaded as is, the master and the invoice agree, so the invoice engine's own bank check passes. Through the gate,
    the change is held for a second person and the last accepted account stays in force, so the check blocks it."""
    src = ROOT / "eval" / "invoice" / "dev" / "master"
    header, rows = read_table("vendors.csv", (src / "vendors.csv").read_bytes())
    # The invoice engine's synthetic master has routing numbers that fail the ABA checksum (the gate rejects them; the
    # invoice engine never checked). Give every vendor a valid one so the only difference is the bank change.
    trusted = [{**r.values, "routing_number": (r.values["routing_number"][:8] + aba_check_digit(r.values["routing_number"][:8]))
                if r.values["routing_number"] else ""} for r in rows]
    fraud = "777000111222"
    v100 = next(r for r in trusted if r["vendor_id"] == "V100")
    changed = [{**r, "bank_account": fraud} if r["vendor_id"] == "V100" else r for r in trusted]

    def write_master(d: Path, vendor_rows: list[dict[str, str]], cols: list[str]) -> Path:
        d.mkdir()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(vendor_rows)
        (d / "vendors.csv").write_text(buf.getvalue(), encoding="utf-8")
        for f in ("purchase_orders.csv", "receipts.csv"):
            (d / f).write_bytes((src / f).read_bytes())
        return d

    ungated = _invoice_outcome(write_master(tmp_path / "ungated", changed, header), tmp_path, fraud, v100["routing_number"])
    assert "BANK_DETAILS_CHANGED" not in {e.code for e in ungated.exceptions}

    source = portal(*({"Supplier ID": r["vendor_id"], "Supplier Name": r["name"], "Also Known As": r["aliases"], "EIN": r["tax_id"],
                       "Sales Tax %": str(float(r["tax_rate"]) * 100) if r["tax_rate"] else "", "Bank Acct": r["bank_account"],
                       "ABA": r["routing_number"], "Status": "A"} for r in changed))
    last_accepted = io.StringIO()
    w = csv.DictWriter(last_accepted, fieldnames=header, lineterminator="\n")
    w.writeheader()
    w.writerows(trusted)
    res = run(("portal", source), previous=("vendors.csv", last_accepted.getvalue().encode()))
    nw = by_name(res, "Northwind Traders")
    assert nw.decision == "review" and {i.code for i in nw.issues} == {"CONTROLLED_FIELD_CHANGED"}
    assert all(r.decision == "accepted" for r in res.records if r is not nw)
    gated = _invoice_outcome(write_master(tmp_path / "gated", accepted_rows(res), res.columns), tmp_path, fraud, v100["routing_number"])
    assert "BANK_DETAILS_CHANGED" in {e.code for e in gated.exceptions} and gated.eligibility == "blocked"


# -- evaluation ------------------------------------------------------------------------------------------------------

def test_synthetic_sets_are_scored_and_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import finops.dq.evaluate as ev

    monkeypatch.setattr(ev, "write_report", lambda name, report, lines, **kw: tmp_path / "r.md")
    s = generate(5, clean=30, per_fault=1, per_legit=1)
    assert len(s.vendor_truth) > 40 and len(s.po_truth) > 40
    lines = run_report("t", ROOT, {"t": 5})
    assert any("0 crash(es)" in ln for ln in lines) and any("0 record(s) changed decision" in ln for ln in lines)


def test_http_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from finops import api as fapi
    from spreader.api import app

    database = Database(tmp_path / "f.sqlite3")
    fapi.configure(database, dq_service=DQService(database, tmp_path / "files", ROOT / "config" / "finops" / "dq"))
    c = TestClient(app)
    h = {"X-Actor": "dana"}
    assert {d["id"] for d in c.get("/api/finops/dq/datasets").json()} == {"vendors", "purchase_orders"}
    runs = c.post("/api/finops/dq/sample", json={}, headers=h).json()
    v = c.get(f"/api/finops/dq/runs/{runs['vendors']}").json()
    assert v["status"] == "succeeded" and v["latest"] and v["counts"]["review"] > 0
    sample = generate(21)
    accounts = [r["Bank Acct"] for r in csv.DictReader(io.StringIO(sample.portal_csv.decode())) if len(r["Bank Acct"]) >= 6]
    shown = json.dumps(v)
    assert accounts and not [a for a in accounts if a in shown]  # no full account number reaches the browser
    held = next(r for r in v["result"]["records"] if r["decision"] == "review" and
                {i["code"] for i in r["issues"]} == {"ACTIVE_VENDOR_NEEDS_CONTACT"})
    bad = c.post(f"/api/finops/dq/runs/{runs['vendors']}/decide", json={"record_id": held["id"], "action": "release", "note": "x"}, headers=h)
    assert bad.status_code == 400 and "reason" in bad.json()["error"]
    ok = c.post(f"/api/finops/dq/runs/{runs['vendors']}/decide",
                json={"record_id": held["id"], "action": "release", "note": "Vendor confirmed AP contact by phone"}, headers=h)
    new = ok.json()["run"]
    assert c.get(f"/api/finops/dq/runs/{new}").json()["counts"]["accepted"] == v["counts"]["accepted"] + 1
    csv_text = c.get(f"/api/finops/dq/runs/{new}/export/quarantine.csv").text
    assert csv_text.startswith("decision,record_id")
    up = c.post("/api/finops/dq/runs", data={"dataset": "vendors.yaml"}, files={"source_portal": ("p.csv", portal({}), "text/csv")}, headers=h)
    assert up.status_code == 200 and c.get(f"/api/finops/dq/runs/{up.json()['run']}").json()["counts"]["accepted"] == 1
    missing = c.post("/api/finops/dq/runs", data={"dataset": "vendors.yaml"},
                     files={"source_portal": ("p.csv", b"Supplier ID\nV1\n", "text/csv")}, headers=h)
    assert missing.status_code == 400 and "has no column" in missing.json()["error"]
    cross = c.post("/api/finops/dq/sample", headers={**h, "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403
    assert any(e["kind"] == "decision_release" for e in c.get("/api/finops/dq/datasets/vendors/events").json())
