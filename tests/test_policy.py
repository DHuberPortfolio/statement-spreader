"""One uncertainty policy for every engine (finops.core.policy): calibrated confidence only, findings in one shape."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import statement_html
from finops.core import policy
from spreader.contracts import MapMethod, ReviewKind, RowMapping
from spreader.ingest import read_document
from spreader.pipeline import spread_document

ROOT = Path(__file__).resolve().parents[1]
IS_ROWS = [("Net sales", "400", "250"), ("Cost of sales", "150", "100"), ("Gross margin", "250", "150"),
           ("Research and development", "50", "40"), ("Selling, general and administrative", "30", "20"),
           ("Total operating expenses", "80", "60"), ("Operating income", "170", "90"),
           ("Provision for income taxes", "40", "20"), ("Net income", "130", "70")]


def _spread(profile: Any, model: Any = None) -> Any:
    html = statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In thousands)",
                          ["Year Ended December 31, 2025", "Year Ended December 31, 2024"], IS_ROWS)
    return spread_document(read_document("t.htm", html.encode()), profile, model=model)[0]


def _with(monkeypatch: pytest.MonkeyPatch, engine: str, cal: policy.Calibration) -> None:
    real = policy.load

    def fake(e: str, path: str | None = None) -> policy.Calibration:
        return cal if e == engine else real(e, path)

    monkeypatch.setattr(policy, "load", fake)


# -- the policy itself ---------------------------------------------------------------------------------------------

def test_auto_accept_needs_a_measured_lower_bound_above_the_bar() -> None:
    outcomes = [("alias", True, "key")] * 97 + [("alias", False, "key")] * 3 + [("rare", True, "key")] * 3
    cal = policy.fit("x", "a row", outcomes, never_auto=["model"], person_methods=["memory"], derived_methods=["total"])
    alias = cal.decide("alias", 0.90)
    assert alias.auto and alias.basis == "calibrated" and 0.91 < alias.confidence < 0.92  # 97 of 100: at least 91.5%
    assert not cal.decide("alias", 0.95).auto  # 97% measured, but its lower bound is under 95%
    rare = cal.decide("rare", 0.80)
    assert not rare.auto and rare.basis == "below_bar"  # 3 of 3 right is not evidence enough (at least 43.8%)
    assert cal.decide("never-seen", 0.0).basis == "uncalibrated" and not cal.decide("never-seen", 0.0).auto
    assert cal.decide("memory", 0.99).auto
    assert cal.decide("total", 0.9, 0.95).auto and not cal.decide("total", 0.9, 0.85).auto


def test_a_model_is_never_auto_even_when_it_measured_perfectly() -> None:
    cal = policy.fit("x", "a row", [("model", True, "key")] * 5000, never_auto=["model"])
    d = cal.decide("model", 0.5)
    assert not d.auto and d.basis == "never_auto" and "5000 of 5000" in d.reason


def test_reviewer_decisions_feed_the_calibration(tmp_path: Path) -> None:
    f = tmp_path / "decisions.jsonl"
    f.write_text('{"method": "fuzzy", "right": true, "source": "reviewer"}\n{"method": "fuzzy", "right": false}\n')
    cal = policy.fit("x", "a row", [("fuzzy", True, "key")] + policy.read_outcomes(f))
    assert cal.methods["fuzzy"].total == 3 and cal.methods["fuzzy"].sources == {"key": 1, "reviewer": 1, "decisions.jsonl": 1}


def test_the_committed_calibrations_record_what_they_were_fitted_on() -> None:
    for engine, dataset in (("statements", "sec-dev"), ("recon", "recon-calibration")):
        cal = policy.load(engine)
        assert cal.methods and cal.fitted["datasets"][0]["name"] == dataset and cal.fitted["commit"]
        assert cal.fitted["outcomes"] == sum(s.total for s in cal.methods.values())


# -- statements --------------------------------------------------------------------------------------------------

def test_mapping_confidence_is_the_rules_measured_lower_bound(profile: Any) -> None:
    """Was a hand-set constant (an exact alias was 1.0, a pattern 0.95)."""
    cal = policy.load("statements")
    rules = {m.rule: m.confidence for res in _spread(profile).statements.values() for m in res.mappings if m.canonical}
    assert rules and all(conf == pytest.approx(cal.confidence(rule) or 0.0, abs=1e-4) for rule, conf in rules.items()
                         if rule.startswith(("alias", "catchall", "fuzzy")))
    assert rules.get("alias.exact") == pytest.approx(cal.methods["alias.exact"].low, abs=1e-4)


def test_without_a_calibration_no_rule_placed_row_is_accepted_alone(profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The policy fails closed: a deployment with no calibration file reviews every mapping."""
    _with(monkeypatch, "statements", policy.Calibration(engine="statements", unit="none"))
    spread = _spread(profile)
    mapped = {(s, m.row_index) for s, res in spread.statements.items() for m in res.mappings
              if m.canonical and m.rule.startswith("alias")}
    flagged = {(i.statement.value, r) for i in spread.review if i.kind is ReviewKind.LOW_CONFIDENCE for r in i.rows}
    assert mapped and mapped <= flagged
    assert any("no measured accuracy" in i.message for i in spread.review)


