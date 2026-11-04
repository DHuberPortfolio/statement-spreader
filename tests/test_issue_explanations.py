"""Blockers and warnings in plain words, with suggested fixes a person applies (D63), and what each document is."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from conftest import statement_html
from spreader.company import detect_filing
from spreader.explain import best_line, explain, explain_item
from spreader.contracts import ReviewItem, ReviewKind, RowMapping, Severity, StatementRow
from spreader.service import Service
from spreader.store import Store

Y = ["December 31, 2025", "December 31, 2024"]
P = "2025-12-31/I"

# Total assets is 700, but the lines placed add to 600: "Trademarks with indefinite lives" (100) has no line.
BS = [("Cash and cash equivalents", "100", "80"), ("Total current assets", "100", "80"),
      ("Property, plant and equipment, net", "500", "420"), ("Trademarks with indefinite lives", "100", "90"),
      ("Total assets", "700", "590"), ("Accounts payable", "60", "50"), ("Total current liabilities", "60", "50"),
      ("Long-term debt", "340", "320"), ("Total liabilities", "400", "370"), ("Retained earnings", "300", "220"),
      ("Total stockholders' equity", "300", "220"), ("Total liabilities and stockholders' equity", "700", "590")]


def _service(tmp_path: Any, profile: Any) -> Service:
    return Service(Store(tmp_path / "db.sqlite3"), profile=profile)


def _upload(svc: Service, rows: list[tuple[str, str, str]] = BS, **kw: Any) -> Any:
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, rows)
    return svc.upload("bs.htm", html.encode(), "tester", **kw)[1]


def _failed(view: Any, profile: Any) -> tuple[ReviewItem, dict[str, Any]]:
    item = next(i for i in view.spread.review if i.id == f"check:bs_assets_parts:{P}")
    return item, explain(view.spread, profile)[item.id]


def test_a_failed_check_says_what_is_wrong_and_shows_the_gap(tmp_path: Any, profile: Any) -> None:
    _, ex = _failed(_upload(_service(tmp_path, profile)), profile)
    assert ex["title"] == "The numbers do not add up"
    assert "Asset lines add up to total assets" in ex["what"]
    assert "Approval is locked" in ex["why"]
    assert (Decimal(ex["compare"]["left"]), Decimal(ex["compare"]["right"]), Decimal(ex["compare"]["gap"])) == (
        Decimal(700000), Decimal(600000), Decimal(100000))
    assert ex["compare"]["left_label"] == "Total assets"


def test_a_row_equal_to_the_gap_is_the_strong_suggestion(tmp_path: Any, profile: Any) -> None:
    _, ex = _failed(_upload(_service(tmp_path, profile)), profile)
    top = ex["suggestions"][0]
    assert top["strength"] == "strong" and "equals the gap exactly" in top["detail"]
    assert top["fix"]["mode"] == "move" and top["fix"]["line"] == "intangibles"
    assert top["reason"], "a reason that follows from the numbers is offered"


def test_rows_that_only_together_close_the_gap_are_named_together(tmp_path: Any, profile: Any) -> None:
    rows = [r if r[0] != "Trademarks with indefinite lives" else ("Trademarks with indefinite lives", "60", "50") for r in BS]
    rows.insert(4, ("Security deposits with landlords", "40", "40"))
    _, ex = _failed(_upload(_service(tmp_path, profile), rows), profile)
    strong = [s for s in ex["suggestions"] if s["strength"] == "strong"]
    assert len(strong) == 2 and all("Together with" in s["detail"] for s in strong)


def test_a_sentence_only_a_person_can_say_is_never_written_for_them(tmp_path: Any, profile: Any) -> None:
    view = _upload(_service(tmp_path, profile))
    for ex in explain(view.spread, profile).values():
        for s in ex["suggestions"]:
            if s["fix"]["mode"] == "accept":
                assert s["reason"] == "", s["title"]


def test_every_open_blocker_and_warning_is_explained_and_info_is_not(tmp_path: Any, profile: Any) -> None:
    view = _upload(_service(tmp_path, profile))
    ex = explain(view.spread, profile)
    for i in view.spread.review:
        if i.resolved or i.severity is Severity.INFO:
            assert i.id not in ex
        else:
            e = ex[i.id]
            assert e["title"] and e["what"] and e["why"] and e["headline"] and e["modes"], i.id


def test_a_warning_says_it_does_not_lock_approval(tmp_path: Any, profile: Any) -> None:
    view = _upload(_service(tmp_path, profile))
    warning = next(i for i in view.spread.review if i.severity is Severity.WARNING and i.kind is ReviewKind.UNCONFIRMED)
    ex = explain(view.spread, profile)[warning.id]
    assert "does not lock approval" in ex["why"] and ex["values"] and ex["suggestions"]


def test_applying_the_suggestion_clears_the_blocker_and_records_the_reason(tmp_path: Any, profile: Any) -> None:
    svc = _service(tmp_path, profile)
    view = _upload(svc)
    _, ex = _failed(view, profile)
    fix = ex["suggestions"][0]
    after = svc.act(view.run["id"], {"type": "remap_row", "statement": fix["fix"]["statement"], "row": fix["fix"]["row"],
                                     "line": fix["fix"]["line"], "reason": fix["reason"]}, "tester")
    assert not [i for i in after.spread.review if i.id.startswith("check:bs_assets_parts") and not i.resolved]
    logged = svc.store.query("SELECT payload FROM events WHERE kind='remap_row'")
    assert fix["reason"] in logged[0]["payload"]


def test_a_blocker_accepted_with_a_reason_stops_blocking(tmp_path: Any, profile: Any) -> None:
    svc = _service(tmp_path, profile)
    view = _upload(svc)
    item, _ = _failed(view, profile)
    after = svc.act(view.run["id"], {"type": "resolve_item", "item": item.id, "note": "Compared with the filing"}, "tester")
    assert next(i for i in after.spread.review if i.id == item.id).resolved
    assert item.id not in explain(after.spread, profile)


def test_a_detail_row_is_never_suggested_for_a_total_or_result(profile: Any) -> None:
    row = StatementRow(index=1, label="Equity income net", label_clean="equity income net")
    got = best_line(row, RowMapping(row_index=1, canonical=None, method="none", confidence=0),  # type: ignore[arg-type]
                    profile, ["net_income", "total_opex", "other_opex", "other_nonoperating"])
    assert got == "other_nonoperating"


def test_an_item_the_explainer_has_no_detail_for_still_reads(profile: Any, tmp_path: Any) -> None:
    view = _upload(_service(tmp_path, profile))
    item = ReviewItem(id="x", kind=ReviewKind.CONFLICT, severity=Severity.BLOCKER, message="Two tables disagree.")
    ex = explain_item(item, view.spread, profile)
    assert ex["what"] == "Two tables disagree." and ex["modes"] == ["accept"]


COVER = (b'<ix:nonNumeric name="dei:EntityRegistrantName" id="f-7">PROCTER &amp; GAMBLE CO</ix:nonNumeric>'
         b'<ix:nonNumeric name="dei:DocumentType" id="f-1">10-K</ix:nonNumeric>'
         b'<ix:nonNumeric name="dei:DocumentFiscalYearFocus" id="f-2">2026</ix:nonNumeric>'
         b'<ix:nonNumeric name="dei:EntityCentralIndexKey" id="f-3">0000080424</ix:nonNumeric>')


def test_a_filing_is_named_from_its_cover_page() -> None:
    assert detect_filing(COVER) == {"company_name": "Procter & Gamble Co", "filing": "10-K fiscal 2026"}
    assert detect_filing(b"<html>no tags</html>") is None


def test_an_sec_filing_is_labelled_and_takes_its_cik(tmp_path: Any, profile: Any) -> None:
    svc = _service(tmp_path, profile)
    html = statement_html("CONSOLIDATED BALANCE SHEETS", "(In thousands)", Y, BS).encode()
    view = svc.upload("pg.htm", COVER + html, "tester")[1]
    doc = svc.store.document(view.run["document_id"])
    assert (doc["origin"], doc["company_name"], doc["filing"], doc["company_id"]) == (
        "sec", "Procter & Gamble Co", "10-K fiscal 2026", "cik:80424")


def test_a_generated_document_says_so_and_a_plain_upload_is_only_an_upload(tmp_path: Any, profile: Any) -> None:
    svc = _service(tmp_path, profile)
    made = _upload(svc, generated=True)
    assert svc.store.document(made.run["document_id"])["origin"] == "generated"
    rows = [*BS[:-1], ("Total liabilities and stockholders' equity", "700", "589")]
    plain = _upload(svc, rows)
    assert svc.store.document(plain.run["document_id"])["origin"] == "uploaded"


def test_a_generated_document_can_carry_a_made_up_company_name(tmp_path: Any, profile: Any) -> None:
    svc = _service(tmp_path, profile)
    made = _upload(svc, generated=True, display_name="Everhollow Trading", company_id="Everhollow Trading")
    doc = svc.store.document(made.run["document_id"])
    assert (doc["company_name"], doc["filing"], doc["origin"]) == ("Everhollow Trading", "Sample statements", "generated")


def test_documents_stored_earlier_are_identified_when_listed(tmp_path: Any, profile: Any) -> None:
    svc = _service(tmp_path, profile)
    view = _upload(svc)
    with svc.store.tx() as c:
        c.execute("UPDATE documents SET origin=NULL")
    assert svc.documents()[0]["origin"] == "uploaded"
    assert svc.store.document(view.run["document_id"])["origin"] == "uploaded"


def test_the_accuracy_page_gets_only_accuracy_reports(tmp_path: Any, monkeypatch: Any) -> None:
    """A comparison report has no rates; it was the newest file after D62, and the page went blank on it."""
    import json

    from conftest import client_as
    from spreader import api

    (tmp_path / "accuracy.json").write_text(json.dumps({"name": "a", "rates": {"silent_error_rate": {"rate": 0.1}}}))
    (tmp_path / "comparison.json").write_text(json.dumps({"name": "c", "without": {}, "with": {}}))
    (tmp_path / "null-rates.json").write_text(json.dumps({"name": "n", "rates": None}))
    (tmp_path / "other-engine.json").write_text(json.dumps({"name": "o", "rates": {"false_matches": {"rate": 0}}}))
    (tmp_path / "a-list.json").write_text("[1, 2]")
    monkeypatch.setattr(api, "REPORTS", tmp_path)
    got = client_as(api.app, "pat").get("/api/evaluation").json()["reports"]
    assert [r["name"] for r in got] == ["a"]
