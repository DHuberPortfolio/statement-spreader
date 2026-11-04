"""Test batches read as plain words, and the results pages get the newest of each batch (D64)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import client_as

from spreader import api
from spreader.report_names import describe_report, latest_batches


@pytest.mark.parametrize(("name", "title"), [
    ("stmt-insurer-dev-d62", "Insurers, practice set, update 62"),
    ("stmt-bank-holdout-d61", "Banks, validation set, update 61"),
    ("stmt-holdout-d62", "Public companies, validation set, update 62"),
    ("stmt-dev", "Public companies, practice set"),
    ("stmt-insurer-holdout-merged", "Insurers, validation set (merged)"),
    ("syn-after-fixes", "Generated statements (after fixes)"),
    ("stmt-syn-v5", "Generated statements (v5)"),
    ("xbrl-check", "Xbrl check"),
])
def test_a_report_name_becomes_plain_words(name: str, title: str) -> None:
    assert describe_report(name)["title"] == title


def _report(folder: Path, stem: str, wrong: int = 0) -> None:
    rates = {"silent_error_rate": {"n": wrong, "d": 100, "rate": wrong / 100, "low": 0, "high": 0.1}}
    (folder / f"{stem}.json").write_text(json.dumps({
        "name": stem, "documents": 3, "rates": rates, "buckets": {"wrong_auto": wrong}, "error_kinds": {}}))


def test_the_newest_is_the_highest_update_not_the_newest_file(tmp_path: Path) -> None:
    _report(tmp_path, "stmt-holdout-d9")
    _report(tmp_path, "stmt-holdout-d62")
    _report(tmp_path, "stmt-holdout-d10")
    _report(tmp_path, "stmt-holdout-d70-merged")
    assert latest_batches(tmp_path)[("public", "holdout")].stem == "stmt-holdout-d62"


def test_the_summary_gives_each_kind_of_company_its_newest_results(tmp_path: Path, monkeypatch: Any) -> None:
    _report(tmp_path, "stmt-holdout-d61", wrong=9)
    _report(tmp_path, "stmt-holdout-d62", wrong=5)
    _report(tmp_path, "stmt-dev-d62")
    _report(tmp_path, "stmt-bank-holdout-d62", wrong=1)
    monkeypatch.setattr(api, "REPORTS", tmp_path)
    groups = client_as(api.app, "pat").get("/api/evaluation/summary").json()["groups"]
    assert [g["title"] for g in groups] == ["Public companies", "Banks"]
    assert groups[0]["holdout"]["rates"]["silent_error_rate"]["n"] == 5
    assert groups[0]["dev"]["update"] == 62 and "dev" not in groups[1]


def test_every_report_says_what_it_is(tmp_path: Path, monkeypatch: Any) -> None:
    _report(tmp_path, "stmt-insurer-dev-d62")
    monkeypatch.setattr(api, "REPORTS", tmp_path)
    got = client_as(api.app, "pat").get("/api/evaluation").json()["reports"]
    assert got[0]["about"]["title"] == "Insurers, practice set, update 62" and got[0]["file"] == "stmt-insurer-dev-d62.json"


def test_the_summary_says_when_there_is_no_sealed_result_yet(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(api, "REPORTS", tmp_path)
    assert client_as(api.app, "pat").get("/api/evaluation/summary").json()["wide"] is None


def test_the_summary_carries_the_sealed_result_without_filing_detail(tmp_path: Path, monkeypatch: Any) -> None:
    block = {"filings": 2}
    (tmp_path / "wide-sealed-first-look.json").write_text(json.dumps(
        {"all": block, "by_sector": {"retail": block}, "by_form": {"10-K": block}, "by_size": {"mid": block}, "documents": [{"doc": "x"}]}))
    monkeypatch.setattr(api, "REPORTS", tmp_path)
    wide = client_as(api.app, "pat").get("/api/evaluation/summary").json()["wide"]
    assert wide["all"] == block and "documents" not in wide

