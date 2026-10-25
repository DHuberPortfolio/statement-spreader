"""Build an independent, blind test set of finance workbooks for a spreadsheet risk scanner.

Every workbook is written with openpyxl. Faults and legitimate exceptions are labelled in
truth.json as each cell is written, then every label is re-checked against the saved file.

Run:  .venv\\Scripts\\python.exe build_set.py   (from anywhere; output goes beside this file)
"""
import io
import json
import os
import random
import re
import sys
import zipfile
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.formula import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter as COL
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string, range_boundaries
from openpyxl.workbook.defined_name import DefinedName

OUT = os.path.dirname(os.path.abspath(__file__))
R = random.Random(20251024)

BLUE = Font(color="FF0000FF")
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=13)
NUM = "#,##0;(#,##0)"
NUM2 = "#,##0.00;(#,##0.00)"
PCT = "0.0%"

ERROR_KINDS = {"REF_ERROR", "MISSING_SHEET", "UNKNOWN_NAME", "BROKEN_NAME",
               "CIRCULAR_REFERENCE", "TEXT_NUMBER_IN_SUM"}
RISK_KINDS = {"INCONSISTENT_FORMULA", "HARDCODED_OVERRIDE", "SUM_OMITS_ROW", "DOUBLE_COUNT",
              "EXTERNAL_LINK", "HARDCODED_PLUG"}
FIXED_TIME = datetime(2025, 10, 24, 9, 0, 0)

TRUTH = {"workbooks": {}, "diffs": []}


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------
class Book:
    def __init__(self, fname, description):
        self.fname = fname
        self.description = description
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        self.wb.properties.creator = "FP&A"
        self.wb.properties.lastModifiedBy = "FP&A"
        self.wb.properties.created = FIXED_TIME
        self.wb.properties.modified = FIXED_TIME
        self.faults = []
        self.legit = []

    def sheet(self, name, hidden=False):
        ws = self.wb.create_sheet(name)
        if hidden:
            ws.sheet_state = "hidden"
        return ws

    def name(self, name, ref):
        self.wb.defined_names[name] = DefinedName(name, attr_text=ref)

    def fault(self, sheet, cell, kind, note, **extra):
        assert kind in ERROR_KINDS | RISK_KINDS, kind
        f = {"sheet": sheet, "cell": cell, "kind": kind,
             "severity": "error" if kind in ERROR_KINDS else "risk", "note": note}
        f.update(extra)
        self.faults.append(f)

    def ok(self, sheet, cell, what):
        self.legit.append({"sheet": sheet, "cell": cell, "what": what})

    def save(self):
        path = os.path.join(OUT, self.fname)
        self.wb.save(path)
        normalise_zip(path)
        TRUTH["workbooks"][self.fname] = {"description": self.description,
                                          "faults": self.faults, "legit": self.legit}
        return path


