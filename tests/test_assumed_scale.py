"""A statement whose unit is assumed flags its calculated lines too (2026-10-24, evening).

Johnson & Johnson's 10-K prints no "in millions" near its income statement, so its values were taken as printed and
the lines read from the table were flagged for review. Net income to the company, calculated from net income, was not
flagged and went out a million times too small, auto-accepted (2 silent errors on the holdout). The same fix was made
for assumed period columns earlier the same day.
"""

from __future__ import annotations

from conftest import statement_html
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from test_redteam import HEAD, IS


def test_calculated_lines_carry_the_assumed_unit_flag(profile) -> None:  # type: ignore[no-untyped-def]
    doc = statement_html("STATEMENTS OF OPERATIONS", "", HEAD, IS)
    spread, _ = spread_document(read_document("u.htm", doc.encode()), profile)
    net = spread.value("net_income", "2025-12-31/12M")
    parent = spread.value("net_income_parent", "2025-12-31/12M")
    assert net is not None and "scale:income_statement" in net.flags
    assert parent is not None and parent.status.value == "calculated"
    assert "scale:income_statement" in parent.flags
