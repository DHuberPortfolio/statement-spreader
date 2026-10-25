"""Reconciliation engine: normalisation, matching rules, exceptions, reruns, decisions, audit."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from finops.core.audit import Database
from finops.core.config import ConfigError, load_config
from finops.core.money import Tolerance, parse_money
from finops.recon.config import ReconProfile
from finops.recon.engine import reconcile
from finops.recon.evaluate import evaluate, shuffled
from finops.recon.model import MatchStatus
from finops.recon.normalize import ReconInputError, load_source, normalize_reference
from finops.recon.service import ActionError, ReconService
from finops.recon.synthetic import generate

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "config" / "finops" / "recon"
BANK_HEAD = "Transaction ID,Posted Date,Description,Reference,Withdrawals,Deposits,Currency\n"
GL_HEAD = "Entry No,Date,Memo,Ref,Counterparty,Debit,Credit,Currency\n"


@pytest.fixture(scope="module")
def profile() -> tuple[ReconProfile, str]:
    return load_config(ReconProfile, PROFILES / "bank-vs-gl.yaml")


def bank(*rows: str) -> bytes:
    return (BANK_HEAD + "".join(r + "\n" for r in rows)).encode()


def gl(*rows: str) -> bytes:
    return (GL_HEAD + "".join(r + "\n" for r in rows)).encode()


def run(profile, b: bytes, g: bytes):  # type: ignore[no-untyped-def]
    p, v = profile
    return reconcile("bank.csv", b, "ledger.csv", g, p, v)


def statuses(res) -> dict[tuple[str, ...], str]:  # type: ignore[no-untyped-def]
    return {tuple(x.left + x.right): x.status.value for x in res.groups}


def codes(res) -> list[str]:  # type: ignore[no-untyped-def]
    return sorted(e.code for e in res.exceptions)


# -- money and tolerance --------------------------------------------------------------------------

@pytest.mark.parametrize("text,value", [
    ("1,234.50", "1234.50"), ("(1,234.50)", "-1234.50"), ("1,234.50-", "-1234.50"), ("USD 1,234.50", "1234.50"),
    ("1,234.50 EUR", "1234.50"), ("250.00 CR", "-250.00"), ("250.00 DR", "250.00"), ("$-5.00", "-5.00"),
])
def test_parse_money_reads_finance_formats(text: str, value: str) -> None:
    assert parse_money(text) == (Decimal(value), None)


@pytest.mark.parametrize("text", ["12%", "1.234,50", "abc", "1,2,3"])
def test_parse_money_refuses_what_it_does_not_understand(text: str) -> None:
    v, why = parse_money(text)
    assert v is None and why


def test_tolerance_boundaries() -> None:
    t = Tolerance(abs=Decimal("1.00"), pct=Decimal("0.01"))  # min: the stricter applies
    assert t.within(Decimal("50"), Decimal("50.50"))  # 1% of 50.50 = 0.505
    assert not t.within(Decimal("50"), Decimal("50.51"))
    assert t.within(Decimal("1000"), Decimal("1001.00"))  # abs 1.00 is stricter than 1% (10)
    assert not t.within(Decimal("1000"), Decimal("1001.01"))
    assert Tolerance().within(Decimal("1.00"), Decimal("1.00")) and not Tolerance().within(Decimal("1.00"), Decimal("1.01"))
    with pytest.raises(ValueError):
        Tolerance(pct=Decimal("2"))


# -- configuration --------------------------------------------------------------------------------

def test_overlay_inherits_and_changes_only_what_it_names() -> None:
    p, v = load_config(ReconProfile, PROFILES / "example-company-signed.yaml")
    base, bv = load_config(ReconProfile, PROFILES / "bank-vs-gl.yaml")
    assert p.left.amount_field == "Amount" and p.left.inflow_field is None
    assert p.right.amount_sign == "negate" and "unique_amount_date" not in p.matching.auto_accept
    assert p.matching.date_window_days == base.matching.date_window_days and v != bv


def test_invalid_profile_is_refused_with_the_field_named(tmp_path: Path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text("extends: " + str(PROFILES / "bank-vs-gl.yaml").replace("\\", "/") +
                 "\nmatching:\n  auto_accept: [reference, guesswork]\n")
    with pytest.raises(ConfigError, match="guesswork"):
        load_config(ReconProfile, f)
    f.write_text("id: x\nname: x\nleft: {name: bank, label: B, date_field: D}\nright: {name: gl, label: G, date_field: D, amount_field: A}\n")
    with pytest.raises(ConfigError, match="amount_field"):
        load_config(ReconProfile, f)


# -- normalisation --------------------------------------------------------------------------------

def test_reference_normalisation(profile) -> None:  # type: ignore[no-untyped-def]
    r = profile[0].matching.references
    assert normalize_reference("INV-000123", r) == normalize_reference("123", r) == normalize_reference("inv 123", r) == "123"
    assert normalize_reference("DEP-0412", r) == "DEP0412"
    assert normalize_reference("", r) == ""


def test_missing_column_names_the_column(profile) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ReconInputError, match="'Reference'"):
        load_source("b.csv", b"Transaction ID,Posted Date,Description,Withdrawals,Deposits,Currency\n", profile[0].left, profile[0])


def test_bad_rows_become_blockers_not_guesses(profile) -> None:  # type: ignore[no-untyped-def]
    data = bank("B1,03/02/2026,X,,10.00,,USD", "B2,31/02/2026,X,,,5.00,USD", "B3,03/02/2026,X,,1.00,2.00,USD",
                "B4,03/02/2026,X,,abc,,USD", "B1,03/03/2026,Y,,7.00,,USD")
    txns, problems = load_source("b.csv", data, profile[0].left, profile[0])
    assert [t.id for t in txns] == ["bank:B1", "bank:B1#2"]
    assert txns[0].amount == Decimal("-10.00")  # a withdrawal is money out
    rows = sorted(p.evidence.get("row") for p in problems if p.code == "INVALID_RECORD")
    assert rows == [3, 4, 5]
    assert all(p.severity.value == "blocker" for p in problems if p.code == "INVALID_RECORD")
    assert any(p.code == "DUPLICATE_SOURCE_ID" for p in problems)


# -- matching rules -------------------------------------------------------------------------------

def test_reference_match_survives_formatting_and_late_clearing(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/25/2026,CHECK,CHK 0042,500.00,,USD"),
              gl("J1,2026-03-01,Vendor payment,42,Acme,,500.00,USD"))
    assert statuses(res) == {("bank:B1", "ledger:J1"): "auto_matched"}
    assert res.groups[0].rule == "reference"


def test_one_bank_line_two_equal_ledger_lines_is_ambiguous_not_guessed(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/10/2026,DEPOSIT,,,100.00,USD"),
              gl("J1,2026-03-09,Receipt,,P,100.00,,USD", "J2,2026-03-08,Receipt,,Q,100.00,,USD"))
    assert all(g.status is MatchStatus.PROPOSED for g in res.groups)
    assert "AMBIGUOUS_CANDIDATES" in codes(res)


def test_greedy_baseline_auto_accepts_the_ambiguous_case(profile) -> None:  # type: ignore[no-untyped-def]
    """The control: the naive strategy does pick one, which is why it is not the default."""
    p, v = profile
    greedy = p.model_copy(update={"matching": p.matching.model_copy(update={"strategy": "greedy"})})
    res = reconcile("b.csv", bank("B1,03/10/2026,DEPOSIT,,,100.00,USD"), "l.csv",
                    gl("J1,2026-03-09,Receipt,,P,100.00,,USD", "J2,2026-03-08,Receipt,,Q,100.00,,USD"), greedy, v)
    assert any(g.status is MatchStatus.AUTO for g in res.groups)


def test_equal_sets_pair_by_clear_mutual_best(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/02/2026,ACH CREDIT PALMER,,,100.00,USD", "B2,03/06/2026,ACH CREDIT QUINN,,,100.00,USD"),
              gl("J1,2026-03-02,R,,Palmer,100.00,,USD", "J2,2026-03-06,R,,Quinn,100.00,,USD"))
    assert statuses(res) == {("bank:B1", "ledger:J1"): "auto_matched", ("bank:B2", "ledger:J2"): "auto_matched"}


def test_amount_difference_is_proposed_with_the_difference(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/05/2026,WIRE IN,INV-77,,9975.00,USD"), gl("J1,2026-03-03,Receipt,INV-77,P,10000.00,,USD"))
    (g,) = res.groups
    assert g.status is MatchStatus.PROPOSED and g.difference == Decimal("-25.00")
    assert "AMOUNT_DIFFERENCE" in codes(res)


def test_same_reference_far_apart_amounts_are_a_proposed_partial(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/05/2026,X,INV-99,,100.00,USD"), gl("J1,2026-03-03,X,INV-99,P,900.00,,USD"))
    (g,) = res.groups
    assert g.status is MatchStatus.PROPOSED and g.rule == "partial" and g.difference == Decimal("-800.00")
    assert "PARTIAL_MATCH" in codes(res)


def test_partial_never_takes_records_a_sum_explains(profile) -> None:  # type: ignore[no-untyped-def]
    """B1 shares J1's reference but only B1 + B2 add up to J1: the sum layer wins, no partial."""
    res = run(profile, bank("B1,03/05/2026,X,INV-99,,100.00,USD", "B2,03/06/2026,Y,,,800.00,USD"),
              gl("J1,2026-03-04,X,INV-99,P,900.00,,USD"))
    assert [(g.rule, sorted(g.left + g.right)) for g in res.groups] == [("many_to_one", ["bank:B1", "bank:B2", "ledger:J1"])]
    assert "PARTIAL_MATCH" not in codes(res)


