"""Spreadsheet risk scanner: the formula reader, every check, the legitimate structures it must leave alone, version
comparison, refusals, the service's review rules, the HTTP routes and the command line."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font
from openpyxl.workbook.defined_name import DefinedName

from finops.core.audit import Database
from finops.core.fingerprint import sha256_bytes
from finops.sheets.config import ScanSpec
from finops.sheets.diff import compare
from finops.sheets.evaluate import folder_set, hostile, score_book, score_set, synthetic_set
from finops.sheets.formula import parse, parse_ref, r1c1
from finops.sheets.scan import scan_workbook
from finops.sheets.service import ActionError, SheetsService, model_name, scan_bytes
from finops.sheets.workbook import WorkbookError, load

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "finops" / "sheets" / "default.yaml"


def xlsx(wb: Workbook) -> bytes:
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def scan(wb: Workbook, spec: ScanSpec | None = None) -> list[Any]:
    findings, _ = scan_workbook(load("t.xlsx", xlsx(wb), spec), spec or ScanSpec())
    return findings


def kinds(findings: list[Any], severity: tuple[str, ...] = ("error", "risk")) -> dict[str, str]:
    """cell -> kind, for findings at these severities."""
    return {f"{f.sheet}!{f.cell}": f.kind for f in findings if f.severity in severity}


def forecast_sheet(rows: int = 4, months: int = 8) -> Workbook:
    """Items down the rows, actuals in C:D, a growth formula from E on, a total row and a full-year column."""
    wb = Workbook()
    a = wb.active
    a.title = "Inputs"
    a["A2"], a["B2"] = "Growth", 0.02
    a["B2"].font = Font(color="FF0000FF")
    ws = wb.create_sheet("Plan")
    for i in range(months):
        ws.cell(2, 3 + i, f"M{i + 1}")
    ws.cell(2, 3 + months, "FY")
    for k in range(rows):
        r = 3 + k
        ws.cell(r, 2, f"Item {k}")
        ws.cell(r, 3, 100 * (k + 1))
        ws.cell(r, 4, 110 * (k + 1))
        for i in range(2, months):
            col = 3 + i
            ws.cell(r, col, f"={ws.cell(r, col - 1).column_letter}{r}*(1+Inputs!$B$2)")
        ws.cell(r, 3 + months, f"=SUM(C{r}:{ws.cell(r, 2 + months).column_letter}{r})")
    t = 3 + rows
    ws.cell(t, 2, "Total")
    for i in range(months + 1):
        col = ws.cell(t, 3 + i).column_letter
        ws[f"{col}{t}"] = f"=SUM({col}3:{col}{t - 1})"
    return wb


# -- the formula reader ------------------------------------------------------------------------------------------

def test_references_and_relative_form() -> None:
    p = parse("='Op Ex'!B5*(1+$B$2)+[1]FX!C3+SUM(A:A)+Rate")
    assert [r.kind for r in p.refs] == ["cell", "cell", "cell", "range", "name"]
    assert p.refs[0].sheet == "Op Ex" and p.refs[2].external == "[1]" and p.refs[3].r1 is None
    assert r1c1(parse("=F14*(1+$B$2)"), 14, 7, "S") == r1c1(parse("=G14*(1+$B$2)"), 14, 8, "S") == "=RC[-1]*(1+R2C2)"
    assert r1c1(parse("=S!B5"), 5, 3, "S") == r1c1(parse("=B5"), 5, 3, "S")  # own sheet named or not
    ext = parse_ref("'C:\\Shared\\[Rates.xlsx]FX'!B2")
    assert ext.external == "C:\\Shared\\Rates.xlsx" and ext.sheet == "FX"
    assert parse("=SUM(").ok in (True, False)  # never raises
    assert parse("=Sheet2!#REF!").has_ref_error and parse("=#REF!+1").has_ref_error


def test_plug_and_factor_literals() -> None:
    assert [lit.additive_partner for lit in parse("=SUM(D5:D12)+2500").literals] == [True]
    assert [lit.additive_partner for lit in parse("=D30-317.42").literals] == [True]
    assert [lit.additive_partner for lit in parse("=C5*(1+0.05)").literals] == [False, False]  # a rate, not a plug
    assert [lit.multiplicative for lit in parse("=B5*12").literals] == [True]
    assert [lit.in_function for lit in parse("=ROUND(B5,2)").literals] == ["ROUND"]


# -- definite errors ---------------------------------------------------------------------------------------------

def test_definite_errors() -> None:
    wb = forecast_sheet()
    ws = wb["Plan"]
    ws["M3"] = "=Missing!A1"
    ws["M4"] = "=NoSuchName*2"
    ws["M5"] = "=#REF!+1"
    ws["N3"] = "=N4+1"
    ws["N4"] = "=N3+1"
    wb.defined_names["Old"] = DefinedName("Old", attr_text="#REF!")
    wb.defined_names["Gone"] = DefinedName("Gone", attr_text="'Deleted sheet'!$A$1")
    found = scan(wb)
    k = kinds(found, ("error",))
    assert k["Plan!M3"] == "MISSING_SHEET" and k["Plan!M4"] == "UNKNOWN_NAME" and k["Plan!M5"] == "REF_ERROR"
    loop = next(f for f in found if f.kind == "CIRCULAR_REFERENCE")
    assert set(loop.cells) == {"Plan!N3", "Plan!N4"} and loop.severity == "error"
    assert {f.cell for f in found if f.kind == "BROKEN_NAME"} == {"name:Old", "name:Gone"}


def test_text_number_inside_a_sum() -> None:
    wb = forecast_sheet()
    wb["Plan"]["C4"] = "1,250"
    wb["Plan"]["D5"] = "n/a"  # text, but not a number: SUM skipping it is right
    k = kinds(scan(wb))
    assert k["Plan!C4"] == "TEXT_NUMBER_IN_SUM" and "Plan!D5" not in k


def test_circular_reference_is_a_risk_when_iteration_is_on() -> None:
    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["A2"] = "=A2*0.5", "=A1+10"
    wb.calculation.iterate = True
    loop = next(f for f in scan(wb) if f.kind == "CIRCULAR_REFERENCE")
    assert loop.severity == "risk" and "Iterative calculation" in loop.detail


def _with_cached(data: bytes, cell: str, value: str) -> bytes:
    """Give one formula cell a saved error value, as Excel would after calculating."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            body = src.read(i.filename)
            if i.filename == "xl/worksheets/sheet1.xml":
                text = body.decode()
                text, n = re.subn(rf'<c r="{cell}"([^>]*)><f>(.*?)</f>(<v\s*/>|<v></v>)?</c>',
                                  rf'<c r="{cell}"\1 t="e"><f>\2</f><v>{value}</v></c>', text)
                assert n == 1
                body = text.encode()
            z.writestr(i, body)
    return out.getvalue()


