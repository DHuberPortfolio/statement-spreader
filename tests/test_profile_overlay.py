"""Adapting to a new organisation by configuration only: an overlay profile."""

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import statement_html

from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.profile import PROFILE_DIR, load_profile

UK_IS = [
    ("Turnover", "500", "400"),
    ("Cost of sales", "300", "240"),
    ("Gross profit", "200", "160"),
    ("Selling, general and administrative", "100", "80"),
    ("Operating income", "100", "80"),
    ("Interest expense", "(50)", "(10)"),
    ("Profit before taxation", "50", "70"),
    ("Income tax expense", "10", "14"),
    ("Profit for the year", "40", "56"),
]


@pytest.fixture(scope="module")
def lender():  # type: ignore[no-untyped-def]
    return load_profile(PROFILE_DIR / "example-lender-overlay.yaml")


def _spread(profile):  # type: ignore[no-untyped-def]
    html = statement_html("CONSOLIDATED INCOME STATEMENT", "(In thousands)",
                          ["Year Ended December 31, 2025", "Year Ended December 31, 2024"], UK_IS)
    return spread_document(read_document("uk.htm", html.encode()), profile)[0]


def test_overlay_maps_the_organisations_labels(lender) -> None:  # type: ignore[no-untyped-def]
    sp = _spread(lender)
    assert sp.value("revenue", "2025-12-31/12M").value == Decimal(500_000)
    assert sp.value("net_income", "2025-12-31/12M").value == Decimal(40_000)
    assert sp.profile_id == "example-lender"


def test_base_profile_is_unchanged(profile) -> None:  # type: ignore[no-untyped-def]
    assert "turnover" not in profile.lines["revenue"].aliases
    sp = _spread(profile)
    assert "income_statement" not in sp.statements  # without the overlay, "profit for the year" is not recognised


def test_covenant_breach_is_a_blocker(lender) -> None:  # type: ignore[no-untyped-def]
    sp = _spread(lender)
    # 2025: EBIT 100 / interest 50 = 2.0x, below the 3.0x minimum. 2024: 80 / 10 = 8.0x, fine.
    cov = {i.id: i for i in sp.review if i.id.startswith("covenant:covenant_interest_cover")}
    assert cov["covenant:covenant_interest_cover:2025-12-31/12M"].severity.value == "blocker"
    assert "covenant:covenant_interest_cover:2024-12-31/12M" not in cov


def test_overlay_cannot_reach_outside_the_profile_folder(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bad = tmp_path / "evil.yaml"
    bad.write_text("extends: ../../etc/passwd\nid: x\n", encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        load_profile(bad)