def test_currencies_are_never_matched_automatically(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/05/2026,X,INV-99,,100.00,EUR"), gl("J1,2026-03-05,X,INV-99,P,100.00,,USD"))
    assert res.groups == [] and "CURRENCY_MISMATCH" in codes(res)


def test_batch_with_shared_reference_is_matched_without_one_is_only_proposed(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/05/2026,DEPOSIT,DEP-1,,300.00,USD"),
              gl("J1,2026-03-04,R,DEP-1,P,100.00,,USD", "J2,2026-03-05,R,DEP-1,Q,200.00,,USD"))
    assert statuses(res) == {("bank:B1", "ledger:J1", "ledger:J2"): "auto_matched"}
    res = run(profile, bank("B1,03/05/2026,DEPOSIT,,,300.00,USD"),
              gl("J1,2026-03-04,R,,P,100.00,,USD", "J2,2026-03-05,R,,Q,200.00,,USD"))
    assert statuses(res) == {("bank:B1", "ledger:J1", "ledger:J2"): "proposed"}
    assert "PROPOSED_GROUP" in codes(res)


def test_two_possible_subsets_propose_nothing(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/05/2026,DEPOSIT,,,300.00,USD"),
              gl("J1,2026-03-04,R,,P,100.00,,USD", "J2,2026-03-05,R,,Q,200.00,,USD", "J3,2026-03-05,R,,S,150.00,,USD",
                 "J4,2026-03-05,R,,T,150.00,,USD"))
    assert res.groups == [] and "AMBIGUOUS_CANDIDATES" in codes(res)


def test_leftovers_get_specific_reasons(profile) -> None:  # type: ignore[no-untyped-def]
    res = run(profile, bank("B1,03/05/2026,MOBILE DEPOSIT,CK-5,,400.00,USD", "B2,03/08/2026,RETURNED ITEM NSF,CK-5,400.00,,USD",
                            "B3,03/12/2026,MONTHLY SERVICE FEE,,25.00,,USD", "B4,03/31/2026,X,,,1.00,USD"),
              gl("J1,2026-03-05,Receipt,CK-5,P,400.00,,USD", "J2,2026-03-30,Vendor payment,CHK 9,Q,,70.00,USD",
                 "J3,2026-03-10,Receipt,,R,55.00,,USD", "J4,2026-03-10,Receipt,,R,55.00,,USD"))
    by_code = {e.code: e.subjects for e in res.exceptions}
    assert by_code["REVERSAL"] == ["bank:B2"]
    assert by_code["UNRECORDED_FEE"] == ["bank:B3"]
    assert by_code["TIMING_DIFFERENCE"] == ["ledger:J2"]
    assert "POSSIBLE_DUPLICATE" in by_code


def test_row_order_never_changes_the_result(profile) -> None:  # type: ignore[no-untyped-def]
    b, g, _ = generate(3, 60)
    a = run(profile, b, g)
    z = run(profile, shuffled(b, 9), shuffled(g, 4))
    assert sorted((x.status.value, tuple(x.left + x.right)) for x in a.groups) == \
        sorted((x.status.value, tuple(x.left + x.right)) for x in z.groups)
    assert sorted(e.id for e in a.exceptions) == sorted(e.id for e in z.exceptions)


def test_completeness_checks_pass_and_every_record_is_in_at_most_one_match(profile) -> None:  # type: ignore[no-untyped-def]
    b, g, _ = generate(5, 100)
    res = run(profile, b, g)
    assert all(c["status"] == "pass" for c in res.checks), res.checks
    seen: list[str] = [m for x in res.groups for m in x.left + x.right]
    assert len(seen) == len(set(seen))


def test_known_answer_evaluation_holds_its_bar(profile) -> None:  # type: ignore[no-untyped-def]
    """Regression bar on a seed the matcher was not tuned on (dev tuning used seed 7)."""
    b, g, truth = generate(11, 100)
    r = evaluate(profile[0], profile[1], b, g, truth)
    assert r["rates"]["false_match_rate"].n == 0
    assert r["rates"]["review_cases_auto_accepted"].n == 0
    assert r["rates"]["auto_recall"].value >= 0.95
    assert r["order_stable"] and r["exceptions_stable"] and not r["checks_failed"]


# -- service: reruns, decisions, audit --------------------------------------------------------------

@pytest.fixture()
def svc(tmp_path: Path) -> ReconService:
    return ReconService(Database(tmp_path / "f.sqlite3"), tmp_path / "files", PROFILES)


def _ws(svc: ReconService) -> int:
    return svc.create_workspace("March", "bank-vs-gl.yaml", "dana")


B = bank("B1,03/10/2026,DEPOSIT,,,100.00,USD", "B2,03/12/2026,ACH CREDIT RIVERA,INV-5,,250.00,USD")
G = gl("J1,2026-03-09,Receipt,,P,100.00,,USD", "J2,2026-03-08,Receipt,,Q,100.00,,USD", "J3,2026-03-11,Receipt,INV-5,Rivera,250.00,,USD")


def test_same_inputs_reuse_the_run(svc: ReconService) -> None:
    wid = _ws(svc)
    first = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    again = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    assert again["reused"] and again["run"]["id"] == first["run"]["id"]
    assert len(svc.db.query("SELECT id FROM recon_runs")) == 1
    assert [e["kind"] for e in svc.events(wid)][-1] == "run_reused"


def test_interrupted_run_leaves_no_partial_result(svc: ReconService) -> None:
    wid = _ws(svc)

    def crash(*a, **k):  # type: ignore[no-untyped-def]
        raise RuntimeError("power cut")

    with pytest.raises(RuntimeError):
        svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G), _engine=crash)
    rows = svc.db.query("SELECT status, result FROM recon_runs")
    assert [(r["status"], r["result"]) for r in rows] == [("failed", None)]
    ok = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    assert ok["run"]["status"] == "succeeded" and not ok["reused"]


