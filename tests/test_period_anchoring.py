"""Period dating anchored on the balance sheet, gaps flagged, assumed columns flagged in full (2026-10-24, late).

Uses two cached SEC filings (eval/sec/raw is downloaded by scripts/fetch_sec.py; the tests skip without it):
Disney (fiscal years end on a Saturday near September 30) and Hasbro (a late-December 52/53-week year).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spreader.contracts import ReviewKind
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"


def spread(ticker: str):  # type: ignore[no-untyped-def]
    manifest = json.loads((SEC / "manifest.json").read_text())
    f = SEC / "raw" / manifest[ticker]["file"]
    if not f.exists():
        pytest.skip(f"{ticker} filing not downloaded")
    sp, _ = spread_document(read_document(f.name, f.read_bytes()), load_profile())
    return sp


def test_full_year_columns_take_the_balance_sheet_date() -> None:
    sp = spread("DIS")
    keys = {p.key for res in sp.statements.values() for p in res.table.periods}
    assert "2025-09-27/12M" in keys and "2025-11-13/12M" not in keys  # not the audit report's date
    assert "2023-12-31/12M" not in keys  # the year-only column follows the fiscal year-end day, as an assumption
    assumed = [it for it in sp.review if it.kind is ReviewKind.ASSUMED_PERIOD and any(p.startswith("2023-") for p in it.periods)]
    assert assumed, "the guessed 2023 date must stay visible to a reviewer"


def test_late_december_years_keep_december_31() -> None:
    sp = spread("HAS")
    keys = {p.key for res in sp.statements.values() for p in res.table.periods}
    assert "2023-12-31/12M" in keys and "2023-12-28/12M" not in keys


def test_calculated_lines_in_an_assumed_column_are_flagged() -> None:
    sp = spread("HAS")
    assumed = {p for it in sp.review if it.kind is ReviewKind.ASSUMED_PERIOD for p in it.periods}
    calc = [v for v in sp.values if v.period in assumed and v.status.value == "calculated" and v.value is not None]
    assert calc and all(v.flags for v in calc)