def put(ws, addr, value, font=None, fmt=None, comment=None):
    c = ws[addr]
    c.value = value
    if font is not None:
        c.font = font
    if fmt is not None:
        c.number_format = fmt
    if comment is not None:
        cm = Comment(comment, "Reviewer")
        cm.width, cm.height = 260, 90
        c.comment = cm
    return c


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def normalise_zip(path):
    """Rewrite the xlsx with fixed zip timestamps and a fixed modified date (byte-stable reruns)."""
    with zipfile.ZipFile(path) as z:
        items = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zo:
        for name, data in items:
            if name == "docProps/core.xml":
                data = re.sub(rb"<dcterms:modified([^>]*)>[^<]*</dcterms:modified>",
                              rb"<dcterms:modified\1>2025-10-24T09:00:00Z</dcterms:modified>", data)
                data = re.sub(rb"<dcterms:created([^>]*)>[^<]*</dcterms:created>",
                              rb"<dcterms:created\1>2025-10-24T09:00:00Z</dcterms:created>", data)
            zi = zipfile.ZipInfo(name, date_time=(2025, 10, 24, 9, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zo.writestr(zi, data)
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())


def money(lo, hi, step=10):
    return R.randrange(lo // step, hi // step + 1) * step


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------------------------
# 1. Departmental budget: months across columns, FY total at the end, total row below
# --------------------------------------------------------------------------------------------
def build_budget():
    b = Book("budget_fy25.xlsx",
             "Marketing department budget FY2025. Line items down rows 5-12, Jan-Dec across B:M "
             "(Jan typed base, Feb-Dec grow by a monthly rate in $B$2), FY total in N, total row 13.")
    ws = b.sheet("Budget")
    put(ws, "A1", "FY2025 Departmental Budget - Marketing", TITLE)
    put(ws, "A2", "Monthly growth")
    put(ws, "B2", 0.004, BLUE, PCT)
    put(ws, "A4", "Line item", BOLD)
    for i, m in enumerate(MONTHS):
        put(ws, f"{COL(2 + i)}4", f"{m}-25", BOLD)
    put(ws, "N4", "FY2025 Total", BOLD)
    lines = ["Salaries", "Contractors", "Paid media", "Events", "Agency fees", "Software",
             "Travel", "Print & collateral"]
    for k, label in enumerate(lines):
        r = 5 + k
        put(ws, f"A{r}", label)
        put(ws, f"B{r}", money(2000, 60000, 50), BLUE, NUM)
        for c in range(3, 14):
            put(ws, f"{COL(c)}{r}", f"={COL(c - 1)}{r}*(1+$B$2)", fmt=NUM)
        put(ws, f"N{r}", f"=SUM(B{r}:M{r})", fmt=NUM)
    put(ws, "A13", "Total", BOLD)
    for c in range(2, 15):
        put(ws, f"{COL(c)}13", f"=SUM({COL(c)}5:{COL(c)}12)", BOLD, NUM)

    # faults
    put(ws, "H8", "=G7*(1+$B$2)")
    b.fault("Budget", "H8", "INCONSISTENT_FORMULA",
            "Events Jul grows from Paid media Jun (row 7) instead of Events Jun (row 8)")
    put(ws, "J6", "=I6")
    b.fault("Budget", "J6", "INCONSISTENT_FORMULA",
            "Contractors Sep drops the growth term: =I6 instead of =I6*(1+$B$2)")
    put(ws, "K10", 4200, fmt=NUM)
    b.fault("Budget", "K10", "HARDCODED_OVERRIDE",
            "typed 4200 in the Software Oct cell; Sep and Nov are growth formulas; no comment")
    put(ws, "F13", "=SUM(F5:F11)", BOLD)
    b.fault("Budget", "F13", "SUM_OMITS_ROW", "May total stops at row 11 and misses Print & collateral (row 12)",
            also_ok=["INCONSISTENT_FORMULA"])

    # legit: documented override
    put(ws, "K12", 9500, BLUE, NUM,
        comment="Oct: annual brochure reprint, fixed quote from printer (PO 55812). Overrides growth formula.")
    b.ok("Budget", "K12", "typed override in a formula run, documented with a cell comment and blue input font")
    b.ok("Budget", "B2", "growth assumption typed input (percentage)")
    b.ok("Budget", "B5:B12", "January base values typed (first period input), Feb-Dec are formulas")
    b.ok("Budget", "N5:N13", "FY2025 total column at the end of the monthly run (SUM across the row)")
    b.ok("Budget", "A1", "number inside a label ('FY2025')")
    put(ws, "A15", "Prepared by FP&A, v3 - 14 Oct 2025. January is the approved base; Feb-Dec grow monthly.")
    b.ok("Budget", "A15", "text note with numbers in it")
    widths(ws, {"A": 22, "N": 14})

    lists = b.sheet("Lists", hidden=True)
    put(lists, "A1", "Cost centre")
    for i, cc in enumerate([4100, 4110, 4120, 4130]):
        put(lists, f"A{2 + i}", cc)
    return b.save()


# --------------------------------------------------------------------------------------------
# 2. Loan amortisation: time down rows, defined names, totals above the table
# --------------------------------------------------------------------------------------------
def build_loan():
    b = Book("loan_amortisation.xlsx",
             "Equipment loan amortisation. Inputs sheet with defined names (LoanAmount, AnnualRate, "
             "TermMonths); Schedule sheet with 60 monthly periods down rows 7-66 starting in column B, "
             "totals in row 4 above the table.")
    inp = b.sheet("Inputs")
    put(inp, "A1", "Equipment loan - amortisation inputs", TITLE)
    put(inp, "A3", "Loan amount")
    put(inp, "B3", 250000, BLUE, NUM)
    put(inp, "A4", "Annual interest rate")
    put(inp, "B4", 0.065, BLUE, "0.00%")
    put(inp, "A5", "Term (years)")
    put(inp, "B5", 5, BLUE)
    put(inp, "A6", "First payment date")
    put(inp, "B6", datetime(2025, 1, 31), BLUE, "dd-mmm-yy")
    put(inp, "A7", "Term (months)")
    put(inp, "B7", "=B5*12")
    put(inp, "A9", "Monthly rate (memo)")
    put(inp, "B9", "=AnnualRt/12", fmt="0.000%")
    b.fault("Inputs", "B9", "UNKNOWN_NAME", "uses AnnualRt; the defined name is AnnualRate")
    b.name("LoanAmount", "Inputs!$B$3")
    b.name("AnnualRate", "Inputs!$B$4")
    b.name("TermMonths", "Inputs!$B$7")
    b.ok("Inputs", "B3:B6", "typed loan inputs")
    b.ok("Inputs", "B7", "multiply by unit constant (*12 years to months)")
    widths(inp, {"A": 24, "B": 14})

    ws = b.sheet("Schedule")
    put(ws, "B2", "Amortisation schedule (monthly)", TITLE)
    put(ws, "B4", "Totals", BOLD)
    for col in "DEF":
        put(ws, f"{col}4", f"=SUM({col}7:{col}66)", BOLD, NUM2)
    for i, h in enumerate(["Period", "Opening balance", "Payment", "Interest", "Principal", "Closing balance"]):
        put(ws, f"{COL(2 + i)}6", h, BOLD)
    for r in range(7, 67):
        put(ws, f"B{r}", 1 if r == 7 else f"=B{r - 1}+1")
        put(ws, f"C{r}", "=LoanAmount" if r == 7 else f"=G{r - 1}", fmt=NUM2)
        put(ws, f"D{r}", "=PMT(AnnualRate/12,TermMonths,-LoanAmount)", fmt=NUM2)
        put(ws, f"E{r}", f"=C{r}*AnnualRate/12", fmt=NUM2)
        put(ws, f"F{r}", f"=D{r}-E{r}", fmt=NUM2)
        put(ws, f"G{r}", f"=C{r}-F{r}", fmt=NUM2)

    put(ws, "E40", "=C40*0.065/12")
    b.fault("Schedule", "E40", "INCONSISTENT_FORMULA",
            "period 34 interest uses a typed 6.5% instead of the AnnualRate name used by every other period")
    put(ws, "C30", 162345.12, fmt=NUM2)
    b.fault("Schedule", "C30", "HARDCODED_OVERRIDE",
            "opening balance for period 24 pasted as a value; rows above and below are =G(previous row)")
    put(ws, "G66", "=C66-F66+0.42")
    b.fault("Schedule", "G66", "HARDCODED_PLUG", "final closing balance forced with +0.42 to show zero")

    b.ok("Schedule", "C7", "first opening balance pulls the loan amount; later rows take prior closing balance")
    b.ok("Schedule", "B7", "period counter starts with a typed 1")
    b.ok("Schedule", "B8:B66", "period counter =previous+1 (constant increment, not a plug)")
    b.ok("Schedule", "D7:D66", "PMT with AnnualRate/12 (unit constant), identical every row")
    b.ok("Schedule", "D4:F4", "totals placed above the table that correctly sum rows 7-66")
    widths(ws, {"B": 8, "C": 16, "D": 12, "E": 12, "F": 12, "G": 16})
    return b.save()


# --------------------------------------------------------------------------------------------
# 3. Three-statement model
# --------------------------------------------------------------------------------------------
def build_model():
    b = Book("three_statement_model.xlsx",
             "Small three-statement model, USD 000. Years across C:G (FY2023A-FY2024A typed actuals, "
             "FY2025E-FY2027E formulas). Sheets Assumptions, P&L, Balance Sheet, Cash Flow reference each "
             "other; hidden Calc sheet; defined names InterestRate and CreditorDays plus two broken names.")
    cover = b.sheet("Cover")
    put(cover, "A1", "Three-statement model - FY2023A to FY2027E", TITLE)
    put(cover, "A3", "Version 4.2 (Oct 2025). USD 000. Blue = input.")
    b.ok("Cover", "A1", "numbers in label text (FY2023A, FY2027E)")

    years = [2023, 2024, 2025, 2026, 2027]
    flags = ["Actual", "Actual", "Forecast", "Forecast", "Forecast"]

    def header(ws, title, only_forecast=False):
        put(ws, "B1", title, TITLE)
        put(ws, "B2", "USD 000")
        for i, (y, f) in enumerate(zip(years, flags)):
            if only_forecast and i < 2:
                continue
            put(ws, f"{COL(3 + i)}3", y, BOLD)
            put(ws, f"{COL(3 + i)}4", f)
        widths(ws, {"B": 34})

    a = b.sheet("Assumptions")
    header(a, "Assumptions")
    rows = {5: ("Revenue growth", [0.08, 0.07, 0.06], PCT),
            6: ("COGS % of revenue", [0.58, 0.575, 0.57], PCT),
            7: ("Opex % of revenue", [0.22, 0.215, 0.21], PCT),
            8: ("Tax rate", [0.25, 0.25, 0.25], PCT),
            9: ("Capex % of revenue", [0.05, 0.05, 0.045], PCT),
            10: ("Depreciation % of opening PP&E", [0.12, 0.12, 0.12], PCT),
            11: ("Debtor days", [45, 44, 43], "0")}
    for r, (label, vals, fmt) in rows.items():
        put(a, f"B{r}", label)
        for i, v in enumerate(vals):
            put(a, f"{COL(5 + i)}{r}", v, BLUE, fmt)
    put(a, "B12", "Creditor days (all years)")
    put(a, "C12", 38, BLUE)
    put(a, "B13", "Interest rate on debt")
    put(a, "C13", 0.068, BLUE, PCT)
    b.name("InterestRate", "Assumptions!$C$13")
    b.name("CreditorDays", "Assumptions!$C$12")
    b.name("PriorYearRev", "Assumptions!#REF!")
    b.fault(None, "name:PriorYearRev", "BROKEN_NAME", "defined name points at Assumptions!#REF! (row deleted)")
    b.name("FX_Rate", "'Old FX'!$B$2")
    b.fault(None, "name:FX_Rate", "BROKEN_NAME", "defined name points at sheet 'Old FX', which no longer exists")
    b.ok("Assumptions", "E5:G11", "typed forecast assumptions (percentages and days)")
    b.ok("Assumptions", "C12:C13", "typed single-value assumptions used through defined names")
    b.ok("Assumptions", "C3:G3", "year header row of typed numbers")

    pl = b.sheet("P&L")
    header(pl, "Income statement")
    put(pl, "B6", "Revenue"); put(pl, "B7", "Cost of sales"); put(pl, "B8", "Gross profit", BOLD)
    put(pl, "B10", "Operating expenses"); put(pl, "B11", "Depreciation"); put(pl, "B12", "EBIT", BOLD)
    put(pl, "B13", "Interest expense"); put(pl, "B14", "Profit before tax", BOLD)
    put(pl, "B15", "Tax"); put(pl, "B16", "Net income", BOLD)
    actuals = {6: (48200, 52650), 7: (-27950, -30480), 10: (-10610, -11420), 11: (-1830, -1905),
               13: (-612, -580), 15: (-1360, -1520)}
    for r, (c, d) in actuals.items():
        put(pl, f"C{r}", c, BLUE, NUM)
        put(pl, f"D{r}", d, BLUE, NUM)
    for i in range(5):
        c = COL(3 + i)
        put(pl, f"{c}8", f"={c}6+{c}7", BOLD, NUM)
        put(pl, f"{c}12", f"={c}8+{c}10+{c}11", BOLD, NUM)
        put(pl, f"{c}14", f"={c}12+{c}13", BOLD, NUM)
        put(pl, f"{c}16", f"={c}14+{c}15", BOLD, NUM)
    for i in range(2, 5):
        c, p = COL(3 + i), COL(2 + i)
        put(pl, f"{c}6", f"={p}6*(1+Assumptions!{c}5)", fmt=NUM)
        put(pl, f"{c}7", f"=-{c}6*Assumptions!{c}6", fmt=NUM)
        put(pl, f"{c}10", f"=-{c}6*Assumptions!{c}7", fmt=NUM)
        put(pl, f"{c}11", f"=-'Balance Sheet'!{p}8*Assumptions!{c}10", fmt=NUM)
        put(pl, f"{c}13", f"=-'Balance Sheet'!{p}12*InterestRate", fmt=NUM)
        put(pl, f"{c}15", f"=-{c}14*Assumptions!{c}8", fmt=NUM)
    put(pl, "F10", "=-F6*Assumptions!E7")
    b.fault("P&L", "F10", "INCONSISTENT_FORMULA",
            "FY2026 opex uses the FY2025 assumption (column E) instead of column F")
    put(pl, "F11", "=-'Balance Sheet'!#REF!*Assumptions!F10")
    b.fault("P&L", "F11", "REF_ERROR", "depreciation lost its PP&E reference after a Balance Sheet row was deleted",
            also_ok=["INCONSISTENT_FORMULA"])
    b.ok("P&L", "C6:D7", "historical actual columns typed, forecast columns are formulas")
    b.ok("P&L", "C10:D11", "historical actual columns typed, forecast columns are formulas")
    b.ok("P&L", "C13:D13", "historical actual interest typed")
    b.ok("P&L", "C15:D15", "historical actual tax typed")
    b.ok("P&L", "E15:G15", "tax row sits between PBT (=x12+x13) and net income (=x14+x15); those two "
                           "happen to share a 'two rows above' pattern but are not a run the tax row breaks")
    b.ok("P&L", "C3:G3", "year header row of typed numbers")
    b.ok("P&L", "E13:G13", "interest via the defined name InterestRate on opening debt")

    bs = b.sheet("Balance Sheet")
    header(bs, "Balance sheet")
    labels = {6: "Cash", 7: "Trade receivables", 8: "PP&E (net)", 9: "Total assets", 11: "Trade payables",
              12: "Debt", 13: "Equity", 14: "Total liabilities and equity", 16: "Balance check (should be 0)",
              18: "Memo: covenant headroom"}
    for r, t in labels.items():
        put(bs, f"B{r}", t, BOLD if r in (9, 14) else None)
    bs_act = {6: (3120, 3870), 7: (5940, 6490), 8: (9150, 9620), 11: (2870, 3120), 12: (8500, 8000),
              13: (6840, 8860)}
    for r, (c, d) in bs_act.items():
        put(bs, f"C{r}", c, BLUE, NUM)
        put(bs, f"D{r}", d, BLUE, NUM)
    for i in range(5):
        c = COL(3 + i)
        put(bs, f"{c}9", f"=SUM({c}6:{c}8)", BOLD, NUM)
        put(bs, f"{c}14", f"=SUM({c}11:{c}13)", BOLD, NUM)
        put(bs, f"{c}16", f"={c}9-{c}14", fmt=NUM)
    for i in range(2, 5):
        c, p = COL(3 + i), COL(2 + i)
        put(bs, f"{c}6", f"='Cash Flow'!{c}16", fmt=NUM)
        put(bs, f"{c}7", f"='P&L'!{c}6*Assumptions!{c}11/365", fmt=NUM)
        put(bs, f"{c}8", f"={p}8-'Cash Flow'!{c}11+'P&L'!{c}11", fmt=NUM)
        put(bs, f"{c}11", f"=-'P&L'!{c}7*CreditorDays/365", fmt=NUM)
        put(bs, f"{c}12", f"={p}12", fmt=NUM)
        put(bs, f"{c}13", f"={p}13+'P&L'!{c}16", fmt=NUM)
    put(bs, "C7", "5,940", BLUE)
    b.fault("Balance Sheet", "C7", "TEXT_NUMBER_IN_SUM",
            "FY2023 receivables stored as text '5,940'; Total assets =SUM(C6:C8) skips it")
    put(bs, "G13", "=F13+'P&L'!G16+1500")
    b.fault("Balance Sheet", "G13", "HARDCODED_PLUG", "FY2027 equity has +1500 typed in to force the balance check")
    put(bs, "E18", "='Covenants'!C5")
    b.fault("Balance Sheet", "E18", "MISSING_SHEET", "references sheet 'Covenants', which is not in the workbook")
    b.ok("Balance Sheet", "D6:D8", "FY2024 actual assets typed")
    b.ok("Balance Sheet", "C11:D13", "actual liabilities and equity typed")
    b.ok("Balance Sheet", "E7:G7", "receivables = revenue * debtor days / 365 (unit constant)")
    b.ok("Balance Sheet", "E11:G11", "payables via defined name CreditorDays / 365")
    b.ok("Balance Sheet", "C16:G16", "balance check row (assets minus liabilities and equity)")

    cf = b.sheet("Cash Flow")
    header(cf, "Cash flow statement", only_forecast=True)
    cf_labels = {6: "Net income", 7: "Add back: depreciation", 8: "(Increase)/decrease in receivables",
                 9: "Increase/(decrease) in payables", 10: "Cash from operations", 11: "Capital expenditure",
                 12: "Cash from investing", 13: "Debt drawn/(repaid)", 14: "Net cash flow",
                 15: "Opening cash", 16: "Closing cash"}
    for r, t in cf_labels.items():
        put(cf, f"B{r}", t, BOLD if r in (10, 12, 14, 16) else None)
    for i in range(2, 5):
        c, p = COL(3 + i), COL(2 + i)
        put(cf, f"{c}6", f"='P&L'!{c}16", fmt=NUM)
        put(cf, f"{c}7", f"=-'P&L'!{c}11", fmt=NUM)
        put(cf, f"{c}8", f"='Balance Sheet'!{p}7-'Balance Sheet'!{c}7", fmt=NUM)
        put(cf, f"{c}9", f"='Balance Sheet'!{c}11-'Balance Sheet'!{p}11", fmt=NUM)
        put(cf, f"{c}10", f"=SUM({c}6:{c}9)", BOLD, NUM)
        put(cf, f"{c}11", f"=-'P&L'!{c}6*Assumptions!{c}9", fmt=NUM)
        put(cf, f"{c}12", f"={c}11", BOLD, NUM)
        put(cf, f"{c}13", f"='Balance Sheet'!{c}12-'Balance Sheet'!{p}12", fmt=NUM)
        put(cf, f"{c}14", f"={c}10+{c}12+{c}13", BOLD, NUM)
        put(cf, f"{c}15", f"='Balance Sheet'!{p}6", fmt=NUM)
        put(cf, f"{c}16", f"={c}15+{c}14", BOLD, NUM)
    b.ok("Cash Flow", "E14:G14", "grand total adds only the three subtotals (operations, investing, debt)")
    b.ok("Cash Flow", "E15:G15", "opening cash pulls prior-year closing cash from the Balance Sheet")

    calc = b.sheet("Calc", hidden=True)
    put(calc, "A1", "Scratch checks")
    put(calc, "A3", "Forecast revenue")
    put(calc, "B3", "=SUM('P&L'!E6:G6)")
    return b.save()


# --------------------------------------------------------------------------------------------
# 4. Sales commission calculator (with circular bonus pool)
# --------------------------------------------------------------------------------------------
def build_commission():
    b = Book("sales_commission.xlsx",
             "Q3 sales commission calculator. Rates sheet with a tiered rate card; 'Commission Q3' sheet with "
             "15 reps in rows 6-20 starting at column B, totals in row 22 and a bonus-pool block below.")
    rt = b.sheet("Rates")
    put(rt, "A1", "Commission rate card - FY2025", TITLE)
    put(rt, "B4", "Attainment from", BOLD)
    put(rt, "C4", "Rate", BOLD)
    for i, (t, rate) in enumerate([(0, 0.03), (0.8, 0.05), (1.0, 0.07), (1.2, 0.09)]):
        put(rt, f"B{5 + i}", t, BLUE, "0%")
        put(rt, f"C{5 + i}", rate, BLUE, PCT)
    put(rt, "B10", "Bonus pool % of profit after bonus")
    put(rt, "C10", 0.1, BLUE, "0%")
    put(rt, "B12", "Prior quarter payout (Q2)")
    put(rt, "C12", "='[Commission_Q2.xlsx]Commission Q2'!$H$22", fmt=NUM)
    b.fault("Rates", "C12", "EXTERNAL_LINK", "pulls Q2 payout from another workbook Commission_Q2.xlsx")
    b.ok("Rates", "B5:C8", "typed tier table (thresholds and rates)")
    b.ok("Rates", "C10", "typed percentage assumption")
    widths(rt, {"B": 34})

    ws = b.sheet("Commission Q3")
    put(ws, "B2", "Q3 FY2025 sales commission", TITLE)
    for i, h in enumerate(["Rep", "Region", "Quota", "Sales", "Attainment", "Rate", "Commission", "Notes"]):
        put(ws, f"{COL(2 + i)}5", h, BOLD)
    regions = ["North", "South", "East", "West"]
    notes = {7: "New territory from Aug", 12: "Includes 2 renewals", 15: "On leave 3 weeks in Sep",
             19: "Split deal with SR-108 (50/50)"}
    for k in range(15):
        r = 6 + k
        quota = money(150000, 300000, 5000)
        put(ws, f"B{r}", f"SR-{101 + k}")
        put(ws, f"C{r}", regions[k % 4])
        put(ws, f"D{r}", quota, fmt=NUM)
        put(ws, f"E{r}", int(round(quota * R.uniform(0.6, 1.35), -2)), fmt=NUM)
        put(ws, f"F{r}", f"=E{r}/D{r}", fmt=PCT)
        put(ws, f"G{r}", f"=IFERROR(VLOOKUP(F{r},Rates!$B$5:$C$8,2,TRUE),0)", fmt=PCT)
        put(ws, f"H{r}", f"=E{r}*G{r}", fmt=NUM)
        if r in notes:
            put(ws, f"I{r}", notes[r])
    put(ws, "B22", "Total", BOLD)
    put(ws, "D22", "=SUM(D6:D20)", BOLD, NUM)
    put(ws, "E22", "=SUM(E6:E20)", BOLD, NUM)
    put(ws, "F22", "=E22/D22", BOLD, PCT)
    put(ws, "H22", "=SUM(H6:H19)", BOLD, NUM)
    b.fault("Commission Q3", "H22", "SUM_OMITS_ROW", "commission total stops at row 19 and misses rep SR-115 (row 20)")

    put(ws, "E9", "148,300")
    b.fault("Commission Q3", "E9", "TEXT_NUMBER_IN_SUM", "SR-104 sales stored as text '148,300'; E22 SUM skips it")
    put(ws, "H14", "=E14*G13", fmt=NUM)
    b.fault("Commission Q3", "H14", "INCONSISTENT_FORMULA", "SR-109 commission uses the rate from row 13")
    put(ws, "G17", 0.06, fmt=PCT)
    b.fault("Commission Q3", "G17", "HARDCODED_OVERRIDE", "typed 6% rate for SR-112 with no note; rows above and below look up the rate card")
    put(ws, "G11", 0.05, BLUE, PCT,
        comment="Guaranteed 5% rate for first two quarters per offer letter, approved by VP Sales.")
    b.ok("Commission Q3", "G11", "typed rate override documented with a cell comment and blue input font")

    put(ws, "B25", "Q3 gross margin (from GL)")
    put(ws, "D25", 1850000, BLUE, NUM)
    put(ws, "B26", "Less: commissions")
    put(ws, "D26", "=-H22", fmt=NUM)
    put(ws, "B27", "Less: bonus pool")
    put(ws, "D27", "=-D29", fmt=NUM)
    put(ws, "B28", "Profit after bonus", BOLD)
    put(ws, "D28", "=SUM(D25:D27)", BOLD, NUM)
    put(ws, "B29", "Bonus pool (10% of profit after bonus)")
    put(ws, "D29", "=D28*Rates!C10", fmt=NUM)
    b.fault("Commission Q3", "D29", "CIRCULAR_REFERENCE",
            "bonus pool is 10% of profit after the bonus pool: D29 -> D28 -> D27 -> D29",
            cycle=["Commission Q3!D29", "Commission Q3!D28", "Commission Q3!D27"])

    b.ok("Commission Q3", "D6:D20", "typed quota inputs")
    b.ok("Commission Q3", "G6:G10", "IFERROR-wrapped VLOOKUP into the rate card")
    b.ok("Commission Q3", "I6:I20", "text notes beside numbers")
    b.ok("Commission Q3", "B2", "numbers in label text (Q3, FY2025)")
    b.ok("Commission Q3", "D25", "typed input (gross margin from GL)")
    widths(ws, {"B": 10, "I": 30})
    return b.save()


# --------------------------------------------------------------------------------------------
# 5. Headcount and payroll plan
# --------------------------------------------------------------------------------------------
def build_payroll():
    b = Book("headcount_payroll.xlsx",
             "Headcount and payroll plan FY2025. Assumptions (defined names), Roster of 20 employees in rows 5-24 "
             "with totals in row 26, Payroll Plan with months across C:N by department, hidden Lookups sheet.")
    a = b.sheet("Assumptions")
    put(a, "B2", "Payroll assumptions FY2025", TITLE)
    for r, (lab, v, fmt, nm) in {4: ("Payroll tax rate", 0.0765, "0.00%", "PayrollTaxRate"),
                                5: ("Benefits per FTE per month", 850, NUM, "BenefitsPerHead"),
                                6: ("Merit increase", 0.035, PCT, "MeritIncrease"),
                                7: ("Merit effective month (1-12)", 7, "0", "MeritMonth")}.items():
        put(a, f"B{r}", lab)
        put(a, f"C{r}", v, BLUE, fmt)
        b.name(nm, f"Assumptions!$C${r}")
    put(a, "B9", "Annual benefits per FTE (memo)")
    put(a, "C9", "=BenefitPerHead*12", fmt=NUM)
    b.fault("Assumptions", "C9", "UNKNOWN_NAME", "uses BenefitPerHead; the defined name is BenefitsPerHead")
    b.ok("Assumptions", "C4:C7", "typed assumption inputs (percentages typed on an assumptions sheet)")
    widths(a, {"B": 32})

    ro = b.sheet("Roster")
    for i, h in enumerate(["Emp ID", "Dept", "Title", "Annual salary", "FTE", "Monthly cost"]):
        put(ro, f"{COL(1 + i)}4", h, BOLD)
    depts = ["Finance", "Sales", "Operations", "IT"]
    titles = {"Finance": ["Analyst", "Senior Accountant", "Controller"],
              "Sales": ["Account Executive", "Sales Manager", "SDR"],
              "Operations": ["Coordinator", "Ops Manager", "Planner"],
              "IT": ["Engineer", "Support Analyst", "IT Manager"]}
    for k in range(20):
        r = 5 + k
        d = depts[k % 4]
        put(ro, f"A{r}", 1001 + k)
        put(ro, f"B{r}", d)
        put(ro, f"C{r}", titles[d][k % 3])
        put(ro, f"D{r}", money(52000, 145000, 500), fmt=NUM)
        put(ro, f"E{r}", 0.5 if k in (6, 15) else 1)
        put(ro, f"F{r}", f"=D{r}/12*E{r}", fmt=NUM)
    put(ro, "A26", "Total", BOLD)
    put(ro, "D26", "=SUM(D5:D22)", BOLD, NUM)
    b.fault("Roster", "D26", "SUM_OMITS_ROW", "salary total stops at row 22 and misses the last two employees (rows 23-24)")
    put(ro, "E26", "=SUM(E5:E24)", BOLD)
    put(ro, "F26", "=SUM(F5:F24)", BOLD, NUM)
    b.ok("Roster", "A5:A24", "numeric employee IDs (codes, not summed)")
    b.ok("Roster", "D5:E24", "typed salary and FTE inputs")
    b.ok("Roster", "F5:F24", "divide by unit constant (/12 annual to monthly)")
    widths(ro, {"B": 12, "C": 20, "D": 14})

    pp = b.sheet("Payroll Plan")
    put(pp, "B2", "Payroll plan FY2025", TITLE)
    put(pp, "B5", "Month #")
    for i in range(12):
        put(pp, f"{COL(3 + i)}5", i + 1)
        put(pp, f"{COL(3 + i)}6", MONTHS[i], BOLD)
    put(pp, "O6", "FY Total", BOLD)
    for k, d in enumerate(depts):
        r = 7 + k
        put(pp, f"B{r}", d)
        put(pp, f"C{r}", f"=SUMIF(Roster!$B$5:$B$24,$B{r},Roster!$F$5:$F$24)", fmt=NUM)
        for c in range(4, 15):
            cl, pl = COL(c), COL(c - 1)
            put(pp, f"{cl}{r}", f"={pl}{r}*IF({cl}$5=MeritMonth,1+MeritIncrease,1)", fmt=NUM)
    put(pp, "B11", "Total salaries", BOLD)
    put(pp, "B12", "Payroll tax")
    put(pp, "B13", "Benefits")
    put(pp, "B15", "Contractors (input)")
    put(pp, "B16", "Total payroll cost", BOLD)
    for c in range(3, 15):
        cl = COL(c)
        put(pp, f"{cl}11", f"=SUM({cl}7:{cl}10)", BOLD, NUM)
        put(pp, f"{cl}12", f"={cl}11*PayrollTaxRate", fmt=NUM)
        put(pp, f"{cl}13", "=Roster!$E$26*BenefitsPerHead", fmt=NUM)
        put(pp, f"{cl}15", money(3000, 9000, 250), BLUE, NUM)
        put(pp, f"{cl}16", f"=SUM({cl}11:{cl}15)", BOLD, NUM)
    for r in (7, 8, 9, 10, 11, 12, 13, 15, 16):
        put(pp, f"O{r}", f"=SUM(C{r}:N{r})", fmt=NUM)
    put(pp, "M16", "=SUM(M7:M15)", BOLD, NUM)
    b.fault("Payroll Plan", "M16", "DOUBLE_COUNT",
            "Nov total payroll sums M7:M15, which holds the department rows M7:M10 and their subtotal M11",
            also_ok=["INCONSISTENT_FORMULA"])
    put(pp, "G13", "=Roster!$E$25*BenefitsPerHead", fmt=NUM)
    b.fault("Payroll Plan", "G13", "INCONSISTENT_FORMULA",
            "May benefits point at Roster!$E$25 (blank row) instead of the FTE total in $E$26")
    put(pp, "I9", 41250, fmt=NUM)
    b.fault("Payroll Plan", "I9", "HARDCODED_OVERRIDE", "Operations July salaries typed over the merit formula; no note")

    b.ok("Payroll Plan", "C5:N5", "header row of typed month numbers above formula columns")
    b.ok("Payroll Plan", "C7:C10", "first month pulls from the roster with SUMIF; later months roll forward")
    b.ok("Payroll Plan", "C15:N15", "typed contractor input row in blue input font")
    b.ok("Payroll Plan", "O7:O16", "FY total column at the end of the monthly run")
    b.ok("Payroll Plan", "C16:L16", "SUM(C11:C15) over the subtotal, tax, benefits and contractor rows plus "
                                    "blank separator row 14; does not include rows 7-10, so no double count")
    widths(pp, {"B": 22})

    lk = b.sheet("Lookups", hidden=True)
    for i, d in enumerate(depts):
        put(lk, f"A{1 + i}", d)
        put(lk, f"B{1 + i}", 5100 + 10 * i)
    return b.save()


# --------------------------------------------------------------------------------------------
# 6. Multi-entity consolidation
# --------------------------------------------------------------------------------------------
CONS_LINES = {6: "Revenue", 7: "Cost of sales", 8: "Gross profit", 10: "Salaries", 11: "Rent",
              12: "Management fee", 13: "Other opex", 14: "Total opex", 16: "EBITDA"}


def build_consolidation():
    b = Book("consolidation_fy25.xlsx",
             "Group consolidation FY2025, USD 000. Three entity sheets (names with spaces), an Eliminations "
             "sheet, an FX sheet with a defined name for EUR/USD, and a Consolidation sheet with entities "
             "across columns C:F and the group in G. Hidden Mapping sheet.")
    data = {"Entity A": {6: 18450, 7: -10920, 10: -3810, 11: -620, 12: 900, 13: -1140},
            "Entity B": {6: 9620, 7: -5770, 10: -2140, 11: -410, 12: -500, 13: -690},
            "Entity C": {6: 7350, 7: -4480, 10: -1650, 11: -380, 12: -400, 13: -520}}
    for name, vals in data.items():
        ws = b.sheet(name)
        cur = "EUR 000" if name == "Entity C" else "USD 000"
        put(ws, "A1", f"{name} - FY2025 trial balance summary ({cur})", TITLE)
        put(ws, "B5", "Line", BOLD)
        put(ws, "C5", "FY2025", BOLD)
        for r, t in CONS_LINES.items():
            put(ws, f"B{r}", t, BOLD if r in (8, 14, 16) else None)
        for r, v in vals.items():
            put(ws, f"C{r}", v, fmt=NUM)
        put(ws, "C8", "=C6+C7", BOLD, NUM)
        put(ws, "C14", "=SUM(C10:C13)", BOLD, NUM)
        put(ws, "C16", "=C8+C14", BOLD, NUM)
        b.ok(name, "C6:C7", "typed trial-balance amounts")
        b.ok(name, "C10:C13", "typed trial-balance amounts")
        widths(ws, {"B": 22})

    el = b.sheet("Eliminations")
    put(el, "A1", "Intercompany eliminations FY2025 (USD 000)", TITLE)
    for r, t in CONS_LINES.items():
        put(el, f"B{r}", t)
    put(el, "C6", -1200, fmt=NUM, comment="Entity A sales to Entity B (IC invoice listing, Dec-25).")
    put(el, "C7", 1200, fmt=NUM)
    put(el, "C8", "=C6+C7", fmt=NUM)
    put(el, "C12", "=-Consolidation!G12", fmt=NUM)
    put(el, "C14", "=SUM(C10:C13)", fmt=NUM)
    put(el, "C16", "=C8+C14", fmt=NUM)
    b.fault("Eliminations", "C12", "CIRCULAR_REFERENCE",
            "fee elimination is set to minus the group fee line, which itself includes this elimination",
            cycle=["Eliminations!C12", "Consolidation!G12", "Consolidation!F12"])
    b.ok("Eliminations", "C6:C7", "typed intercompany elimination entries")

    fx = b.sheet("FX")
    put(fx, "B3", "Rate", BOLD)
    put(fx, "B4", "EUR/USD average FY2025")
    put(fx, "C4", 1.082, BLUE, "0.0000")
    put(fx, "B5", "GBP/USD average FY2025")
    put(fx, "C5", r"='C:\Shared\Treasury\[FX_Rates_2025.xlsx]Month End'!$D$14", fmt="0.0000")
    b.fault("FX", "C5", "EXTERNAL_LINK", "GBP rate linked to a treasury workbook on a shared drive")
    b.name("FX_EURUSD", "FX!$C$4")
    b.ok("FX", "C4", "typed FX rate input, used through defined name FX_EURUSD")
    widths(fx, {"B": 26})

    cs = b.sheet("Consolidation")
    put(cs, "A1", "Consolidated income statement FY2025 (USD 000)", TITLE)
    for i, h in enumerate(["Entity A", "Entity B", "Entity C (USD)", "Eliminations", "Group"]):
        put(cs, f"{COL(3 + i)}5", h, BOLD)
    for r, t in CONS_LINES.items():
        put(cs, f"B{r}", t, BOLD if r in (8, 14, 16) else None)
    for r in (6, 7, 10, 11, 12, 13):
        put(cs, f"C{r}", f"='Entity A'!C{r}", fmt=NUM)
        put(cs, f"D{r}", f"='Entity B'!C{r}", fmt=NUM)
        put(cs, f"E{r}", f"='Entity C'!C{r}*FX_EURUSD", fmt=NUM)
        put(cs, f"F{r}", f"=Eliminations!C{r}", fmt=NUM)
        put(cs, f"G{r}", f"=SUM(C{r}:F{r})", fmt=NUM)
    for c in "CDEFG":
        put(cs, f"{c}8", f"={c}6+{c}7", BOLD, NUM)
        put(cs, f"{c}14", f"=SUM({c}10:{c}13)", BOLD, NUM)
        put(cs, f"{c}16", f"={c}8+{c}14", BOLD, NUM)
    put(cs, "D11", "='Entity B'!C10", fmt=NUM)
    b.fault("Consolidation", "D11", "INCONSISTENT_FORMULA", "Entity B rent pulls Entity B salaries (row 10)")
    put(cs, "G13", "=SUM(C13:E13)", fmt=NUM)
    b.fault("Consolidation", "G13", "SUM_OMITS_ROW", "group other opex omits the Eliminations column F",
            also_ok=["INCONSISTENT_FORMULA"])
    put(cs, "G16", "=G8+G14-1250", BOLD, NUM)
    b.fault("Consolidation", "G16", "HARDCODED_PLUG", "group EBITDA has -1250 typed in to agree to the reported figure")
    b.ok("Consolidation", "E6:E7", "EUR entity converted with the defined name FX_EURUSD")
    b.ok("Consolidation", "E10:E13", "EUR entity converted with the defined name FX_EURUSD")
    b.ok("Consolidation", "C16:F16", "EBITDA adds only the two subtotals (gross profit and total opex)")
    b.ok("Consolidation", "C14:F14", "total opex sums the opex lines")
    b.ok("Consolidation", "C6:C13", "cross-sheet references to entity sheets whose names contain spaces (quoted)")
    widths(cs, {"B": 20})

    mp = b.sheet("Mapping", hidden=True)
    put(mp, "A1", "GL account")
    put(mp, "B1", "Line")
    for i, (gl, line) in enumerate([(4000, "Revenue"), (5000, "Cost of sales"), (6100, "Salaries"),
                                    (6200, "Rent"), (6300, "Management fee"), (6900, "Other opex")]):
        put(mp, f"A{2 + i}", gl)
        put(mp, f"B{2 + i}", line)
    return b.save()


# --------------------------------------------------------------------------------------------
# 7. Capex / depreciation schedule
# --------------------------------------------------------------------------------------------
def build_capex():
    b = Book("capex_depreciation.xlsx",
             "Fixed asset register with straight-line depreciation forecast FY2025-FY2029. Two categories with "
             "subtotals (rows 14 and 22) and a grand total (row 24); Disposals and Summary sheets.")
    ws = b.sheet("Asset Register")
    put(ws, "B2", "Fixed asset register and depreciation forecast - FY2025", TITLE)
    heads = ["Asset ID", "Description", "In service (year)", "Cost", "Useful life (yrs)", "Annual depreciation"]
    for i, h in enumerate(heads):
        put(ws, f"{COL(2 + i)}6", h, BOLD)
    for i, y in enumerate(range(2025, 2030)):
        put(ws, f"{COL(8 + i)}6", y, BOLD)
    it = [("Laptops batch 1", 2021, 4), ("Core switch", 2022, 5), ("Laptops batch 2", 2023, 3),
          ("Storage array", 2024, 5), ("Laptops batch 3", 2025, 3), ("Conference room AV", 2025, 5)]
    veh = [("Delivery van 1", 2021, 5), ("Forklift", 2022, 5), ("Delivery van 2", 2024, 5),
           ("Racking system", 2024, 5), ("Pallet wrapper", 2025, 4)]
    put(ws, "B7", "IT equipment", BOLD)
    put(ws, "B16", "Vehicles & plant", BOLD)

    def asset_rows(start, assets, prefix):
        for k, (desc, yr, life) in enumerate(assets):
            r = start + k
            put(ws, f"B{r}", f"{prefix}-{1001 + k}")
            put(ws, f"C{r}", desc)
            put(ws, f"D{r}", yr)
            put(ws, f"E{r}", money(12000, 90000, 500), fmt=NUM)
            put(ws, f"F{r}", life)
            put(ws, f"G{r}", f"=E{r}/F{r}", fmt=NUM)
            for c in range(8, 13):
                cl = COL(c)
                put(ws, f"{cl}{r}", f"=IF(AND({cl}$6>=$D{r},{cl}$6<$D{r}+$F{r}),$G{r},0)", fmt=NUM)

    asset_rows(8, it, "IT")
    asset_rows(17, veh, "VP")
    for r, (lo, hi, lab) in {14: (8, 13, "Subtotal IT equipment"), 22: (17, 21, "Subtotal vehicles & plant")}.items():
        put(ws, f"B{r}", lab, BOLD)
        for cl in ["E", "G", "H", "I", "J", "K", "L"]:
            put(ws, f"{cl}{r}", f"=SUM({cl}{lo}:{cl}{hi})", BOLD, NUM)
    put(ws, "B24", "Total fixed assets", BOLD)
    for cl in ["G", "H", "I", "J", "K", "L"]:
        put(ws, f"{cl}24", f"={cl}14+{cl}22", BOLD, NUM)
    put(ws, "E24", "=SUM(E8:E22)", BOLD, NUM)
    b.fault("Asset Register", "E24", "DOUBLE_COUNT",
            "total cost sums E8:E22, which contains the IT items and their subtotal E14 (and E17:E21 with E22)")

    put(ws, "K11", "=IF(AND(K$6>=$D11,K$6<$D11+$F11),$G10,0)", fmt=NUM)
    b.fault("Asset Register", "K11", "INCONSISTENT_FORMULA", "FY2028 depreciation for IT-1004 uses row 10's annual charge ($G10)")
    put(ws, "J19", 8400, fmt=NUM)
    b.fault("Asset Register", "J19", "HARDCODED_OVERRIDE", "FY2027 depreciation for VP-1003 typed over the formula, no note")
    put(ws, "E18", "36500")
    b.fault("Asset Register", "E18", "TEXT_NUMBER_IN_SUM", "forklift cost stored as text '36500'; subtotal E22 skips it")
    put(ws, "J9", 0, BLUE, NUM,
        comment="Core switch held for disposal from FY2027 - depreciation suspended. Approved by Controller, memo FA-2025-07.")
    b.ok("Asset Register", "J9", "typed override documented with a cell comment and blue font")
    b.ok("Asset Register", "D8:F13", "typed asset inputs (in-service year, cost, life)")
    b.ok("Asset Register", "D17:D21", "typed in-service years")
    b.ok("Asset Register", "H6:L6", "header row of typed years above formula columns")
    b.ok("Asset Register", "G24:L24", "grand total adds only the two category subtotals")
    b.ok("Asset Register", "B2", "number in label text (FY2025)")
    widths(ws, {"B": 22, "C": 22})

    dp = b.sheet("Disposals")
    put(dp, "B2", "Disposals FY2025", TITLE)
    for i, h in enumerate(["Asset ID", "Proceeds", "NBV at disposal", "Gain/(loss)"]):
        put(dp, f"{COL(2 + i)}4", h, BOLD)
    for k, (aid, pro, nbv) in enumerate([("VP-0907", 6500, 5120), ("IT-0950", 400, 910)]):
        r = 5 + k
        put(dp, f"B{r}", aid)
        put(dp, f"C{r}", pro, fmt=NUM)
        put(dp, f"D{r}", nbv, fmt=NUM)
        put(dp, f"E{r}", f"=C{r}-D{r}", fmt=NUM)
    put(dp, "B8", "Total", BOLD)
    for cl in "CDE":
        put(dp, f"{cl}8", f"=SUM({cl}5:{cl}7)", BOLD, NUM)
    b.ok("Disposals", "C8:E8", "totals over rows 5-7 including a blank row 7")

    sm = b.sheet("Summary")
    put(sm, "B2", "Fixed asset summary", TITLE)
    put(sm, "B5", "Total cost")
    put(sm, "C5", "='Asset Register'!E24", fmt=NUM)
    put(sm, "B6", "FY2025 depreciation")
    put(sm, "C6", "='Asset Register'!H24", fmt=NUM)
    put(sm, "B7", "Gain/(loss) on disposals")
    put(sm, "C7", "=SUM(Disposals!#REF!)", fmt=NUM)
    b.fault("Summary", "C7", "REF_ERROR", "disposals gain/(loss) reference became #REF! after a column was deleted")
    put(sm, "B8", "FY2026 depreciation")
    put(sm, "C8", "='Asset Register'!I24", fmt=NUM)
    widths(sm, {"B": 26})
    return b.save()


# --------------------------------------------------------------------------------------------
# 8. Accruals workpaper and GL reconciliation
# --------------------------------------------------------------------------------------------
def build_accruals():
    b = Book("accruals_rec.xlsx",
             "October month-end accruals workpaper and accrued-liabilities reconciliation. Accruals table at "
             "B7 with recurring accruals (rows 8-21), cut-off invoices (rows 26-31) and a total; GL Rec sheet.")
    ws = b.sheet("Accruals Oct-25")
    put(ws, "B2", "Month-end accruals - October 2025", TITLE)
    put(ws, "B3", "Entity: US Operations. Period: Oct-25.")
    for i, h in enumerate(["Description", "GL account", "Monthly amount", "Months accrued", "Accrual",
                           "Basis / notes"]):
        put(ws, f"{COL(2 + i)}7", h, BOLD)
    items = [("Electricity", 610200, "Avg of last 3 bills"), ("Gas", 610210, "Avg of last 3 bills"),
             ("Water", 610220, "Quarterly bill, 1 month"), ("Audit fee", 640100, "Engagement letter / 12"),
             ("Legal - contract review", 640200, "Estimate from counsel email 28 Oct"),
             ("Cleaning contract", 620300, "Contract rate"), ("Security services", 620310, "Contract rate"),
             ("Telecoms", 615100, "Avg of last 3 bills"), ("Freight - inbound", 520100, "Open POs received"),
             ("Temp staff", 600500, "Agency timesheets wk 43-44"), ("Bonus accrual", 600900, "Plan / 12"),
             ("Software licences", 615400, "Annual renewal spread"),
             ("Marketing agency", 650100, "Retainer"), ("Waste removal", 620400, "Contract rate")]
    for k, (desc, gl, note) in enumerate(items):
        r = 8 + k
        put(ws, f"B{r}", desc)
        put(ws, f"C{r}", gl)
        put(ws, f"D{r}", money(400, 18000, 10), fmt=NUM2)
        put(ws, f"E{r}", 2 if k in (2, 11) else 1)
        put(ws, f"F{r}", f"=D{r}*E{r}", fmt=NUM2)
        put(ws, f"G{r}", note)
    put(ws, "B23", "Subtotal - recurring accruals", BOLD)
    put(ws, "F23", "=SUM(F8:F22)", BOLD, NUM2)
    put(ws, "B25", "Invoices received after cut-off", BOLD)
    inv = [("Courier charges", 520200, 842.50, "Inv 4471 rec'd 3 Nov"),
           ("Office supplies", 630100, 316.20, "Inv 88120 rec'd 4 Nov"),
           ("Equipment hire", 625100, 2150.00, "Inv H-2291 rec'd 5 Nov"),
           ("Recruitment fee", 600600, 1250.00, "Inv R-104 rec'd 5 Nov"),
           ("Catering - board meeting", 650300, 486.75, "Inv 3317 rec'd 6 Nov"),
           ("Consulting - tax", 640300, 3900.00, "Inv T-55 rec'd 7 Nov")]
    for k, (desc, gl, amt, note) in enumerate(inv):
        r = 26 + k
        put(ws, f"B{r}", desc)
        put(ws, f"C{r}", gl)
        put(ws, f"F{r}", amt, fmt=NUM2)
        put(ws, f"G{r}", note)
    put(ws, "F29", "1,250.00")
    b.fault("Accruals Oct-25", "F29", "TEXT_NUMBER_IN_SUM", "recruitment fee pasted as text '1,250.00'; F32 SUM skips it")
    put(ws, "B32", "Subtotal - cut-off invoices", BOLD)
    put(ws, "F32", "=SUM(F26:F31)", BOLD, NUM2)
    put(ws, "B34", "Total accruals", BOLD)
    put(ws, "F34", "=F23+F32", BOLD, NUM2)
    put(ws, "F17", "=D17*E16", fmt=NUM2)
    b.fault("Accruals Oct-25", "F17", "INCONSISTENT_FORMULA", "temp staff accrual multiplies by row 16's months")
    b.ok("Accruals Oct-25", "D8:E21", "typed monthly amounts and months accrued")
    b.ok("Accruals Oct-25", "C8:C21", "numeric GL account codes (not summed)")
    b.ok("Accruals Oct-25", "C26:C31", "numeric GL account codes (not summed)")
    b.ok("Accruals Oct-25", "G8:G21", "text notes beside numbers")
    b.ok("Accruals Oct-25", "F23", "subtotal SUM range includes blank separator row 22")
    b.ok("Accruals Oct-25", "F26:F28", "typed invoice amounts (cut-off list is a typed input block)")
    b.ok("Accruals Oct-25", "F34", "grand total adds only the two subtotals")
    b.ok("Accruals Oct-25", "B2", "numbers in label text (October 2025)")
    widths(ws, {"B": 30, "C": 11, "G": 34})

    gl = b.sheet("GL Rec")
    put(gl, "B2", "Accrued liabilities reconciliation - GL 2100 - Oct-25", TITLE)
    put(gl, "B5", "Balance per trial balance")
    put(gl, "C5", "='[GL_TB_Oct25.xlsx]TB'!$F$212", fmt=NUM2)
    b.fault("GL Rec", "C5", "EXTERNAL_LINK", "TB balance linked to the trial balance export workbook")
    put(gl, "B6", "Balance per accruals schedule")
    put(gl, "C6", "='Accruals Oct-25'!F34", fmt=NUM2)
    put(gl, "B7", "Difference", BOLD)
    put(gl, "C7", "=C5-C6", BOLD, NUM2)
    put(gl, "B9", "Reconciling items:", BOLD)
    put(gl, "B10", "Timing - payroll accrual posted 1 Nov")
    put(gl, "C10", 4820.00, fmt=NUM2)
    put(gl, "D10", "JE 11-0003, posted in November")
    put(gl, "B11", "Reversal of September accruals not yet posted")
    put(gl, "C11", "=-'Sep-25 Accruals'!F34", fmt=NUM2)
    b.fault("GL Rec", "C11", "MISSING_SHEET", "references sheet 'Sep-25 Accruals', which is not in this workbook")
    put(gl, "B12", "FX revaluation on EUR invoices")
    put(gl, "C12", -186.40, fmt=NUM2)
    put(gl, "D12", "Reval run 31 Oct, rate 1.0794")
    put(gl, "B13", "Rounding")
    put(gl, "C13", 0.35, fmt=NUM2)
    put(gl, "B14", "Unexplained difference", BOLD)
    put(gl, "C14", "=C7-SUM(C10:C13)-317.42", BOLD, NUM2)
    b.fault("GL Rec", "C14", "HARDCODED_PLUG", "-317.42 typed in to make the unexplained difference show zero")
    put(gl, "B16", "Prepared by: AP team    Reviewed by: Controller")
    b.ok("GL Rec", "C10", "typed reconciling item with an explanatory note beside it")
    b.ok("GL Rec", "C12:C13", "typed reconciling items with notes")
    b.ok("GL Rec", "B2", "numbers in label text (GL 2100, Oct-25)")
    widths(gl, {"B": 44, "D": 32})
    return b.save()


# --------------------------------------------------------------------------------------------
# 9. Regional sales summary (clean workbook: legit exceptions only)
# --------------------------------------------------------------------------------------------
def build_regional():
    b = Book("regional_sales_summary.xlsx",
             "Clean workbook (no faults). Regional sales FY2025 by quarter with the total row placed ABOVE the "
             "items, region group label rows inside the SUM range, a 'n/a' text row, mix % (*100) and an "
             "IFERROR growth calc against a typed FY2024 sheet.")
    regions = [(7, None, "Americas"), (8, "NA East", None), (9, "NA West", None), (10, "LatAm", None),
               (11, None, "EMEA"), (12, "UK & Ireland", None), (13, "DACH", None), (14, "Nordics", None),
               (15, None, "APAC"), (16, "ANZ", None), (17, "Japan", None), (18, "Middle East", None)]
    prior = b.sheet("FY2024")
    ws = b.sheet("Summary")
    b.wb.move_sheet("Summary", offset=-1)
    for sh, title in ((ws, "Regional sales summary FY2025 (USD 000)"), (prior, "Regional sales FY2024 (USD 000)")):
        put(sh, "B2", title, TITLE)
        for i, h in enumerate(["Region", "Q1", "Q2", "Q3", "Q4", "FY"]):
            put(sh, f"{COL(2 + i)}4", h, BOLD)
        put(sh, "B5", "Total", BOLD)
        for cl in "CDEFG":
            put(sh, f"{cl}5", f"=SUM({cl}7:{cl}18)", BOLD, NUM)
        for r, name, group in regions:
            if group:
                put(sh, f"B{r}", group, BOLD)
                continue
            put(sh, f"B{r}", name)
            if name == "Middle East":
                for cl in "CDEF":
                    put(sh, f"{cl}{r}", "n/a")
            else:
                for cl in "CDEF":
                    put(sh, f"{cl}{r}", money(800, 9000, 10), fmt=NUM)
            put(sh, f"G{r}", f"=SUM(C{r}:F{r})", fmt=NUM)
        widths(sh, {"B": 18})
    put(ws, "H4", "Mix %", BOLD)
    put(ws, "I4", "Growth vs FY2024", BOLD)
    put(ws, "H5", "=SUM(H7:H18)", BOLD, "0.0")
    put(ws, "I5", "=IFERROR(G5/FY2024!G5-1,\"\")", BOLD, PCT)
    for r, name, group in regions:
        if group:
            continue
        put(ws, f"H{r}", f"=G{r}/G$5*100", fmt="0.0")
        put(ws, f"I{r}", f"=IFERROR(G{r}/FY2024!G{r}-1,\"\")", fmt=PCT)
    put(ws, "B20", "Middle East launched Q1 FY2026; shown as n/a. Mix % is in points (x100).")
    b.ok("Summary", "C5:I5", "total row placed above its items, correctly summing rows 7-18")
    b.ok("Summary", "C8:F17", "typed quarterly actuals")
    b.ok("Summary", "C18:F18", "text 'n/a' (not a number) inside the SUM range")
    b.ok("Summary", "B11", "group label rows 7, 11, 15 sit inside the total's SUM range (blank in number columns)")
    b.ok("Summary", "H8:H18", "mix percentage times 100 (unit constant)")
    b.ok("Summary", "I8:I18", "IFERROR-wrapped growth calc; the '-1' is the growth formula, not a plug")
    b.ok("Summary", "C4:F4", "quarter labels Q1-Q4 (numbers in label text)")
    b.ok("FY2024", "C8:F17", "typed prior-year actuals")
    b.ok("FY2024", "C5:G5", "total row above items")
    return b.save()


# --------------------------------------------------------------------------------------------
# Version pairs
# --------------------------------------------------------------------------------------------
def build_opex_pair():
    lines_v1 = ["Salaries", "Benefits", "Rent", "Utilities", "Travel & Entertainment", "Training",
                "Professional fees", "Insurance"]
    rng = random.Random(77)
    base = {ln: money_r(rng, 1500, 90000) for ln in lines_v1 + ["Software subscriptions"]}

    def make(version):
        v2 = version == 2
        fname = f"opex_forecast_v{version}.xlsx"
        b = Book(fname, f"Operating expense forecast FY2026, version {version}. Sheet 'Op Ex' (name with a space) "
                        f"with months across B:M and FY total in N; Summary sheet references it.")
        ws = b.sheet("Op Ex")
        put(ws, "A1", "Operating expense forecast FY2026", TITLE)
        put(ws, "A3", "Growth per month")
        put(ws, "B3", 0.0035 if v2 else 0.003, BLUE, "0.00%")
        put(ws, "A5", "Expense", BOLD)
        for i, m in enumerate(MONTHS):
            put(ws, f"{COL(2 + i)}5", f"{m}-26", BOLD)
        put(ws, "N5", "FY2026", BOLD)
        lines = list(lines_v1)
        if v2:
            lines.insert(3, "Software subscriptions")
            lines[lines.index("Travel & Entertainment")] = "Travel and entertainment"
        rows = {}
        for k, ln in enumerate(lines):
            r = 6 + k
            key = "Travel & Entertainment" if ln == "Travel and entertainment" else ln
            rows[key] = r
            put(ws, f"A{r}", ln)
            put(ws, f"B{r}", base[key], BLUE, NUM)
            for c in range(3, 14):
                put(ws, f"{COL(c)}{r}", f"={COL(c - 1)}{r}*(1+$B$3)", fmt=NUM)
            put(ws, f"N{r}", f"=SUM(B{r}:M{r})", fmt=NUM)
        last = 6 + len(lines) - 1
        tot = last + 1
        put(ws, f"A{tot}", "Total", BOLD)
        for c in range(2, 15):
            put(ws, f"{COL(c)}{tot}", f"=SUM({COL(c)}6:{COL(c)}{last})", BOLD, NUM)
        if v2:
            r = rows["Professional fees"]
            put(ws, f"H{r}", 18500, BLUE, NUM,
                comment="Jul: fixed fee per signed audit engagement letter (Oct-25). Replaces growth formula.")
            b.ok("Op Ex", f"H{r}", "typed override documented with a cell comment and blue font")
        b.ok("Op Ex", "B3", "growth assumption input")
        b.ok("Op Ex", f"B6:B{last}", "January base values typed")
        b.ok("Op Ex", f"N6:N{tot}", "FY total column at the end of the monthly run")
        widths(ws, {"A": 26})
        sm = b.sheet("Summary")
        put(sm, "B2", "FY2026 opex summary", TITLE)
        put(sm, "B4", "FY2026 opex total")
        put(sm, "C4", f"='Op Ex'!N{tot}", fmt=NUM)
        put(sm, "B5", "People costs")
        put(sm, "C5", "='Op Ex'!N6+'Op Ex'!N7" if v2 else "='Op Ex'!N6", fmt=NUM)
        put(sm, "B6", "People cost share")
        put(sm, "C6", "=C5/C4", fmt=PCT)
        widths(sm, {"B": 22})
        b.save()
        return rows, tot

    rows1, tot1 = make(1)
    rows2, tot2 = make(2)
    pf1, pf2 = rows1["Professional fees"], rows2["Professional fees"]
    TRUTH["diffs"].append({
        "before": "opex_forecast_v1.xlsx", "after": "opex_forecast_v2.xlsx",
        "changes": [
            {"sheet": "Op Ex", "cell": f"H{pf2}", "before_cell": f"H{pf1}", "kind": "FORMULA_TO_VALUE",
             "note": "Professional fees Jul growth formula replaced by a typed fixed fee (documented with a comment)"},
            {"sheet": "Summary", "cell": "C5", "before_cell": "C5", "kind": "FORMULA_CHANGED",
             "note": "People costs now adds Benefits (N7) to Salaries (N6)"}],
        "not_material": [
            {"sheet": "Op Ex", "what": "row inserted at 9 (Software subscriptions); every row below shifts down one, "
                                       "formulas keep their meaning"},
            {"sheet": "Op Ex", "what": f"total row moved from {tot1} to {tot2}; its SUM range grew from B6:B{tot1 - 1} "
                                       f"to B6:B{tot2 - 1} to include the new row"},
            {"sheet": "Summary", "what": f"C4 reference shifted from 'Op Ex'!N{tot1} to 'Op Ex'!N{tot2} (same total)"},
            {"sheet": "Op Ex", "what": "input B3 growth per month updated 0.30% -> 0.35%"},
            {"sheet": "Op Ex", "what": f"label renamed 'Travel & Entertainment' -> 'Travel and entertainment' "
                                       f"(A{rows1['Travel & Entertainment']} -> A{rows2['Travel & Entertainment']})"}]})


def money_r(rng, lo, hi, step=50):
    return rng.randrange(lo // step, hi // step + 1) * step


def build_pricing_pair():
    skus = [("SKU-100", 1.00, 1200), ("SKU-110", 1.15, 950), ("SKU-120", 1.30, 600), ("SKU-130", 0.85, 2100),
            ("SKU-140", 1.45, 380), ("SKU-150", 1.10, 1500), ("SKU-160", 0.95, 1750), ("SKU-170", 1.60, 240)]

    def make(version):
        v2 = version == 2
        fname = f"pricing_model_v{version}.xlsx"
        b = Book(fname, f"Product pricing build, version {version}. Inputs sheet, 'Price Build' with 8 SKUs in rows "
                        f"6-13, " + ("a new Sensitivity sheet." if v2 else "and an unreferenced 'Old Scenarios' sheet."))
        inp = b.sheet("Inputs")
        put(inp, "B2", "Pricing inputs", TITLE)
        vals = [("Base unit cost", 44.10 if v2 else 42.50, NUM2), ("Target margin", 0.35, PCT),
                ("Freight per unit", 3.20, NUM2), ("Volume discount threshold (units)", 500, NUM)]
        for i, (lab, v, fmt) in enumerate(vals):
            put(inp, f"B{3 + i}", lab)
            put(inp, f"C{3 + i}", v, BLUE, fmt)
        b.ok("Inputs", "C3:C6", "typed pricing inputs")
        widths(inp, {"B": 34})

        pb = b.sheet("Price Build")
        put(pb, "B2", "Price build FY2026", TITLE)
        for i, h in enumerate(["SKU", "Cost multiplier", "Unit cost", "Freight", "Landed cost", "List price",
                               "Rounded price", "Forecast units"]):
            put(pb, f"{COL(2 + i)}5", h, BOLD)
        for k, (sku, mult, units) in enumerate(skus):
            r = 6 + k
            put(pb, f"B{r}", sku)
            put(pb, f"C{r}", mult, BLUE, "0.00")
            put(pb, f"D{r}", f"=Inputs!$C$3*C{r}", fmt=NUM2)
            put(pb, f"E{r}", "=Inputs!$C$5", fmt=NUM2)
            put(pb, f"F{r}", f"=D{r}+E{r}", fmt=NUM2)
            put(pb, f"G{r}", f"=F{r}/(1-Inputs!$C$4)", fmt=NUM2)
            put(pb, f"H{r}", f"=ROUND(G{r},0)-0.01", fmt=NUM2)
            put(pb, f"I{r}", units, BLUE, NUM)
        if not v2:
            put(pb, "G10", 99.00, fmt=NUM2)
            b.fault("Price Build", "G10", "HARDCODED_OVERRIDE",
                    "SKU-140 list price typed as 99.00 over the margin formula; no note")
        put(pb, "B16", "Average price")
        put(pb, "C16", "=SUMPRODUCT(H6:H13,I6:I13)/SUM(I6:I13)" if v2 else "=AVERAGE(H6:H13)", fmt=NUM2)
        b.ok("Price Build", "C6:C13", "typed cost multipliers")
        b.ok("Price Build", "I6:I13", "typed unit forecasts")
        b.ok("Price Build", "H6:H13", "charm pricing ROUND(...)-0.01 to end in .99; the 0.01 is a pricing rule, not a plug")
        b.ok("Price Build", "D6:F13", "absolute $ anchoring to single input cells on the Inputs sheet")
        widths(pb, {"B": 14})

        if v2:
            se = b.sheet("Sensitivity")
            put(se, "B2", "List price sensitivity to target margin", TITLE)
            margins = [0.30, 0.35, 0.40, 0.45]
            for i, m in enumerate(margins):
                put(se, f"{COL(3 + i)}4", m, BLUE, "0%")
            for k in range(len(skus)):
                r = 5 + k
                put(se, f"B{r}", f"='Price Build'!B{6 + k}")
                for i in range(4):
                    cl = COL(3 + i)
                    put(se, f"{cl}{r}", f"='Price Build'!$F{6 + k}/(1-{cl}$4)", fmt=NUM2)
            b.ok("Sensitivity", "C4:F4", "header row of typed margin percentages above formula columns")
        else:
            os_ = b.sheet("Old Scenarios")
            put(os_, "B2", "Scenarios used in FY2025 pricing review (archived)", TITLE)
            for i, (lab, m) in enumerate([("Low", 0.28), ("Base", 0.33), ("High", 0.38)]):
                put(os_, f"B{4 + i}", lab)
                put(os_, f"C{4 + i}", m, fmt="0%")
        b.save()

    make(1)
    make(2)
    TRUTH["diffs"].append({
        "before": "pricing_model_v1.xlsx", "after": "pricing_model_v2.xlsx",
        "changes": [
            {"sheet": "Old Scenarios", "cell": None, "kind": "SHEET_REMOVED", "note": "archived scenarios sheet deleted"},
            {"sheet": "Sensitivity", "cell": None, "kind": "SHEET_ADDED", "note": "new margin sensitivity table"},
            {"sheet": "Price Build", "cell": "G10", "before_cell": "G10", "kind": "VALUE_TO_FORMULA",
             "note": "SKU-140 typed 99.00 replaced by the margin formula"},
            {"sheet": "Price Build", "cell": "C16", "before_cell": "C16", "kind": "FORMULA_CHANGED",
             "note": "simple AVERAGE replaced by a volume-weighted average"}],
        "not_material": [
            {"sheet": "Inputs", "what": "C3 base unit cost input updated 42.50 -> 44.10"},
            {"sheet": "Price Build", "what": "B16 label 'Average price' unchanged; all other formulas identical"}]})


def build_aging_pair():
    rng = random.Random(4242)
    custs = [f"Customer {i:03d}" for i in range(1, 11)]
    new_custs = ["Customer 011", "Customer 012"]
    bal = {c: [money_r(rng, 0, 40000, 10) if rng.random() > 0.25 else 0 for _ in range(5)] for c in custs + new_custs}

    def make(version):
        v2 = version == 2
        fname = f"ar_aging_v{version}.xlsx"
        b = Book(fname, f"Accounts receivable aging, version {version}. Customers down rows from 6, aging buckets "
                        f"C:G, row total H, column totals below a blank row, provision block under the table, "
                        f"provision rates typed at K6:K7.")
        ws = b.sheet("Aging")
        put(ws, "B2", "Accounts receivable aging - as at 31 Oct 2025", TITLE)
        for i, h in enumerate(["Customer", "Current", "1-30", "31-60", "61-90", "Over 90", "Total"]):
            put(ws, f"{COL(2 + i)}5", h, BOLD)
        put(ws, "J5", "Provision rates", BOLD)
        put(ws, "J6", "61-90 days")
        put(ws, "K6", 0.15 if v2 else 0.10, BLUE, "0%")
        put(ws, "J7", "Over 90 days")
        put(ws, "K7", 0.5, BLUE, "0%")
        order = list(custs)
        if v2:
            order = custs[:6] + new_custs + custs[6:]
        rowof = {}
        for k, c in enumerate(order):
            r = 6 + k
            rowof[c] = r
            put(ws, f"B{r}", c)
            vals = list(bal[c])
            if v2 and c == "Customer 003":
                vals[0] = vals[0] + 5200
            for i, v in enumerate(vals):
                put(ws, f"{COL(3 + i)}{r}", v, fmt=NUM)
            put(ws, f"H{r}", f"=SUM(C{r}:G{r})", fmt=NUM)
        last = 6 + len(order) - 1
        tot = last + 2
        put(ws, f"B{tot}", "Total", BOLD)
        for c in range(3, 9):
            cl = COL(c)
            put(ws, f"{cl}{tot}", f"=SUM({cl}6:{cl}{last + 1})", BOLD, NUM)
        if v2:
            put(ws, f"E{tot}", 61840, BOLD, NUM)
            b.fault("Aging", f"E{tot}", "HARDCODED_OVERRIDE",
                    "31-60 bucket total typed as 61840 between SUM formulas in D and F; no note")
        p = tot + 3
        put(ws, f"B{p}", "Bad debt provision", BOLD)
        put(ws, f"C{p}", f"=G{tot}*$K$7+F{tot}*$K$6" if v2 else f"=G{tot}*$K$7", BOLD, NUM)
        put(ws, f"B{p + 1}", "Provision as % of total receivables")
        put(ws, f"C{p + 1}", f"=C{p}/H{tot}*100", fmt="0.0")
        b.ok("Aging", f"C6:G{last}", "typed customer balances by bucket")
        b.ok("Aging", f"C{tot}:D{tot}", f"column totals over rows 6-{last + 1}, including blank row {last + 1}")
        b.ok("Aging", "K6:K7", "typed provision rate inputs")
        b.ok("Aging", f"C{p + 1}", "percentage times 100 (unit constant)")
        widths(ws, {"B": 16, "J": 14})
        b.save()
        return tot, p, rowof

    tot1, p1, rows1 = make(1)
    tot2, p2, rows2 = make(2)
    TRUTH["diffs"].append({
        "before": "ar_aging_v1.xlsx", "after": "ar_aging_v2.xlsx",
        "changes": [
            {"sheet": "Aging", "cell": f"C{p2}", "before_cell": f"C{p1}", "kind": "FORMULA_CHANGED",
             "note": "provision now also covers the 61-90 bucket (adds F*$K$6)"},
            {"sheet": "Aging", "cell": f"E{tot2}", "before_cell": f"E{tot1}", "kind": "FORMULA_TO_VALUE",
             "note": "31-60 bucket total SUM replaced by a typed number"}],
        "not_material": [
            {"sheet": "Aging", "what": "two customer rows inserted at rows 12-13 inside the table; rows below shift down two"},
            {"sheet": "Aging", "what": f"totals moved from row {tot1} to {tot2}; SUM ranges grew from rows 6-{tot1 - 1} "
                                       f"to 6-{tot2 - 1} to include the new customers"},
            {"sheet": "Aging", "what": f"provision block moved from rows {p1}-{p1 + 1} to {p2}-{p2 + 1}"},
            {"sheet": "Aging", "what": "input K6 provision rate for 61-90 days updated 10% -> 15%"},
            {"sheet": "Aging", "what": f"Customer 003 current balance updated (typed input, C{rows1['Customer 003']})"}]})


# --------------------------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------------------------
CELL_RE = re.compile(r"^\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?$")
NUMTEXT_RE = re.compile(r"^-?[\d,]+(\.\d+)?$")


def operands(formula):
    try:
        toks = Tokenizer(formula).items
    except Exception:
        return []
    return [t.value for t in toks if t.type == "OPERAND" and t.subtype in ("RANGE", "ERROR")]


def classify(tok, cursheet):
    if "#REF!" in tok:
        return ("err", None, tok)
    if "[" in tok:
        return ("ext", None, tok)
    if "!" in tok:
        sh, rng = tok.rsplit("!", 1)
        if sh.startswith("'") and sh.endswith("'"):
            sh = sh[1:-1].replace("''", "'")
        return ("ref", sh, rng.replace("$", "")) if CELL_RE.match(rng) else ("other", sh, rng)
    if CELL_RE.match(tok):
        return ("ref", cursheet, tok.replace("$", ""))
    return ("name", None, tok)


def expand(rng):
    c1, r1, c2, r2 = range_boundaries(rng)
    return [f"{COL(c)}{r}" for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


def in_range(cell, rng):
    if ":" not in rng:
        return cell == rng
    c1, r1, c2, r2 = range_boundaries(rng)
    col, row = coordinate_from_string(cell)
    ci = column_index_from_string(col)
    return c1 <= ci <= c2 and r1 <= row <= r2


def is_formula(v):
    return isinstance(v, str) and v.startswith("=")


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def translate(formula, src, dst):
    try:
        return Translator(formula, origin=src).translate_formula(dst)
    except Exception:
        return None


def run_pattern(ws, addr):
    """Return list of (axis, expected) where both neighbours on an axis share one formula pattern."""
    col, row = coordinate_from_string(addr)
    ci = column_index_from_string(col)
    out = []
    for axis, (a, b) in {"row": ((ci - 1, row), (ci + 1, row)), "col": ((ci, row - 1), (ci, row + 1))}.items():
        if a[0] < 1 or a[1] < 1:
            continue
        aa, bb = f"{COL(a[0])}{a[1]}", f"{COL(b[0])}{b[1]}"
        fa, fb = ws[aa].value, ws[bb].value
        if is_formula(fa) and is_formula(fb) and translate(fa, aa, bb) == fb:
            out.append((axis, translate(fa, aa, addr)))
    return out


def name_targets(wb):
    out = {}
    for nm, dn in wb.defined_names.items():
        out[nm] = dn.attr_text
    return out


def deps(wb, sheet, formula, names):
    res = []
    for tok in operands(formula):
        kind, sh, rng = classify(tok, sheet)
        if kind == "name" and tok in names:
            kind, sh, rng = classify(names[tok], sheet)
        if kind == "ref" and sh in wb.sheetnames:
            res.extend((sh, c) for c in expand(rng))
    return res


def sccs(graph):
    index, low, stack, on, out = {}, {}, [], set(), []
    counter = [0]
    sys.setrecursionlimit(100000)

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in graph.get(v, ()):
                out.append(set(comp))

    for v in list(graph):
        if v not in index:
            strong(v)
    return out


def labelled(entry, sheet, cell):
    for f in entry["faults"]:
        if f["sheet"] == sheet and f["cell"] == cell:
            return True
    for g in entry["legit"]:
        if g["sheet"] == sheet and in_range(cell, g["cell"]):
            return True
    return False


def verify_workbook(fname, entry):
    problems, warnings = [], []
    wb = load_workbook(os.path.join(OUT, fname))
    names = name_targets(wb)

    def chk(cond, msg):
        if not cond:
            problems.append(f"{fname}: {msg}")

    for f in entry["faults"]:
        kind, sheet, cell = f["kind"], f["sheet"], f["cell"]
        tag = f"{kind} {sheet}!{cell}"
        chk(f["severity"] == ("error" if kind in ERROR_KINDS else "risk"), f"{tag} severity")
        if kind == "BROKEN_NAME":
            nm = cell.split(":", 1)[1]
            chk(sheet is None, f"{tag} sheet must be null")
            chk(nm in names, f"{tag} name not defined")
            if nm in names:
                k, sh, _ = classify(names[nm], None)
                chk(k == "err" or (sh is not None and sh not in wb.sheetnames), f"{tag} name is not broken")
            continue
        chk(sheet in wb.sheetnames, f"{tag} sheet missing")
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        v = ws[cell].value
        if kind == "TEXT_NUMBER_IN_SUM":
            chk(isinstance(v, str) and not v.startswith("=") and NUMTEXT_RE.match(v), f"{tag} not numeric text: {v!r}")
            covered = any(is_formula(c.value) and "SUM(" in c.value.upper()
                          and any(classify(t, sheet)[0] == "ref" and classify(t, sheet)[1] == sheet
                                  and in_range(cell, classify(t, sheet)[2]) for t in operands(c.value))
                          for row in ws.iter_rows() for c in row)
            chk(covered, f"{tag} not inside any SUM range")
            continue
        if kind == "HARDCODED_OVERRIDE":
            chk(is_number(v), f"{tag} not a typed number: {v!r}")
            chk(len(run_pattern(ws, cell)) > 0, f"{tag} neighbours are not a matching formula run")
            chk(ws[cell].comment is None, f"{tag} has a comment (would be documented)")
            continue
        chk(is_formula(v), f"{tag} not a formula: {v!r}")
        if not is_formula(v):
            continue
        ops = [classify(t, sheet) for t in operands(v)]
        if kind == "REF_ERROR":
            chk("#REF!" in v, f"{tag} no #REF!")
        elif kind == "MISSING_SHEET":
            chk(any(k in ("ref", "other") and sh not in wb.sheetnames for k, sh, _ in ops), f"{tag} no missing sheet")
        elif kind == "UNKNOWN_NAME":
            chk(any(k == "name" and r not in names for k, _, r in ops), f"{tag} no unknown name")
        elif kind == "EXTERNAL_LINK":
            chk(any(k == "ext" for k, _, _ in ops), f"{tag} no external ref")
        elif kind == "HARDCODED_PLUG":
            chk(re.search(r"[+\-]\s*\d+(\.\d+)?\s*$", v) is not None, f"{tag} no typed +/- constant")
        elif kind == "INCONSISTENT_FORMULA":
            pats = run_pattern(ws, cell)
            chk(len(pats) > 0 and all(exp != v for _, exp in pats), f"{tag} neighbours do not form a differing run")
        elif kind in ("SUM_OMITS_ROW", "DOUBLE_COUNT"):
            chk(v.upper().startswith("=SUM("), f"{tag} not a SUM")
            if kind == "DOUBLE_COUNT":
                rng = [r for k, sh, r in ops if k == "ref"][0]
                inner = [c for c in expand(rng) if is_formula(ws[c].value) and "SUM(" in ws[c].value.upper()
                         and any(in_range(x, rng) for k2, _, r2 in [classify(t, sheet) for t in operands(ws[c].value)]
                                 if k2 == "ref" for x in expand(r2))]
                chk(len(inner) > 0, f"{tag} range holds no subtotal of cells in the range")
        elif kind == "CIRCULAR_REFERENCE":
            cyc = f["cycle"]
            chk(f"{sheet}!{cell}" in cyc, f"{tag} anchor not in cycle")
            for i, node in enumerate(cyc):
                nsh, nc = node.rsplit("!", 1)
                nxt = cyc[(i + 1) % len(cyc)].rsplit("!", 1)
                fv = wb[nsh][nc].value
                chk(is_formula(fv) and tuple(nxt) in deps(wb, nsh, fv, names), f"{tag} {node} does not reference {nxt}")

    for g in entry["legit"]:
        chk(g["sheet"] in wb.sheetnames, f"legit sheet {g['sheet']} missing")
        if g["sheet"] in wb.sheetnames:
            ws = wb[g["sheet"]]
            cells = expand(g["cell"]) if ":" in g["cell"] else [g["cell"]]
            chk(any(ws[c].value is not None for c in cells), f"legit {g['sheet']}!{g['cell']} empty")
            for f in entry["faults"]:
                if f["sheet"] == g["sheet"] and f["cell"] and not f["cell"].startswith("name:"):
                    chk(not in_range(f["cell"], g["cell"]), f"legit {g['cell']} contains fault {f['cell']}")

    # whole-workbook lint: every error-looking or run-breaking cell must be labelled
    graph = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v, addr = c.value, c.coordinate
                if is_formula(v):
                    graph[(ws.title, addr)] = deps(wb, ws.title, v, names)
                    ops = [classify(t, ws.title) for t in operands(v)]
                    bad = ("#REF!" in v or any(k == "ext" for k, _, _ in ops)
                           or any(k in ("ref", "other") and sh not in wb.sheetnames for k, sh, _ in ops)
                           or any(k == "name" and r not in names for k, _, r in ops))
                    if bad and not labelled(entry, ws.title, addr):
                        problems.append(f"{fname}: unlabelled error-type formula {ws.title}!{addr}: {v}")
                    if re.search(r"[+\-]\s*\d+(\.\d+)?(?![\w:$!.])", v) and not labelled(entry, ws.title, addr):
                        warnings.append(f"{fname}: +/- constant (check plug-like) {ws.title}!{addr}: {v}")
                if ws.sheet_state != "visible":
                    continue
                if is_formula(v) or is_number(v):
                    pats = run_pattern(ws, addr)
                    if pats and (is_number(v) or all(exp != v for _, exp in pats)) and not labelled(entry, ws.title, addr):
                        problems.append(f"{fname}: unlabelled run break {ws.title}!{addr}: {v!r}")
                if isinstance(v, str) and not v.startswith("=") and NUMTEXT_RE.match(v.strip()) \
                        and not labelled(entry, ws.title, addr):
                    problems.append(f"{fname}: unlabelled numeric text {ws.title}!{addr}: {v!r}")
    labelled_cycles = [set(tuple(n.rsplit("!", 1)) for n in f["cycle"])
                       for f in entry["faults"] if f["kind"] == "CIRCULAR_REFERENCE"]
    for comp in sccs(graph):
        if comp not in labelled_cycles:
            problems.append(f"{fname}: unlabelled or mis-listed cycle {sorted(comp)}")
    for cyc in labelled_cycles:
        if cyc not in sccs(graph):
            problems.append(f"{fname}: labelled cycle is not exactly a strongly connected component {sorted(cyc)}")
    for nm, ref in names.items():
        k, sh, _ = classify(ref, None)
        broken = k == "err" or (sh is not None and sh not in wb.sheetnames)
        if broken and not any(f["cell"] == f"name:{nm}" for f in entry["faults"]):
            problems.append(f"{fname}: unlabelled broken name {nm}")
    return problems, warnings


def verify_diffs():
    problems = []
    for d in TRUTH["diffs"]:
        wa = load_workbook(os.path.join(OUT, d["before"]))
        wb = load_workbook(os.path.join(OUT, d["after"]))
        for ch in d["changes"]:
            k, sh = ch["kind"], ch["sheet"]
            tag = f"{d['after']} {k} {sh}!{ch['cell']}"
            if k == "SHEET_REMOVED":
                ok = sh in wa.sheetnames and sh not in wb.sheetnames and ch["cell"] is None
            elif k == "SHEET_ADDED":
                ok = sh not in wa.sheetnames and sh in wb.sheetnames and ch["cell"] is None
            else:
                bv, av = wa[sh][ch["before_cell"]].value, wb[sh][ch["cell"]].value
                if k == "FORMULA_TO_VALUE":
                    ok = is_formula(bv) and is_number(av)
                elif k == "VALUE_TO_FORMULA":
                    ok = is_number(bv) and is_formula(av)
                else:
                    ok = is_formula(bv) and is_formula(av) and translate(bv, ch["before_cell"], ch["cell"]) != av
            if not ok:
                problems.append(f"diff check failed: {tag}")
    return problems


def main():
    build_budget()
    build_loan()
    build_model()
    build_commission()
    build_payroll()
    build_consolidation()
    build_capex()
    build_accruals()
    build_regional()
    build_opex_pair()
    build_pricing_pair()
    build_aging_pair()
    with open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(TRUTH, fh, indent=2, sort_keys=False)
        fh.write("\n")

    problems, warnings = [], []
    for fname, entry in TRUTH["workbooks"].items():
        p, w = verify_workbook(fname, entry)
        problems += p
        warnings += w
    problems += verify_diffs()
    for w in warnings:
        print("WARN", w)
    counts = {}
    for e in TRUTH["workbooks"].values():
        for f in e["faults"]:
            counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    n_legit = sum(len(e["legit"]) for e in TRUTH["workbooks"].values())
    n_changes = sum(len(d["changes"]) for d in TRUTH["diffs"])
    print(f"workbooks: {len(TRUTH['workbooks'])}  faults: {sum(counts.values())}  legit: {n_legit}  "
          f"diff pairs: {len(TRUTH['diffs'])}  changes: {n_changes}")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    if problems:
        for p in problems:
            print("FAIL", p)
        sys.exit(1)
    print("all labels verified")


if __name__ == "__main__":
    main()