def test_saved_error_values_report_the_source_only() -> None:
    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["A2"], ws["A3"], ws["A4"] = 10, "=A1/0", "=A2*2", "=VLOOKUP(9,B1:C2,2,FALSE)"
    data = _with_cached(_with_cached(_with_cached(xlsx(wb), "A2", "#DIV/0!"), "A3", "#DIV/0!"), "A4", "#N/A")
    model = load("c.xlsx", data)
    assert model.has_cached_values
    k = kinds(scan_workbook(model, ScanSpec())[0])
    assert k == {"Sheet!A2": "CACHED_ERROR", "Sheet!A4": "CACHED_NA"}  # A3 only inherits A2's error


# -- risks -------------------------------------------------------------------------------------------------------

def test_inconsistent_formula_override_and_plug() -> None:
    wb = forecast_sheet()
    ws = wb["Plan"]
    ws["G4"] = "=F3*(1+Inputs!$B$2)"  # reads the row above
    ws["H5"] = 777  # typed over a formula
    ws["L3"] = "=K3+2500"  # a plug beside the full-year column
    found = scan(wb)
    k = kinds(found)
    assert k["Plan!G4"] == "INCONSISTENT_FORMULA" and k["Plan!H5"] == "HARDCODED_OVERRIDE" and k["Plan!L3"] == "HARDCODED_PLUG"
    g4 = next(f for f in found if f.cell == "G4")
    assert g4.expected == "=F4*(1+Inputs!$B$2)" and g4.downstream > 0 and g4.feeds