def test_accepted_decision_survives_a_rerun_and_locks_its_records(svc: ReconService) -> None:
    wid = _ws(svc)
    r = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    prop = next(g for g in r["result"]["groups"] if g["status"] == "proposed")
    r2 = svc.accept(r["run"]["id"], prop["id"], "dana")
    acc = [g for g in r2["result"]["groups"] if g["status"] == "accepted"]
    assert len(acc) == 1 and acc[0]["decided_by"] == "dana"
    # A new bank file that only adds a line: the decision carries over, the new line is matched fresh.
    B2 = B + b"B3,03/20/2026,ACH CREDIT,,,77.00,USD\n"
    r3 = svc.run(wid, "dana", ("bank.csv", B2), None)
    assert [g["left"] + g["right"] for g in r3["result"]["groups"] if g["status"] == "accepted"] == [acc[0]["left"] + acc[0]["right"]]
    started = [e for e in svc.events(wid) if e["kind"] == "run_started"][-1]
    assert started["payload"]["changes"][0]["what"] == "bank/left file"


def test_changed_record_invalidates_the_decision_visibly(svc: ReconService) -> None:
    wid = _ws(svc)
    r = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    prop = next(g for g in r["result"]["groups"] if g["status"] == "proposed")
    svc.accept(r["run"]["id"], prop["id"], "dana")
    changed = B.replace(b"03/10/2026,DEPOSIT,,,100.00", b"03/10/2026,DEPOSIT,,,100.50")
    r3 = svc.run(wid, "dana", ("bank.csv", changed), None)
    inv = [e for e in r3["result"]["exceptions"] if e["code"] == "DECISION_INVALIDATED"]
    assert inv and inv[0]["severity"] == "blocker" and "changed" in inv[0]["detail"]
    assert not any(g["status"] == "accepted" for g in r3["result"]["groups"])


