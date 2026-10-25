"""The opt-in XBRL second reader (D37): the tag on each printed cell, compared with what the reader read."""

from __future__ import annotations

from typing import Any

import pytest

from spreader.contracts import ReviewKind
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.second_reader import compare, tagged_cells

CONTEXTS = """
<xbrli:context id="d25"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="d24"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="i24"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="e25"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="i23"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
"""


def _cell(concept: str, ctx: str, text: str, scale: int = 6) -> str:
    return (f'<td>$</td><td><ix:nonFraction name="us-gaap:{concept}" contextRef="{ctx}" unitRef="usd" decimals="-6" '
            f'scale="{scale}">{text}</ix:nonFraction></td><td></td>')


def _row(label: str, concept: str, v25: str, v24: str, scale24: int = 6, ctx25: str = "d25", ctx24: str = "d24") -> tuple[str, str]:
    return label, _cell(concept, ctx25, v25) + _cell(concept, ctx24, v24, scale24)


def _doc(revenue_2024_scale: int = 6, opening_cash_ctx: str = "i24") -> bytes:
    income = [_row("Net sales", "Revenues", "400", "250", scale24=revenue_2024_scale),
              _row("Cost of sales", "CostOfRevenue", "150", "100"),
              _row("Gross margin", "GrossProfit", "250", "150"),
              _row("Research and development", "ResearchAndDevelopmentExpense", "50", "40"),
              _row("Selling, general and administrative", "SellingGeneralAndAdministrativeExpense", "30", "20"),
              _row("Total operating expenses", "OperatingExpenses", "80", "60"),
              _row("Operating income", "OperatingIncomeLoss", "170", "90"),
              _row("Provision for income taxes", "IncomeTaxExpenseBenefit", "40", "20"),
              _row("Net income", "NetIncomeLoss", "130", "70")]
    cash = [_row("Net income", "NetIncomeLoss", "130", "70"),
            _row("Depreciation and amortization", "DepreciationDepletionAndAmortization", "20", "15"),
            _row("Net cash provided by operating activities", "NetCashProvidedByUsedInOperatingActivities", "150", "85"),
            _row("Purchases of property and equipment", "PaymentsToAcquirePropertyPlantAndEquipment", "(60)", "(40)"),
            _row("Net cash used in investing activities", "NetCashProvidedByUsedInInvestingActivities", "(60)", "(40)"),
            _row("Dividends paid", "PaymentsOfDividends", "(30)", "(35)"),
            _row("Net cash used in financing activities", "NetCashProvidedByUsedInFinancingActivities", "(30)", "(35)"),
            _row("Net increase in cash and cash equivalents", "CashPeriodIncreaseDecrease", "60", "10"),
            _row("Cash and cash equivalents, beginning of year", "CashAndCashEquivalentsAtCarryingValue", "90", "80",
                 ctx25=opening_cash_ctx, ctx24="i23"),
            _row("Cash and cash equivalents, end of year", "CashAndCashEquivalentsAtCarryingValue", "150", "90",
                 ctx25="e25", ctx24="i24")]

    def table(title: str, body: list[tuple[str, str]]) -> str:
        head = '<tr><td></td><td colspan="3">Year Ended December 31, 2025</td><td colspan="3">Year Ended December 31, 2024</td></tr>'
        return (f"<p>{title}</p><p>(In millions)</p><table>{head}"
                + "".join(f"<tr><td>{label}</td>{cells}</tr>" for label, cells in body) + "</table>")

    return ('<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance" '
            'xmlns:us-gaap="http://fasb.org/us-gaap/2024"><body>'
            f'<div style="display:none"><ix:header><ix:resources>{CONTEXTS}</ix:resources></ix:header></div>'
            + table("CONSOLIDATED STATEMENTS OF OPERATIONS", income)
            + table("CONSOLIDATED STATEMENTS OF CASH FLOWS", cash) + "</body></html>").encode()


def _spread(data: bytes, profile: Any, tags: bool) -> Any:
    return spread_document(read_document("x.htm", data), profile, tags=tagged_cells(data) if tags else None)[0]


def test_agreeing_tags_add_nothing(profile: Any) -> None:
    data = _doc()
    spread = _spread(data, profile, tags=False)
    comp = compare(spread, tagged_cells(data))
    assert comp.cells >= 10 and comp.agree == comp.cells and not comp.items


def test_opening_cash_tagged_at_the_start_of_the_year_agrees(profile: Any) -> None:
    """Printed in the 2025 column, tagged as the balance at December 31, 2024: the same number (found on every SEC
    filing's cash-flow statement before this rule)."""
    data = _doc(opening_cash_ctx="i24")
    assert not compare(_spread(data, profile, tags=False), tagged_cells(data)).items
    wrong = _doc(opening_cash_ctx="i23")  # the same 90, tagged two years back: a real period disagreement
    comp = compare(_spread(wrong, profile, tags=False), tagged_cells(wrong))
    assert comp.kinds == {"period": 1}


def test_a_scale_disagreement_is_a_warning_on_that_value_only(profile: Any) -> None:
    data = _doc(revenue_2024_scale=3)  # the tag says 250 thousand; the page says millions
    spread = _spread(data, profile, tags=True)
    items = [i for i in spread.review if i.kind is ReviewKind.SECOND_READER]
    assert [(i.lines, i.periods) for i in items] == [(["revenue"], ["2024-12-31/12M"])]
    assert "250,000" in items[0].message and "power of ten" in items[0].message
    flagged = {v.line for v in spread.values if v.period == "2024-12-31/12M" and items[0].id in v.flags}
    assert flagged == {"revenue"}


def test_off_by_default(profile: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from spreader.service import Service
    from spreader.store import Store

    data = _doc(revenue_2024_scale=3)
    monkeypatch.delenv("SPREADER_XBRL_CHECK", raising=False)
    svc = Service(Store(tmp_path / "a.sqlite3"), profile=profile)
    _, off = svc.upload("x.htm", data, "dana")
    assert not any(i.kind is ReviewKind.SECOND_READER for i in off.spread.review)
    monkeypatch.setenv("SPREADER_XBRL_CHECK", "1")
    on = svc.run(off.run["document_id"], "dana")  # a different mode is a different run
    assert on.run["id"] != off.run["id"]
    assert any(i.kind is ReviewKind.SECOND_READER for i in on.spread.review)


def test_documents_without_tags_compare_nothing(profile: Any) -> None:
    assert tagged_cells(b"%PDF-1.4 not xml") == {}
    assert tagged_cells(b"<html><body><table><tr><td>1</td></tr></table></body></html>") == {}
