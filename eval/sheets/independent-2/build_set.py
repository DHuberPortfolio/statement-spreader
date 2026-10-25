"""Build the independent-2 blind test set for the spreadsheet risk scanner.

Writes every workbook with openpyxl, plus truth.json with the labelled faults,
labelled legitimate exceptions and the version-pair diffs. Reruns are
byte-identical (fixed seeds, fixed document timestamps, fixed zip timestamps).

Run from this folder with the repo venv:
    ..\\..\\..\\.venv\\Scripts\\python.exe build_set.py

After building, the script reopens every workbook and checks each label against
what was written, then runs a simple self-scan for suspicious cells that carry
no label. It exits non-zero if any label check fails.
"""
import datetime
import io
import json
import os
import random
import re
import sys
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles import Font
from openpyxl.utils import column_index_from_string as CI
from openpyxl.utils import get_column_letter as CL
from openpyxl.utils.cell import coordinate_from_string, range_boundaries
from openpyxl.workbook.defined_name import DefinedName

OUT = os.path.dirname(os.path.abspath(__file__))
FIXED = datetime.datetime(2026, 10, 1, 9, 0, 0)
ZIP_TIME = (2026, 10, 1, 9, 0, 0)
BLUE = Font(color="FF0000FF")
BOLD = Font(bold=True)
NUM = '#,##0;(#,##0);"-"'
NUM2 = '#,##0.00;(#,##0.00);"-"'
PCT = "0.0%"
AUTHOR = "Model owner"

SEV = {k: "error" for k in ["REF_ERROR", "MISSING_SHEET", "UNKNOWN_NAME", "BROKEN_NAME",
                            "CIRCULAR_REFERENCE", "TEXT_NUMBER_IN_SUM"]}
SEV.update({k: "risk" for k in ["INCONSISTENT_FORMULA", "HARDCODED_OVERRIDE", "SUM_OMITS_ROW",
                                "DOUBLE_COUNT", "EXTERNAL_LINK", "HARDCODED_PLUG"]})


def cols(a, b):
    return [CL(i) for i in range(CI(a), CI(b) + 1)]


def prv(c):
    return CL(CI(c) - 1)


def sh(c, n):
    return CL(CI(c) + n)


def P(ws, ref, v, inp=False, fmt=None, bold=False, note=None):
    c = ws[ref]
    c.value = v
    if inp:
        c.font = BLUE
    if bold:
        c.font = BOLD
    if fmt:
        c.number_format = fmt
    if note:
        c.comment = Comment(note, AUTHOR)
    return c


class Book:
    def __init__(self, fname, description):
        self.fname = fname
        self.description = description
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        self.faults = []
        self.legit = []

    def ws(self, title, hidden=False):
        w = self.wb.create_sheet(title)
        w.column_dimensions["A"].width = 38
        if hidden:
            w.sheet_state = "hidden"
        return w

    def fault(self, sheet, cell, kind, note, **extra):
        d = {"sheet": sheet, "cell": cell, "kind": kind, "severity": SEV[kind], "note": note}
        d.update(extra)
        self.faults.append(d)

    def ok(self, sheet, cell, what):
        self.legit.append({"sheet": sheet, "cell": cell, "what": what})

    def name(self, n, text):
        self.wb.defined_names.add(DefinedName(n, attr_text=text))

    def save(self):
        p = self.wb.properties
        p.creator = "Finance team"
        p.lastModifiedBy = "Finance team"
        p.created = FIXED
        p.modified = FIXED
        bio = io.BytesIO()
        self.wb.save(bio)
        write_normalised(bio.getvalue(), os.path.join(OUT, self.fname))

    def truth(self):
        return {"description": self.description, "faults": self.faults, "legit": self.legit}