def test_short_total_double_count_and_external_link() -> None:
    wb = forecast_sheet(rows=5)
    ws = wb["Plan"]
    for col in "CDEFGHIJK":
        ws[f"{col}8"] = f"=SUM({col}3:{col}6)"  # every column leaves out row 7
    ws["B10"] = "Grand"
    ws["C10"] = "=SUM(C3:C8)"  # items and their total
    ws["D12"] = "='[Prior year.xlsx]Plan'!D8"
    found = scan(wb)
    short = next(f for f in found if f.kind == "SUM_OMITS_ROW")
    assert short.cell == "C8" and len(short.group) == 8  # one problem copied across, reported once
    k = kinds(found)
    assert k["Plan!C10"] == "DOUBLE_COUNT" and k["Plan!D12"] == "EXTERNAL_LINK"


def test_row_totals_plus_column_totals_is_a_double_count() -> None:
    wb = forecast_sheet()
    ws = wb["Plan"]
    ws["K7"] = "=SUM(K3:K6)+SUM(C7:J7)"
    assert kinds(scan(wb))["Plan!K7"] == "DOUBLE_COUNT"


def test_three_period_rows_are_checked() -> None:
    """Regression (independent set 1, P&L!F10): a three-year forecast has one agreeing cell on each side."""
    wb = Workbook()
    ws = wb.active
    for c, v in zip("CDEFG", [100, 110, "=D6*(1+$H$1)", "=E6*(1+$H$1)", "=F6*(1+$H$1)"], strict=True):
        ws[f"{c}6"] = v
    ws["F6"] = "=E6*(1+$H$2)"
    ws["H1"], ws["H2"] = 0.1, 0.2
    assert kinds(scan(wb)).get("Sheet!F6") == "INCONSISTENT_FORMULA"


# -- legitimate structure is left alone --------------------------------------------------------------------------

def test_a_clean_model_has_no_errors_or_risks() -> None:
    wb = forecast_sheet()
    ws = wb["Plan"]
    ws["B9"], ws["C9"] = "Real terms", "=K7/(1+Inputs!B2)"  # reads an input
    ws["B11"], ws["C11"] = "Per month", "=K7/12"
    found = scan(wb)
    assert kinds(found) == {}


def test_documented_overrides_input_blocks_and_subtotals() -> None:
    wb = forecast_sheet()
    ws = wb["Plan"]
    ws["G3"] = 999
    ws["G3"].font = Font(color="FF0000FF")
    ws["H4"] = 888
    ws["H4"].comment = Comment("Signed contract", "FP&A")
    found = scan(wb)
    assert kinds(found) == {}
    assert {f.cell for f in found if f.kind == "DOCUMENTED_OVERRIDE"} == {"G3", "H4"}


def test_grand_total_of_subtotals_and_a_total_that_starts_at_a_subtotal() -> None:
    """Regression (independent set 1, Payroll C16): =SUM(C11:C15) whose first cell is a subtotal of the rows above is
    not leaving those rows out."""
    wb = Workbook()
    ws = wb.active
    for r, v in [(3, 10), (4, 20), (5, 30)]:
        ws[f"A{r}"], ws[f"C{r}"], ws[f"D{r}"] = f"Dept {r}", f"=D{r}*12", v  # department rows are formulas, as in the case
    ws["A6"], ws["C6"] = "Salaries", "=SUM(C3:C5)"
    ws["A7"], ws["C7"] = "Tax", "=C6*0.1"
    ws["A8"], ws["C8"] = "Contractors", 5
    ws["A9"], ws["C9"] = "Total cost", "=SUM(C6:C8)"
    ws["A11"], ws["C11"] = "Check", "=C6+C8"
    assert kinds(scan(wb)) == {}


def test_rounding_to_a_price_point_is_not_a_plug() -> None:
    """Regression (independent set 1, Price Build H6): =ROUND(G6,0)-0.01 makes a price end in .99."""
    wb = Workbook()
    ws = wb.active
    ws["G6"], ws["H6"] = 12.4, "=ROUND(G6,0)-0.01"
    assert kinds(scan(wb)) == {}
    ws["H6"] = "=G6-0.01"
    assert kinds(scan(wb)) == {"Sheet!H6": "HARDCODED_PLUG"}


