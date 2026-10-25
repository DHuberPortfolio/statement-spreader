"""Reading CSV and Excel files into rows that remember where they came from.

Every row keeps its file, sheet and 1-based row number (the number a person sees in Excel,
header included), so any record built from it can be traced back to the cell.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

MAX_ROWS = 200_000
MAX_BYTES = 50 * 1024 * 1024


class TableError(ValueError):
    """The file cannot be read as a table (wrong format, no header, too large)."""


@dataclass(frozen=True)
class RowRef:
    file: str
    row: int  # 1-based, as Excel and a text editor number it (the header is row 1)
    sheet: str | None = None

    def text(self) -> str:
        return f"{self.file}{'!' + self.sheet if self.sheet else ''} row {self.row}"


@dataclass(frozen=True)
class TableRow:
    ref: RowRef
    values: dict[str, str]  # header -> the cell exactly as text
    # Headers of cells that hold a formula with no saved result (read as ""): only filled when asked for, see read_table.
    formulas: frozenset[str] = frozenset()


def _cell_text(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return str(Decimal(str(v)))
    return str(v).strip()


def read_table(name: str, data: bytes, sheet: str | None = None, find_formulas: bool = False) -> tuple[list[str], list[TableRow]]:
    """Return (header, rows). Blank rows are skipped; their numbers are not reused.

    Excel cells are read as their saved values. A formula saved without its result (a file written by a program
    rather than by Excel) reads as an empty cell; with find_formulas=True each row also lists those cells, so a
    caller can say so instead of treating them as blank.
    """
    if len(data) > MAX_BYTES:
        raise TableError(f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB")
    suffix = Path(name).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(name, data, sheet, find_formulas)
    if suffix in (".csv", ".txt", ""):
        return _read_csv(name, data)
    raise TableError(f"{name}: only .csv and .xlsx files are read")


def _clean_header(header: list[str], name: str) -> list[str]:
    cleaned = [h.strip() for h in header]
    if not any(cleaned):
        raise TableError(f"{name}: the first row is empty; it must hold the column names")
    seen: set[str] = set()
    for h in cleaned:
        if h and h in seen:
            raise TableError(f"{name}: column '{h}' appears twice in the header")
        seen.add(h)
    return cleaned


def _read_csv(name: str, data: bytes) -> tuple[list[str], list[TableRow]]:
    if b"\x00" in data[:65536]:
        raise TableError(f"{name} is not a text file (it contains binary data)")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise TableError(f"{name} is not text in UTF-8 or Windows-1252") from exc
    try:
        return _parse_csv(name, csv.reader(io.StringIO(text)))
    except csv.Error as exc:  # a malformed or oversized cell: the file cannot be read as a table
        raise TableError(f"{name} is not a readable CSV ({exc})") from exc


def _parse_csv(name: str, reader: Iterator[list[str]]) -> tuple[list[str], list[TableRow]]:
    try:
        header = _clean_header(next(reader), name)
    except StopIteration as exc:
        raise TableError(f"{name} is empty") from exc
    rows: list[TableRow] = []
    for i, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(rows) >= MAX_ROWS:
            raise TableError(f"{name} has more than {MAX_ROWS} rows")
        values = {h: (cells[j].strip() if j < len(cells) else "") for j, h in enumerate(header) if h}
        if len(cells) > len(header) and any(c.strip() for c in cells[len(header):]):
            values["__extra__"] = " | ".join(c.strip() for c in cells[len(header):] if c.strip())
        rows.append(TableRow(RowRef(name, i), values))
    return header, rows


def _read_xlsx(name: str, data: bytes, sheet: str | None, find_formulas: bool = False) -> tuple[list[str], list[TableRow]]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        formulas_wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False) if find_formulas else None
    except Exception as exc:  # openpyxl raises several types for a bad file
        raise TableError(f"{name} is not a readable Excel workbook ({type(exc).__name__})") from exc
    if sheet is not None and sheet not in wb.sheetnames:
        raise TableError(f"{name} has no sheet '{sheet}' (sheets: {', '.join(wb.sheetnames)})")
    ws = wb[sheet] if sheet else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    raw_rows = None
    if formulas_wb is not None:
        fws = formulas_wb[ws.title]
        raw_rows = fws.iter_rows(values_only=True)
        next(raw_rows, None)
    try:
        header = _clean_header([_cell_text(v) for v in next(it)], name)
    except StopIteration as exc:
        raise TableError(f"{name} sheet '{ws.title}' is empty") from exc
    rows: list[TableRow] = []
    for i, cells in enumerate(it, start=2):
        raw = next(raw_rows, ()) if raw_rows is not None else ()
        texts = [_cell_text(v) for v in cells]
        unsaved = frozenset(h for j, h in enumerate(header) if h and j < len(raw) and j < len(cells) and cells[j] is None
                            and isinstance(raw[j], str) and raw[j].startswith("="))
        if not any(texts) and not unsaved:
            continue
        if len(rows) >= MAX_ROWS:
            raise TableError(f"{name} has more than {MAX_ROWS} rows")
        values = {h: (texts[j] if j < len(texts) else "") for j, h in enumerate(header) if h}
        rows.append(TableRow(RowRef(name, i, ws.title), values, unsaved))
    wb.close()
    if formulas_wb is not None:
        formulas_wb.close()
    return header, rows
