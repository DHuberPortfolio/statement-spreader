"""Opening a workbook for inspection: read from bytes in memory, never written back, never calculated.

The scanner receives the file's bytes and gives openpyxl a copy in memory, so the source file is not opened for
writing at any point (the evaluation hashes every workbook before and after to show it). Two reads of the same
bytes: one for formulas, one for the values Excel saved the last time it calculated (a file written by a program
rather than Excel may have none; the result says so and the value-based checks are skipped).

Refused before openpyxl sees the file: anything that is not an .xlsx/.xlsm zip (old .xls and password-protected
files are OLE containers, and say so), files over the size limits, zips that expand far beyond their size, and XML
that declares a DOCTYPE or entities (openpyxl parses with the standard library, which does not defend against
entity expansion unless defusedxml is installed).
"""

from __future__ import annotations

import io
import re
import warnings
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from finops.core.fingerprint import sha256_bytes

from .config import ScanSpec
from .formula import Parsed, parse, r1c1

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_DTD = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)
_ERRORS = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A", "#GETTING_DATA", "#SPILL!", "#CALC!"}


class WorkbookError(ValueError):
    """The file cannot be scanned; the message says why and what to do."""


@dataclass
class Cell:
    row: int
    col: int
    kind: str  # formula | number | text | bool | date | error
    value: Any  # the typed value, or the formula text
    number_format: str = "General"
    font_color: str | None = None
    comment: str | None = None
    cached: Any = None  # the value Excel saved for a formula (None when the file has none)
    parsed: Parsed | None = None
    sig: str | None = None  # formula in R1C1 form, or "#" for a typed number

    @property
    def is_number(self) -> bool:
        return self.kind == "number"


@dataclass
class Sheet:
    name: str
    state: str  # visible | hidden | veryHidden
    cells: dict[tuple[int, int], Cell] = field(default_factory=dict)
    max_row: int = 0
    max_col: int = 0
    rows: dict[int, list[int]] = field(default_factory=dict)  # row -> sorted columns that hold something

    def get(self, r: int, c: int) -> Cell | None:
        return self.cells.get((r, c))


@dataclass
class Workbook:
    name: str
    sha256: str
    size: int
    sheets: dict[str, Sheet]
    sheet_order: list[str]
    names: dict[str, str]  # lower-case defined name -> its definition ("Sheet1!$B$2")
    name_display: dict[str, str]
    local_names: dict[tuple[str, str], str]  # (sheet lower, name lower) -> definition
    tables: set[str]
    external_links: dict[str, str]  # "[1]" -> target file
    iterative: bool
    has_cached_values: bool
    macros: bool
    formula_count: int = 0

    def sheet(self, name: str | None) -> Sheet | None:
        if name is None:
            return None
        if name in self.sheets:
            return self.sheets[name]
        low = name.lower()
        return next((s for k, s in self.sheets.items() if k.lower() == low), None)


def _precheck(name: str, data: bytes, spec: ScanSpec) -> bool:
    """Returns whether the file carries macros."""
    if len(data) > spec.max_file_mb * 1024 * 1024:
        raise WorkbookError(f"{name} is larger than {spec.max_file_mb:g} MB")
    if data[:8] == _OLE:
        raise WorkbookError(f"{name} is an old-format (.xls) or password-protected workbook. Save it as .xlsx without a "
                            "password and scan that copy.")
    if data[:4] != b"PK\x03\x04":
        raise WorkbookError(f"{name} is not an Excel workbook (.xlsx or .xlsm)")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = z.infolist()
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        raise WorkbookError(f"{name} is damaged: it is not a readable .xlsx package") from exc
    names = {i.filename for i in infos}
    if "xl/workbook.bin" in names:
        raise WorkbookError(f"{name} is a binary workbook (.xlsb). Save it as .xlsx and scan that copy.")
    if "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
        raise WorkbookError(f"{name} is a zip file but not an Excel workbook")
    total = sum(i.file_size for i in infos)
    if total > spec.max_uncompressed_mb * 1024 * 1024:
        raise WorkbookError(f"{name} expands to {total // (1024 * 1024)} MB, over the {spec.max_uncompressed_mb:g} MB limit")
    for i in infos:
        if i.filename.endswith((".xml", ".rels", ".vml")):
            with z.open(i) as f:
                head = f.read(4096)
            if _DTD.search(head):
                raise WorkbookError(f"{name} contains XML with a DOCTYPE or entity declaration ({i.filename}); "
                                    "Excel never writes these, so the file was refused")
    return "xl/vbaProject.bin" in names


