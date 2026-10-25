"""Reviewer decisions recorded as labelled outcomes, and calibration learning from them (finops.core.outcomes, D40)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from finops.core import outcomes, policy
from spreader.learning import approval_outcomes
from spreader.service import Service
from spreader.store import Store
from test_company import BS, _bs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "outcomes"
    monkeypatch.setenv("FINOPS_OUTCOMES_DIR", str(d))
    return d


@pytest.fixture()
def svc(tmp_path: Path, profile: Any) -> Service:
    return Service(Store(tmp_path / "db.sqlite3"), profile=profile)


def _approved(svc: Service, **action: Any) -> Any:
    _, run = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana", company_id="acme")
    if action:
        svc.act(run.run["id"], action, "dana")
    return svc.act(run.run["id"], {"type": "approve"}, "dana")


def test_an_approval_records_one_outcome_per_placed_row_and_one_per_unit(svc: Service, folder: Path) -> None:
    view = _approved(svc)
    rows = outcomes.read("statements", folder)
    placed = [m for r in view.spread.statements.values() for m in r.mappings if m.canonical and not m.excluded]
    assert rows and all(o.right and o.how == "approved_unchanged" and o.decided_by == "dana" for o in rows)
    assert len(rows) == len([m for m in placed if m.rule != "memory"])
    assert {o.refs["company"] for o in rows} == {"acme"}
    (unit,) = outcomes.read("units", folder)
    assert unit.right and unit.method == view.spread.statements["balance_sheet"].table.scale.rule


def test_a_remap_records_the_placing_rule_as_wrong(svc: Service, folder: Path) -> None:
    _, run = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana")
    res = run.spread.statements["balance_sheet"]
    row = next(r for r in res.table.rows if r.label.startswith("Long-term debt"))
    rule = next(m.rule for m in res.mappings if m.row_index == row.index)
    svc.act(run.run["id"], {"type": "remap_row", "statement": "balance_sheet", "row": row.index,
                            "line": "other_noncurrent_liabilities"}, "dana")
    (wrong,) = outcomes.read("statements", folder)
    assert (wrong.method, wrong.right, wrong.how, wrong.refs["moved_to"]) == (rule, False, "remapped",
                                                                              "other_noncurrent_liabilities")


def test_a_corrected_line_is_not_judged_and_a_power_of_ten_correction_marks_the_unit_wrong(svc: Service, profile: Any) -> None:
    _, run = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana")
    state = {"overrides": {"cash@2025-12-31/I": {"value": "100000000", "previous": "100000"}}}
    got = approval_outcomes(run.spread, state, {}, "dana", "now", profile.line_statement)
    assert not any(o.refs.get("line") == "cash" for o in got if o.engine == "statements")
    (unit,) = [o for o in got if o.engine == "units"]
    assert not unit.right and unit.how == "corrected"
    state = {"overrides": {"cash@2025-12-31/I": {"value": "100250", "previous": "100000"}}}  # not a unit slip
    assert all(o.right for o in approval_outcomes(run.spread, state, {}, "dana", "now", profile.line_statement)
               if o.engine == "units")


def test_calibration_learns_from_the_folder(svc: Service, folder: Path) -> None:
    _approved(svc)
    learned = outcomes.as_calibration_outcomes(outcomes.read("statements", folder))
    cal = policy.fit("statements", "row", learned)
    assert all(s.sources == {"reviewers (approved_unchanged)": s.total} for s in cal.methods.values())
    summary = outcomes.summary(folder)
    assert summary["engines"]["statements"]["outcomes"] == len(learned)


def test_the_audit_log_rebuilds_the_same_outcomes(svc: Service, folder: Path, tmp_path: Path) -> None:
    _, run = svc.upload("2025.htm", _bs(["December 31, 2025", "December 31, 2024"]), "dana")
    row = next(r for r in run.spread.statements["balance_sheet"].table.rows if r.label.startswith("Long-term debt"))
    after = svc.act(run.run["id"], {"type": "remap_row", "statement": "balance_sheet", "row": row.index,
                                    "line": "other_noncurrent_liabilities"}, "dana")
    svc.act(after.run["id"], {"type": "approve"}, "dana")
    sys.path.insert(0, str(ROOT / "scripts"))
    from export_outcomes import rebuild

    live = outcomes.read("statements", folder) + outcomes.read("units", folder)
    again = rebuild(svc.store)

    def key(o: outcomes.Outcome) -> tuple:
        return (o.engine, o.method, o.right, o.how, o.refs.get("statement"), o.refs.get("row"))

    assert sorted(map(key, again)) == sorted(map(key, live))


def test_a_reconciliation_verdict_is_recorded(tmp_path: Path, folder: Path) -> None:
    from finops.core.audit import Database
    from finops.recon.service import ReconService
    from test_recon import PROFILES, B, G

    rs = ReconService(Database(tmp_path / "f.sqlite3"), tmp_path / "files", PROFILES)
    wid = rs.create_workspace("March", "bank-vs-gl.yaml", "dana")
    r = rs.run(wid, "dana", ("bank.csv", B), ("gl.csv", G))
    prop = next(g for g in r["result"]["groups"] if g["status"] == "proposed")
    rs.reject(r["run"]["id"], prop["id"], "dana")
    (o,) = outcomes.read("recon", folder)
    assert (o.method, o.right, o.how) == (prop["rule"], False, "rejected")


def test_a_failed_write_never_stops_a_decision(svc: Service, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the folder should be")
    monkeypatch.setenv("FINOPS_OUTCOMES_DIR", str(blocker))
    view = _approved(svc)
    assert view.run["state"]["approved"]["by"] == "dana"


def test_tests_never_write_to_the_real_outcomes_folder() -> None:
    """Approvals in other tests must not become 'reviewer' evidence (conftest gives each test its own folder)."""
    assert outcomes.directory().resolve() != (ROOT / "var" / "outcomes").resolve()
    assert BS[0][0] == "Cash and cash equivalents"
