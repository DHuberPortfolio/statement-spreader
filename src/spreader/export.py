"""Exports: an Excel workbook an analyst can use, a long CSV for systems, and JSON.

Every export carries what it is: the document hash, profile version, run id, approval state,
and the status of every value (extracted, calculated, corrected...). An export of an unapproved
spread says so on its first sheet.

Text from documents can start with "=" or "+" and would become a live formula in Excel or a
spreadsheet opened from CSV ("formula injection"). Such text is written as plain text in Excel
and prefixed with an apostrophe in CSV.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .contracts import Spread, ValueStatus
from .profile import Profile

STATUS_FILL = {
    ValueStatus.EXTRACTED: None,
    ValueStatus.NORMALIZED: "EEF3FB",
    ValueStatus.CALCULATED: "F1EEFB",
    ValueStatus.AI_MAPPED: "FFF4DB",
    ValueStatus.HUMAN: "E6F4EA",
    ValueStatus.ASSUMED: "FDECEA",
    ValueStatus.MISSING: "F2F2F2",
}
DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _safe_text(s: str) -> str:
    return "'" + s if s.startswith(DANGEROUS) else s


def _put(ws: Any, row: int, col: int, value: Any) -> Any:
    cell = ws.cell(row=row, column=col)
    if isinstance(value, Decimal):
        cell.value = float(value) if abs(value) < Decimal("1e15") else str(value)
    elif isinstance(value, str):
        cell.value = value
        if value.startswith(DANGEROUS):
            cell.data_type = "s"  # never a formula
    else:
        cell.value = value
    return cell


def _source(v: Any) -> tuple[str, str]:
    if not v.refs:
        return "", ""
    r = v.refs[0]
    where = (f"page {r.page}" if r.page else "") or (f"{r.sheet}!{r.cell}" if r.cell else "") or f"table {r.table + 1}, row {r.row + 1}"
    return r.text, where


def to_xlsx(spread: Spread, profile: Profile, meta: dict[str, Any]) -> bytes:
    wb = Workbook()
    about = wb.active
    about.title = "About"
    rows = [
        ("Statement Spreader export", ""),
        ("Document", meta.get("filename", "")),
        ("Document SHA-256", spread.doc_id),
        ("Run", meta.get("run_id", "")),
        ("Profile", f"{spread.profile_id} {spread.profile_version}"),
        ("Approved", meta.get("approved") or "NO: this spread has not been approved by a reviewer"),
        ("Exported", meta.get("exported_at", "")),
        ("Open review items", sum(1 for i in spread.review if not i.resolved and i.severity.value != "info")),
        ("", ""),
        ("Value status", "Meaning"),
        ("extracted", "Read from one printed number; only the stated unit was applied"),
        ("normalized", "Read from the document, then transformed (rows added, sign of a cost)"),
        ("calculated", "Not printed; computed from other values by the formula shown in Sources"),
        ("ai_mapped", "Read from the document; a model chose its template line"),
        ("human", "Corrected or entered by a reviewer"),
        ("assumed", "Depends on an assumption (e.g. no unit statement was found)"),
    ]
    for i, (a, b) in enumerate(rows, start=1):
        _put(about, i, 1, a).font = Font(bold=i in (1, 10))
        _put(about, i, 2, b)
    about.column_dimensions["A"].width = 24
    about.column_dimensions["B"].width = 90

    ws = wb.create_sheet("Spread")
    periods = spread.periods
    _put(ws, 1, 1, "Line").font = Font(bold=True)
    _put(ws, 1, 2, "Statement").font = Font(bold=True)
    for j, p in enumerate(periods):
        c = _put(ws, 1, 3 + j, p.key)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="right")
    index = {(v.line, v.period): v for v in spread.values}
    r = 2
    for stype, sdef in profile.statements.items():
        lines = [ln for ln in sdef.lines if any((ln.id, p.key) in index for p in periods)]
        if not lines:
            continue
        _put(ws, r, 1, sdef.title).font = Font(bold=True)
        r += 1
        for ln in lines:
            _put(ws, r, 1, ln.label)
            _put(ws, r, 2, stype.value)
            for j, p in enumerate(periods):
                v = index.get((ln.id, p.key))
                if v is None or v.value is None:
                    continue
                c = _put(ws, r, 3 + j, v.value)
                c.number_format = "#,##0.00" if ln.unit.value == "per_share" else "#,##0;(#,##0)"
                fill = STATUS_FILL.get(v.status)
                if fill:
                    c.fill = PatternFill("solid", start_color=fill, end_color=fill)
                if v.flags:
                    c.font = Font(color="B3261E", bold=True)
            r += 1
        r += 1
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 18
    for j in range(len(periods)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 18
    ws.freeze_panes = "C2"

    src = wb.create_sheet("Sources")
    head = ["Line", "Period", "Value", "Status", "Confidence", "Printed text", "Where", "How it was derived", "Open review items"]
    for j, h in enumerate(head, start=1):
        _put(src, 1, j, h).font = Font(bold=True)
    for i, v in enumerate(spread.values, start=2):
        text, where = _source(v)
        vals = [profile.lines[v.line].label if v.line in profile.lines else v.line, v.period, v.value, v.status.value,
                round(v.confidence, 2), text, where, " | ".join(s.detail for s in v.steps), ", ".join(v.flags)]
        for j, val in enumerate(vals, start=1):
            _put(src, i, j, val)

    chk = wb.create_sheet("Checks")
    for j, h in enumerate(["Check", "Period", "Result", "Left", "Right", "Difference", "Allowed", "Explanation"], start=1):
        _put(chk, 1, j, h).font = Font(bold=True)
    for i, c in enumerate(spread.checks, start=2):
        for j, val in enumerate([c.title, c.period, c.status.value, c.lhs, c.rhs, c.difference, c.tolerance, c.explanation], start=1):
            _put(chk, i, j, val)

    rev = wb.create_sheet("Review")
    for j, h in enumerate(["Severity", "Kind", "Message", "Resolved", "Resolution"], start=1):
        _put(rev, 1, j, h).font = Font(bold=True)
    for i, it in enumerate(spread.review, start=2):
        for j, val in enumerate([it.severity.value, it.kind.value, it.message, "yes" if it.resolved else "no", it.resolution or ""],
                                start=1):
            _put(rev, i, j, val)

    rat = wb.create_sheet("Ratios")
    for j, h in enumerate(["Ratio", "Period", "Value", "Formula", "Not computable because", "Note"], start=1):
        _put(rat, 1, j, h).font = Font(bold=True)
    for i, ra in enumerate(spread.ratios, start=2):
        for j, val in enumerate([ra.label, ra.period, ra.value, ra.formula, ra.reason or "", ra.note], start=1):
            _put(rat, i, j, val)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(spread: Spread, profile: Profile) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["statement", "line", "label", "period", "value", "status", "confidence", "open_review_items",
                "printed_text", "where"])
    for v in spread.values:
        text, where = _source(v)
        stmt = profile.line_statement[v.line].value if v.line in profile.line_statement else ""
        label = profile.lines[v.line].label if v.line in profile.lines else v.line
        w.writerow([stmt, v.line, _safe_text(label), v.period, "" if v.value is None else str(v.value), v.status.value,
                    f"{v.confidence:.2f}", " ".join(v.flags), _safe_text(text), _safe_text(where)])
    return out.getvalue().encode("utf-8")


def to_json(spread: Spread, meta: dict[str, Any]) -> bytes:
    payload = {"meta": meta, "spread": json.loads(spread.model_dump_json())}
    return json.dumps(payload, indent=1).encode("utf-8")
