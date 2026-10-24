"""The ROI model's honesty rules, with hand-worked numbers."""

from __future__ import annotations

import pytest

from spreader import roi


def _inputs(sessions: list[roi.Session], **overrides: float) -> roi.RoiInputs:
    a = {k: (v, "default") for k, (v, _) in roi.DEFAULT_ASSUMPTIONS.items()}
    for k, v in overrides.items():
        a[k] = (v, "entered")
    return roi.RoiInputs(assumptions=a, sessions=sessions, compute_seconds=[1.0, 2.0])


def test_no_sessions_means_not_measured_never_zero() -> None:
    rep = roi.compute(_inputs([]))
    assert rep.numbers["minutes_saved"].value is None
    assert rep.numbers["capacity_hours"].value is None
    assert any("placeholders" in w for w in rep.warnings)


def test_two_sessions_are_not_enough() -> None:
    s = [roi.Session("baseline", "d1", 1800), roi.Session("assisted", "d1", 600)] * 2
    rep = roi.compute(_inputs(s))
    assert rep.numbers["minutes_saved"].value is None


def test_paired_sessions_hand_worked() -> None:
    # Three documents, each 30 min by hand and 10 min assisted: 20 minutes saved per document.
    s = []
    for d in ("a", "b", "c"):
        s += [roi.Session("baseline", d, 1800), roi.Session("assisted", d, 600)]
    rep = roi.compute(_inputs(s, documents_per_month=60, analyst_hourly_cost=90))
    saved = rep.numbers["minutes_saved"]
    assert saved.value == pytest.approx(20.0) and saved.label == "observed" and saved.n == 3
    # 20 min x 60 docs / 60 = 20 hours a month, worth 20 x 90 = 1,800 of capacity...
    assert rep.numbers["capacity_hours"].value == pytest.approx(20.0)
    assert rep.numbers["capacity_value"].value == pytest.approx(1800.0)
    # ...but no cash is claimed until a cash-realisation share is entered.
    assert rep.numbers["cash_savings"].value == 0
    assert rep.numbers["payback_months_cash"].value is None
    assert any("No payback" in w for w in rep.warnings)


def test_cash_only_from_the_entered_share() -> None:
    s = []
    for d in ("a", "b", "c"):
        s += [roi.Session("baseline", d, 1800), roi.Session("assisted", d, 600)]
    rep = roi.compute(_inputs(s, documents_per_month=60, analyst_hourly_cost=90, cash_realization_share=0.5,
                              maintenance_hours_per_month=2, engineer_hourly_cost=100, infrastructure_per_month=0,
                              implementation_hours=40))
    # cash 900 - running 200 = 700 a month; implementation 4,000 -> payback 4,000 / 700 months.
    assert rep.numbers["cash_savings"].value == pytest.approx(900.0)
    assert rep.numbers["net_monthly_cash"].value == pytest.approx(700.0)
    assert rep.numbers["payback_months_cash"].value == pytest.approx(4000 / 700)


def test_review_time_counts_against_the_tool() -> None:
    # Assisted review slower than doing it by hand: savings are negative, not hidden.
    s = []
    for d in ("a", "b", "c"):
        s += [roi.Session("baseline", d, 600), roi.Session("assisted", d, 900)]
    rep = roi.compute(_inputs(s))
    assert rep.numbers["minutes_saved"].value == pytest.approx(-5.0)
    assert rep.numbers["capacity_hours"].value < 0