def test_row_specific_rates_are_a_pattern_not_an_error() -> None:
    wb = forecast_sheet()
    ws = wb["Plan"]
    wb["Inputs"]["B3"] = 0.05
    for col in "EFGHIJ":
        prev = chr(ord(col) - 1)
        ws[f"{col}4"] = f"={prev}4*(1+Inputs!$B$3)"  # one item grows at its own rate
    found = scan(wb)
    assert kinds(found) == {}
    assert any(f.kind == "PATTERN_BREAK" for f in found)


def test_severity_can_be_changed_in_configuration() -> None:
    wb = forecast_sheet()
    wb["Plan"]["D12"] = "='[Prior.xlsx]Plan'!D8"
    found = scan(wb, ScanSpec(severity={"EXTERNAL_LINK": "anomaly"}))
    assert kinds(found) == {} and any(f.kind == "EXTERNAL_LINK" and f.severity == "anomaly" for f in found)


# -- version comparison ------------------------------------------------------------------------------------------

def _versions() -> tuple[bytes, bytes]:
    v1 = forecast_sheet()
    v2 = forecast_sheet(rows=5)  # a row inserted inside the block: totals grow, formulas shift
    v2["Plan"]["B5"] = "Item 1 (new)"
    v2["Plan"]["H6"] = 4321  # formula replaced by a typed value
    v2["Plan"]["I3"] = "=H3*(1+Inputs!$B$2)+0"  # logic edited
    v2["Plan"]["C3"] = 150  # an input changed: not material
    v2.create_sheet("Notes")
    return xlsx(v1), xlsx(v2)


def test_comparison_reports_meaning_not_movement() -> None:
    a, b = _versions()
    comp = compare(load("v1.xlsx", a), load("v2.xlsx", b))
    material = {(c.kind, c.cell) for c in comp.changes if c.material}
    assert ("FORMULA_TO_VALUE", "H6") in material and ("FORMULA_CHANGED", "I3") in material
    assert ("SHEET_ADDED", None) in material
    assert len(material) == 3, material  # nothing for the shifted rows or the grown totals
    assert comp.summary["typed_values_changed"] >= 1


def test_a_renamed_sheet_is_not_removed_and_added() -> None:
    v1, v2 = forecast_sheet(), forecast_sheet()
    v2["Plan"].title = "Plan FY26"
    comp = compare(load("a.xlsx", xlsx(v1)), load("b.xlsx", xlsx(v2)))
    assert [c.kind for c in comp.changes] == ["SHEET_RENAMED"]


# -- files the scanner refuses, and that it never changes ---------------------------------------------------------

def test_hostile_files_are_refused_or_scanned_never_crash() -> None:
    rows = hostile(ScanSpec())
    assert all(r["result"] == r["expected"] for r in rows), [r for r in rows if r["result"] != r["expected"]]


def test_limits_are_enforced() -> None:
    data = xlsx(forecast_sheet())
    with pytest.raises(WorkbookError, match="filled cells"):
        load("big.xlsx", data, ScanSpec(max_cells=10))
    with pytest.raises(WorkbookError, match="larger than"):
        load("big.xlsx", data, ScanSpec(max_file_mb=0.001))


def test_scanning_never_changes_the_file(tmp_path: Path) -> None:
    p = tmp_path / "model.xlsx"
    p.write_bytes(xlsx(forecast_sheet()))
    before, mtime = sha256_bytes(p.read_bytes()), p.stat().st_mtime_ns
    from spreader.cli import main

    assert main(["scan", str(p), "--out", str(tmp_path / "out")]) == 0
    assert sha256_bytes(p.read_bytes()) == before and p.stat().st_mtime_ns == mtime


def test_command_line_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from spreader.cli import main

    wb = forecast_sheet()
    wb["Plan"]["M3"] = "=#REF!"
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(xlsx(wb))
    assert main(["scan", str(bad), "--out", str(tmp_path / "o"), "--strict"]) == 1
    assert "REF_ERROR" in capsys.readouterr().out
    (tmp_path / "not.xlsx").write_bytes(b"hello")
    assert main(["scan", str(tmp_path / "not.xlsx"), "--out", str(tmp_path / "o")]) == 2
    a, b = _versions()
    (tmp_path / "v1.xlsx").write_bytes(a)
    (tmp_path / "v2.xlsx").write_bytes(b)
    assert main(["scan", str(tmp_path / "v2.xlsx"), "--previous", str(tmp_path / "v1.xlsx"), "--out", str(tmp_path / "o")]) == 0
    assert "FORMULA_TO_VALUE" in capsys.readouterr().out