def _kind(value: Any, data_type: str) -> str:
    if data_type == "f":
        return "formula"
    if data_type == "e":
        return "error"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, datetime | date | time | timedelta):
        return "date"
    if isinstance(value, int | float):
        return "number"
    return "text"


def _font_color(cell: Any) -> str | None:
    try:
        color = cell.font.color
    except AttributeError:
        return None
    if color is not None and getattr(color, "type", None) == "rgb" and isinstance(color.rgb, str):
        return color.rgb.upper()
    return None


def load(name: str, data: bytes, spec: ScanSpec | None = None) -> Workbook:
    import openpyxl

    spec = spec or ScanSpec()
    macros = _precheck(name, data, spec)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False, keep_links=True)
            values = openpyxl.load_workbook(io.BytesIO(data), data_only=True, keep_links=True)
    except WorkbookError:
        raise
    except Exception as exc:  # openpyxl raises many types for damaged packages
        raise WorkbookError(f"{name} could not be read as a workbook ({type(exc).__name__})") from exc

    sheets: dict[str, Sheet] = {}
    order: list[str] = []
    local: dict[tuple[str, str], str] = {}
    tables: set[str] = set()
    count = 0
    formulas = 0
    cached_any = False
    for ws in wb.worksheets:
        sh = Sheet(ws.title, ws.sheet_state)
        vws = values[ws.title]
        # ws._cells holds only the cells that exist; iterating the used rectangle would visit every empty cell.
        for (r, c), cell in sorted(ws._cells.items()):
            v = cell.value
            if v is None:
                continue
            count += 1
            if count > spec.max_cells:
                raise WorkbookError(f"{name} has more than {spec.max_cells:,} filled cells; split it or raise max_cells")
            dt = cell.data_type
            text = None
            if dt == "f" or (isinstance(v, str) and v.startswith("=") and dt == "f"):
                text = v if isinstance(v, str) else getattr(v, "text", None) or str(v)
            elif hasattr(v, "text") and type(v).__name__ in ("ArrayFormula", "DataTableFormula"):
                dt, text = "f", getattr(v, "text", None) or "=" + str(getattr(v, "ref", ""))
            kind = _kind(v, dt)
            comment = cell.comment.text if cell.comment is not None else None
            c_obj = Cell(r, c, kind, text if kind == "formula" else v, cell.number_format or "General", _font_color(cell), comment)
            if kind == "formula":
                formulas += 1
                c_obj.value = text if str(text).startswith("=") else "=" + str(text)
                c_obj.parsed = parse(c_obj.value)
                c_obj.sig = r1c1(c_obj.parsed, r, c, ws.title)
                cv = vws.cell(r, c).value
                c_obj.cached = cv
                cached_any = cached_any or cv is not None
            elif kind == "number":
                c_obj.sig = "#"
            sh.cells[(r, c)] = c_obj
            sh.rows.setdefault(r, []).append(c)
            sh.max_row, sh.max_col = max(sh.max_row, r), max(sh.max_col, c)
        for cols in sh.rows.values():
            cols.sort()
        try:
            for nm, dn in ws.defined_names.items():
                local[(ws.title.lower(), nm.lower())] = str(dn.attr_text or "")
        except AttributeError:
            pass
        tables.update(t.lower() for t in ws.tables)
        sheets[ws.title] = sh
        order.append(ws.title)

    names: dict[str, str] = {}
    display: dict[str, str] = {}
    for nm, dn in wb.defined_names.items():
        names[nm.lower()] = str(dn.attr_text or "")
        display[nm.lower()] = nm
    links: dict[str, str] = {}
    for i, link in enumerate(getattr(wb, "_external_links", []) or [], 1):
        target = getattr(getattr(link, "file_link", None), "Target", None) or f"external workbook {i}"
        links[f"[{i}]"] = str(target)
    calc = getattr(wb, "calculation", None)
    return Workbook(name, sha256_bytes(data), len(data), sheets, order, names, display, local, tables, links,
                    bool(getattr(calc, "iterate", False)), cached_any, macros, formulas)