def test_rejected_pairing_is_not_proposed_again(svc: ReconService) -> None:
    wid = _ws(svc)
    r = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    prop = next(g for g in r["result"]["groups"] if g["status"] == "proposed")
    r2 = svc.reject(r["run"]["id"], prop["id"], "dana")
    assert all(set(g["left"] + g["right"]) != set(prop["left"] + prop["right"]) for g in r2["result"]["groups"])


def test_decisions_need_the_latest_run_a_person_and_notes(svc: ReconService) -> None:
    wid = _ws(svc)
    r = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    rid = r["run"]["id"]
    auto = next(g for g in r["result"]["groups"] if g["status"] == "auto_matched")
    prop = next(g for g in r["result"]["groups"] if g["status"] == "proposed")
    with pytest.raises(ActionError, match="named reviewer"):
        svc.accept(rid, prop["id"], "model")
    with pytest.raises(ActionError, match="note"):
        svc.reject(rid, auto["id"], "dana")
    with pytest.raises(ActionError, match="note"):
        svc.manual_match(rid, ["bank:B1"], ["ledger:J2"], "dana", "")
    exc = r["result"]["exceptions"][0]
    with pytest.raises(ActionError, match="named reviewer"):
        svc.resolve(rid, exc["id"], "explained", "assistant", "The model says it is fine.")
    svc.reject(rid, prop["id"], "dana")
    with pytest.raises(ActionError, match="out of date"):
        svc.accept(rid, prop["id"], "dana")


