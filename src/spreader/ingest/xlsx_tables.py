"""Excel workbooks (.xlsx) -> DocumentIR.

A cell is the best possible provenance: "Sheet1!C14". Numbers are read from the cell value, not
its display, so 1,234.5 stays 1,234.5 even when the format shows 1,235; the token's text is the
number written plainly so the rest of the pipeline treats it like printed text.

What is refused or skipped, and said so:
- hidden rows and columns (a person reviewing the sheet would not see them);
- formulas with no saved result (a workbook written by a program, never opened in Excel): the
  value is unknown, and computing it ourselves would be guessing;
- workbooks whose uncompressed size is absurd (a "zip bomb").
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from ..contracts import DocumentIR, RawRow, RawTable, SourceFormat, SourceRef, Token
from ..numbers import clean_text, is_amount_like
from . import IngestError, doc_id_for

MAX_UNCOMPRESSED = 200 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLS = 60
MAX_SHEETS = 50
_TITLE = re.compile(r"\b(statements?|balance\s+sheets?)\s+of\b|\bbalance\s+sheets?\b", re.I)
_YEARISH = re.compile(r"^(19|20)\d\d$")
_PERIOD_WORDS = re.compile(r"year|fiscal|ended|ending|period|as of|as at|months|weeks|quarter|december|june|september|march",
                           re.I)


def _format_scaling(fmt: str) -> int:
    """Thousands scaling a number format applies on screen: "#,##0," -> 1, "#,##0,," -> 2."""
    section = fmt.split(";")[0]
    section = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", section)  # drop quoted text, escaped characters, [colors]
    m = re.search(r"[0#?](,+)(?![0#?])", section)
    return len(m.group(1)) if m else 0


def _number_text(v: float | int | Decimal) -> str:
    d = v if isinstance(v, Decimal) else Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    text = f"{abs(d):,}"
    return f"-{text}" if d < 0 else text


def read_xlsx(filename: str, data: bytes) -> DocumentIR:
    doc_id = doc_id_for(data)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total = sum(i.file_size for i in zf.infolist())
    except zipfile.BadZipFile as exc:
        raise IngestError("The workbook is damaged or not an .xlsx file") from exc
    if total > MAX_UNCOMPRESSED:
        raise IngestError(f"The workbook expands to {total / 1e6:.0f} MB; the limit is {MAX_UNCOMPRESSED / 1e6:.0f} MB")
    try:
        wb_values = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
        wb_formulas = load_workbook(io.BytesIO(data), data_only=False, read_only=False)
    except Exception as exc:  # openpyxl raises many types on a damaged file
        raise IngestError(f"Could not open the workbook: {type(exc).__name__}") from exc

    tables: list[RawTable] = []
    warnings: list[str] = []
    for s_index, ws in enumerate(wb_values.worksheets[:MAX_SHEETS]):
        if ws.sheet_state != "visible":
            warnings.append(f"Sheet '{ws.title}' is hidden and was not read.")
            continue
        wf = wb_formulas[ws.title]
        hidden_cols: set[str] = set()
        for d in ws.column_dimensions.values():
            if d.hidden or (d.width is not None and d.customWidth and d.width < 0.5):
                lo, hi = (d.min or 0), (d.max or 0)
                hidden_cols.update(get_column_letter(i) for i in range(max(lo, 1), min(hi, MAX_COLS) + 1))
        merged: dict[tuple[int, int], int] = {}
        for rng in ws.merged_cells.ranges:
            merged[(rng.min_row, rng.min_col)] = rng.max_col
        rows: list[tuple[int, RawRow]] = []
        data_seen = False  # a data row has appeared since the last statement title
        scaled_cells: list[str] = []
        max_row = min(ws.max_row or 0, MAX_ROWS)
        max_col = min(ws.max_column or 0, MAX_COLS)
        if (ws.max_row or 0) > MAX_ROWS:
            warnings.append(f"Sheet '{ws.title}' has more than {MAX_ROWS} rows; only the first {MAX_ROWS} were read.")
        for r in range(1, max_row + 1):
            rd = ws.row_dimensions[r]
            if rd.hidden or (rd.height is not None and rd.customHeight and rd.height < 0.5):
                continue
            tokens: list[Token] = []
            indent = 0.0
            bold = False
            # A row whose only numbers are two or more whole years is a column-header row, wherever
            # it sits on the sheet: write its years as "2024", not as the amount "2,024".
            nums = [ws.cell(row=r, column=c).value for c in range(2, max_col + 1)]
            nums = [x for x in nums if isinstance(x, int | float | Decimal) and not isinstance(x, bool)]
            first = ws.cell(row=r, column=1).value
            if first is not None and _TITLE.search(str(first)):
                data_seen = False
            header_label = first is None or bool(_PERIOD_WORDS.search(str(first)))
            all_years = len(nums) >= 2 and all(float(x).is_integer() and 1900 <= x <= 2100 for x in nums)
            # Before any data in a statement block, or labelled with period words. "Inventories
            # 2,021 | 1,987" after the data has started is data, not a header.
            year_row = all_years and (header_label or not data_seen)
            if len(nums) >= 2 and not year_row:
                data_seen = True
            for c in range(1, max_col + 1):
                letter = get_column_letter(c)
                if letter in hidden_cols:
                    continue
                cell = ws.cell(row=r, column=c)
                v = cell.value
                if v is None:
                    fcell = wf.cell(row=r, column=c)
                    if isinstance(fcell.value, str) and fcell.value.startswith("="):
                        text = "(formula without a saved result)"
                        warnings.append(f"{ws.title}!{letter}{r} is a formula with no saved result; open and save the "
                                        "workbook in Excel so its values are stored.")
                    else:
                        continue
                elif isinstance(v, bool):
                    continue
                elif isinstance(v, datetime | date):
                    # A header typed as a real Excel date: write it the way a statement prints it.
                    text = f"{v:%B} {v.day}, {v.year}"
                elif isinstance(v, int | float) and c > 1 and year_row:
                    v = int(v)
                    # A year typed as a number near the top of the sheet is a column header, not 2,022.
                    text = str(v)
                elif isinstance(v, int | float | Decimal) and re.fullmatch(r"\s*;\s*;\s*;?\s*", cell.number_format or ""):
                    continue  # the ";;;" format shows nothing: a hidden number
                elif isinstance(v, int | float | Decimal):
                    # A format like "#,##0,," shows the stored 1,234,000,000 as "1,234". The unit line
                    # ("in millions") describes what is shown, so read the number as shown.
                    k = _format_scaling(cell.number_format or "")
                    if k:
                        d = Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
                        v = d / (Decimal(1000) ** k)
                        scaled_cells.append(f"{ws.title}!{get_column_letter(c)}{r}")
                    text = _number_text(v)
                else:
                    text = clean_text(str(v))
                    if not text:
                        continue
                if not tokens:
                    lead = len(str(v)) - len(str(v).lstrip(" ")) if isinstance(v, str) else 0
                    indent = float((cell.alignment.indent or 0) * 9 + lead * 3)
                    bold = bool(cell.font and cell.font.b)
                x1 = merged.get((r, c), c) + 1
                ref = SourceRef(doc_id=doc_id, format=SourceFormat.XLSX, table=0, row=r, sheet=ws.title,
                                cell=f"{letter}{r}", text=text)
                tokens.append(Token(text=text, x0=float(c), x1=float(x1), ref=ref))
            if tokens:
                rows.append((r, RawRow(index=r, tokens=tokens, indent=indent, bold=bold)))
        if scaled_cells:
            warnings.append(f"{len(scaled_cells)} cells on sheet '{ws.title}' display a scaled number through their "
                            f"format (e.g. {scaled_cells[0]}); they were read as displayed.")
        for seg in _segments(rows):
            numbers = sum(1 for _, rr in seg for t in rr.tokens if is_amount_like(t.text))
            if numbers < 4:
                continue
            t_index = len(tables)
            raw_rows = []
            for _, rr in seg:
                for t in rr.tokens:
                    t.ref.table = t_index
                raw_rows.append(rr)
            context = f"Sheet {ws.title}. " + " ".join(" ".join(t.text for t in rr.tokens) for _, rr in seg[:5])
            tables.append(RawTable(index=t_index, rows=raw_rows, context=context))
        del s_index
    if not tables:
        raise IngestError("No statement-like tables (labels with columns of numbers) were found in the workbook")
    return DocumentIR(doc_id=doc_id, filename=filename, format=SourceFormat.XLSX, tables=tables, warnings=warnings)


def _segments(rows: list[tuple[int, RawRow]]) -> list[list[tuple[int, RawRow]]]:
    """Split a sheet into statements at a new title or new year headers that follow data."""
    segs: list[list[tuple[int, RawRow]]] = [[]]
    seen_data = False
    for r, row in rows:
        text = " ".join(t.text for t in row.tokens)
        years = sum(1 for t in row.tokens if _YEARISH.match(t.text))
        numbers = sum(1 for t in row.tokens if is_amount_like(t.text) and not _YEARISH.match(t.text))
        if seen_data and numbers == 0 and (bool(_TITLE.search(text)) or years >= 2):
            segs.append([])
            seen_data = False
        segs[-1].append((r, row))
        if numbers >= 2:
            seen_data = True
    return [s for s in segs if s]
