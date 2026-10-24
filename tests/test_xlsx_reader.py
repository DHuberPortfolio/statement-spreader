"""The Excel reader on small workbooks built in the test."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from spreader.ingest import IngestError, read_document
from spreader.pipeline import spread_document


def _book(hidden_row: bool = False, formula: bool = False) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Balance sheet"
    rows = [
        ["Acme Corp. Consolidated Balance Sheets"],
        ["(In thousands)"],
        [None, "December 31, 2025", "December 31, 2024"],
        ["Current assets:"],
        ["  Cash and cash equivalents", 100, 80],
        ["  Accounts receivable, net", 50.5, 40],
        ["Total current assets", 150.5, 120],
        ["Property and equipment, net", 249.5, 220],
        ["Total assets", 400, 340],
        ["Accounts payable", 60, 50],
        ["Total current liabilities", 60, 50],
        ["Long-term debt", 140, 130],
        ["Total liabilities", 200, 180],
        ["Retained earnings", 200, 160],
        ["Total stockholders' equity", 200, 160],
        ["Total liabilities and stockholders' equity", 400, 340],
    ]
    for r in rows:
        ws.append(r)
    if hidden_row:
        ws.insert_rows(6)
        ws["A6"] = "Other current assets"
        ws["B6"] = 999999
        ws["C6"] = 999999
        ws.row_dimensions[6].hidden = True
    if formula:
        ws["B9"] = "=B7+B8"  # no saved result: openpyxl does not calculate
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reads_cells_with_exact_provenance(profile) -> None:  # type: ignore[no-untyped-def]
    ir = read_document("bs.xlsx", _book())
    spread, _ = spread_document(ir, profile)
    cash = spread.value("cash", "2025-12-31/I")
    assert cash is not None and cash.value == Decimal(100_000)
    assert cash.refs[0].sheet == "Balance sheet" and cash.refs[0].cell == "B5"
    ar = spread.value("receivables", "2025-12-31/I")
    assert ar.value == Decimal("50500")  # 50.5 thousand, not rounded to 51
    assert not [c for c in spread.checks if c.status.value == "fail"]


def test_hidden_rows_are_not_read(profile) -> None:  # type: ignore[no-untyped-def]
    ir = read_document("bs.xlsx", _book(hidden_row=True))
    spread, _ = spread_document(ir, profile)
    assert spread.value("other_current_assets", "2025-12-31/I") is None


def test_formula_without_saved_value_is_not_guessed(profile) -> None:  # type: ignore[no-untyped-def]
    ir = read_document("bs.xlsx", _book(formula=True))
    assert any("no saved result" in w for w in ir.warnings)
    spread, _ = spread_document(ir, profile)
    ta = spread.value("total_assets", "2025-12-31/I")
    assert ta is None or ta.value != Decimal(400_000) or ta.status.value == "calculated"


def test_damaged_workbook_is_refused() -> None:
    with pytest.raises(IngestError):
        read_document("x.xlsx", b"PK\x03\x04" + b"\x00" * 100)