# -- the service: reviews ----------------------------------------------------------------------------------------

def _service(tmp_path: Path) -> SheetsService:
    return SheetsService(Database(tmp_path / "f.sqlite3"), tmp_path / "files", CONFIG)


def _problem_book(value: int = 777) -> bytes:
    wb = forecast_sheet()
    wb["Plan"]["H5"] = value
    wb["Plan"]["M3"] = "=#REF!"
    return xlsx(wb)


def test_scans_are_reused_and_reviews_follow_the_rules(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    s1 = svc.scan("Budget v1.xlsx", _problem_book(), "dana")
    assert svc.scan("Budget v1.xlsx", _problem_book(), "dana") == s1  # same bytes, same scan
    got = svc.get(s1)
    assert got["model"] == "budget"
    risk = next(f for f in got["result"]["findings"] if f["kind"] == "HARDCODED_OVERRIDE")
    err = next(f for f in got["result"]["findings"] if f["kind"] == "REF_ERROR")
    with pytest.raises(ActionError, match="named reviewer"):
        svc.review(s1, risk["id"], "dismiss", "system", "looks fine to me")
    with pytest.raises(ActionError, match="reason"):
        svc.review(s1, risk["id"], "dismiss", "dana", "ok")
    with pytest.raises(ActionError, match="cannot be dismissed"):
        svc.review(s1, err["id"], "dismiss", "dana", "we never use that cell")
    after = svc.review(s1, risk["id"], "dismiss", "dana", "Contracted amount agreed with the model owner")
    assert after["open"]["risk"] == got["open"]["risk"] - 1
    # The next version of the same model, with the override still there (one more row above it): the review carries.
    wb = forecast_sheet()
    wb["Plan"]["H5"] = 777
    wb["Plan"]["M3"] = "=#REF!"
    s2 = svc.scan("Budget v2.xlsx", xlsx(wb), "dana")
    carried = next(f for f in svc.get(s2)["result"]["findings"] if f["kind"] == "HARDCODED_OVERRIDE")
    assert carried["review"]["action"] == "dismiss" and carried["review"]["actor"] == "dana"
    with pytest.raises(Exception, match="append-only"), svc.db.tx() as c:
        c.execute("DELETE FROM sheet_reviews")
    assert any(e["kind"] == "finding_dismiss" for e in svc.events("budget"))


def test_failed_scan_is_recorded_and_export_is_safe(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    with pytest.raises(ActionError, match="not an Excel workbook"):
        svc.scan("x.xlsx", b"not a workbook", "dana")
    assert svc.scans()[0]["status"] == "failed"
    wb = forecast_sheet()
    wb["Plan"]["B12"] = "=cmd|' /C calc'!A0"
    sid = svc.scan("m.xlsx", xlsx(wb), "dana")
    _, body = svc.export(sid)
    assert b",=cmd" not in body and b"'=cmd" in body  # formula-like text is written as plain text


def test_model_names() -> None:
    assert model_name("Budget FY26 v3 (final).xlsx") == "budget fy26"
    assert model_name("opex_forecast_v2.xlsx") == "opex_forecast"


def test_http_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from finops import api as fapi
    from spreader.api import app

    database = Database(tmp_path / "f.sqlite3")
    fapi.configure(database, sheets_service=SheetsService(database, tmp_path / "files", CONFIG))
    c = TestClient(app)
    h = {"X-Actor": "dana"}
    sample = c.post("/api/finops/sheets/sample", json={}, headers=h).json()["scans"]
    one = c.get(f"/api/finops/sheets/scans/{sample[0]}").json()
    assert one["status"] == "succeeded" and one["counts"]["error"] + one["counts"]["risk"] > 0
    two = c.get(f"/api/finops/sheets/scans/{sample[1]}").json()
    assert two["counts"]["material_changes"] >= 3
    up = c.post("/api/finops/sheets/scans", files={"workbook": ("b.xlsx", _problem_book(), "application/octet-stream")}, headers=h)
    sid = up.json()["scan"]
    f = next(x for x in c.get(f"/api/finops/sheets/scans/{sid}").json()["result"]["findings"] if x["kind"] == "REF_ERROR")
    bad = c.post(f"/api/finops/sheets/scans/{sid}/review", json={"finding_id": f["id"], "action": "dismiss", "note": "not used"}, headers=h)
    assert bad.status_code == 400 and "cannot be dismissed" in bad.json()["error"]
    ok = c.post(f"/api/finops/sheets/scans/{sid}/review", json={"finding_id": f["id"], "action": "confirm", "note": "will fix in v2"}, headers=h)
    assert ok.status_code == 200
    assert c.get(f"/api/finops/sheets/scans/{sid}/export.csv").text.startswith("severity,kind")
    missing = c.post("/api/finops/sheets/scans", data={"model": "x"}, headers=h)
    assert missing.status_code in (400, 415)  # no workbook attached (the app refuses non-multipart forms first)
    refused = c.post("/api/finops/sheets/scans", files={"workbook": ("a.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)}, headers=h)
    assert refused.status_code == 400 and "old-format" in refused.json()["error"]
    cross = c.post("/api/finops/sheets/sample", headers={**h, "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403


# -- the evaluation itself ---------------------------------------------------------------------------------------

def test_scoring_rules() -> None:
    class F:
        def __init__(self, kind: str, sheet: str, cell: str, severity: str = "risk", group: list[str] | None = None) -> None:
            self.kind, self.sheet, self.cell, self.severity, self.group, self.cells, self.id = kind, sheet, cell, severity, group or [], [], cell
    truth = [{"sheet": "S", "cell": "B2", "kind": "SUM_OMITS_ROW", "group": ["C2"]}, {"sheet": "S", "cell": "D9", "kind": "REF_ERROR"}]
    s = score_book([F("INCONSISTENT_FORMULA", "S", "C2"), F("CONSTANT_IN_FORMULA", "S", "D9", "anomaly"), F("X", "S", "Z1")], truth)
    assert (s["found"], s["claims"], s["right_claims"], s["kind_agrees"]) == (1, 2, 1, 0)


def test_synthetic_truth_is_found_and_files_are_unchanged() -> None:
    books, pairs = synthetic_set(7)
    for name, data, faults, _ in books:
        model = load(name, data)
        for t in faults:
            if t["sheet"]:
                assert model.sheet(t["sheet"]) is not None, (name, t)
    result = score_set(books, pairs, ScanSpec())
    assert result["rates"]["recall"].n >= 0.9 * result["rates"]["recall"].d
    assert result["counts"]["baseline"] > 5 * result["counts"]["claims"]  # the naive checker is far noisier


def test_independent_sets_load() -> None:
    for folder in sorted((ROOT / "eval" / "sheets").glob("independent-*")):
        books, pairs = folder_set(folder)
        assert books and all(json.loads((folder / "truth.json").read_text(encoding="utf-8"))["workbooks"])
        assert scan_bytes(books[0][0], books[0][1], ScanSpec()).findings is not None


# -- regressions from independent set 2 ---------------------------------------------------------------------------

def test_half_year_columns_between_quarters_are_structure() -> None:
    """Regression (set 2, KPIs E6/E9/F9): H1 and H2 columns break every quarter row; that is the layout."""
    wb = Workbook()
    ws = wb.active
    for c, h in zip("BCDEFGH", ["Q1", "Q2", "H1", "Q3", "Q4", "H2", "FY"], strict=True):
        ws[f"{c}3"] = h
    ws["A5"], ws["B5"], ws["C5"], ws["D5"], ws["E5"], ws["F5"], ws["G5"] = "Heads", 182, 188, "=C5", 195, 201, "=F5"
    ws["A6"] = "Revenue per head"
    for c in "BCEF":
        ws[f"{c}6"] = f"=P!{c}7*4/{c}5"
    ws["D6"], ws["G6"] = "=P!D7*2/D5", "=P!G7*2/G5"
    ws["A7"], ws["B7"], ws["C7"], ws["D7"], ws["E7"], ws["F7"], ws["G7"] = "New", 38, 41, "=B7+C7", 35, 47, "=E7+F7"
    ws["A8"], ws["B8"], ws["C8"], ws["D8"], ws["E8"], ws["F8"], ws["G8"] = "Lost", 12, 9, "=B8+C8", 14, 11, "=E8+F8"
    ws["A9"], ws["B9"], ws["C9"], ws["D9"], ws["E9"], ws["F9"], ws["G9"] = "Customers", "=400+B7-B8", "=B9+C7-C8", "=C9", "=C9+E7-E8", "=E9+F7-F8", "=F9"
    p = wb.create_sheet("P")
    for c in "BCDEFG":
        p[f"{c}7"] = 1000
    found = scan(wb)
    assert {k for k in kinds(found) if k.startswith("Sheet!")} - {"Sheet!B9"} == set(), kinds(found)


def test_actual_rows_between_subtotals_are_not_overrides() -> None:
    """Regression (set 2, Forecast B15/C15): typed actual interest and tax between two subtotal rows."""
    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["B1"], ws["C1"], ws["D1"], ws["E1"], ws["F1"] = "", "FY24A", "FY25A", "FY26F", "FY27F", "FY28F"
    ws["A2"] = "Rate"
    ws["B2"] = 0.05
    for r, label in [(4, "EBIT"), (5, "Interest"), (6, "PBT"), (7, "Tax"), (8, "Net income")]:
        ws[f"A{r}"] = label
    for c in "BCDEF":
        ws[f"{c}4"] = 1000
        ws[f"{c}6"] = f"={c}4+{c}5"
        ws[f"{c}8"] = f"={c}6+{c}7"
    for c, v in (("B", -50), ("C", -45)):
        ws[f"{c}5"], ws[f"{c}7"] = v, v * 4
    for c in "DEF":
        ws[f"{c}5"] = f"=-{c}4*$B$2"
        ws[f"{c}7"] = f"=-MAX(0,{c}6)*0.25"
    assert kinds(scan(wb)) == {}


def test_a_counting_heading_is_not_an_omitted_item() -> None:
    """Regression (set 2, Cohorts B17): months 0, 1, 2, 3 above the cohort rows are a heading."""
    wb = Workbook()
    ws = wb.active
    for i, c in enumerate("BCDE"):
        ws[f"{c}4"] = i
        for r in range(5, 9):
            ws[f"{c}{r}"] = 100 + r + i
        ws[f"{c}9"] = f"=SUM({c}5:{c}8)"
    ws["A4"], ws["A9"] = "Cohort", "Total"
    assert kinds(scan(wb)) == {}


def test_coinciding_mistakes_in_one_column_are_still_reported() -> None:
    """Three planted problems in one column of a 6-row block are not a structural column (seed 32, I12)."""
    wb = forecast_sheet(rows=6)
    ws = wb["Plan"]
    ws["G3"] = "=F3"
    ws["G5"] = "=F4*(1+Inputs!$B$2)"
    ws["G7"] = 999
    k = kinds(scan(wb))
    assert k.get("Plan!G3") == "INCONSISTENT_FORMULA" and k.get("Plan!G5") == "INCONSISTENT_FORMULA"
    assert k.get("Plan!G7") == "HARDCODED_OVERRIDE"


def test_typed_cells_below_do_not_excuse_an_override() -> None:
    """Set 2, Cash K14: a typed payment between formulas, with a typed row underneath, is still an override."""
    wb = forecast_sheet()
    ws = wb["Plan"]
    ws["G4"] = -118400
    for c in "CDEFGHIJ":
        ws[f"{c}5"] = 0  # a typed row under it
    assert kinds(scan(wb)).get("Plan!G4") == "HARDCODED_OVERRIDE"


def test_roi_quotes_the_first_scorings() -> None:
    """The ROI page quotes the worst first scoring of the independent sets, never a score made after fixing."""
    from finops.roi import compute

    sheets = compute(ROOT / "eval" / "reports")["engines"]["sheets"]
    assert "first-score" in sheets["source"] and sheets["precision"]["value"] < 1
