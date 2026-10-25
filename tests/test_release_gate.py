"""The release gate and the evaluation manifests: each rule is shown to fire on a planted defect."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from finops import evalsets, gate

ROOT = Path(__file__).resolve().parents[1]


def _base() -> dict[str, Any]:
    return {"provenance": {"created": "t", "commit": "abc"},
            "sets": {"statements-synthetic": {"engine": "statements", "dataset": "v1", "crashes": [],
                                              "metrics": {"silent_errors": [6, 13452]},
                                              "failures": {"a.html is_revenue FY2025": 1, "b.pdf is_cogs FY2025": 2}},
                     "recon-dev": {"engine": "recon", "dataset": "r1", "crashes": [],
                                   "metrics": {"false_automatic_matches": [0, 213]}, "failures": {}}}}


def test_an_identical_run_passes() -> None:
    assert gate.compare(_base(), copy.deepcopy(_base())) == []


def test_a_changed_dataset_is_never_compared_silently() -> None:
    run = copy.deepcopy(_base())
    run["sets"]["recon-dev"]["dataset"] = "r2"
    assert any("dataset version r2" in p for p in gate.compare(_base(), run))


def test_a_new_crash_fails() -> None:
    run = copy.deepcopy(_base())
    run["sets"]["statements-synthetic"]["crashes"] = ["c.pdf: ValueError"]
    assert any("new crash" in p for p in gate.compare(_base(), run))


def test_a_rate_above_the_baselines_upper_bound_fails() -> None:
    run = copy.deepcopy(_base())
    run["sets"]["statements-synthetic"]["metrics"]["silent_errors"] = [30, 13452]  # upper bound of 6 of 13,452 is ~0.1%
    assert any("above the baseline's 95% upper bound" in p for p in gate.compare(_base(), run))


def test_one_more_wrong_item_fails_even_inside_the_range() -> None:
    """7 of 13,452 is inside 6 of 13,452's range; on a deterministic set it is still one value that broke."""
    run = copy.deepcopy(_base())
    run["sets"]["statements-synthetic"]["metrics"]["silent_errors"] = [7, 13452]
    run["sets"]["statements-synthetic"]["failures"]["c.xlsx bs_cash FY2025"] = 2
    problems = gate.compare(_base(), run)
    assert any("rose from 6 to 7" in p for p in problems)
    assert any("c.xlsx bs_cash FY2025: right in the baseline, now silent" in p for p in problems)


def test_a_value_that_was_caught_and_is_now_silent_fails() -> None:
    run = copy.deepcopy(_base())
    run["sets"]["statements-synthetic"]["failures"]["a.html is_revenue FY2025"] = 2
    assert any("caught in the baseline, now silent" in p for p in gate.compare(_base(), run))


def test_improvements_pass_and_are_reported() -> None:
    run = copy.deepcopy(_base())
    del run["sets"]["statements-synthetic"]["failures"]["b.pdf is_cogs FY2025"]
    run["sets"]["statements-synthetic"]["metrics"]["silent_errors"] = [5, 13452]
    assert gate.compare(_base(), run) == []
    assert gate.improvements(_base(), run) == ["statements-synthetic: 1 item(s) better than the baseline (refresh the baseline to lock them in)"]


def test_a_planted_defect_in_a_real_engine_fails_the_committed_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: reconciliation run with the naive greedy strategy instead of the default, against the committed
    baseline. Greedy makes false automatic matches on the round-amount stress set (IMPROVEMENT_LOG P1, P2)."""
    from finops.recon import evaluate as recon_eval

    real = recon_eval.evaluate

    def greedy(profile: Any, *a: Any) -> Any:
        p = profile.model_copy(update={"matching": profile.matching.model_copy(update={"strategy": "greedy"})})
        return real(p, *a)

    monkeypatch.setattr(recon_eval, "evaluate", greedy)
    baseline = json.loads(gate.BASELINE.read_text(encoding="utf-8"))
    baseline["sets"] = {k: v for k, v in baseline["sets"].items() if v["engine"] == "recon"}
    run = gate.snapshot(["recon"])
    problems = gate.compare(baseline, run)
    assert any(p.startswith("recon-stress: new failure: false automatic match") for p in problems)
    assert any("need_a_person_but_auto_accepted" in p for p in problems)


def test_the_unchanged_engines_pass_the_committed_baseline_on_the_fast_sets() -> None:
    baseline = json.loads(gate.BASELINE.read_text(encoding="utf-8"))
    baseline["sets"] = {k: v for k, v in baseline["sets"].items() if v["engine"] in ("recon", "dq", "sheets")}
    assert gate.compare(baseline, gate.snapshot(["recon", "dq", "sheets"])) == []


# -- manifests ------------------------------------------------------------------------------------------------------

def test_every_set_matches_its_committed_manifest() -> None:
    for name, build in evalsets.registry().items():
        ds = build()
        manifest = json.loads((evalsets.MANIFESTS / f"{name}.json").read_text(encoding="utf-8"))
        assert manifest["version"] == ds.version, name


def test_an_edited_answer_key_changes_the_version_and_its_key_version(tmp_path: Path) -> None:
    src = ROOT / "eval" / "dq" / "independent-1"
    shutil.copytree(src, tmp_path / "set")
    before = evalsets._folder("x", tmp_path / "set")
    truth = tmp_path / "set" / "truth.json"
    truth.write_bytes(truth.read_bytes().replace(b'"accepted"', b'"review"', 1))
    after = evalsets._folder("x", tmp_path / "set")
    assert after.version != before.version and after.key_version != before.key_version
    (tmp_path / "set" / "README.md").write_text("notes only")  # documentation is not part of the data
    assert evalsets._folder("x", tmp_path / "set").version == after.version


def test_generated_workbooks_are_hashed_by_content_not_by_save_time() -> None:
    from openpyxl import Workbook

    from finops.core.fingerprint import stable_xlsx

    wb = Workbook()
    wb.active["A1"] = "=B1*2"
    a = stable_xlsx(wb)
    assert stable_xlsx(wb) == a  # the same bytes, whatever the clock says
    wb.active["A1"] = "=B1*3"
    assert evalsets.workbook_content_hash(stable_xlsx(wb)) != evalsets.workbook_content_hash(a)


def test_reports_carry_provenance(tmp_path: Path) -> None:
    from finops.core.evaluation import write_report

    path = write_report("t", {"x": 1}, ["# t"], directory=tmp_path, datasets=["recon-dev", "unknown"], config={"profile": "p 1"})
    report = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    prov = report["provenance"]
    assert prov["commit"] and prov["created"] and prov["config"] == {"profile": "p 1"}
    assert prov["datasets"][0]["name"] == "recon-dev" and prov["datasets"][0]["matches_manifest"] is True
    assert prov["datasets"][1]["version"] is None
    assert "Provenance:" in path.read_text(encoding="utf-8")