def test_resolution_carries_over_and_history_cannot_be_edited(svc: ReconService) -> None:
    wid = _ws(svc)
    r = svc.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    exc = r["result"]["exceptions"][0]
    r2 = svc.resolve(r["run"]["id"], exc["id"], "explained", "dana", "Checked the deposit slip.")
    assert next(e for e in r2["result"]["exceptions"] if e["id"] == exc["id"])["status"] == "resolved"
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        svc.db.conn.execute("UPDATE recon_decisions SET actor = 'someone else'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        svc.db.conn.execute("DELETE FROM audit_events")
    assert svc.db.verify_chain() == (True, None)


def test_profile_outside_the_profile_folder_is_refused(svc: ReconService) -> None:
    with pytest.raises(ActionError):
        svc.create_workspace("x", "../../../pyproject.toml", "dana")


def test_company_overlay_reads_a_differently_shaped_export_the_same_way(profile) -> None:  # type: ignore[no-untyped-def]
    """Same transactions, exported as one signed column with other headers and the opposite ledger sign:
    the overlay (configuration only) finds the same match sets; only its stricter policy changes statuses."""
    import csv
    import io

    over = load_config(ReconProfile, PROFILES / "example-company-signed.yaml")
    b, g, _ = generate(5, 100)
    B = [r for r in csv.DictReader(io.StringIO(b.decode())) if r["Currency"] == "USD"]
    G = [r for r in csv.DictReader(io.StringIO(g.decode())) if r["Currency"] == "USD"]

    def out(cols: list[str], rows: list[list[str]]) -> bytes:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows([cols, *rows])
        return buf.getvalue().encode()

    def dec(x: str) -> Decimal:
        return Decimal((x or "0").replace(",", ""))

    plain = run(profile, out(list(B[0]), [list(r.values()) for r in B]), out(list(G[0]), [list(r.values()) for r in G]))
    signed = reconcile(
        "b.csv", out(["Bank Ref No", "Value Date", "Narrative", "Customer Ref", "Amount"],
                     [[r["Transaction ID"], r["Posted Date"], r["Description"], r["Reference"],
                       str(dec(r["Deposits"]) - dec(r["Withdrawals"]))] for r in B]),
        "g.csv", out(["Document Number", "Posting Date", "Text", "Assignment", "Amount (LC)"],
                     [[r["Entry No"], r["Date"], r["Memo"], r["Ref"], str(dec(r["Credit"]) - dec(r["Debit"]))] for r in G]),
        over[0], over[1])
    assert {frozenset(x.left + x.right) for x in plain.groups} == {frozenset(x.left + x.right) for x in signed.groups}
    assert all(plain.records[k].amount == signed.records[k].amount for k in plain.records)
    assert not any(x.rule == "unique_amount_date" and x.status is MatchStatus.AUTO for x in signed.groups)
