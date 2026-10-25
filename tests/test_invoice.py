"""Invoice engine: extraction, arithmetic, three-way matching, duplicates, bank control, service rules."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from finops.core.audit import Database
from finops.core.config import load_config
from finops.invoice.config import APPolicy
from finops.invoice.engine import history_entry, process
from finops.invoice.evaluate import evaluate_set
from finops.invoice.master import BankFingerprinter, load_master, normalize_number
from finops.invoice.matching import History
from finops.invoice.service import ActionError, InvoiceService

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "eval" / "invoice" / "dev"
POLICY = ROOT / "config" / "finops" / "invoice" / "default-ap.yaml"
pytestmark = pytest.mark.skipif(not (DEV / "truth.json").exists(), reason="synthetic invoices not generated")


@pytest.fixture(scope="module")
def policy() -> APPolicy:
    return load_config(APPolicy, POLICY)[0]


@pytest.fixture(scope="module")
def fp() -> BankFingerprinter:
    return BankFingerprinter(b"test-key")


@pytest.fixture(scope="module")
def master(policy: APPolicy, fp: BankFingerprinter):  # type: ignore[no-untyped-def]
    return load_master(DEV / "master", policy.master_data.model_dump(), fp)


@pytest.fixture(scope="module")
def truth() -> dict:
    return json.loads((DEV / "truth.json").read_text(encoding="utf-8"))


def doc_of(truth: dict, kind: str, layout: str | None = None) -> dict:
    return next(d for d in truth["inbox"] if d["kind"] == kind and (layout is None or d["layout"] == layout))


def run(doc: dict, policy, master, fp, history: History | None = None, **kw):  # type: ignore[no-untyped-def]
    return process(Path(doc["file"]).name, (DEV / doc["file"]).read_bytes(), policy, master, history or History(), fp, **kw)


def json_invoice(**over) -> bytes:  # type: ignore[no-untyped-def]
    body = {"vendor": {"name": "Unknown Vendor Ltd"}, "invoice_number": "A-1", "invoice_date": "2026-03-03",
            "due_date": "2026-04-02", "po_number": "PO-1", "currency": "USD", "subtotal": "100.00", "total": "100.00",
            "lines": [{"description": "Widget", "quantity": "2", "unit_price": "50.00", "amount": "100.00"}]}
    body.update(over)
    return json.dumps(body).encode()


def test_document_numbers_normalise() -> None:
    assert normalize_number("INV-000123") == normalize_number("inv 123") == normalize_number("#123") == "123"
    assert normalize_number("PO-4501") == "4501" and normalize_number("A-0012") == "A0012"


@pytest.mark.parametrize("layout", ["A", "B", "C"])
def test_each_layout_reads_header_lines_and_evidence(truth, policy, master, fp, layout) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "clean", layout)
    o = run(doc, policy, master, fp)
    inv = o.invoice
    assert inv.get("invoice_number") == doc["invoice_number"] and inv.get("invoice_date") == doc["invoice_date"]
    assert inv.get("total") == Decimal(doc["total"]) and o.vendor_id == doc["vendor_id"]
    assert [str(ln.amount.value) for ln in inv.lines] == [ln["amount"] for ln in doc["lines"]]
    ev = inv.fields["total"].evidence
    assert ev is not None and ev.page == 1 and ev.bbox is not None  # traceable to the printed spot
    assert inv.fields["invoice_date"].origin.value == "normalized" and inv.fields["invoice_date"].original
    assert o.touchless and o.eligibility == "eligible_for_approval" and o.authorization == "not_authorized"


def test_multipage_table_reads_as_one(truth, policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "multipage")
    o = run(doc, policy, master, fp)
    assert o.invoice.pages >= 2 and len(o.invoice.lines) == len(doc["lines"]) and o.touchless


@pytest.mark.parametrize("kind,code", [("line_math", "LINE_EXTENSION_MISMATCH"), ("total_math", "TOTAL_MISMATCH"),
                                       ("tax_wrong", "TAX_MISMATCH"), ("tax_unverified", "TAX_UNVERIFIED"),
                                       ("price_over", "PRICE_OVER_PO"), ("over_receipt", "QTY_EXCEEDS_RECEIVED"),
                                       ("missing_receipt", "MISSING_RECEIPT"), ("closed_po", "PO_NOT_OPEN"),
                                       ("vendor_mismatch", "VENDOR_MISMATCH"), ("po_not_found", "PO_NOT_FOUND"),
                                       ("no_po_ref", "NO_PO_REFERENCE"), ("bank_changed", "BANK_DETAILS_CHANGED"),
                                       ("bank_unverified", "BANK_DETAILS_UNVERIFIED")])
def test_planted_problem_blocks_or_holds_the_invoice(truth, policy, master, fp, kind, code) -> None:  # type: ignore[no-untyped-def]
    o = run(doc_of(truth, kind), policy, master, fp)
    assert code in {e.code for e in o.exceptions}
    assert not o.touchless and o.eligibility != "eligible_for_approval"


def test_amounts_are_reported_never_corrected(truth, policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "total_math")
    o = run(doc, policy, master, fp)
    assert o.invoice.get("total") == Decimal(doc["total"])  # the printed (wrong) total is kept
    e = next(e for e in o.exceptions if e.code == "TOTAL_MISMATCH")
    assert Decimal(e.evidence["printed"]) == Decimal(doc["total"])


def test_bank_numbers_never_stored_in_full(truth, policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "bank_changed")
    o = run(doc, policy, master, fp)
    dumped = o.model_dump_json()
    assert doc["bank_account"] not in dumped and doc["bank_account"][-4:] in dumped
    assert "_bank_raw" not in o.invoice.fields


def test_service_line_matches_two_way_and_says_so(truth, policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    o = run(doc_of(truth, "service_2way"), policy, master, fp)
    assert o.touchless and any("two-way" in n for lm in o.line_matches for n in lm.notes)


def test_cumulative_quantity_across_two_invoices(truth, policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    first, second = [d for d in truth["inbox"] if d["kind"] == "sequential"][:1], None
    second = next(d for d in truth["inbox"] if d["kind"] == "sequential" and d["po_number"] == first[0]["po_number"] and d is not first[0])
    h = History()
    o1 = run(first[0], policy, master, fp, h)
    h.invoices.append(history_entry(o1))
    o2 = run(second, policy, master, fp, h)
    assert o2.touchless
    h.invoices.append(history_entry(o2))
    o3 = run(second, policy, master, fp, History(invoices=[e for e in h.invoices if e["doc_id"] != second["file"]] +
                                                  [{**history_entry(o2), "doc_id": "other"}]))
    assert {"QTY_EXCEEDS_RECEIVED", "QTY_EXCEEDS_ORDERED"} & {e.code for e in o3.exceptions}


def test_duplicates_exact_reformatted_and_distinct(truth, policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    dup = doc_of(truth, "exact_dup")
    original = next(d for d in truth["inbox"] if d["vendor_id"] == dup["vendor_id"] and d["kind"] == "clean"
                    and d["total"] == dup["total"] and d["invoice_date"] == dup["invoice_date"])
    h = History()
    h.invoices.append(history_entry(run(original, policy, master, fp)))
    assert dup["invoice_number"] != original["invoice_number"]  # re-typed, e.g. without the INV- prefix
    assert "EXACT_DUPLICATE" in {e.code for e in run(dup, policy, master, fp, h).exceptions}
    distinct = doc_of(truth, "similar_distinct")
    assert not {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"} & {e.code for e in run(distinct, policy, master, fp, h).exceptions}


def test_unknown_vendor_and_missing_fields_fail_closed(policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    o = process("x.json", json_invoice(invoice_number=None, total=None), policy, master, History(), fp)
    codes = {e.code for e in o.exceptions}
    assert {"VENDOR_UNKNOWN", "MISSING_FIELD", "PO_NOT_FOUND"} <= codes
    assert o.eligibility == "blocked" and o.extraction == "incomplete"


def test_unreadable_pdf_is_not_guessed(policy, master, fp) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="not a readable PDF"):
        process("broken.pdf", b"%PDF-1.4 not really a pdf", policy, master, History(), fp)
    with pytest.raises(ValueError, match="not a readable invoice JSON"):
        process("broken.json", b"[1, 2", policy, master, History(), fp)


def test_known_answer_evaluation_holds_its_bar(policy) -> None:  # type: ignore[no-untyped-def]
    r = evaluate_set(DEV, policy)
    assert r["rates"]["false_touchless"].n == 0
    assert r["rates"]["reason_codes"].value == 1.0
    assert r["rates"]["header_fields"].value >= 0.99


# -- service -------------------------------------------------------------------------------------

@pytest.fixture()
def svc(tmp_path: Path) -> InvoiceService:
    return InvoiceService(Database(tmp_path / "f.sqlite3"), tmp_path / "files", POLICY, DEV / "master", tmp_path / "key")


def test_same_file_twice_is_one_invoice(svc: InvoiceService, truth) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "clean")
    data = (DEV / doc["file"]).read_bytes()
    a = svc.upload("a.pdf", data, "dana")
    b = svc.upload("a-copy.pdf", data, "dana")
    assert b["already_uploaded"] and a["document"]["doc_id"] == b["document"]["doc_id"]
    assert len(svc.inbox()) == 1
    again = svc.process(a["document"]["doc_id"], "dana")
    assert again["reused"]


def test_correction_keeps_the_original_and_ends_touchless(svc: InvoiceService, truth) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "clean")
    r = svc.upload("a.pdf", (DEV / doc["file"]).read_bytes(), "dana")
    did = r["document"]["doc_id"]
    with pytest.raises(ActionError, match="where the corrected value"):
        svc.correct(did, "invoice_number", "X-1", "", "dana")
    r2 = svc.correct(did, "terms", "Net 45", "As printed in the footer.", "dana")
    f = r2["outcome"]["invoice"]["fields"]["terms"]
    assert f["value"] == "Net 45" and f["original"] == doc["terms"] and f["origin"] == "human" and f["corrected_by"] == "dana"
    assert r2["outcome"]["touchless"] is False


def test_bank_change_needs_a_different_person_and_a_real_note(svc: InvoiceService, truth) -> None:  # type: ignore[no-untyped-def]
    doc = doc_of(truth, "bank_changed")
    r = svc.upload("b.pdf", (DEV / doc["file"]).read_bytes(), "dana")
    did = r["document"]["doc_id"]
    e = next(x for x in r["outcome"]["exceptions"] if x["code"] == "BANK_DETAILS_CHANGED")
    with pytest.raises(ActionError, match="someone other"):
        svc.resolve(did, e["id"], "verified_independently", "Called the vendor at the number on file, confirmed.", "dana")
    with pytest.raises(ActionError, match="Describe"):
        svc.resolve(did, e["id"], "verified_independently", "ok", "lee")
    with pytest.raises(ActionError):
        svc.resolve(did, e["id"], "explained", "The model says the change is fine.", "lee")
    with pytest.raises(ActionError, match="named reviewer"):
        svc.resolve(did, e["id"], "verified_independently", "Verified by the assistant automatically today.", "assistant")
    r2 = svc.resolve(did, e["id"], "verified_independently", "Called the vendor on the number in the vendor master, 3/10.", "lee")
    assert r2["outcome"]["authorization"] == "not_authorized"
    assert next(x for x in r2["outcome"]["exceptions"] if x["code"] == "BANK_DETAILS_CHANGED")["status"] == "resolved"
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        svc.db.conn.execute("DELETE FROM inv_decisions")


def test_api_routes_end_to_end(tmp_path: Path, truth) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from finops import api as fapi
    from finops.recon.service import ReconService
    from spreader.api import app

    database = Database(tmp_path / "f.sqlite3")
    fapi.configure(database, ReconService(database, tmp_path / "files", ROOT / "config" / "finops" / "recon"),
                   InvoiceService(database, tmp_path / "inv", POLICY, DEV / "master", tmp_path / "key"))
    c = TestClient(app)
    h = {"X-Actor": "dana"}
    wid = c.post("/api/finops/recon/workspaces", json={"name": "March", "profile": "bank-vs-gl.yaml"}, headers=h).json()["id"]
    run = c.post(f"/api/finops/recon/workspaces/{wid}/sample", json={}, headers=h).json()
    assert run["run"]["status"] == "succeeded" and run["result"]["groups"]
    rid = run["run"]["id"]
    bad = c.post(f"/api/finops/recon/runs/{rid}/resolve", json={"exception_id": "nope", "action": "explained"}, headers=h)
    assert bad.status_code == 400 and "error" in bad.json()
    assert c.get(f"/api/finops/recon/runs/{rid}/export.csv").text.startswith("record,source")
    doc = doc_of(truth, "bank_changed")
    up = c.post("/api/finops/invoices", files={"file": ("b.pdf", (DEV / doc["file"]).read_bytes(), "application/pdf")}, headers=h)
    assert up.status_code == 200 and up.json()["outcome"]["eligibility"] == "blocked"
    assert doc["bank_account"] not in up.text
    cross = c.post("/api/finops/invoices/sample", headers={**h, "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403
    assert c.get("/api/finops/overview").json()["engines"][2]["invoices"] == 1