def test_a_model_suggestion_is_reviewed_whatever_confidence_it_states(profile: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    perfect = policy.load("statements").model_copy(deep=True)
    perfect.methods["model"] = policy.MethodStats(right=1000, total=1000, rate=1.0, low=0.996, high=1.0)
    _with(monkeypatch, "statements", perfect)

    def overconfident(table: Any, row: Any, lines: Any) -> RowMapping:
        return RowMapping(row_index=row.index, canonical="other_opex", method=MapMethod.MODEL, confidence=1.0, rule="model",
                          reason="The model is sure.")

    rows = [*IS_ROWS[:5], ("Widget restructuring", "5", "0"), *IS_ROWS[5:]]
    html = statement_html("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In thousands)",
                          ["Year Ended December 31, 2025", "Year Ended December 31, 2024"], rows)
    spread = spread_document(read_document("t.htm", html.encode()), profile, model=overconfident)[0]
    by_model = [(s, m.row_index) for s, res in spread.statements.items() for m in res.mappings if m.rule == "model"]
    assert by_model
    flagged = {(i.statement.value, r) for i in spread.review if i.kind is ReviewKind.LOW_CONFIDENCE for r in i.rows}
    assert set(by_model) <= flagged


# -- reconciliation ---------------------------------------------------------------------------------------------

def test_an_uncalibrated_reconciliation_rule_proposes_instead_of_settling(monkeypatch: pytest.MonkeyPatch) -> None:
    from finops.core.config import load_config
    from finops.recon.config import ReconProfile
    from finops.recon.engine import reconcile
    from finops.recon.model import MatchStatus
    from finops.recon.synthetic import generate

    profile, version = load_config(ReconProfile, ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml")
    bank, ledger, _ = generate(7, 60)
    before = reconcile("b.csv", bank, "l.csv", ledger, profile, version)
    assert any(g.rule == "reference" and g.status is MatchStatus.AUTO for g in before.groups)
    assert any("right 3416 of 3416" in e for g in before.groups if g.rule == "reference" for e in g.explanation)
    cal = policy.load("recon").model_copy(deep=True)
    del cal.methods["reference"]
    _with(monkeypatch, "recon", cal)
    after = reconcile("b.csv", bank, "l.csv", ledger, profile, version)
    refs = [g for g in after.groups if g.rule == "reference"]
    assert refs and all(g.status is MatchStatus.PROPOSED for g in refs)
    assert "no measured accuracy" in refs[0].explanation[-1]


# -- every engine's findings in one shape ----------------------------------------------------------------------------

def _check(findings: list[policy.Finding], engine: str) -> None:
    assert findings, engine
    for f in findings:
        assert f.engine == engine and f.reason and f.required_action and f.produced_by and f.evidence, f


def test_every_engine_reports_findings_in_the_shared_shape(profile: Any) -> None:
    from openpyxl import Workbook

    from finops.core.config import load_config
    from finops.dq.config import DatasetSpec
    from finops.dq.engine import SourceInput, gate
    from finops.dq.engine import as_findings as dq_findings
    from finops.dq.synthetic import generate as dq_generate
    from finops.invoice.config import APPolicy
    from finops.invoice.engine import process
    from finops.invoice.master import BankFingerprinter, load_master
    from finops.invoice.matching import History
    from finops.recon.config import ReconProfile
    from finops.recon.engine import reconcile
    from finops.recon.synthetic import generate
    from finops.sheets.config import ScanSpec
    from finops.sheets.scan import as_findings as sheet_findings
    from finops.sheets.scan import scan_workbook
    from finops.sheets.workbook import load as load_workbook
    from spreader.review import as_findings as statement_findings

    syn = ROOT / "eval" / "synthetic" / "s7-031-no-unit-statement"
    spread, _ = spread_document(read_document("s.html", (syn / "statement.html").read_bytes()), profile)
    _check(statement_findings(spread), "statements")
    assert any(f.blocking and f.code == "assumed_scale" for f in statement_findings(spread))

    rp, rv = load_config(ReconProfile, ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml")
    bank, ledger, _ = generate(7, 60)
    _check([policy.from_exception(e) for e in reconcile("b.csv", bank, "l.csv", ledger, rp, rv).exceptions], "recon")

    ap = load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "default-ap.yaml")[0]
    fp = BankFingerprinter(b"test-key")
    master = load_master(ROOT / "eval" / "invoice" / "dev" / "master", ap.master_data.model_dump(), fp)
    body = json.dumps({"vendor": {"name": "Unknown Vendor Ltd"}, "invoice_number": "A-1", "invoice_date": "2026-03-03",
                       "currency": "USD", "subtotal": "100.00", "total": "100.00",
                       "lines": [{"description": "Widget", "quantity": "2", "unit_price": "50.00", "amount": "100.00"}]})
    outcome = process("x.json", body.encode(), ap, master, History(), fp)
    _check([policy.from_exception(e) for e in outcome.exceptions], "invoice")

    vspec, vver = load_config(DatasetSpec, ROOT / "config" / "finops" / "dq" / "vendors.yaml")
    s = dq_generate(21)
    result = gate(vspec, [SourceInput("portal", "portal.csv", s.portal_csv)], config_version=vver)
    _check(dq_findings(result), "dq")

    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["B1"] = 5, "=#REF!+A1"
    from finops.core.fingerprint import stable_xlsx

    findings, _ = scan_workbook(load_workbook("m.xlsx", stable_xlsx(wb), ScanSpec()), ScanSpec())
    _check(sheet_findings(findings), "sheets")
