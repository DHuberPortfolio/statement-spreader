"""A simulated workspace says so, and is never written over real data (D69)."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

from conftest import client_as

from spreader import api

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import simulate_two_weeks as sim  # noqa: E402


def test_a_real_workspace_is_not_marked_simulated() -> None:
    assert client_as(api.app, "pat").get("/api/health").json()["simulated"] is None


def test_a_marked_workspace_says_so() -> None:
    svc = api.service()
    with svc.store.tx() as c:
        c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('simulated', 'two weeks')")
    try:
        assert client_as(api.app, "pat").get("/api/health").json()["simulated"] == "two weeks"
    finally:
        with svc.store.tx() as c:
            c.execute("DELETE FROM meta WHERE key='simulated'")


def test_the_simulation_refuses_a_folder_that_already_exists(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, str(ROOT / "scripts/simulate_two_weeks.py"), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode != 0 and "already exists" in r.stderr


def test_ten_working_days_skip_the_weekend() -> None:
    days = sim.working_days(date(2026, 11, 4))
    assert len(days) == 10 and days[0] == date(2026, 10, 22) and all(d.weekday() < 5 for d in days)


def test_the_clock_only_moves_forward() -> None:
    from datetime import UTC, datetime

    clock = sim.Clock()
    clock.set(datetime(2026, 11, 2, tzinfo=UTC))
    clock.set(datetime(2026, 11, 1, tzinfo=UTC))
    assert clock.now().startswith("2026-11-02")