def write_normalised(data, path):
    """Rewrite the xlsx zip with fixed timestamps so reruns are byte-identical."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                body = re.sub(rb"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:\2>)",
                              rb"\g<1>2026-10-01T09:00:00Z\g<3>", body)
            zi = zipfile.ZipInfo(info.filename, date_time=ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            z.writestr(zi, body)
    with open(path, "wb") as f:
        f.write(out.getvalue())


# ---------------------------------------------------------------------------
# 1. 13-week cash-flow forecast
# ---------------------------------------------------------------------------
def build_cash():
    b = Book("cash_13wk.xlsx",
             "13-week cash-flow forecast, weeks across columns C:O with a total column P; "
             "assumptions sheet, hidden helper sheet, treasury tie-out row.")
    a = b.ws("Assumptions")
    c = b.ws("Cash 13wk")
    lst = b.ws("Lists", hidden=True)

    P(a, "A1", "13-week cash forecast - assumptions", bold=True)
    P(a, "A2", "USD. Week 1 = week ending 4 Oct 2026")
    for r, lab, v, f in [(4, "Opening cash (bank, 27 Sep)", 412600, NUM),
                         (5, "Minimum cash covenant", 150000, NUM),
                         (6, "Monthly rent", 38500, NUM),
                         (7, "Base weekly collections", 182000, NUM),
                         (8, "Weekly collections growth", 0.004, PCT),
                         (9, "Supplier payments as % of collections", 0.62, PCT)]:
        P(a, f"A{r}", lab)
        P(a, f"B{r}", v, inp=True, fmt=f)
    P(a, "A11", "Weekly payroll")
    P(a, "B11", "=B14/52", fmt=NUM)
    P(a, "A13", "Annual inputs", bold=True)
    P(a, "A14", "Annual payroll cost (incl. employer taxes)")
    P(a, "B14", 4212000, inp=True, fmt=NUM)

    W = cols("C", "O")
    P(c, "A1", "13-week cash flow forecast", bold=True)
    P(c, "A3", "Week", bold=True)
    P(c, "P3", "13-wk total", bold=True)
    P(c, "A4", "Week ending")
    P(c, "A5", "Basis")
    for i, col in enumerate(W):
        P(c, f"{col}3", i + 1, bold=True)
        P(c, f"{col}4", datetime.datetime(2026, 10, 4) + datetime.timedelta(days=7 * i), fmt="dd-mmm")
        P(c, f"{col}5", "Actual" if i < 2 else "Forecast")

    P(c, "A6", "Receipts", bold=True)
    P(c, "A7", "Customer collections")
    P(c, "C7", 176420, fmt=NUM)
    P(c, "D7", 189315, fmt=NUM)
    for col in W[2:]:
        P(c, f"{col}7", f"=ROUND(Assumptions!$B$7*(1+Assumptions!$B$8)^({col}$3-1),0)", fmt=NUM)
    P(c, "A8", "Other receipts (asset sales, refunds)")
    other = [0, 4200, 0, "1,250.00", 0, 0, 8900, 0, 0, 2750, 0, 0, 0]
    for col, v in zip(W, other):
        P(c, f"{col}8", v, inp=True, fmt=NUM)
    P(c, "A9", "Total receipts", bold=True)
    for col in W:
        P(c, f"{col}9", f"=SUM({col}7:{col}8)", fmt=NUM)

    P(c, "A11", "Disbursements", bold=True)
    P(c, "A12", "Payroll")
    P(c, "A13", "Rent (paid every 4th week)")
    P(c, "A14", "Suppliers")
    P(c, "A15", "Tax & one-off items")
    taxes = [0] * 13
    taxes[8] = -48000
    for col, t in zip(W, taxes):
        P(c, f"{col}12", "=-Assumptions!$B$11", fmt=NUM)
        P(c, f"{col}13", f"=IF(MOD({col}$3,4)=1,-Assumptions!$B$6,0)", fmt=NUM)
        P(c, f"{col}14", f"=-ROUND({col}7*Assumptions!$B$9,0)", fmt=NUM)
        P(c, f"{col}15", t, inp=True, fmt=NUM)
    # fault: payroll week 8 points at the rent assumption
    P(c, "J12", "=-Assumptions!$B$6", fmt=NUM)
    # legit: documented payroll override week 10 (bonus run)
    P(c, "L12", -96500, inp=True, fmt=NUM,
      note="Week 10 payroll includes the Q3 bonus run (HR schedule 22 Sep). Typed on purpose.")
    # fault: undocumented typed supplier figure week 9
    P(c, "K14", -118400, fmt=NUM)
    c["K15"].comment = Comment("Q4 estimated tax instalment due 1 Dec.", AUTHOR)
    P(c, "A16", "Total disbursements", bold=True)
    for col in W:
        P(c, f"{col}16", f"=SUM({col}12:{col}15)", fmt=NUM)

    P(c, "A18", "Net cash flow", bold=True)
    P(c, "A20", "Opening cash")
    P(c, "A21", "Net cash flow")
    P(c, "A22", "Closing cash", bold=True)
    P(c, "A24", "Headroom over covenant")
    for col in W:
        P(c, f"{col}18", f"={col}9+{col}16", fmt=NUM)
        P(c, f"{col}20", "=Assumptions!$B$4" if col == "C" else f"={prv(col)}22", fmt=NUM)
        P(c, f"{col}21", f"={col}18", fmt=NUM)
        P(c, f"{col}22", f"={col}20+{col}21", fmt=NUM)
        P(c, f"{col}24", f"={col}22-Assumptions!$B$5", fmt=NUM)
    P(c, "A26", "Opening cash per treasury system")
    P(c, "C26", "='[Treasury Positions.xlsx]Daily'!$F$12", fmt=NUM)
    P(c, "A27", "Difference (should be nil)")
    P(c, "C27", "=C20-C26", fmt=NUM)

    for r in [7, 8, 9, 12, 13, 14, 15, 16, 18]:
        P(c, f"P{r}", f"=SUM(C{r}:O{r})", fmt=NUM)
    P(c, "P20", "=C20", fmt=NUM)
    P(c, "P21", "=SUM(C21:O21)", fmt=NUM)
    P(c, "P22", "=P20+P21", fmt=NUM)
    P(c, "P24", "=MIN(C24:O24)", fmt=NUM)

    P(lst, "A1", "Week label")
    for i in range(13):
        P(lst, f"A{i + 2}", f"Wk {i + 1}")

    S = "Cash 13wk"
    b.fault(S, "F8", "TEXT_NUMBER_IN_SUM", "Other receipts week 4 pasted from the bank export as text '1,250.00'; F9 and P8 SUMs skip it.")
    b.fault(S, "J12", "INCONSISTENT_FORMULA", "Week 8 payroll references the monthly rent assumption ($B$6) instead of weekly payroll ($B$11).")
    b.fault(S, "K14", "HARDCODED_OVERRIDE", "Week 9 supplier payments typed (-118,400) in the middle of the formula row; no comment, black font.")
    b.fault(S, "C26", "EXTERNAL_LINK", "Treasury tie-out reads another workbook [Treasury Positions.xlsx].")
    b.ok("Assumptions", "B4:B9", "input block (blue font)")
    b.ok("Assumptions", "B11", "unit constant /52 converts annual payroll to weekly")
    b.ok("Assumptions", "B14", "annual input (blue)")
    b.ok(S, "C3:O3", "year/period header row of typed week numbers 1-13 (also used by the rent MOD test)")
    b.ok(S, "C7:D7", "actual weeks typed, then forecast formulas E7:O7")
    b.ok(S, "E7:O7", "forecast formulas after actual columns; the first forecast cell differs from the typed actuals on its left")
    b.ok(S, "C8:E8", "input row (blue) inside a summed block")
    b.ok(S, "G8:O8", "input row (blue) inside a summed block")
    b.ok(S, "L12", "documented hardcoded override (blue font and a cell comment: bonus payroll)")
    b.ok(S, "C13:O13", "rent formula returns rent or 0 by MOD on the week number; one consistent formula, values alternate")
    b.ok(S, "C15:O15", "input row of one-off items; K15 carries a comment")
    b.ok(S, "C20", "opening balance from Assumptions; D20:O20 take the prior week's closing (roll-forward)")
    b.ok(S, "D20:O20", "roll-forward: closing becomes next opening")
    b.ok(S, "P7:P18", "13-week total column at the end of the period run")
    b.ok(S, "P20", "total column opening = week 1 opening (not a sum of openings)")
    b.ok(S, "P24", "total column shows MIN of headroom, not a sum")
    b.ok(S, "C27", "check cell: difference to treasury")
    b.ok("Lists", "A1:A14", "hidden helper sheet, labels only")
    return b


# ---------------------------------------------------------------------------
# 2. Revenue bridge
# ---------------------------------------------------------------------------
def build_bridge():
    b = Book("revenue_bridge.xlsx",
             "Revenue waterfall FY2025 to FY2026: product price/volume data sheet, a vertical bridge "
             "using defined names, and a P&L summary sheet with a space in its name.")
    rnd = random.Random(202)
    d = b.ws("Product Data")
    br = b.ws("Bridge")
    pl = b.ws("P&L Summary")

    P(d, "A1", "Revenue by product - price / volume analysis", bold=True)
    hdr = ["Product", "PY units", "PY price", "PY revenue", "CY units", "CY price", "CY revenue",
           "Volume effect", "Price effect"]
    for i, h in enumerate(hdr):
        P(d, f"{CL(i + 1)}4", h, bold=True)
    prods = ["Core Platform", "Analytics Add-on", "Mobile Suite", "API Access", "Premium Support",
             "Training", "Integrations Pack", "Starter Kit (new)"]
    for i, p in enumerate(prods):
        r = 5 + i
        if i == 7:
            pyu, pyp = 1200, 49.0
            cyu, cyp = 14800, 52.0
        else:
            pyu = rnd.randint(8, 60) * 1000 + rnd.randint(0, 999)
            pyp = round(rnd.uniform(40, 300), 2)
            cyu = int(pyu * rnd.uniform(0.92, 1.18))
            cyp = round(pyp * rnd.uniform(0.98, 1.07), 2)
        P(d, f"A{r}", p)
        P(d, f"B{r}", pyu, fmt=NUM)
        P(d, f"C{r}", pyp, fmt=NUM2)
        P(d, f"D{r}", f"=B{r}*C{r}", fmt=NUM)
        P(d, f"E{r}", cyu, fmt=NUM)
        P(d, f"F{r}", cyp, fmt=NUM2)
        P(d, f"G{r}", f"=E{r}*F{r}", fmt=NUM)
        P(d, f"H{r}", f"=(E{r}-B{r})*C{r}", fmt=NUM)
        P(d, f"I{r}", f"=(F{r}-C{r})*B{r}", fmt=NUM)
    P(d, "A13", "Total", bold=True)
    P(d, "B13", "=SUM(B5:B12)", fmt=NUM)
    P(d, "D13", "=SUM(D5:D11)", fmt=NUM)
    P(d, "E13", "=SUM(E5:E12)", fmt=NUM)
    for col in "GHI":
        P(d, f"{col}13", f"=SUM({col}5:{col}11)", fmt=NUM)

    b.name("PY_Revenue", "'Product Data'!$D$13")
    b.name("CY_Revenue", "'Product Data'!$G$13")

    P(br, "A1", "Revenue bridge FY2025 to FY2026", bold=True)
    P(br, "B3", "USD", bold=True)
    P(br, "C3", "% of PY", bold=True)
    rows = [(5, "FY2025 revenue", "=PY_Revenue"),
            (6, "Volume", "='Product Data'!H13"),
            (7, "Price", "='Product Data'!I13"),
            (8, "Mix (residual)", "=CY_Revenue-PY_Revenue-B6-B7"),
            (9, "FX translation", "='P&L Summary'!C8*('[FX Rates 2026.xlsx]Rates'!$C$4-'P&L Summary'!C9)"),
            (10, "Price concessions & churn credits", "=-'P&L Summary'!C10"),
            (12, "FY2026 revenue (bridge)", "=B5+SUM(B6:B10)+3200"),
            (14, "FY2026 revenue per P&L", "='P&L Summary'!C5"),
            (15, "Check (should be 0)", "=ROUND(B12-B14,0)"),
            (16, "Variance to management accounts", "=B14-CY_Revenue_Mgmt")]
    for r, lab, f in rows:
        P(br, f"A{r}", lab, bold=r in (5, 12))
        P(br, f"B{r}", f, fmt=NUM)
    for r in range(6, 11):
        P(br, f"C{r}", f"=B{r}/$B$5", fmt=PCT)
    P(br, "C12", "=B12/$B$5-1", fmt=PCT)

    P(pl, "A1", "FY2026 summary (management accounts)", bold=True)
    P(pl, "C4", "FY2026", bold=True)
    P(pl, "A5", "Revenue (reported)")
    P(pl, "C5", 18604200, inp=True, fmt=NUM)
    P(pl, "A7", "Memo: FX", bold=True)
    P(pl, "A8", "Revenue billed in EUR (EUR)")
    P(pl, "C8", 2150000, inp=True, fmt=NUM)
    P(pl, "A9", "Budget EUR/USD rate")
    P(pl, "C9", 1.08, inp=True, fmt="0.0000")
    P(pl, "A10", "Price concessions & churn credits")
    P(pl, "C10", 186300, inp=True, fmt=NUM)

    b.fault("Product Data", "D13", "SUM_OMITS_ROW",
            "Totals stop at row 11 and miss the new product in row 12; copied across the revenue and effect columns.",
            group=["G13", "H13", "I13"])
    b.fault("Bridge", "B9", "EXTERNAL_LINK", "FX step reads the closing rate from [FX Rates 2026.xlsx].")
    b.fault("Bridge", "B12", "HARDCODED_PLUG", "Bridge total forced with +3200 to agree to the P&L.")
    b.fault("Bridge", "B16", "UNKNOWN_NAME", "CY_Revenue_Mgmt is not a defined name (only PY_Revenue and CY_Revenue exist).")
    b.ok("Bridge", "B5:B8", "vertical bridge: each step row has its own formula (a list of different items, not a copied run)")
    b.ok("Bridge", "B10", "bridge step reading a quoted sheet name with a space and '&'")
    b.ok("Bridge", "B8", "mix is a residual balancing formula from defined names, with no typed number")
    b.ok("Bridge", "C6:C10", "% of PY anchored on $B$5")
    b.ok("Bridge", "C12", "growth % = total / PY - 1 (the -1 is not a plug)")
    b.ok("Bridge", "B15", "ROUND check cell")
    b.ok("P&L Summary", "C5", "input (blue)")
    b.ok("P&L Summary", "C8:C10", "input block (blue)")
    b.ok("Product Data", "B13", "units total correctly covers all eight products")
    return b


# ---------------------------------------------------------------------------
# 3. Lease schedule (IFRS 16 / ASC 842)
# ---------------------------------------------------------------------------
def build_lease():
    b = Book("lease_ifrs16.xlsx",
             "IFRS 16 / ASC 842 lease schedule: months down the rows (vertical orientation), liability and "
             "right-of-use roll-forwards, defined names, and a disclosure sheet built with SUMIFS.")
    i = b.ws("Inputs")
    s = b.ws("Schedule")
    d = b.ws("Disclosure")

    P(i, "A1", "Lease inputs", bold=True)
    P(i, "A3", "Lease")
    P(i, "B3", "Warehouse 4, Unit B")
    vals = [(4, "First payment date", datetime.datetime(2026, 1, 31), "dd-mmm-yy"),
            (5, "Term (months)", 36, "0"),
            (6, "Incremental borrowing rate (annual)", 0.065, "0.00%"),
            (7, "Monthly payment (year 1)", 21500, NUM),
            (8, "Annual escalation", 0.03, PCT),
            (9, "Initial direct costs", 12000, NUM)]
    for r, lab, v, f in vals:
        P(i, f"A{r}", lab)
        P(i, f"B{r}", v, inp=True, fmt=f)
    b.name("IBR", "Inputs!$B$6")
    b.name("Lease_Term", "Inputs!$B$5")

    # python-side figures for a plausible stale override
    rate = 0.065 / 12
    pays = [21500 * (1.03 ** ((k - 1) // 12)) for k in range(1, 37)]
    npv = sum(p / (1 + rate) ** k for k, p in enumerate(pays, start=1))
    dep = (npv + 12000) / 36

    P(s, "A1", "Lease schedule - Warehouse 4, Unit B", bold=True)
    hdr = ["Period", "Month", "Opening liability", "Interest", "Payment", "Closing liability",
           "ROU opening", "Depreciation", "ROU closing", "Lease year"]
    for k, h in enumerate(hdr):
        P(s, f"{CL(k + 1)}4", h, bold=True)
    for k in range(36):
        r = 5 + k
        P(s, f"A{r}", k + 1)
        P(s, f"B{r}", "=Inputs!$B$4" if r == 5 else f"=EDATE(B{r - 1},1)", fmt="mmm-yy")
        P(s, f"C{r}", "=NPV(IBR/12,E5:E40)" if r == 5 else f"=F{r - 1}", fmt=NUM2)
        P(s, f"D{r}", f"=C{r}*IBR/12", fmt=NUM2)
        P(s, f"E{r}", f"=Inputs!$B$7*(1+Inputs!$B$8)^(J{r}-1)", fmt=NUM2)
        P(s, f"F{r}", f"=C{r}+D{r}-E{r}", fmt=NUM2)
        P(s, f"G{r}", "=C5+Inputs!$B$9" if r == 5 else f"=I{r - 1}", fmt=NUM2)
        P(s, f"H{r}", "=$G$5/Lease_Term", fmt=NUM2)
        P(s, f"I{r}", f"=G{r}-H{r}", fmt=NUM2)
        P(s, f"J{r}", f"=INT((A{r}-1)/12)+1", fmt="0")
    P(s, "F40", "=ROUND(C40+D40-E40,2)", fmt=NUM2,
      note="Final period rounded so the liability closes at exactly nil.")
    P(s, "D24", "=F24*IBR/12", fmt=NUM2)
    P(s, "H29", round(dep - 845.17, 2), fmt=NUM2)
    P(s, "A42", "Total", bold=True)
    for col in "DEH":
        P(s, f"{col}42", f"=SUM({col}5:{col}40)", fmt=NUM2)

    P(d, "A1", "Lease disclosures FY2026", bold=True)
    P(d, "A3", "Maturity analysis - undiscounted lease payments", bold=True)
    P(d, "A4", "Lease year", bold=True)
    P(d, "B4", "Payments", bold=True)
    for k in range(3):
        r = 5 + k
        P(d, f"A{r}", k + 1)
        P(d, f"B{r}", f"=SUMIFS(Schedule!$E$5:$E$40,Schedule!$J$5:$J$40,$A{r})", fmt=NUM)
    P(d, "A8", "Total undiscounted")
    P(d, "B8", "=SUM(B5:B7)", fmt=NUM)
    P(d, "A10", "Lease liability at 31 Dec 2026", bold=True)
    P(d, "A11", "Current (due within 12 months)")
    P(d, "B11", "=Schedule!F16-Schedule!F28", fmt=NUM2)
    P(d, "A12", "Non-current")
    P(d, "B12", "=Schedule!F28", fmt=NUM2)
    P(d, "A13", "Total lease liability (agrees to GL 2410)")
    P(d, "B13", "=B11+B12+0.42", fmt=NUM2)
    P(d, "A15", "Prior-year comparative (closing liability)")
    P(d, "B15", "='Lease Schedule'!F16", fmt=NUM2)
    P(d, "A17", "Interest expense FY2026")
    P(d, "B17", "=SUMIFS(Schedule!$D$5:$D$40,Schedule!$J$5:$J$40,1)", fmt=NUM2)
    P(d, "A18", "Depreciation FY2026")
    P(d, "B18", "=SUMIFS(Schedule!$H$5:$H$40,Schedule!$J$5:$J$40,1)", fmt=NUM2)

    b.fault("Schedule", "D24", "CIRCULAR_REFERENCE",
            "Month 20 interest computed on the closing liability F24, which itself includes D24.",
            cycle=["Schedule!D24", "Schedule!F24"], also_ok=["INCONSISTENT_FORMULA"])
    b.fault("Schedule", "H29", "HARDCODED_OVERRIDE", "Month 25 depreciation typed (stale value) between formula cells.")
    b.fault("Disclosure", "B13", "HARDCODED_PLUG", "Total liability forced with +0.42 to agree to the GL.")
    b.fault("Disclosure", "B15", "MISSING_SHEET", "References sheet 'Lease Schedule', which was renamed to Schedule.")
    b.ok("Inputs", "B4:B9", "input block (blue)")
    b.ok("Schedule", "A5:A40", "typed period counter column (not summed)")
    b.ok("Schedule", "B5", "first month from Inputs; B6:B40 use EDATE on the row above")
    b.ok("Schedule", "C5", "opening liability = NPV of payments; C6:C40 take the prior closing (roll-forward)")
    b.ok("Schedule", "C6:C40", "roll-forward: prior closing becomes opening")
    b.ok("Schedule", "D5:D23", "interest with unit constant /12 on the named annual rate")
    b.ok("Schedule", "G5", "initial ROU asset = liability + initial direct costs; G6:G40 roll from prior closing")
    b.ok("Schedule", "F40", "last period differs on purpose: ROUND to clear the residual (commented)")
    b.ok("Schedule", "H5:H28", "straight-line depreciation anchored on $G$5 and the defined name Lease_Term")
    b.ok("Schedule", "J5:J40", "lease-year helper column, INT((period-1)/12)+1")
    b.ok("Schedule", "D42:E42", "totals of flow columns only (balances are not totalled)")
    b.ok("Disclosure", "A5:A7", "typed lease-year numbers used as SUMIFS criteria")
    b.ok("Disclosure", "B5:B7", "SUMIFS summary by lease year")
    b.ok("Disclosure", "B11", "current portion as a difference of two balances")
    b.ok("Disclosure", "B17:B18", "SUMIFS over different schedule columns (interest vs depreciation)")
    return b


# ---------------------------------------------------------------------------
# 4. Bank reconciliation workpaper
# ---------------------------------------------------------------------------
def build_bankrec():
    b = Book("bank_rec_sep.xlsx",
             "Bank reconciliation workpaper for September: deposits in transit in two batches, outstanding "
             "cheques looked up against a cheque register on a sheet named 'GL & Bank Data'.")
    rnd = random.Random(404)
    rec = b.ws("Rec")
    g = b.ws("GL & Bank Data")

    payees = ["Northside Office Supply", "Keller Logistics", "Brightline Telecom", "Harbor Insurance",
              "Metro Utilities", "Atlas Facilities", "Pinecrest Legal", "Summit Staffing",
              "Clearwater IT", "Redwood Catering"]
    P(g, "A1", "Cheque register - September 2026", bold=True)
    for k, h in enumerate(["Cheque no", "Payee", "Amount", "Date"]):
        P(g, f"{CL(k + 1)}4", h, bold=True)
    register = {}
    for k in range(30):
        r = 5 + k
        no = 10441 + k
        amt = round(rnd.uniform(120, 9800), 2)
        if no == 10466:
            amt = 845.20
        pay = payees[rnd.randrange(len(payees))]
        register[no] = amt
        P(g, f"A{r}", no)
        P(g, f"B{r}", pay)
        P(g, f"C{r}", amt, fmt=NUM2)
        P(g, f"D{r}", datetime.datetime(2026, 9, 1) + datetime.timedelta(days=k), fmt="dd-mmm")
    P(g, "A38", "GL cash balance (account 1010) at 30 Sep")
    P(g, "B38", 1201337.86, fmt=NUM2)

    P(rec, "A1", "Bank reconciliation - Operating account - 30 September 2026", bold=True)
    P(rec, "A3", "Balance per bank statement")
    P(rec, "D3", 1284916.42, inp=True, fmt=NUM2)
    P(rec, "A5", "Add: deposits in transit", bold=True)
    P(rec, "A6", "Lockbox batch 29 Sep")
    for r, (desc, v) in zip([7, 8, 9], [("Customer receipt", 18450.00), ("Customer receipt", 7320.55),
                                        ("Customer receipt", 2104.10)]):
        P(rec, f"B{r}", desc)
        P(rec, f"C{r}", v, fmt=NUM2)
    P(rec, "A10", "Batch subtotal")
    P(rec, "C10", "=SUM(C7:C9)", fmt=NUM2)
    P(rec, "A11", "Branch deposit 30 Sep")
    for r, v in zip([12, 13], [5600.00, 912.40]):
        P(rec, f"B{r}", "Counter deposit")
        P(rec, f"C{r}", v, fmt=NUM2)
    P(rec, "A14", "Batch subtotal")
    P(rec, "C14", "=SUM(C12:C13)", fmt=NUM2)
    P(rec, "A15", "Total deposits in transit")
    P(rec, "D15", "=SUM(C7:C14)", fmt=NUM2)

    P(rec, "A17", "Less: outstanding cheques", bold=True)
    P(rec, "D17", "=-SUM(C19:C30)", fmt=NUM2)
    P(rec, "A18", "Cheque no", bold=True)
    P(rec, "B18", "Payee (from register)", bold=True)
    P(rec, "C18", "Amount", bold=True)
    outstanding = {19: 10447, 20: 10452, 21: 10455, 22: 10458, 23: 10461, 25: 10466, 26: 10467,
                   28: 10469, 29: 10470, 30: 10471}
    for r, no in outstanding.items():
        P(rec, f"A{r}", no)
        P(rec, f"B{r}", f"=IFERROR(VLOOKUP(A{r},'GL & Bank Data'!$A$5:$C$34,2,FALSE),\"Not in register\")")
        amt = register.get(no, 1312.00)
        P(rec, f"C{r}", "845.20" if r == 25 else amt, fmt=NUM2)
    P(rec, "B22", "=VLOOKUP(A22,'GL & Bank Data'!$A$5:$C$34,2,FALSE)")
    P(rec, "A27", "-- cheque 10458 voided and re-issued as 10471, see note 2 --")

    P(rec, "A32", "Adjusted bank balance", bold=True)
    P(rec, "D32", "=D3+D15+D17", fmt=NUM2)
    P(rec, "A34", "Balance per general ledger")
    P(rec, "D34", "='GL & Bank Data'!B38", fmt=NUM2)
    for r, lab, v in [(35, "Less: bank charges not yet recorded", -86.50),
                      (36, "Add: interest credited by bank", 212.18),
                      (37, "Less: NSF cheque returned (Keller Logistics)", -1450.00)]:
        P(rec, f"A{r}", lab)
        P(rec, f"C{r}", v, inp=True, fmt=NUM2)
    P(rec, "A38", "Adjusted GL balance", bold=True)
    P(rec, "D38", "=D34+SUM(C35:C37)-37.50", fmt=NUM2)
    P(rec, "A40", "Unreconciled difference")
    P(rec, "D40", "=ROUND(D32-D38,2)", fmt=NUM2)
    P(rec, "A42", "Prepared: AK 3-Oct-2026    Reviewed: ________")

    b.fault("Rec", "D15", "DOUBLE_COUNT", "Total deposits SUM(C7:C14) includes both batch subtotals (C10, C14) and their items.")
    b.fault("Rec", "C25", "TEXT_NUMBER_IN_SUM", "Cheque 10466 amount stored as text '845.20'; D17's SUM skips it.")
    b.fault("Rec", "D38", "HARDCODED_PLUG", "Adjusted GL balance forced with -37.50 to make the difference nil.")
    b.fault("Rec", "B22", "INCONSISTENT_FORMULA", "Payee lookup without the IFERROR wrapper used on every other row.")
    b.ok("Rec", "D3", "input: bank statement balance (blue)")
    b.ok("Rec", "C10", "batch subtotal")
    b.ok("Rec", "C14", "batch subtotal")
    b.ok("Rec", "D17", "total placed above its items (outstanding cheques listed below)")
    b.ok("Rec", "C19:C24", "SUM range with a blank separator row (row 24)")
    b.ok("Rec", "C26:C30", "SUM range continuing past a text memo row (row 27)")
    b.ok("Rec", "B19:B21", "IFERROR lookups against the register")
    b.ok("Rec", "B23:B30", "IFERROR lookups against the register (blank and memo rows skipped)")
    b.ok("Rec", "C35:C37", "typed reconciling items (blue inputs), not formulas")
    b.ok("Rec", "D34", "cross-sheet reference to a quoted sheet name containing '&'")
    b.ok("Rec", "D40", "ROUND check cell")
    return b


# ---------------------------------------------------------------------------
# 5. VAT return working
# ---------------------------------------------------------------------------
def build_vat():
    b = Book("vat_return_q3.xlsx",
             "Quarterly VAT return working: sales and purchase ledgers with VAT looked up from a hidden "
             "rate table (defined name), the nine-box return, and a SUMIFS analysis by rate code.")
    rnd = random.Random(505)
    sl = b.ws("Sales Ledger")
    pl = b.ws("Purchase Ledger")
    ret = b.ws("Return")
    rc = b.ws("RateCodes", hidden=True)

    P(rc, "A3", "Code", bold=True)
    P(rc, "B3", "Rate", bold=True)
    P(rc, "C3", "Description", bold=True)
    for r, (code, rate, desc) in zip(range(4, 8), [("S", 0.2, "Standard"), ("R", 0.05, "Reduced"),
                                                   ("Z", 0.0, "Zero-rated"), ("E", 0.0, "Exempt")]):
        P(rc, f"A{r}", code)
        P(rc, f"B{r}", rate, fmt=PCT)
        P(rc, f"C{r}", desc)
    b.name("VAT_Rates", "RateCodes!$A$4:$B$7")
    b.name("Rates_2024", "#REF!")
    b.name("PY_Box1", "'Return Q2'!$C$5")

    custs = ["Albion Retail Ltd", "Mercer & Hale", "Tidewater Foods", "Graystone Clinics",
             "Oakfield Schools Trust", "Lumen Studios", "Fenwick Hardware"]
    supps = ["Brightline Telecom", "Castle Freight", "Northgate Paper", "Kestrel Software",
             "Overseas Parts GmbH", "Orchard Cleaning"]

    def ledger(ws, title, n, names, codes, weights, start):
        P(ws, "A1", title, bold=True)
        for k, h in enumerate(["Date", "Ref", "Counterparty", "Code", "Net", "VAT", "Gross"]):
            P(ws, f"{CL(k + 1)}4", h, bold=True)
        for k in range(n):
            r = 5 + k
            P(ws, f"A{r}", datetime.datetime(2026, 7, 1) + datetime.timedelta(days=3 * k), fmt="dd-mmm")
            P(ws, f"B{r}", f"{start}{1000 + k}")
            P(ws, f"C{r}", names[rnd.randrange(len(names))])
            P(ws, f"D{r}", rnd.choices(codes, weights)[0])
            P(ws, f"E{r}", round(rnd.uniform(200, 12000), 2), fmt=NUM2)
            P(ws, f"F{r}", f"=ROUND(E{r}*IFERROR(VLOOKUP(D{r},VAT_Rates,2,FALSE),0),2)", fmt=NUM2)
            P(ws, f"G{r}", f"=E{r}+F{r}", fmt=NUM2)
        tr = 5 + n + 1
        P(ws, f"A{tr}", "Totals", bold=True)
        for col in "EFG":
            P(ws, f"{col}{tr}", f"=SUM({col}5:{col}{4 + n})", fmt=NUM2)

    ledger(sl, "Sales ledger Q3 2026 (Jul-Sep)", 30, custs, ["S", "R", "Z", "E"], [70, 10, 15, 5], "INV")
    ledger(pl, "Purchase ledger Q3 2026 (Jul-Sep)", 25, supps, ["S", "Z", "E", "RC"], [70, 10, 8, 12], "PI")
    P(sl, "D21", "R")
    P(sl, "F21", "=ROUND(E21*0.2,2)", fmt=NUM2)

    P(ret, "A1", "VAT return - quarter ended 30 Sep 2026", bold=True)
    P(ret, "A3", "Box", bold=True)
    P(ret, "B3", "Description", bold=True)
    P(ret, "C3", "Amount", bold=True)
    boxes = [(5, 1, "VAT due on sales", "=SUM('Sales Ledger'!$F$5:$F$34)"),
             (6, 2, "VAT due on reverse-charge acquisitions",
              "=SUMIFS('Purchase Ledger'!#REF!,'Purchase Ledger'!$D$5:$D$29,\"RC\")"),
             (7, 3, "Total VAT due", "=C5+C6"),
             (8, 4, "VAT reclaimed on purchases", "=SUM('Purchase Ledger'!$F$5:$F$29)"),
             (9, 5, "Net VAT payable", "=C7-C8"),
             (10, 6, "Total sales excluding VAT", "=ROUNDDOWN(SUM('Sales Ledger'!$E$5:$E$34),0)"),
             (11, 7, "Total purchases excluding VAT", "=ROUNDDOWN(SUM('Purchase Ledger'!$E$5:$E$29),0)"),
             (12, 8, "Supplies of goods to EU", 0),
             (13, 9, "Acquisitions of goods from EU", 0)]
    for r, box, desc, f in boxes:
        P(ret, f"A{r}", box)
        P(ret, f"B{r}", desc)
        P(ret, f"C{r}", f, inp=not (isinstance(f, str)), fmt=NUM2)
    P(ret, "A15", "Analysis of sales by rate code", bold=True)
    P(ret, "A16", "Code", bold=True)
    P(ret, "B16", "Net sales", bold=True)
    P(ret, "C16", "Output VAT", bold=True)
    for r, code in zip(range(17, 21), ["S", "R", "Z", "E"]):
        P(ret, f"A{r}", code)
        P(ret, f"B{r}", f"=SUMIFS('Sales Ledger'!$E$5:$E$34,'Sales Ledger'!$D$5:$D$34,$A{r})", fmt=NUM2)
        P(ret, f"C{r}", f"=SUMIFS('Sales Ledger'!$F$5:$F$34,'Sales Ledger'!$D$5:$D$34,$A{r})", fmt=NUM2)
    P(ret, "A21", "Total")
    P(ret, "B21", "=SUM(B17:B20)", fmt=NUM2)
    P(ret, "C21", "=SUM(C17:C20)", fmt=NUM2)
    P(ret, "A22", "Check to Box 1")
    P(ret, "C22", "=C21-C5", fmt=NUM2)

    b.fault("Return", "C6", "REF_ERROR", "Box 2 SUMIFS sum range is #REF! (the notional-VAT column was deleted).")
    b.fault(None, "name:Rates_2024", "BROKEN_NAME", "Defined name Rates_2024 = #REF!.")
    b.fault(None, "name:PY_Box1", "BROKEN_NAME", "Defined name PY_Box1 points at sheet 'Return Q2', which does not exist.")
    b.fault("Sales Ledger", "F21", "INCONSISTENT_FORMULA", "VAT typed at 20% instead of the rate lookup; the line is reduced-rate (R).")
    b.ok("RateCodes", "A4:B7", "hidden helper sheet holding the rate table behind the defined name VAT_Rates")
    b.ok("Sales Ledger", "F5:F20", "ROUND(IFERROR(VLOOKUP(...))) rate lookups")
    b.ok("Sales Ledger", "F22:F34", "ROUND(IFERROR(VLOOKUP(...))) rate lookups")
    b.ok("Purchase Ledger", "F5:F29", "IFERROR lookup returns 0 for the RC code that is not in the rate table")
    b.ok("Return", "A5:A13", "typed box numbers 1-9 (labels, not summed)")
    b.ok("Return", "C7", "Box 3 = Box 1 + Box 2 (total of two boxes)")
    b.ok("Return", "C9", "Box 5 = Box 3 - Box 4 (a difference, not a sum)")
    b.ok("Return", "C10:C11", "ROUNDDOWN to whole units, as the return requires")
    b.ok("Return", "C12:C13", "typed nil boxes (blue inputs)")
    b.ok("Return", "B17:C20", "SUMIFS pivot-style summary by rate code")
    b.ok("Return", "C22", "check cell")
    return b


# ---------------------------------------------------------------------------
# 6. Inventory roll-forward
# ---------------------------------------------------------------------------
def build_inventory():
    b = Book("inventory_rollforward.xlsx",
             "Monthly inventory roll-forward (raw materials and finished goods blocks plus a total block) "
             "driven by a sales forecast sheet, and a September stock-count valuation by warehouse.")
    rnd = random.Random(606)
    i = b.ws("Inputs")
    sf = b.ws("Sales Forecast")
    rf = b.ws("Roll-forward")
    v = b.ws("Valuation")
    M = cols("C", "N")
    mlab = [f"{m}-26" for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                                "Nov", "Dec"]]

    P(i, "A1", "Inventory inputs", bold=True)
    for r, lab, val, f in [(4, "Opening raw materials (1 Jan)", 842000, NUM),
                           (5, "Opening finished goods (1 Jan)", 1316500, NUM),
                           (7, "Monthly write-off rate (of opening)", 0.002, "0.00%"),
                           (8, "RM content of production cost", 0.58, PCT),
                           (9, "Obsolescence provision %", 0.035, PCT)]:
        P(i, f"A{r}", lab)
        P(i, f"B{r}", val, inp=True, fmt=f)
    b.name("Obsolescence_Pct", "Inputs!$B$9")

    P(sf, "A1", "Sales forecast 2026", bold=True)
    for col, lab in zip(M, mlab):
        P(sf, f"{col}3", lab, bold=True)
    P(sf, "A5", "Units shipped")
    P(sf, "A6", "Standard cost per unit")
    P(sf, "A7", "Cost of sales")
    P(sf, "A8", "RM consumed")
    for col in M:
        P(sf, f"{col}5", rnd.randint(18000, 26000), inp=True, fmt=NUM)
        P(sf, f"{col}6", 41.20 if col == "C" else f"={prv(col)}6", inp=col == "C", fmt=NUM2)
        P(sf, f"{col}7", f"=ROUND({col}5*{col}6,0)", fmt=NUM)
        P(sf, f"{col}8", f"=ROUND({col}7*Inputs!$B$8,0)", fmt=NUM)
    P(sf, "H6", 43.10, inp=True, fmt=NUM2,
      note="Standard cost revised from June (cost roll signed off 28 May).")

    P(rf, "A1", "Inventory roll-forward 2026", bold=True)
    for col, lab in zip(M, mlab):
        P(rf, f"{col}3", lab, bold=True)
    P(rf, "O3", "FY 2026", bold=True)
    labels = {5: "Raw materials", 6: "Opening", 7: "Purchases", 8: "Consumed to production",
              9: "Write-offs", 10: "Closing raw materials", 12: "Finished goods", 13: "Opening",
              14: "Transfers in from production", 15: "Cost of sales", 16: "Write-offs",
              17: "Customer returns to stock", 18: "Closing finished goods", 20: "Total inventory",
              21: "Opening", 22: "Closing", 23: "Movement in month", 25: "FG days on hand"}
    for r, lab in labels.items():
        P(rf, f"A{r}", lab, bold=r in (5, 12, 20))
    for col in M:
        first = col == "C"
        P(rf, f"{col}6", "=Inputs!$B$4" if first else f"={prv(col)}10", fmt=NUM)
        P(rf, f"{col}7", rnd.randint(420, 520) * 1000, inp=True, fmt=NUM)
        P(rf, f"{col}8", f"=-'Sales Forecast'!{col}8", fmt=NUM)
        P(rf, f"{col}9", f"=-ROUND({col}6*Inputs!$B$7,0)", fmt=NUM)
        P(rf, f"{col}10", f"=SUM({col}6:{col}9)", fmt=NUM)
        P(rf, f"{col}13", "=Inputs!$B$5" if first else f"={prv(col)}18", fmt=NUM)
        P(rf, f"{col}14", f"=-{col}8/Inputs!$B$8", fmt=NUM)
        P(rf, f"{col}15", f"=-'Sales Forecast'!{col}7", fmt=NUM)
        P(rf, f"{col}16", f"=-ROUND({col}13*Inputs!$B$7,0)", fmt=NUM)
        P(rf, f"{col}17", rnd.randint(2, 9) * 1000, inp=True, fmt=NUM)
        P(rf, f"{col}18", f"=SUM({col}13:{col}16)", fmt=NUM)
        P(rf, f"{col}21", f"={col}6+{col}13", fmt=NUM)
        P(rf, f"{col}22", f"={col}10+{col}18", fmt=NUM)
        P(rf, f"{col}23", f"={col}22-{col}21", fmt=NUM)
        P(rf, f"{col}25", f"=IFERROR({col}18/-{col}15*30,0)", fmt="0.0")
    P(rf, "J15", -861250, fmt=NUM)
    P(rf, "O6", "=C6", fmt=NUM)
    P(rf, "O13", "=C13", fmt=NUM)
    for r in [7, 8, 9, 14, 15, 16, 17]:
        P(rf, f"O{r}", f"=SUM(C{r}:N{r})", fmt=NUM)
    P(rf, "O10", "=SUM(O6:O9)", fmt=NUM)
    P(rf, "O18", "=SUM(O13:O16)", fmt=NUM)
    for r, f in [(21, "=O6+O13"), (22, "=O10+O18"), (23, "=O22-O21")]:
        P(rf, f"O{r}", f, fmt=NUM)
    P(rf, "O25", "=IFERROR(O18/-O15*365,0)", fmt="0.0")

    P(v, "A1", "Stock count valuation - 30 Sep 2026", bold=True)
    for k, h in enumerate(["SKU", "Description", "Qty", "Unit cost", "Value"]):
        P(v, f"{CL(k + 1)}4", h, bold=True)
    blocks = [(5, "Leeds DC", [6, 7, 8, 9], 10), (12, "Hull DC", [13, 14, 15], 16),
              (18, "Consignment stock", [19, 20], 21)]
    sku = 1001
    for hr, name, items, sub in blocks:
        P(v, f"A{hr}", name, bold=True)
        for r in items:
            P(v, f"A{r}", f"FG-{sku}")
            P(v, f"B{r}", f"Finished unit type {sku - 1000}")
            P(v, f"C{r}", rnd.randint(800, 9000), fmt=NUM)
            P(v, f"D{r}", round(rnd.uniform(38, 46), 2), fmt=NUM2)
            P(v, f"E{r}", f"=ROUND(C{r}*D{r},2)", fmt=NUM2)
            sku += 1
        P(v, f"A{sub}", f"{name} subtotal")
        P(v, f"E{sub}", f"=SUM(E{items[0]}:E{items[-1]})", fmt=NUM2)
    P(v, "A23", "Total stock at cost", bold=True)
    P(v, "E23", "=SUM(E6:E21)", fmt=NUM2)
    P(v, "A25", "Obsolescence provision")
    P(v, "E25", "=-ROUND(E23*Obsolescence_Rate,0)", fmt=NUM2)
    P(v, "A26", "Net stock value", bold=True)
    P(v, "E26", "=E23+E25", fmt=NUM2)
    P(v, "A28", "Per roll-forward (Sep closing FG)")
    P(v, "E28", "='Roll-forward'!K18", fmt=NUM2)
    P(v, "A29", "Difference")
    P(v, "E29", "=E26-E28", fmt=NUM2)

    b.fault("Roll-forward", "C18", "SUM_OMITS_ROW",
            "FG closing SUM(C13:C16) stops above the customer-returns row 17; copied across every month and FY.",
            group=[f"{c}18" for c in cols("D", "O")])
    b.fault("Roll-forward", "J15", "HARDCODED_OVERRIDE", "August cost of sales typed (-861,250) inside the formula row.")
    b.fault("Valuation", "E23", "DOUBLE_COUNT", "Total SUM(E6:E21) includes the three warehouse subtotals and their items.")
    b.fault("Valuation", "E25", "UNKNOWN_NAME", "Obsolescence_Rate is not defined; the name is Obsolescence_Pct.")
    b.ok("Inputs", "B4:B9", "input block (blue)")
    b.ok("Sales Forecast", "C5:N5", "input row (blue)")
    b.ok("Sales Forecast", "D6:N6", "standard cost carried forward from the prior month")
    b.ok("Sales Forecast", "H6", "documented hardcoded override (blue font and comment: standard-cost revision)")
    b.ok("Roll-forward", "C6", "opening balance from Inputs; D6:N6 take the prior closing")
    b.ok("Roll-forward", "D6:N6", "roll-forward: closing becomes next opening")
    b.ok("Roll-forward", "C13", "opening balance from Inputs; D13:N13 take the prior closing")
    b.ok("Roll-forward", "D13:N13", "roll-forward: closing becomes next opening")
    b.ok("Roll-forward", "O6", "FY column opening = January opening, not a sum")
    b.ok("Roll-forward", "O13", "FY column opening = January opening, not a sum")
    b.ok("Roll-forward", "O7:O9", "FY column sums the flows")
    b.ok("Roll-forward", "O10", "FY closing = FY opening + FY flows (same SUM shape as the month columns)")
    b.ok("Roll-forward", "C7:N7", "input row (blue)")
    b.ok("Roll-forward", "C17:N17", "input row (blue)")
    b.ok("Roll-forward", "C21:O23", "total block = sum of the two block subtotals (grand total of subtotals)")
    b.ok("Roll-forward", "O25", "FY days-on-hand uses *365 while the months use *30 (unit constants)")
    b.ok("Roll-forward", "C25:N25", "IFERROR ratio with unit constant *30")
    b.ok("Valuation", "E10", "warehouse subtotal")
    b.ok("Valuation", "E16", "warehouse subtotal")
    b.ok("Valuation", "E21", "warehouse subtotal")
    b.ok("Valuation", "E29", "check cell")
    return b


# ---------------------------------------------------------------------------
# 7. Quarterly board pack
# ---------------------------------------------------------------------------
def build_board():
    b = Book("board_pack_q.xlsx",
             "Quarterly board pack: P&L with Q1, Q2, H1, Q3, Q4, H2, FY columns interleaved, budget, "
             "variance and variance %; a KPI sheet with point-in-time half-year columns.")
    rnd = random.Random(707)
    md = b.ws("Monthly Data")
    pl = b.ws("P&L")
    kp = b.ws("KPIs")
    M = cols("C", "N")
    mlab = [f"{m}-26" for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                                "Nov", "Dec"]]

    P(md, "A1", "Monthly actuals 2026 (ERP extract)", bold=True)
    for col, lab in zip(M, mlab):
        P(md, f"{col}3", lab, bold=True)
    mdrows = {5: "Subscription revenue", 6: "Services revenue", 8: "Cost of revenue", 10: "Salaries",
              11: "Benefits", 13: "Marketing", 14: "G&A", 16: "D&A"}
    for r, lab in mdrows.items():
        P(md, f"A{r}", lab)
    for m, col in enumerate(M):
        sub = int(1420000 * 1.012 ** m * rnd.uniform(0.98, 1.02))
        svc = rnd.randint(150, 260) * 1000
        sal = int(620000 * 1.008 ** m * rnd.uniform(0.99, 1.01))
        vals = {5: sub, 6: svc, 8: -int((sub + svc) * rnd.uniform(0.23, 0.27)), 10: -sal,
                11: -int(sal * 0.18), 13: -rnd.randint(140, 220) * 1000, 14: -rnd.randint(95, 130) * 1000,
                16: -rnd.randint(42, 48) * 1000}
        for r, val in vals.items():
            P(md, f"{col}{r}", val, fmt=NUM)

    P(pl, "A1", "Board pack - income statement FY2026", bold=True)
    heads = {"C": "Q1", "D": "Q2", "E": "H1", "F": "Q3", "G": "Q4", "H": "H2", "I": "FY 2026",
             "J": "Budget FY", "K": "Var", "L": "Var %"}
    for col, h in heads.items():
        P(pl, f"{col}3", h, bold=True)
    qsrc = {"C": ("C", "E"), "D": ("F", "H"), "F": ("I", "K"), "G": ("L", "N")}
    items = {5: 5, 6: 6, 8: 8, 13: 10, 14: 11, 16: 13, 17: 14, 21: 16}
    lab = {5: "Subscription revenue", 6: "Services revenue", 7: "Total revenue", 8: "Cost of revenue",
           9: "Gross profit", 10: "Gross margin %", 12: "Operating expenses", 13: "Salaries",
           14: "Benefits", 15: "People costs", 16: "Marketing", 17: "G&A",
           18: "Total operating expenses", 19: "EBITDA", 20: "EBITDA margin %", 21: "D&A", 22: "EBIT"}
    for r, t in lab.items():
        P(pl, f"A{r}", t, bold=r in (7, 9, 12, 18, 19, 22))
    totals_q = {7: "=SUM({c}5:{c}6)", 9: "={c}7+{c}8", 15: "=SUM({c}13:{c}14)",
                18: "=SUM({c}13:{c}17)", 19: "={c}9+{c}18", 22: "={c}19+{c}21"}
    ratio = {10: "=IF({c}7=0,0,{c}9/{c}7)", 20: "=IF({c}7=0,0,{c}19/{c}7)"}
    flow_rows = [5, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 21, 22]
    for r in flow_rows:
        for c, (m1, m2) in qsrc.items():
            f = f"=SUM('Monthly Data'!{m1}{items[r]}:{m2}{items[r]})" if r in items else totals_q[r].format(c=c)
            P(pl, f"{c}{r}", f, fmt=NUM)
        P(pl, f"E{r}", f"=C{r}+D{r}", fmt=NUM)
        P(pl, f"H{r}", f"=F{r}+G{r}", fmt=NUM)
        P(pl, f"I{r}", f"=E{r}+H{r}", fmt=NUM)
    for r, f in ratio.items():
        for c in "CDEFGHIJ":
            P(pl, f"{c}{r}", f.format(c=c), fmt=PCT)
    P(pl, "I14", "=E14+G14", fmt=NUM)
    # budget column
    budget = {5: 19300000, 6: 2350000, 8: -5380000, 13: -7900000, 14: -1420000, 16: -2150000,
              17: -1360000, 21: -540000}
    for r, val in budget.items():
        P(pl, f"J{r}", val, inp=True, fmt=NUM)
    for r, f in {7: "=SUM(J5:J6)", 9: "=J7+J8", 15: "=SUM(J13:J14)", 18: "=J15+J16+J17",
                 19: "=J9+J18", 22: "=J19+J21"}.items():
        P(pl, f"J{r}", f, fmt=NUM)
    for r in flow_rows + [10, 20]:
        P(pl, f"K{r}", f"=I{r}-J{r}", fmt=PCT if r in (10, 20) else NUM)
        if r not in (10, 20):
            P(pl, f"L{r}", f"=IF(J{r}=0,\"n/a\",K{r}/J{r})", fmt=PCT)

    P(kp, "A1", "Board pack - KPIs FY2026", bold=True)
    for col, h in list(heads.items())[:7]:
        P(kp, f"{col}3", h, bold=True)
    P(kp, "B3", "FY25 close", bold=True)
    P(kp, "A5", "Headcount (period end)")
    for c, val in zip("CDFG", [182, 188, 195, 201]):
        P(kp, f"{c}5", val, inp=True)
    P(kp, "E5", "=D5")
    P(kp, "H5", "=G5")
    P(kp, "I5", "=G5")
    P(kp, "A6", "Revenue per head (annualised)")
    for c, k in zip("CDEFGH", [4, 4, 2, 4, 4, 2]):
        P(kp, f"{c}6", f"='P&L'!{c}7*{k}/{c}5", fmt=NUM)
    P(kp, "I6", "='P&L'!I7/I5", fmt=NUM)
    P(kp, "A7", "New logos")
    P(kp, "A8", "Churned logos")
    for c, n, ch in zip("CDFG", [38, 41, 35, 47], [12, 9, 14, 11]):
        P(kp, f"{c}7", n, inp=True)
        P(kp, f"{c}8", ch, inp=True)
    for r in (7, 8):
        P(kp, f"E{r}", f"=C{r}+D{r}")
        P(kp, f"H{r}", f"=F{r}+G{r}")
        P(kp, f"I{r}", f"=E{r}+H{r}")
    P(kp, "A9", "Customers (period end)")
    P(kp, "B9", 412, inp=True)
    for c, f in {"C": "=B9+C7-C8", "D": "=C9+D7-D8", "E": "=D9", "F": "=D9+F7-F8", "G": "=F9+G7-G8",
                 "H": "=G9", "I": "=G9"}.items():
        P(kp, f"{c}9", f)
    P(kp, "A10", "EBITDA per head (FY)")
    P(kp, "I10", "='P&L'!I19/#REF!", fmt=NUM)

    b.fault("P&L", "C18", "DOUBLE_COUNT",
            "Total opex SUM(C13:C17) includes the People costs subtotal (row 15) and its items; copied to every quarter column.",
            group=["D18", "F18", "G18"])
    b.fault("P&L", "I14", "INCONSISTENT_FORMULA", "FY benefits = H1 + Q4 (E14+G14) instead of H1 + H2 (E14+H14).")
    b.fault("KPIs", "I10", "REF_ERROR", "Denominator is #REF! (headcount row was deleted and re-added).")
    b.ok("P&L", "C5:G5", "each quarter column reads a different 3-month block of Monthly Data, so every formula differs from its neighbours (same on each item row)")
    b.ok("P&L", "E5:E22", "H1 column = Q1 + Q2, interleaved between quarter columns")
    b.ok("P&L", "H5:H22", "H2 column = Q3 + Q4, interleaved between quarter columns")
    b.ok("P&L", "I5:I13", "FY column = H1 + H2")
    b.ok("P&L", "I15:I22", "FY column = H1 + H2")
    b.ok("P&L", "C7:G7", "subtotal row sitting between item rows (column neighbours are item lookups)")
    b.ok("P&L", "C15:G15", "subtotal row sitting between item rows (column neighbours are item lookups)")
    b.ok("P&L", "C10:J10", "ratio row recomputed in H1/FY/budget columns rather than summed")
    b.ok("P&L", "C20:J20", "ratio row recomputed in H1/FY/budget columns rather than summed")
    b.ok("P&L", "J5:J22", "budget column: blue inputs with subtotal formulas")
    b.ok("P&L", "K5:K22", "variance column (actual minus budget)")
    b.ok("P&L", "L5:L22", "variance % column with IF guard; blank on ratio rows")
    b.ok("KPIs", "E5", "H1 headcount = Q2 period-end (point in time, not a sum)")
    b.ok("KPIs", "H5:I5", "H2 and FY headcount = Q4 period-end")
    b.ok("KPIs", "C6:I6", "annualisation constants *4 for quarters, *2 for halves, none for FY")
    b.ok("KPIs", "B9", "opening customer count (blue input)")
    b.ok("KPIs", "C9:I9", "customer roll-forward that skips the half-year column (F9 continues from D9)")
    return b


# ---------------------------------------------------------------------------
# 8. Scenario model
# ---------------------------------------------------------------------------
def build_scenarios():
    b = Book("scenario_model.xlsx",
             "Five-year scenario model with Base, Upside and Downside blocks side by side (blank separator "
             "columns), a CHOOSE-driven selected-scenario block, and an acquisition funding sheet named 'Funding & Fees'.")
    dr = b.ws("Drivers")
    sc = b.ws("Scenarios")
    ff = b.ws("Funding & Fees")

    P(dr, "A1", "Scenario drivers", bold=True)
    P(dr, "A4", "Scenario selector (1=Base, 2=Upside, 3=Downside)")
    P(dr, "C4", 1, inp=True)
    for c, h in zip("CDE", ["Base", "Upside", "Downside"]):
        P(dr, f"{c}6", h, bold=True)
    P(dr, "A7", "FY2025 revenue")
    P(dr, "C7", 24000000, inp=True, fmt=NUM)
    P(dr, "D7", "=$C$7", fmt=NUM)
    P(dr, "E7", "=$C$7", fmt=NUM)
    drv = [(8, "Revenue growth p.a.", [0.08, 0.14, 0.02]), (9, "Gross margin", [0.61, 0.64, 0.57]),
           (10, "Opex % of revenue", [0.38, 0.36, 0.41]), (11, "Capex % of revenue", [0.05, 0.06, 0.04]),
           (12, "Tax rate", [0.25, 0.25, 0.25])]
    for r, lab, vals in drv:
        P(dr, f"A{r}", lab)
        for c, val in zip("CDE", vals):
            P(dr, f"{c}{r}", val, inp=True, fmt=PCT)

    P(sc, "A1", "Scenario outputs FY2026-FY2030", bold=True)
    blocks = [("C", "BASE", "C"), ("I", "UPSIDE", "D"), ("O", "DOWNSIDE", "E")]
    labels = {5: "Revenue", 6: "Gross profit", 7: "Operating expenses", 8: "EBITDA", 9: "Capex",
              10: "Tax", 11: "Free cash flow", 13: "Cumulative FCF"}
    for r, t in labels.items():
        P(sc, f"A{r}", t, bold=r in (8, 11))
    for start, title, x in blocks:
        P(sc, f"{start}3", title, bold=True)
        bc = [sh(start, k) for k in range(5)]
        for k, c in enumerate(bc):
            P(sc, f"{c}4", 2026 + k, bold=True)
            if k == 0:
                P(sc, f"{c}5", f"=Drivers!${x}$7*(1+Drivers!${x}$8)", fmt=NUM)
                P(sc, f"{c}13", f"={c}11", fmt=NUM)
            else:
                P(sc, f"{c}5", f"={prv(c)}5*(1+Drivers!${x}$8)", fmt=NUM)
                P(sc, f"{c}13", f"={prv(c)}13+{c}11", fmt=NUM)
            P(sc, f"{c}6", f"={c}5*Drivers!${x}$9", fmt=NUM)
            P(sc, f"{c}7", f"=-{c}5*Drivers!${x}$10", fmt=NUM)
            P(sc, f"{c}8", f"={c}6+{c}7", fmt=NUM)
            P(sc, f"{c}9", f"=-{c}5*Drivers!${x}$11", fmt=NUM)
            P(sc, f"{c}10", f"=-MAX(0,{c}8)*Drivers!${x}$12", fmt=NUM)
            P(sc, f"{c}11", f"={c}8+{c}9+{c}10", fmt=NUM)
    P(sc, "Q5", "=P5*(1+Drivers!$D$8)", fmt=NUM)
    P(sc, "K7", -11950000, fmt=NUM)
    P(sc, "P7", -10950000, fmt=NUM,
      note="Downside FY2027 opex includes a 0.7m restructuring cost (board paper 14 Aug). Typed on purpose.")

    P(sc, "A15", "Selected scenario", bold=True)
    P(sc, "C15", "=CHOOSE(Drivers!$C$4,\"Base\",\"Upside\",\"Downside\")")
    for c in cols("C", "G"):
        P(sc, f"{c}16", f"={c}4", bold=True)
    sel = {17: "Revenue", 18: "Gross profit", 19: "Operating expenses", 20: "EBITDA", 21: "Capex",
           22: "Tax", 23: "Free cash flow"}
    for r, t in sel.items():
        P(sc, f"A{r}", t)
        for c in cols("C", "G"):
            P(sc, f"{c}{r}", f"=CHOOSE(Drivers!$C$4,{c}{r - 12},{sh(c, 6)}{r - 12},{sh(c, 12)}{r - 12})", fmt=NUM)
    P(sc, "A25", "5-year FCF (selected)", bold=True)
    P(sc, "C25", "=SUM(C23:G23)", fmt=NUM)
    P(sc, "A27", "Interest on acquisition facility")
    for c in cols("C", "G"):
        P(sc, f"{c}27", "=-Facility*'Funding & Fees'!$B$13", fmt=NUM)

    P(ff, "A1", "Acquisition funding requirement", bold=True)
    P(ff, "A5", "Purchase price")
    P(ff, "B5", 8500000, inp=True, fmt=NUM)
    P(ff, "A6", "Transaction costs")
    P(ff, "B6", 310000, inp=True, fmt=NUM)
    P(ff, "A7", "Funding need before fees")
    P(ff, "B7", "=B5+B6", fmt=NUM)
    P(ff, "A8", "Arrangement fee rate")
    P(ff, "B8", 0.02, inp=True, fmt=PCT)
    P(ff, "A9", "Arrangement fee (on total facility)")
    P(ff, "B9", "=B10*B8", fmt=NUM)
    P(ff, "A10", "Total facility drawn", bold=True)
    P(ff, "B10", "=B7+B9", fmt=NUM)
    P(ff, "A12", "Annual interest")
    P(ff, "B12", "=B10*B13", fmt=NUM)
    P(ff, "A13", "Interest rate")
    P(ff, "B13", 0.071, inp=True, fmt=PCT)
    b.name("Facility", "'Funding & Fees'!$B$10")

    b.fault("Scenarios", "Q5", "INCONSISTENT_FORMULA", "Downside FY2028 revenue grows at the Upside rate (Drivers!$D$8, not $E$8).")
    b.fault("Scenarios", "K7", "HARDCODED_OVERRIDE", "Upside FY2028 opex typed (-11,950,000), no comment, black font.")
    b.fault("Funding & Fees", "B9", "CIRCULAR_REFERENCE", "Fee is a % of the total facility, and the facility includes the fee.",
            cycle=["Funding & Fees!B9", "Funding & Fees!B10"])
    b.ok("Drivers", "C4", "scenario selector input (blue)")
    b.ok("Drivers", "C7", "base-year revenue input")
    b.ok("Drivers", "D7:E7", "Upside/Downside base year linked to $C$7 (same absolute formula)")
    b.ok("Drivers", "C8:E12", "input block (blue), one column per scenario")
    b.ok("Scenarios", "C4:G4", "year header row of typed numbers")
    b.ok("Scenarios", "I4:M4", "year header row of typed numbers")
    b.ok("Scenarios", "O4:S4", "year header row of typed numbers")
    b.ok("Scenarios", "C5:G11", "Base block; same layout as the other blocks but anchored on Drivers column C")
    b.ok("Scenarios", "I5:M6", "Upside block anchored on Drivers column D (scenario blocks side by side with different drivers)")
    b.ok("Scenarios", "I8:M11", "Upside block anchored on Drivers column D")
    b.ok("Scenarios", "O5:P11", "Downside block anchored on Drivers column E")
    b.ok("Scenarios", "R5:S11", "Downside block anchored on Drivers column E")
    b.ok("Scenarios", "P7", "documented hardcoded override (cell comment: restructuring cost)")
    b.ok("Scenarios", "C13:S13", "cumulative FCF: first year differs from the running-total formula; blank separator columns H and N")
    b.ok("Scenarios", "C17:G23", "CHOOSE selected-scenario block")
    b.ok("Scenarios", "C27:G27", "defined name Facility and quoted cross-sheet reference to 'Funding & Fees'")
    b.ok("Funding & Fees", "B5:B6", "inputs (blue)")
    return b


# ---------------------------------------------------------------------------
# 9. Unit economics / cohort table
# ---------------------------------------------------------------------------
def build_unit_econ():
    b = Book("unit_economics.xlsx",
             "Customer cohort triangle (12 monthly cohorts by months since acquisition), retention % sheet "
             "with mixed anchors, and an LTV/CAC sheet named 'LTV & CAC'.")
    rnd = random.Random(909)
    co = b.ws("Cohorts")
    re_ = b.ws("Retention")
    lt = b.ws("LTV & CAC")
    MC = cols("B", "M")
    cohorts = [f"{m}-25" for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                                   "Nov", "Dec"]]

    for ws, title in [(co, "Customers retained by months since acquisition"),
                      (re_, "Retention % by months since acquisition")]:
        P(ws, "A1", title, bold=True)
        P(ws, "A4", "Cohort", bold=True)
        for k, c in enumerate(MC):
            P(ws, f"{c}4", k, bold=True)
    P(co, "N4", "Customer-months", bold=True)
    for i, name in enumerate(cohorts):
        r = 5 + i
        P(co, f"A{r}", name)
        new = rnd.randint(120, 220)
        for m in range(0, 12 - i):
            val = new if m == 0 else int(round(new * 0.82 * 0.97 ** (m - 1) * rnd.uniform(0.97, 1.03)))
            if r == 9 and m == 3:
                val = str(val)
            P(co, f"{MC[m]}{r}", val, fmt=NUM)
        P(co, f"N{r}", f"=SUM(B{r}:M{r})", fmt=NUM)
    P(co, "A17", "Total", bold=True)
    for c in MC:
        P(co, f"{c}17", f"=SUM({c}5:{c}16)", fmt=NUM)
    P(co, "N17", "=SUM(B5:N16)", fmt=NUM)

    for i in range(12):
        r = 5 + i
        P(re_, f"A{r}", f"=Cohorts!A{r}")
        for c in MC:
            P(re_, f"{c}{r}", f"=IF(Cohorts!{c}{r}=\"\",\"\",Cohorts!{c}{r}/Cohorts!$B{r})", fmt=PCT)
    P(re_, "A18", "Average", bold=True)
    for c in MC:
        P(re_, f"{c}18", f"=IFERROR(AVERAGE({c}5:{c}16),\"\")", fmt=PCT)

    P(lt, "A1", "Unit economics", bold=True)
    rows = [(4, "Monthly ARPU", 89, True, NUM2), (5, "Gross margin", 0.72, True, PCT),
            (6, "Monthly churn (implied from M1-M11 retention)", "=1-(Retention!M18/Retention!C18)^(1/10)", False, "0.00%"),
            (8, "Annual gross profit per customer", "=B4*B5*12", False, NUM2),
            (9, "Expected lifetime (months)", "=IFERROR(1/B6,0)", False, "0.0"),
            (10, "LTV", "=B4*B5*B9", False, NUM2),
            (12, "Sales & marketing spend FY2025", "='CAC Detail'!B20", False, NUM),
            (13, "New customers FY2025", "=SUM(Cohorts!B5:B16)", False, NUM),
            (14, "CAC", "=IFERROR(B12/B13,0)", False, NUM2),
            (15, "LTV : CAC", "=IFERROR(B10/B14,0)", False, "0.0x"),
            (16, "CAC payback (months)", "=IFERROR(B14/(B4*B5),0)", False, "0.0"),
            (17, "Churn (basis points per month)", "=B6*10000", False, "0")]
    for r, lab, val, inp, f in rows:
        P(lt, f"A{r}", lab)
        P(lt, f"B{r}", val, inp=inp, fmt=f)

    b.fault("Cohorts", "E9", "TEXT_NUMBER_IN_SUM", "May-25 cohort month-3 count stored as text; N9 and E17 SUMs skip it.")
    b.fault("Cohorts", "N17", "DOUBLE_COUNT", "Grand total SUM(B5:N16) adds the row-total column N to the cells it totals.")
    b.fault("LTV & CAC", "B12", "MISSING_SHEET", "References sheet 'CAC Detail', which is not in the workbook.")
    b.ok("Cohorts", "B4:M4", "header row of typed month numbers 0-11")
    b.ok("Cohorts", "N5:N16", "row totals over a triangle with blank cells")
    b.ok("Cohorts", "B17:M17", "column totals over a triangle with blank cells")
    b.ok("Retention", "B4:M4", "header row of typed month numbers 0-11")
    b.ok("Retention", "B5:M16", "mixed anchors (Cohorts!$B5) and IF(...=\"\",\"\") for the empty triangle")
    b.ok("Retention", "B18:M18", "IFERROR(AVERAGE) over ranges with blank strings")
    b.ok("LTV & CAC", "B4:B5", "inputs (blue)")
    b.ok("LTV & CAC", "B8", "unit constant *12 (monthly to annual)")
    b.ok("LTV & CAC", "B17", "unit constant *10000 (to basis points)")
    b.ok("LTV & CAC", "B14:B16", "IFERROR-guarded ratios")
    return b


# ---------------------------------------------------------------------------
# 10. Budget vs actual variance report
# ---------------------------------------------------------------------------
def build_bva():
    b = Book("bva_variance.xlsx",
             "Budget-vs-actual variance report (month and YTD side by side) from a trial-balance sheet via SUMIFS "
             "and a budget sheet via INDEX/MATCH, plus a SUMIFS department summary.")
    rnd = random.Random(1010)
    tb = b.ws("TB Sep")
    bu = b.ws("Budget 2026")
    bv = b.ws("BvA")
    ds = b.ws("Dept Summary")

    accts = [(4000, "Subscription revenue", ["Corp"]), (4100, "Professional services", ["Corp"]),
             (4200, "Other income", ["Corp"]),
             (6000, "Salaries", ["Sales", "Engineering", "G&A"]), (6100, "Contractors", ["Engineering", "G&A"]),
             (6200, "Travel", ["Sales", "Engineering", "G&A"]), (6300, "Software subscriptions", ["Engineering", "G&A"]),
             (6400, "Rent & facilities", ["G&A"]), (6500, "Professional fees", ["G&A"]),
             (6600, "Training", ["Sales", "Engineering"])]
    scale = {4000: 1650000, 4100: 210000, 4200: 9000, 6000: 210000, 6100: 45000, 6200: 12000,
             6300: 26000, 6400: 64000, 6500: 30000, 6600: 6000}
    P(tb, "A1", "Trial balance extract - September 2026 (P&L accounts)", bold=True)
    for k, h in enumerate(["Account", "Name", "Dept", "Sep actual", "YTD actual"]):
        P(tb, f"{CL(k + 1)}4", h, bold=True)
    r = 5
    sep_tot = {}
    for code, name, depts in accts:
        for dp in depts:
            sep = round(scale[code] * rnd.uniform(0.85, 1.15) / len(depts), 2)
            ytd = round(sep * rnd.uniform(8.6, 9.3), 2)
            P(tb, f"A{r}", code)
            P(tb, f"B{r}", name)
            P(tb, f"C{r}", dp)
            P(tb, f"D{r}", sep, fmt=NUM2)
            P(tb, f"E{r}", ytd, fmt=NUM2)
            r += 1

    P(bu, "A1", "Budget 2026", bold=True)
    for k, h in enumerate(["Account", "Name", "Sep budget", "YTD budget"]):
        P(bu, f"{CL(k + 1)}4", h, bold=True)
    for k, (code, name, _) in enumerate(accts):
        rr = 5 + k
        P(bu, f"A{rr}", code)
        P(bu, f"B{rr}", name)
        P(bu, f"C{rr}", scale[code], inp=True, fmt=NUM)
        P(bu, f"D{rr}", scale[code] * 9, inp=True, fmt=NUM)

    P(bv, "A1", "Budget vs actual - September 2026", bold=True)
    P(bv, "C2", "September", bold=True)
    P(bv, "H2", "Year to date", bold=True)
    for c, h in zip("ABCDEFHIJK", ["Account", "Code", "Actual", "Budget", "Variance", "Var %", "Actual",
                                   "Budget", "Variance", "Var %"]):
        P(bv, f"{c}3", h, bold=True)
    P(bv, "A5", "Revenue", bold=True)
    P(bv, "A12", "Operating costs", bold=True)
    rev_rows = {6: accts[0], 7: accts[1], 8: accts[2]}
    cost_rows = {13 + k: accts[3 + k] for k in range(7)}

    def line(rr, acct, revenue):
        code, name, _ = acct
        P(bv, f"A{rr}", name)
        P(bv, f"B{rr}", code)
        for a_col, b_col, v_col, p_col, tbc, buc in [("C", "D", "E", "F", "D", "C"), ("H", "I", "J", "K", "E", "D")]:
            P(bv, f"{a_col}{rr}", f"=SUMIFS('TB Sep'!${tbc}$5:${tbc}$60,'TB Sep'!$A$5:$A$60,$B{rr})", fmt=NUM)
            P(bv, f"{b_col}{rr}",
              f"=IFERROR(INDEX('Budget 2026'!${buc}$5:${buc}$14,MATCH($B{rr},'Budget 2026'!$A$5:$A$14,0)),0)", fmt=NUM)
            if revenue:
                P(bv, f"{v_col}{rr}", f"={a_col}{rr}-{b_col}{rr}", fmt=NUM)
            else:
                P(bv, f"{v_col}{rr}", f"={b_col}{rr}-{a_col}{rr}", fmt=NUM)
            P(bv, f"{p_col}{rr}", f"=IF({b_col}{rr}=0,\"n/a\",{v_col}{rr}/{b_col}{rr})", fmt=PCT)

    for rr, a in rev_rows.items():
        line(rr, a, True)
    for rr, a in cost_rows.items():
        line(rr, a, False)
    P(bv, "A9", "Total revenue", bold=True)
    P(bv, "A10", "Memo: subscription share of revenue")
    P(bv, "A20", "Total operating costs", bold=True)
    P(bv, "A22", "Operating result", bold=True)
    for a_col, b_col, v_col, p_col in [("C", "D", "E", "F"), ("H", "I", "J", "K")]:
        P(bv, f"{a_col}9", f"=SUM({a_col}6:{a_col}8)", fmt=NUM)
        P(bv, f"{b_col}9", f"=SUM({b_col}6:{b_col}8)", fmt=NUM)
        P(bv, f"{v_col}9", f"={a_col}9-{b_col}9", fmt=NUM)
        P(bv, f"{p_col}9", f"=IF({b_col}9=0,\"n/a\",{v_col}9/{b_col}9)", fmt=PCT)
        P(bv, f"{a_col}10", f"=IF({a_col}9=0,0,{a_col}6/{a_col}9)", fmt=PCT)
        end = 18 if a_col == "C" else 19
        P(bv, f"{a_col}20", f"=SUM({a_col}13:{a_col}{end})", fmt=NUM)
        P(bv, f"{b_col}20", f"=SUM({b_col}13:{b_col}{end})", fmt=NUM)
        P(bv, f"{v_col}20", f"={b_col}20-{a_col}20", fmt=NUM)
        P(bv, f"{p_col}20", f"=IF({b_col}20=0,\"n/a\",{v_col}20/{b_col}20)", fmt=PCT)
        P(bv, f"{a_col}22", f"={a_col}9-{a_col}20", fmt=NUM)
        P(bv, f"{b_col}22", f"={b_col}9-{b_col}20", fmt=NUM)
        P(bv, f"{v_col}22", f"={a_col}22-{b_col}22", fmt=NUM)
        P(bv, f"{p_col}22", f"=IF({b_col}22=0,\"n/a\",{v_col}22/{b_col}22)", fmt=PCT)
    P(bv, "F16", "=IF(C16=0,\"n/a\",E16/C16)", fmt=PCT)
    P(bv, "H22", "=H9-H20+1200", fmt=NUM)
    P(bv, "A24", "Variance sign: positive = favourable (revenue above budget, costs below budget).")

    P(ds, "A1", "Operating costs by department - September 2026", bold=True)
    P(ds, "A4", "Department", bold=True)
    P(ds, "C4", "Sep actual", bold=True)
    P(ds, "D4", "YTD actual", bold=True)
    for k, dp in enumerate(["Sales", "Engineering", "G&A"]):
        rr = 5 + k
        P(ds, f"A{rr}", dp)
        for c, tbc in [("C", "D"), ("D", "E")]:
            P(ds, f"{c}{rr}",
              f"=SUMIFS('TB Sep'!${tbc}$5:${tbc}$60,'TB Sep'!$C$5:$C$60,$A{rr},'TB Sep'!$A$5:$A$60,\">=6000\")", fmt=NUM)
    P(ds, "A8", "Total", bold=True)
    P(ds, "C8", "=SUM(C5:C7)", fmt=NUM)
    P(ds, "D8", "=SUM(D5:D7)", fmt=NUM)
    P(ds, "A10", "Check to BvA total operating costs")
    P(ds, "C10", "=C8-BvA!C20", fmt=NUM)
    P(ds, "D10", "=D8-BvA!H20", fmt=NUM)

    b.fault("BvA", "C20", "SUM_OMITS_ROW", "September cost total SUM(C13:C18) misses Training (row 19); budget total copied the same way.",
            group=["D20"])
    b.fault("BvA", "F16", "INCONSISTENT_FORMULA", "Var % for Rent divides by actual (C16) instead of budget (D16).")
    b.fault("BvA", "H22", "HARDCODED_PLUG", "YTD operating result forced with +1200 to agree to the management accounts.")
    b.ok("BvA", "C6:C8", "SUMIFS actuals from the TB")
    b.ok("BvA", "C13:C19", "SUMIFS actuals from the TB")
    b.ok("BvA", "D6:D19", "IFERROR(INDEX/MATCH) budget lookups (blank rows 9-12 aside)")
    b.ok("BvA", "E6:E9", "revenue variance = actual - budget (positive = favourable)")
    b.ok("BvA", "E13:E20", "cost variance = budget - actual: sign convention flips by section on purpose")
    b.ok("BvA", "J13:J20", "cost variance = budget - actual (YTD block)")
    b.ok("BvA", "F6:F15", "variance % with IF guard against a zero budget")
    b.ok("BvA", "C10", "memo % row below the total, deliberately outside the SUM")
    b.ok("BvA", "H10", "memo % row below the total, deliberately outside the SUM")
    b.ok("BvA", "H20:I20", "YTD cost totals cover all seven cost rows")
    b.ok("BvA", "E22", "operating-result variance = actual - budget")
    b.ok("Dept Summary", "C5:D7", "SUMIFS pivot-style summary with two criteria")
    b.ok("Dept Summary", "C10:D10", "check cells to the BvA totals")
    b.ok("Budget 2026", "C5:D14", "budget input block (blue)")
    return b


# ---------------------------------------------------------------------------
# 11. Short annual forecast (clean)
# ---------------------------------------------------------------------------
def build_annual():
    b = Book("annual_forecast_3yr.xlsx",
             "Short annual forecast: two actual years then three forecast years (few columns), growth from "
             "per-year defined names, CAGR, ROUND to thousands. No injected faults (clean workbook).")
    a = b.ws("Assumptions")
    f = b.ws("Forecast")
    F3 = ["D", "E", "F"]

    P(a, "A1", "Forecast assumptions", bold=True)
    for c, h in zip(F3, ["FY2026F", "FY2027F", "FY2028F"]):
        P(a, f"{c}4", h, bold=True)
    for r, lab, vals, fm in [(5, "Revenue growth", [0.09, 0.07, 0.06], PCT),
                             (6, "Gross margin", [0.58, 0.585, 0.59], PCT),
                             (7, "Opex growth", [0.05, 0.045, 0.04], PCT),
                             (8, "D&A % revenue", [0.031, 0.031, 0.03], PCT),
                             (9, "Net debt (year end)", [6200000, 5100000, 3900000], NUM)]:
        P(a, f"A{r}", lab)
        for c, val in zip(F3, vals):
            P(a, f"{c}{r}", val, inp=True, fmt=fm)
    P(a, "A10", "Interest rate on net debt")
    P(a, "C10", 0.068, inp=True, fmt=PCT)
    P(a, "A11", "Tax rate")
    P(a, "C11", 0.25, inp=True, fmt=PCT)
    b.name("Growth_FY26", "Assumptions!$D$5")
    b.name("Growth_FY27", "Assumptions!$E$5")
    b.name("Growth_FY28", "Assumptions!$F$5")

    P(f, "A1", "Three-year forecast (USD)", bold=True)
    for k, c in enumerate("BCDEF"):
        P(f, f"{c}3", 2024 + k, bold=True)
        P(f, f"{c}4", f"FY{2024 + k}{'A' if k < 2 else 'F'}", bold=True)
    P(f, "G4", "CAGR 25-28", bold=True)
    labels = {6: "Revenue", 7: "Growth %", 8: "Cost of sales", 9: "Gross profit", 10: "Gross margin %",
              11: "Operating expenses", 12: "EBITDA", 13: "D&A", 14: "EBIT", 15: "Net interest",
              16: "Profit before tax", 17: "Tax", 18: "Net income", 20: "Revenue (USD k)",
              21: "EBITDA margin %"}
    for r, t in labels.items():
        P(f, f"A{r}", t, bold=r in (6, 9, 12, 14, 16, 18))
    actuals = {6: (21480000, 23915000), 8: (-9102000, -10046000), 11: (-8215000, -8870000),
               13: (-655000, -712000), 15: (-498000, -451000), 17: (-1089000, -1244000)}
    for r, (x, y) in actuals.items():
        P(f, f"B{r}", x, fmt=NUM)
        P(f, f"C{r}", y, fmt=NUM)
    for c, nm in zip(F3, ["Growth_FY26", "Growth_FY27", "Growth_FY28"]):
        P(f, f"{c}6", f"={prv(c)}6*(1+{nm})", fmt=NUM)
        P(f, f"{c}8", f"=-{c}6*(1-Assumptions!{c}6)", fmt=NUM)
        P(f, f"{c}11", f"={prv(c)}11*(1+Assumptions!{c}7)", fmt=NUM)
        P(f, f"{c}13", f"=-ROUND({c}6*Assumptions!{c}8,-3)", fmt=NUM)
        P(f, f"{c}15", f"=-Assumptions!$C$10*Assumptions!{c}9", fmt=NUM)
        P(f, f"{c}17", f"=-MAX(0,{c}16)*Assumptions!$C$11", fmt=NUM)
    P(f, "E11", -9640000, inp=True, fmt=NUM)
    for c in "BCDEF":
        if c != "B":
            P(f, f"{c}7", f"={c}6/{prv(c)}6-1", fmt=PCT)
        P(f, f"{c}9", f"={c}6+{c}8", fmt=NUM)
        P(f, f"{c}10", f"=IF({c}6=0,0,{c}9/{c}6)", fmt=PCT)
        P(f, f"{c}12", f"={c}9+{c}11", fmt=NUM)
        P(f, f"{c}14", f"={c}12+{c}13", fmt=NUM)
        P(f, f"{c}16", f"={c}14+{c}15", fmt=NUM)
        P(f, f"{c}18", f"={c}16+{c}17", fmt=NUM)
        P(f, f"{c}20", f"={c}6/1000", fmt=NUM)
        P(f, f"{c}21", f"=IF({c}6=0,0,{c}12/{c}6)", fmt=PCT)
    P(f, "G6", "=(F6/C6)^(1/3)-1", fmt=PCT)

    S = "Forecast"
    b.ok(S, "B3:F3", "year header row of typed numbers")
    b.ok(S, "B6:C6", "actual years typed, then forecast formulas (same for rows 8, 11, 13, 15, 17)")
    b.ok(S, "B8:C8", "actual years typed, then forecast formulas")
    b.ok(S, "D6:F6", "each forecast year reads a different named growth input, so every formula differs from its neighbours")
    b.ok(S, "C7:F7", "growth % starts in the second actual year (B7 blank); the -1 is not a plug")
    b.ok(S, "G6", "CAGR formula with exponent 1/3 and -1")
    b.ok(S, "E11", "documented hardcoded override (blue input font): board-approved FY2027 opex")
    b.ok(S, "D13:F13", "ROUND to thousands")
    b.ok(S, "B15:F15", "item row sitting between two subtotal rows (EBIT above, PBT below); typed actuals then formulas")
    b.ok(S, "B17:F17", "item row sitting between two subtotal rows (PBT above, net income below); typed actuals then formulas")
    b.ok(S, "D15:F15", "mixed absolute ($C$10) and relative references")
    b.ok(S, "B20:F20", "unit constant /1000")
    b.ok("Assumptions", "D5:F9", "per-year input block (blue)")
    b.ok("Assumptions", "C10:C11", "inputs (blue)")
    return b


# ---------------------------------------------------------------------------
# Version pair A: rolling opex forecast
# ---------------------------------------------------------------------------
def build_rolling(v):
    b = Book(f"rolling_fcst_v{v}.xlsx",
             f"Rolling monthly opex forecast, version {v}. "
             + ("Jan-Jun, six cost lines." if v == 1 else
                "Jan-Jul (new month added), Cloud hosting line inserted at row 9, efficiency factor on the H1 summary."))
    i = b.ws("Inputs")
    o = b.ws("Opex")
    s = b.ws("Summary")
    P(i, "A1", "Monthly growth assumptions", bold=True)
    grow = [(4, "Salaries", 0.004 if v == 1 else 0.005), (5, "Software", 0.01), (6, "Travel", 0.0),
            (7, "Marketing", 0.02), (8, "Professional fees", 0.0)]
    if v == 2:
        grow.append((9, "Cloud hosting", 0.03))
    for r, lab, g in grow:
        P(i, f"A{r}", lab)
        P(i, f"B{r}", g, inp=True, fmt="0.0%")
    if v == 2:
        P(i, "A11", "Efficiency saving applied to H1 total")
        P(i, "B11", 0.015, inp=True, fmt="0.0%")

    lines = [("Salaries", 4, 184000), ("Rent", None, 38500), ("Software", 5, 22400),
             ("Travel & subsistence" if v == 1 else "Travel and expenses", 6, 9100),
             ("Marketing", 7, 31000), ("Professional fees", 8, 12500)]
    if v == 2:
        lines.insert(3, ("Cloud hosting", 9, 14800))
    months = ["Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26"] + (["Jul-26"] if v == 2 else [])
    MC = [CL(3 + k) for k in range(len(months))]
    P(o, "A1", "Opex forecast 2026", bold=True)
    for c, m in zip(MC, months):
        P(o, f"{c}4", m, bold=True)
    for k, (lab, gi, base) in enumerate(lines):
        r = 6 + k
        P(o, f"A{r}", lab)
        for c in MC:
            if c == "C":
                P(o, f"C{r}", base, inp=True, fmt=NUM)
            elif gi is None:
                P(o, f"{c}{r}", f"={prv(c)}{r}", fmt=NUM)
            else:
                P(o, f"{c}{r}", f"={prv(c)}{r}*(1+Inputs!$B${gi})", fmt=NUM)
    tr = 6 + len(lines)
    P(o, f"A{tr}", "Total opex", bold=True)
    for c in MC:
        P(o, f"{c}{tr}", f"=SUM({c}6:{c}{tr - 1})", fmt=NUM)
    if v == 2:
        P(o, "F8", 23100, fmt=NUM)

    P(s, "A1", "H1 2026 opex summary", bold=True)
    P(s, "A5", "Total H1 opex")
    P(s, "B5", "=SUM(Opex!C12:H12)" if v == 1 else "=SUM(Opex!C13:H13)*(1-Inputs!$B$11)", fmt=NUM)
    P(s, "A6", "Average per month")
    P(s, "B6", "=B5/6", fmt=NUM)

    last_in = "B8" if v == 1 else "B9"
    b.ok("Inputs", f"B4:{last_in}", "input block (blue)")
    b.ok("Opex", f"C6:C{tr - 1}", "base-month inputs (blue); later months are formulas")
    b.ok("Opex", f"D7:{MC[-1]}7", "rent carried forward unchanged (=prior month)")
    b.ok("Opex", f"C{tr}:{MC[-1]}{tr}", "total row")
    b.ok("Summary", "B6", "unit constant /6 (months in the half)")
    if v == 2:
        b.ok("Inputs", "B11", "input (blue)")
        b.fault("Opex", "F8", "HARDCODED_OVERRIDE", "April software cost pasted as a value (23,100) between formula cells.")
    return b


# ---------------------------------------------------------------------------
# Version pair B: debt schedule
# ---------------------------------------------------------------------------
def build_debt(v):
    b = Book(f"debt_schedule_v{v}.xlsx",
             f"Term-loan schedule 2026-2030, version {v}. "
             + ("Includes a covenant sheet; 2030 interest is a documented placeholder." if v == 1 else
                "Covenant sheet removed, refinancing sheet added, 2030 interest now a formula."))
    i = b.ws("Inputs")
    d = b.ws("Debt")
    Y = cols("C", "G")
    P(i, "A1", "Debt inputs", bold=True)
    P(i, "A4", "Opening term loan (1 Jan 2026)")
    P(i, "B4", 12000000, inp=True, fmt=NUM)
    P(i, "A5", "Scheduled amortisation p.a.")
    P(i, "B5", 2000000 if v == 1 else 2250000, inp=True, fmt=NUM)
    P(i, "A8", "EBITDA forecast")
    for k, c in enumerate(Y):
        P(i, f"{c}7", 2026 + k, bold=True)
        P(i, f"{c}8", [4100000, 4450000, 4800000, 5150000, 5500000][k], inp=True, fmt=NUM)

    P(d, "A1", "Term loan schedule", bold=True)
    P(d, "A5", "Opening balance")
    P(d, "A6", "Drawdowns")
    P(d, "A7", "Repayments" if v == 1 else "Scheduled amortisation")
    P(d, "A8", "Closing balance", bold=True)
    P(d, "A10", "Interest")
    P(d, "A11", "All-in rate")
    rates = [0.064, 0.062, 0.060, 0.060] + ([] if v == 1 else [0.059])
    for k, c in enumerate(Y):
        P(d, f"{c}4", 2026 + k, bold=True)
        P(d, f"{c}5", "=Inputs!$B$4" if c == "C" else f"={prv(c)}8", fmt=NUM)
        P(d, f"{c}6", [0, 1500000, 0, 0, 0][k], inp=True, fmt=NUM)
        P(d, f"{c}7", f"=-MIN({c}5+{c}6,Inputs!$B$5)", fmt=NUM)
        P(d, f"{c}8", f"=SUM({c}5:{c}7)", fmt=NUM)
        if k < len(rates):
            P(d, f"{c}11", rates[k], inp=True, fmt="0.00%")
        if c != "G" or v == 2:
            P(d, f"{c}10", f"=ROUND(AVERAGE({c}5,{c}8)*{c}11,0)", fmt=NUM)
    if v == 1:
        P(d, "G10", 312000, inp=True, fmt=NUM,
          note="Placeholder: 2030 margin not yet agreed with the lender.")

    if v == 1:
        cv = b.ws("Covenants")
        P(cv, "A1", "Covenant tests", bold=True)
        P(cv, "A5", "Net debt / EBITDA")
        P(cv, "A6", "Maximum leverage")
        P(cv, "A7", "Headroom")
        for c, mx in zip(Y, [3.5, 3.25, 3.0, 3.0, 3.0]):
            P(cv, f"{c}4", f"=Debt!{c}4", bold=True)
            P(cv, f"{c}5", f"=IFERROR(Debt!{c}8/Inputs!{c}8,0)", fmt="0.00x")
            P(cv, f"{c}6", mx, inp=True, fmt="0.00x")
            P(cv, f"{c}7", f"={c}6-{c}5", fmt="0.00x")
        b.ok("Covenants", "C5:G5", "IFERROR-guarded leverage ratio")
        b.ok("Covenants", "C6:G6", "covenant input row (blue)")
        b.ok("Debt", "G10", "documented hardcoded placeholder (blue font and comment)")
    else:
        rf = b.ws("Refinancing")
        P(rf, "A1", "Refinancing option", bold=True)
        P(rf, "A4", "Refinance at end of")
        P(rf, "B4", 2028, inp=True)
        P(rf, "A5", "Balance to refinance")
        P(rf, "B5", "=Debt!E8", fmt=NUM)
        P(rf, "A6", "New all-in rate (lender term sheet)")
        P(rf, "B6", "='[Lender Term Sheet.xlsx]Pricing'!$C$7", fmt="0.00%")
        P(rf, "A7", "Arrangement fee %")
        P(rf, "B7", 0.0125, inp=True, fmt="0.00%")
        P(rf, "A8", "Arrangement fee")
        P(rf, "B8", "=ROUND(B5*B7,0)", fmt=NUM)
        P(rf, "A9", "Annual interest saving")
        P(rf, "B9", "=ROUND(B5*(Debt!F11-B6),0)", fmt=NUM)
        b.fault("Refinancing", "B6", "EXTERNAL_LINK", "New rate read from another workbook [Lender Term Sheet.xlsx].")
        b.ok("Refinancing", "B4", "input (blue)")
        b.ok("Refinancing", "B7", "input (blue)")
        b.ok("Refinancing", "B8:B9", "ROUND calculations")
    b.ok("Inputs", "B4:B5", "inputs (blue)")
    b.ok("Inputs", "C8:G8", "input row (blue)")
    b.ok("Debt", "C4:G4", "year header row of typed numbers")
    b.ok("Debt", "C5", "opening from Inputs; D5:G5 take the prior closing (roll-forward)")
    b.ok("Debt", "D5:G5", "roll-forward: closing becomes next opening")
    b.ok("Debt", "C6:G6", "input row (blue)")
    b.ok("Debt", "C11:F11" if v == 1 else "C11:G11", "rate input row (blue)")
    return b


# ---------------------------------------------------------------------------
# Version pair C: capex and depreciation plan
# ---------------------------------------------------------------------------
def build_capex(v):
    b = Book(f"capex_plan_v{v}.xlsx",
             f"Capex and straight-line depreciation plan by asset class, version {v}. "
             + ("2026-2029, four asset classes." if v == 1 else
                "2030 added, Software class inserted at row 8, a disposals adjustment on the summary."))
    rnd = random.Random(1300)
    i = b.ws("Inputs")
    cx = b.ws("Capex")
    dp = b.ws("Depreciation")
    classes = [("Buildings", 30), ("Plant & machinery", 10), ("IT hardware", 4), ("Vehicles", 5)]
    if v == 2:
        classes.insert(2, ("Software", 3))
    Y = cols("C", "F") if v == 1 else cols("C", "G")
    base = {"Buildings": [1200000, 0, 450000, 0, 0], "Plant & machinery": [820000, 640000, 700000, 560000, 610000],
            "IT hardware": [150000, 170000, 160000, 180000, 175000], "Vehicles": [95000, 0, 120000, 80000, 0],
            "Software": [210000, 90000, 95000, 100000, 105000]}
    if v == 2:
        base["Plant & machinery"] = [820000, 720000, 700000, 560000, 610000]

    P(i, "A1", "Asset class inputs", bold=True)
    P(i, "A4", "Useful life (years)", bold=True)
    for k, (cls, life) in enumerate(classes):
        P(i, f"A{6 + k}", cls)
        P(i, f"B{6 + k}", life, inp=True)
    if v == 2:
        P(i, "A13", "Accumulated depreciation released on disposals (2026-2029)")
        P(i, "B13", 85000, inp=True, fmt=NUM)

    last = 5 + len(classes)
    tr = last + 1
    for ws, title in [(cx, "Capital expenditure plan"), (dp, "Depreciation (straight line, full year in year of spend)")]:
        P(ws, "A1", title, bold=True)
        for k, c in enumerate(Y):
            P(ws, f"{c}4", 2026 + k, bold=True)
        for k, (cls, _) in enumerate(classes):
            P(ws, f"A{6 + k}", cls)
        P(ws, f"A{tr}", "Total", bold=True)
        for c in Y:
            P(ws, f"{c}{tr}", f"=SUM({c}6:{c}{last})", fmt=NUM)
    for k, (cls, _) in enumerate(classes):
        r = 6 + k
        for j, c in enumerate(Y):
            P(cx, f"{c}{r}", base[cls][j], inp=True, fmt=NUM)
            P(dp, f"{c}{r}", f"=SUM(Capex!$C{r}:{c}{r})/Inputs!$B{r}", fmt=NUM)
    if v == 2:
        P(dp, "E7", 216000, fmt=NUM)
    sr = tr + 2
    P(dp, f"A{sr}", "Total depreciation 2026-2029")
    P(dp, f"B{sr}", f"=SUM(C{tr}:F{tr})" if v == 1 else f"=SUM(C{tr}:F{tr})-Inputs!$B$13", fmt=NUM)

    b.ok("Inputs", f"B6:B{last}", "useful-life inputs (blue)")
    b.ok("Capex", f"C4:{Y[-1]}4", "year header row of typed numbers")
    b.ok("Capex", f"C6:{Y[-1]}{last}", "capex input block (blue)")
    b.ok("Depreciation", f"C4:{Y[-1]}4", "year header row of typed numbers")
    b.ok("Depreciation", f"C6:D{last}", "expanding SUM range with a mixed anchor (Capex!$C6:D6) divided by a mixed-anchor life")
    b.ok("Depreciation", f"F6:{Y[-1]}{last}", "expanding SUM range with a mixed anchor")
    b.ok("Depreciation", f"C{tr}:{Y[-1]}{tr}", "total row")
    if v == 2:
        b.ok("Inputs", "B13", "input (blue)")
        b.fault("Depreciation", "E7", "HARDCODED_OVERRIDE", "2028 plant depreciation pasted as a value (216,000) between formula cells.")
        b.ok("Depreciation", f"E6", "expanding SUM range with a mixed anchor")
        b.ok("Depreciation", f"E8:E{last}", "expanding SUM range with a mixed anchor")
    else:
        b.ok("Depreciation", f"E6:E{last}", "expanding SUM range with a mixed anchor")
    return b


DIFFS = [
    {"before": "rolling_fcst_v1.xlsx", "after": "rolling_fcst_v2.xlsx",
     "changes": [
         {"sheet": "Opex", "cell": "F8", "before_cell": "F8", "kind": "FORMULA_TO_VALUE",
          "note": "April software cost: growth formula replaced by a pasted value 23,100."},
         {"sheet": "Summary", "cell": "B5", "before_cell": "B5", "kind": "FORMULA_CHANGED",
          "note": "H1 total now multiplied by (1 - efficiency saving); the Opex!C12->C13 shift alone would not be material."}],
     "not_material": [
         {"sheet": "Opex", "what": "row inserted at 9 (Cloud hosting); rows 9-12 moved to 10-13"},
         {"sheet": "Opex", "what": "column I added at the end (Jul-26, a new period)"},
         {"sheet": "Opex", "what": "total row SUM ranges grew from C6:C11 to C6:C12 with the inserted row"},
         {"sheet": "Opex", "what": "label reworded: 'Travel & subsistence' -> 'Travel and expenses' (A9 -> A10)"},
         {"sheet": "Inputs", "what": "input updated: salaries growth B4 0.4% -> 0.5%"},
         {"sheet": "Inputs", "what": "new input rows added: B9 cloud growth, B11 efficiency saving"}]},
    {"before": "debt_schedule_v1.xlsx", "after": "debt_schedule_v2.xlsx",
     "changes": [
         {"sheet": "Debt", "cell": "G10", "before_cell": "G10", "kind": "VALUE_TO_FORMULA",
          "note": "2030 interest placeholder 312,000 replaced by the ROUND(AVERAGE()*rate) formula."},
         {"sheet": "Covenants", "cell": None, "before_cell": None, "kind": "SHEET_REMOVED",
          "note": "Covenant sheet removed."},
         {"sheet": "Refinancing", "cell": None, "before_cell": None, "kind": "SHEET_ADDED",
          "note": "Refinancing sheet added."}],
     "not_material": [
         {"sheet": "Inputs", "what": "input updated: scheduled amortisation B5 2,000,000 -> 2,250,000"},
         {"sheet": "Debt", "what": "label reworded: A7 'Repayments' -> 'Scheduled amortisation'"},
         {"sheet": "Debt", "what": "input filled in: 2030 rate G11 = 5.9%"}]},
    {"before": "capex_plan_v1.xlsx", "after": "capex_plan_v2.xlsx",
     "changes": [
         {"sheet": "Depreciation", "cell": "E7", "before_cell": "E7", "kind": "FORMULA_TO_VALUE",
          "note": "2028 plant depreciation formula replaced by a pasted value 216,000."},
         {"sheet": "Depreciation", "cell": "B13", "before_cell": "B12", "kind": "FORMULA_CHANGED",
          "note": "4-year total now deducts Inputs!$B$13 (disposals release); the C10->C11 shift alone would not be material."}],
     "not_material": [
         {"sheet": "Inputs", "what": "row inserted at 8 (Software useful life); rows 8-9 moved to 9-10"},
         {"sheet": "Capex", "what": "row inserted at 8 (Software); total moved from row 10 to 11"},
         {"sheet": "Depreciation", "what": "row inserted at 8 (Software); total moved from row 10 to 11"},
         {"sheet": "Capex", "what": "column G added at the end (2030, a new period)"},
         {"sheet": "Depreciation", "what": "column G added at the end (2030, a new period)"},
         {"sheet": "Capex", "what": "total row SUM ranges grew from C6:C9 to C6:C10 with the inserted row"},
         {"sheet": "Capex", "what": "input updated: plant & machinery 2027 (D7) 640,000 -> 720,000"},
         {"sheet": "Inputs", "what": "new input B13 (disposals release)"}]},
]


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
CELL_ONLY = re.compile(r"[A-Z]{1,3}\d+(:[A-Z]{1,3}\d+)?")


def split_sheet(v):
    if "!" in v:
        s, r = v.rsplit("!", 1)
        if s.startswith("'") and s.endswith("'"):
            s = s[1:-1].replace("''", "'")
        return s, r
    return None, v


def formula_refs(f):
    out = []
    try:
        toks = Tokenizer(f).items
    except Exception:
        return [("bad", None, f)]
    for t in toks:
        if t.type != Token.OPERAND:
            continue
        if t.subtype == Token.RANGE:
            if "#REF!" in t.value:
                out.append(("err", None, t.value))
                continue
            s, r = split_sheet(t.value)
            if s is not None and s.startswith("["):
                out.append(("ext", s, r))
                continue
            rr = r.replace("$", "")
            if CELL_ONLY.fullmatch(rr):
                out.append(("range", s, rr))
            elif s is None:
                out.append(("name", None, r))
            else:
                out.append(("bad", s, r))
        elif t.subtype == Token.ERROR:
            out.append(("err", None, t.value))
    return out


def cells_of(rng):
    c1, r1, c2, r2 = range_boundaries(rng)
    return [f"{CL(c)}{r}" for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


def is_formula(v):
    return isinstance(v, str) and v.startswith("=")


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def textnum(v):
    return isinstance(v, str) and re.fullmatch(r"-?[\d,]+(\.\d+)?", v.strip()) is not None


def same(fa, oa, fb, ob):
    try:
        return Translator(fa, origin=oa).translate_formula(ob) == fb
    except Exception:
        return False


def name_dests(wb, n):
    try:
        return list(wb.defined_names[n].destinations)
    except Exception:
        return []


def analyse(path):
    wb = load_workbook(path)
    names = set(wb.defined_names.keys())
    sheets = set(wb.sheetnames)
    val = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    val[(ws.title, c.coordinate)] = c.value
    hits = []  # (kind, sheet, cell, detail)
    graph = {}
    sum_ranges = []  # (sheet, cell-of-formula, [cells])
    for (s, co), v in val.items():
        if not is_formula(v):
            continue
        deps = set()
        if "#REF!" in v:
            hits.append(("REF_ERROR", s, co, v))
        for kind, rs, r in formula_refs(v):
            if kind == "ext":
                hits.append(("EXTERNAL_LINK", s, co, v))
            elif kind == "name":
                if r not in names:
                    hits.append(("UNKNOWN_NAME", s, co, r))
                else:
                    for ds, dr in name_dests(wb, r):
                        for x in cells_of(dr.replace("$", "")):
                            deps.add((ds, x))
            elif kind == "range":
                tgt = rs or s
                if tgt not in sheets:
                    hits.append(("MISSING_SHEET", s, co, tgt))
                    continue
                cs = cells_of(r)
                for x in cs:
                    deps.add((tgt, x))
                if re.search(r"(?<![A-Z])SUM(IFS)?\(", v):
                    sum_ranges.append((s, co, [(tgt, x) for x in cs]))
            elif kind == "bad":
                hits.append(("BAD_TOKEN", s, co, r))
        m = re.search(r"[+\-]\s*(\d+(?:\.\d+)?)\s*$", v)
        if m and float(m.group(1)) != 1 and re.search(r"[A-Z]+\$?\d", v[:m.start()]):
            hits.append(("HARDCODED_PLUG", s, co, v))
        graph[(s, co)] = deps
    for n in names:
        t = wb.defined_names[n].attr_text
        bad = "#REF!" in t
        if not bad:
            for ds, _ in name_dests(wb, n):
                if ds not in sheets:
                    bad = True
        if bad:
            hits.append(("BROKEN_NAME", None, f"name:{n}", t))
    # text numbers in SUM ranges
    seen = set()
    for s, co, cs in sum_ranges:
        for key in cs:
            if key in val and textnum(val[key]) and key not in seen:
                seen.add(key)
                hits.append(("TEXT_NUMBER_IN_SUM", key[0], key[1], val[key]))
    # cycles (Tarjan)
    sys.setrecursionlimit(10000)
    index, low, stack, on, sccs = {}, {}, [], set(), []
    counter = [0]

    def strong(n):
        index[n] = low[n] = counter[0]
        counter[0] += 1
        stack.append(n)
        on.add(n)
        for m in graph.get(n, ()):
            if m not in graph:
                continue
            if m not in index:
                strong(m)
                low[n] = min(low[n], low[m])
            elif m in on:
                low[n] = min(low[n], index[m])
        if low[n] == index[n]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == n:
                    break
            if len(comp) > 1 or n in graph.get(n, ()):
                sccs.append(comp)

    for n in list(graph):
        if n not in index:
            strong(n)
    for comp in sccs:
        hits.append(("CIRCULAR_REFERENCE", comp[0][0], comp[0][1], sorted(f"{a}!{b}" for a, b in comp)))
    # run breaks
    for (s, co), v in val.items():
        if not (is_formula(v) or is_num(v)):
            continue
        col, row = coordinate_from_string(co)
        ci = CI(col)
        for (ka, kb) in [((CL(ci - 1), row), (CL(ci + 1), row)) if ci > 1 else (None, None),
                         ((col, row - 1), (col, row + 1)) if row > 1 else (None, None)]:
            if ka is None:
                continue
            a = f"{ka[0]}{ka[1]}"
            bb = f"{kb[0]}{kb[1]}"
            fa, fb = val.get((s, a)), val.get((s, bb))
            if not (is_formula(fa) and is_formula(fb)) or not same(fa, a, fb, bb):
                continue
            if is_num(v):
                hits.append(("HARDCODED_OVERRIDE", s, co, f"between {a} and {bb}"))
            elif not same(fa, a, v, co):
                hits.append(("INCONSISTENT_FORMULA", s, co, f"between {a} and {bb}"))
    # sum omits (simple same-column / same-row SUM)
    for (s, co), v in val.items():
        if not is_formula(v):
            continue
        m = re.fullmatch(r"=-?SUM\(\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)\)", v)
        if not m:
            continue
        c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        col, row = coordinate_from_string(co)
        if c1 == c2 == col and row > r2:
            gap = [f"{col}{r}" for r in range(r2 + 1, row)]
        elif r1 == r2 == row and CI(col) > CI(c2):
            gap = [f"{CL(k)}{row}" for k in range(CI(c2) + 1, CI(col))]
        else:
            continue
        if any(is_num(val.get((s, g))) or is_formula(val.get((s, g))) for g in gap):
            hits.append(("SUM_OMITS_ROW", s, co, v))
    # double count: SUM range that contains a SUM over cells also in the range
    for s, co, cs in sum_ranges:
        f = val[(s, co)]
        if not re.search(r"(?<![A-Z])SUM\(", f):
            continue
        cset = set(cs)
        for key in cs:
            g = val.get(key)
            if is_formula(g) and key != (s, co):
                m = re.fullmatch(r"=SUM\((\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)", g)
                if m:
                    inner = {(key[0], x) for x in cells_of(m.group(1).replace("$", ""))}
                    if inner <= cset:
                        hits.append(("DOUBLE_COUNT", s, co, f"includes {key[1]}"))
                        break
    return wb, val, hits, sccs


def in_range(cell, rng):
    if ":" not in rng:
        return cell == rng
    c1, r1, c2, r2 = range_boundaries(rng)
    col, row = coordinate_from_string(cell)
    return c1 <= CI(col) <= c2 and r1 <= row <= r2


def verify(books):
    problems = []
    unlabelled = []
    for b in books:
        path = os.path.join(OUT, b.fname)
        wb, val, hits, sccs = analyse(path)
        hitset = {(k, s, c) for k, s, c, _ in hits}
        fault_cells = {}
        for f in b.faults:
            cells = [f["cell"]] + f.get("group", []) + [x.split("!", 1)[1] for x in f.get("cycle", [])]
            for c in cells:
                fault_cells.setdefault((f["sheet"], c), []).append(f["kind"])
            kinds = [f["kind"]] + f.get("also_ok", [])
            for c in [f["cell"]] + f.get("group", []):
                if f["kind"] == "BROKEN_NAME":
                    ok = ("BROKEN_NAME", None, c) in hitset
                elif f["kind"] == "CIRCULAR_REFERENCE":
                    want = set(f["cycle"])
                    ok = any(want <= {f"{a}!{bb}" for a, bb in comp} and f"{f['sheet']}!{c}" in want
                             for comp in sccs)
                else:
                    ok = any((k, f["sheet"], c) in hitset for k in kinds)
                if not ok:
                    problems.append(f"{b.fname}: label {f['kind']} at {f['sheet']}!{c} not confirmed")
            if f["kind"] not in ("BROKEN_NAME",) and (f["sheet"], f["cell"]) not in val:
                problems.append(f"{b.fname}: fault cell {f['sheet']}!{f['cell']} is empty")
        for lg in b.legit:
            for (s, c), ks in fault_cells.items():
                if s == lg["sheet"] and c and not c.startswith("name:") and in_range(c, lg["cell"]):
                    problems.append(f"{b.fname}: legit {lg['sheet']}!{lg['cell']} overlaps fault {s}!{c} {ks}")
            if lg["sheet"] not in wb.sheetnames:
                problems.append(f"{b.fname}: legit sheet {lg['sheet']} missing")
        for k, s, c, detail in hits:
            if k == "CIRCULAR_REFERENCE":
                if any(set(f.get("cycle", [])) == set(detail) for f in b.faults):
                    continue
            if (s, c) in fault_cells:
                continue
            if any(lg["sheet"] == s and in_range(c, lg["cell"]) for lg in b.legit):
                if os.environ.get("SHOW_LEGIT_HITS"):
                    print(f"  (legit) {b.fname}: {k} {s}!{c} ({detail})")
                continue
            unlabelled.append(f"{b.fname}: {k} {s}!{c} ({detail})")
    return problems, unlabelled


def main():
    builders = [build_cash, build_bridge, build_lease, build_bankrec, build_vat, build_inventory,
                build_board, build_scenarios, build_unit_econ, build_bva, build_annual]
    books = [fn() for fn in builders]
    for v in (1, 2):
        books += [build_rolling(v), build_debt(v), build_capex(v)]
    for b in books:
        b.save()
    truth = {"workbooks": {b.fname: b.truth() for b in books}, "diffs": DIFFS}
    with open(os.path.join(OUT, "truth.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(truth, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # diff anchors exist
    problems = []
    for d in DIFFS:
        wa = load_workbook(os.path.join(OUT, d["after"]))
        wbf = load_workbook(os.path.join(OUT, d["before"]))
        for ch in d["changes"]:
            k = ch["kind"]
            if k == "SHEET_REMOVED":
                if ch["sheet"] in wa.sheetnames or ch["sheet"] not in wbf.sheetnames:
                    problems.append(f"diff {k} {ch['sheet']} wrong")
                continue
            if k == "SHEET_ADDED":
                if ch["sheet"] not in wa.sheetnames or ch["sheet"] in wbf.sheetnames:
                    problems.append(f"diff {k} {ch['sheet']} wrong")
                continue
            a = wa[ch["sheet"]][ch["cell"]].value
            bv = wbf[ch["sheet"]][ch["before_cell"]].value
            exp = {"FORMULA_TO_VALUE": is_formula(bv) and is_num(a),
                   "VALUE_TO_FORMULA": is_num(bv) and is_formula(a),
                   "FORMULA_CHANGED": is_formula(bv) and is_formula(a) and bv != a}[k]
            if not exp:
                problems.append(f"diff {k} {ch['sheet']}!{ch['cell']} wrong: {bv!r} -> {a!r}")

    p2, unlabelled = verify(books)
    problems += p2
    nf = sum(len(b.faults) for b in books)
    nl = sum(len(b.legit) for b in books)
    by = {}
    for b in books:
        for f in b.faults:
            by[f["kind"]] = by.get(f["kind"], 0) + 1
    print(f"workbooks: {len(books)}  faults: {nf}  legit: {nl}  diff pairs: {len(DIFFS)}  "
          f"changes: {sum(len(d['changes']) for d in DIFFS)}")
    for k in sorted(by):
        print(f"  {k}: {by[k]}")
    print(f"unlabelled self-scan hits: {len(unlabelled)}")
    for u in unlabelled:
        print("  ?", u)
    if problems:
        print("LABEL PROBLEMS:")
        for p in problems:
            print("  !", p)
        sys.exit(1)
    print("all labels confirmed")


if __name__ == "__main__":
    main()
