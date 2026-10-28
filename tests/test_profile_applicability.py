"""Industry profiles say which base checks and ratios do not apply, and change nothing else (DECISIONS D50)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from spreader.profile import _overlay, load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "config" / "profiles"


def test_banks_and_insurers_do_not_run_corporate_checks_and_ratios_that_cannot_hold() -> None:
    base = load_profile()
    for name, expected in {
        "us-bank": {"check:is_gross_profit", "check:bs_current_assets", "ratio:current_ratio", "ratio:interest_coverage",
                    "ratio:ebitda", "ratio:dso"},
        "us-insurer": {"check:is_gross_profit", "check:bs_current_liabilities", "ratio:quick_ratio", "ratio:dio"},
    }.items():
        p = load_profile(PROFILES / f"{name}.yaml")
        assert expected <= set(p.not_applicable), name
        running = {f"check:{c.id}" for c in p.checks} | {f"ratio:{r.id}" for r in p.ratios}
        assert not (set(p.not_applicable) & running), "declared not applicable but still running"
        assert all(len(why) > 20 for why in p.not_applicable.values()), "every exclusion says why"
        # nothing else changed: a base check or ratio the overlay does not redefine in its own file is the base's
        raw = yaml.safe_load((PROFILES / f"{name}.yaml").read_text(encoding="utf-8"))
        declared = {d["id"] for d in (raw.get("checks") or []) + (raw.get("ratios") or [])}
        for c in p.checks:
            b = next((x for x in base.checks if x.id == c.id), None)
            assert b is None or c.id in declared or b == c, f"{name} silently changed check {c.id}"
        for r in p.ratios:
            b = next((x for x in base.ratios if x.id == r.id), None)
            assert b is None or r.id in declared or b == r, f"{name} silently changed ratio {r.id}"
    assert load_profile().not_applicable == {}, "the commercial template excludes nothing"


def test_mistakes_in_not_applicable_are_refused() -> None:
    base = yaml.safe_load((PROFILES / "us-commercial.yaml").read_text(encoding="utf-8"))
    for bad in ({"not_applicable": {"checks": {"is_gross_proft": "typo in the id"}}},
                {"not_applicable": {"checks": {"is_gross_profit": " "}}},
                {"not_applicable": {"lines": {"revenue": "lines cannot be removed"}}}):
        with pytest.raises(ValueError):
            _overlay(base, bad)


def test_the_profile_api_shows_what_does_not_apply(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from conftest import client_as
    from spreader import api
    from spreader.service import Service
    from spreader.store import Store

    svc = Service(Store(tmp_path / "db.sqlite3"), profile=load_profile(PROFILES / "us-bank.yaml"))
    monkeypatch.setattr(api, "service", lambda: svc)
    out = client_as(api.app, "vic").get("/api/profile").json()
    assert "ratio:current_ratio" in out["not_applicable"]
    assert "current_ratio" not in {r["id"] for r in out["ratios"]}
