"""Synthetic workbooks with known answers: four kinds of finance model, problems planted where the truth says.

Each seed builds two budgets, a loan schedule, a multi-entity consolidation and a commission calculator, with
random sizes, offsets and a random subset of planted problems, plus two version pairs (a clean budget and an
edited copy). Every workbook also carries the legitimate exceptions a real model has (actual columns before
forecast columns, input blocks, full-year columns, documented overrides, opening balances, grand totals of
subtotals, unit constants, hidden helper sheets), listed in the truth so false alarms on them can be counted.

A problem copied across a row (a total row whose every column omits the same item) is one planted problem with
its other cells in `group`, as an analyst would count it.

These workbooks are written by openpyxl, so they hold no calculated values: the checks of saved error values
(CACHED_ERROR, CACHED_NA) are tested by unit tests with hand-made files instead.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font
from openpyxl.utils.cell import get_column_letter as L
from openpyxl.workbook.defined_name import DefinedName

BLUE = Font(color="FF0000FF")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SECTIONS = {
    "Revenue": ["Product sales", "Subscriptions", "Services", "Licences", "Support contracts", "Training", "Other revenue"],
    "Cost of sales": ["Materials", "Freight", "Hosting", "Contractors", "Payment fees", "Royalties"],
    "Operating expenses": ["Salaries", "Benefits", "Rent", "Software", "Travel", "Marketing", "Insurance", "Legal",
                           "Utilities", "Recruiting"],
}


@dataclass
class Book:
    name: str
    data: bytes
    faults: list[dict[str, Any]] = field(default_factory=list)
    legit: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Pair:
    before: Book
    after: Book
    changes: list[dict[str, Any]] = field(default_factory=list)
    not_material: list[str] = field(default_factory=list)


def _bytes(wb: Workbook) -> bytes:
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _fault(sheet: str | None, cell: str, kind: str, note: str, group: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    return {"sheet": sheet, "cell": cell, "kind": kind, "note": note, "group": group or [], **kw}


# -- budget -----------------------------------------------------------------------------------------------------

@dataclass
class BudgetSpec:
    name: str
    year: int
    r0: int
    c0: int
    n_actual: int
    sections: list[tuple[str, list[str]]]
    rates: list[float]
    year_row: bool
    grand_style: str  # "plus" | "sumlist"
    rng: random.Random
    overrides: dict[tuple[str, int], Any] = field(default_factory=dict)  # (item label, month) -> value or formula
    renames: dict[str, str] = field(default_factory=dict)
    extra_sheet: str | None = None


@dataclass
class BudgetLayout:
    row: dict[str, int]  # item label -> row
    subtotal: dict[str, int]  # section -> row
    grand: int
    first_col: int  # January
    fy_col: int
    memo: int  # first free row below the table
    items: dict[str, list[str]]
    base: dict[str, int]

    def cell(self, label: str, month: int) -> str:
        return f"{L(self.first_col + month)}{self.row[label]}"


def _build_budget(s: BudgetSpec) -> tuple[Workbook, BudgetLayout]:
    rng = random.Random(s.name)  # values depend only on the name, so both versions of a pair agree
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = f"FY{s.year} budget assumptions"
    for k, ((sec, _), rate) in enumerate(zip(s.sections, s.rates, strict=True)):
        a.cell(3 + k, 1, f"{sec} monthly growth")
        a.cell(3 + k, 2, rate).font = BLUE
        a.cell(3 + k, 2).number_format = "0.0%"
    wb.defined_names["Inflation"] = DefinedName("Inflation", attr_text="Assumptions!$B$10")
    a["A10"], a["B10"] = "Inflation", 0.03
    a["B10"].font = BLUE
    ws = wb.create_sheet("Budget")
    r0, c0 = s.r0, s.c0
    ws.cell(r0, c0, f"FY{s.year} operating budget")
    hr = r0 + 3
    if s.year_row:
        for m in range(12):
            ws.cell(hr - 1, c0 + 1 + m, s.year)
    ws.cell(hr, c0, "Line")
    for m in range(12):
        ws.cell(hr, c0 + 1 + m, MONTHS[m] + (" (A)" if m < s.n_actual else ""))
    fy = c0 + 13
    ws.cell(hr, fy, f"FY{s.year}")
    r = hr + 2
    rows: dict[str, int] = {}
    subs: dict[str, int] = {}
    base: dict[str, int] = {}
    for k, (sec, items) in enumerate(s.sections):
        ws.cell(r, c0, sec)
        r += 1
        first = r
        for it in items:
            rows[it] = r
            ws.cell(r, c0, s.renames.get(it, it))
            b = base[it] = rng.randrange(20, 400) * 100
            for m in range(12):
                col = c0 + 1 + m
                if m < max(1, s.n_actual):
                    ws.cell(r, col, int(b * (1 + rng.uniform(-0.08, 0.08))))
                else:
                    ws.cell(r, col, f"={L(col - 1)}{r}*(1+Assumptions!$B${3 + k})")
                ov = s.overrides.get((it, m))
                if ov is not None:
                    if callable(ov):
                        ov(ws, r, col, k)
                    else:
                        ws.cell(r, col, ov)
            ws.cell(r, fy, f"=SUM({L(c0 + 1)}{r}:{L(c0 + 12)}{r})")
            r += 1
        subs[sec] = r
        ws.cell(r, c0, f"Total {sec.lower()}")
        for m in range(13):
            col = c0 + 1 + m
            ws.cell(r, col, f"=SUM({L(col)}{first}:{L(col)}{r - 1})")
        r += 2
    grand = r
    ws.cell(r, c0, "Net budget")
    for m in range(13):
        col = c0 + 1 + m
        refs = [f"{L(col)}{subs[sec]}" for sec, _ in s.sections]
        if s.grand_style == "plus":
            ws.cell(r, col, f"={refs[0]}-" + "-".join(refs[1:]))
        else:
            ws.cell(r, col, f"={refs[0]}-SUM({','.join(refs[1:])})")
    if s.extra_sheet:
        n = wb.create_sheet(s.extra_sheet)
        n["A1"] = "Notes"
        n["A2"] = "Assumptions agreed with department heads."
    return wb, BudgetLayout(rows, subs, grand, c0 + 1, fy, grand + 3, {sec: list(it) for sec, it in s.sections}, base)


def _budget_spec(rng: random.Random, name: str, year: int) -> BudgetSpec:
    n_sec = rng.choice([2, 3, 3])
    secs = []
    for sec in list(SECTIONS)[:n_sec]:
        pool = SECTIONS[sec]
        secs.append((sec, rng.sample(pool, rng.randint(3, min(6, len(pool))))))
    return BudgetSpec(name, year, rng.randint(1, 4), rng.randint(1, 3), rng.choice([0, 2, 3, 5]), secs,
                      [round(rng.uniform(0.002, 0.02), 4) for _ in secs], rng.random() < 0.5,
                      rng.choice(["plus", "sumlist"]), rng)


def budget(rng: random.Random, name: str, year: int, plant: set[str]) -> Book:
    s = _budget_spec(rng, name, year)
    lay: BudgetLayout  # set once the workbook is built; the label callbacks below run after that
    faults: list[dict[str, Any]] = []
    legit: list[dict[str, Any]] = []
    first_fc = max(1, s.n_actual)  # first forecast month
    # Interior forecast months: at least one formula on each side and three agreeing in all.
    interior = list(range(first_fc + 1, 11))
    cells_used: set[tuple[str, int]] = set()

    def pick(section_items: list[str] | None = None) -> tuple[str, int]:
        items = section_items or [it for _, its in s.sections for it in its]
        for _ in range(200):
            it, m = rng.choice(items), rng.choice(interior)
            if all((it, mm) not in cells_used for mm in (m - 1, m, m + 1)) and \
                    all((o, m) not in cells_used for o in items if abs(items.index(o) - items.index(it)) <= 1):
                cells_used.add((it, m))
                return it, m
        raise RuntimeError("no free cell")

    later: list[Any] = []
    post: list[Any] = []
    if "INCONSISTENT_FORMULA" in plant:
        sec, items = rng.choice([x for x in s.sections if len(x[1]) >= 2])
        it, m = pick(items)
        other = items[items.index(it) - 1] if items.index(it) > 0 else items[1]
        mode = rng.choice(["row", "drop"])

        k_sec = [x[0] for x in s.sections].index(sec)

        def wrong(ws: Any, lay: BudgetLayout, it: str = it, m: int = m, other: str = other, mode: str = mode) -> None:
            r, col = lay.row[it], lay.first_col + m
            if mode == "drop":
                ws.cell(r, col, f"={L(col - 1)}{r}")
            else:
                ws.cell(r, col, f"={L(col - 1)}{lay.row[other]}*(1+Assumptions!$B${3 + k_sec})")
        post.append(wrong)
        later.append(lambda it=it, m=m, mode=mode: _fault("Budget", lay.cell(it, m), "INCONSISTENT_FORMULA",
                                                         "growth term dropped" if mode == "drop" else "points at the row above/below"))
    if "HARDCODED_OVERRIDE" in plant:
        it, m = pick()
        s.overrides[(it, m)] = rng.randrange(50, 300) * 100
        later.append(lambda it=it, m=m: _fault("Budget", lay.cell(it, m), "HARDCODED_OVERRIDE", "forecast formula typed over"))
    # Legitimate: a documented override, by colour or by comment.
    it, m = pick()
    how = rng.choice(["colour", "comment"])

    def documented(ws: Any, r: int, col: int, k: int, how: str = how) -> None:
        c = ws.cell(r, col, rng.randrange(50, 300) * 100)
        if how == "colour":
            c.font = BLUE
        else:
            c.comment = Comment("Signed contract amount for this month", "FP&A")
    s.overrides[(it, m)] = documented
    later_legit = [lambda it=it, m=m, how=how: {"sheet": "Budget", "cell": lay.cell(it, m), "what": f"override documented by {how}"}]
    if "TEXT_NUMBER_IN_SUM" in plant and s.n_actual >= 1:
        it = rng.choice([it for _, its in s.sections for it in its])
        m = rng.randrange(0, s.n_actual)
        s.overrides[(it, m)] = f"{rng.randrange(1, 99)},{rng.randrange(100, 999)}"
        cells_used.add((it, m))
        later.append(lambda it=it, m=m: _fault("Budget", lay.cell(it, m), "TEXT_NUMBER_IN_SUM", "actual typed as text"))
    if "REF_ERROR" in plant:
        it, m = pick()

        def ref_err(ws: Any, r: int, col: int, k: int) -> None:
            ws.cell(r, col, f"=#REF!*(1+Assumptions!$B${3 + k})")
        s.overrides[(it, m)] = ref_err
        later.append(lambda it=it, m=m: _fault("Budget", lay.cell(it, m), "REF_ERROR", "previous month deleted"))

    wb, lay = _build_budget(s)
    ws = wb["Budget"]
    for fn in post:
        fn(ws, lay)
    c0 = lay.first_col - 1
    faults += [f() for f in later]
    legit += [f() for f in later_legit]
    memo = lay.memo
    secs = [sec for sec, _ in s.sections]
    if "SUM_OMITS_ROW" in plant:
        sec = rng.choice(secs)
        items = lay.items[sec]
        sub = lay.subtotal[sec]
        first, last = lay.row[items[0]], lay.row[items[-1]]
        whole = rng.random() < 0.6
        cols = range(13) if whole else [rng.randrange(0, 12)]
        for m in cols:
            col = lay.first_col + m
            ws.cell(sub, col, f"=SUM({L(col)}{first}:{L(col)}{last - 1})")
        addrs = [f"{L(lay.first_col + m)}{sub}" for m in cols]
        faults.append(_fault("Budget", addrs[0], "SUM_OMITS_ROW", f"{sec} total leaves out its last item", addrs[1:]))
    if "DOUBLE_COUNT" in plant:
        g = lay.grand
        ws.cell(g, c0, "Total cost")
        sec_c = [x for x in secs if x != "Revenue"] or secs
        top = lay.row[lay.items[sec_c[0]][0]]
        bottom = lay.subtotal[sec_c[-1]]
        if len(sec_c) >= 1:
            for m in range(13):
                col = lay.first_col + m
                ws.cell(g, col, f"=SUM({L(col)}{top}:{L(col)}{bottom})")
            addrs = [f"{L(lay.first_col + m)}{g}" for m in range(13)]
            faults.append(_fault("Budget", addrs[0], "DOUBLE_COUNT", "total cost adds the items and their subtotals", addrs[1:]))
    else:
        legit.append({"sheet": "Budget", "cell": f"{L(lay.first_col)}{lay.grand}:{L(lay.fy_col)}{lay.grand}",
                      "what": "net budget from the subtotals only"})
    if "HARDCODED_PLUG" in plant:
        m = rng.randrange(0, 12)
        col = lay.first_col + m
        g = lay.grand
        ws.cell(g, col, f"{ws.cell(g, col).value}+{rng.randrange(1, 90) * 50}")
        faults.append(_fault("Budget", f"{L(col)}{g}", "HARDCODED_PLUG", "a typed amount forces the net budget"))
    if "EXTERNAL_LINK" in plant:
        ws.cell(memo, c0, "Prior year (memo)")
        for m in range(12):
            col = lay.first_col + m
            ws.cell(memo, col, f"='[FY{s.year - 1} budget.xlsx]Budget'!{L(col)}{lay.grand}")
        addrs = [f"{L(lay.first_col + m)}{memo}" for m in range(12)]
        faults.append(_fault("Budget", addrs[0], "EXTERNAL_LINK", "prior-year file linked", addrs[1:]))
        memo += 1
    if "UNKNOWN_NAME" in plant:
        ws.cell(memo, c0, "Real terms (memo)")
        col = lay.fy_col
        ws.cell(memo, col, f"={L(col)}{lay.grand}/(1+InflationRate)")
        faults.append(_fault("Budget", f"{L(col)}{memo}", "UNKNOWN_NAME", "name InflationRate never defined (Inflation is)"))
        memo += 1
    else:
        ws.cell(memo, c0, "Real terms (memo)")
        ws.cell(memo, lay.fy_col, f"={L(lay.fy_col)}{lay.grand}/(1+Inflation)")
        legit.append({"sheet": "Budget", "cell": f"{L(lay.fy_col)}{memo}", "what": "uses the defined name Inflation"})
        memo += 1
    if "MISSING_SHEET" in plant:
        ws.cell(memo, c0, "Headcount check")
        ws.cell(memo, lay.fy_col, "='Headcount plan'!B20")
        faults.append(_fault("Budget", f"{L(lay.fy_col)}{memo}", "MISSING_SHEET", "sheet was deleted"))
        memo += 1
    if "BROKEN_NAME" in plant:
        wb.defined_names["PriorYearTotal"] = DefinedName("PriorYearTotal", attr_text="#REF!")
        faults.append(_fault(None, "name:PriorYearTotal", "BROKEN_NAME", "its sheet was deleted"))
    if "CIRCULAR_REFERENCE" in plant and "Operating expenses" in secs:
        it = lay.items["Operating expenses"][-1]
        r = lay.row[it]
        m = rng.randrange(first_fc, 12)
        col = lay.first_col + m
        ws.cell(r, c0, "Contingency")
        for mm in range(12):
            ws.cell(r, lay.first_col + mm, 1000)
        ws.cell(r, col, f"=ABS({L(col)}{lay.grand})*0.05")
        cyc = [f"Budget!{L(col)}{r}", f"Budget!{L(col)}{lay.subtotal['Operating expenses']}", f"Budget!{L(col)}{lay.grand}"]
        faults.append(_fault("Budget", f"{L(col)}{r}", "CIRCULAR_REFERENCE", "contingency is 5% of a total that includes it",
                             cycle=cyc))
    # Legitimate structure, listed so false alarms on it are counted.
    if s.n_actual:
        legit.append({"sheet": "Budget", "cell": f"{L(lay.first_col)}:{L(lay.first_col + s.n_actual - 1)}",
                      "what": "actual months typed before forecast formulas"})
    else:
        legit.append({"sheet": "Budget", "cell": f"{L(lay.first_col)}", "what": "January typed as the base month"})
    legit.append({"sheet": "Budget", "cell": f"{L(lay.fy_col)}", "what": "full-year column of row totals"})
    legit.append({"sheet": "Assumptions", "cell": "B3:B10", "what": "typed growth rates in the input colour"})
    if s.year_row:
        legit.append({"sheet": "Budget", "cell": "year row", "what": "typed year heading above the months"})
    for sec in secs:
        legit.append({"sheet": "Budget", "cell": f"{L(lay.first_col)}{lay.subtotal[sec]}", "what": f"{sec} subtotal"})
    return Book(name, _bytes(wb), faults, legit)


# -- loan schedule (time runs down the rows) -------------------------------------------------------------------

def loan(rng: random.Random, name: str, plant: set[str]) -> Book:
    wb = Workbook()
    ws = wb.active
    ws.title = rng.choice(["Loan", "Amortisation", "Term loan"])
    sh = ws.title
    ws["A1"] = "Term loan schedule"
    inputs = [("Principal", rng.randrange(50, 500) * 1000), ("Annual rate", round(rng.uniform(0.04, 0.11), 4)),
              ("Term (years)", rng.choice([2, 3, 4, 5]))]
    for i, (k, v) in enumerate(inputs):
        ws.cell(3 + i, 1, k)
        ws.cell(3 + i, 2, v).font = BLUE
    ws["A6"] = "Monthly payment"
    ws["B6"] = "=PMT($B$4/12,$B$5*12,-$B$3)"
    n = int(inputs[2][1]) * 12
    h = 9
    for j, t in enumerate(["Period", "Opening", "Interest", "Payment", "Principal", "Closing"]):
        ws.cell(h, 1 + j, t)
    first, last = h + 1, h + n
    for i in range(n):
        r = first + i
        ws.cell(r, 1, i + 1)
        ws.cell(r, 2, "=$B$3" if i == 0 else f"=F{r - 1}")
        ws.cell(r, 3, f"=B{r}*$B$4/12")
        ws.cell(r, 4, "=$B$6")
        ws.cell(r, 5, f"=D{r}-C{r}")
        ws.cell(r, 6, f"=B{r}-E{r}")
    tr = last + 2
    ws.cell(tr, 1, "Total")
    for col in "CDE":
        ws[f"{col}{tr}"] = f"=SUM({col}{first}:{col}{last})"
    faults: list[dict[str, Any]] = []
    used: set[int] = set()

    def row() -> int:
        for _ in range(1000):
            r = rng.randrange(first + 2, last - 2)
            if not used & {r - 1, r, r + 1}:
                used.add(r)
                return r
        raise RuntimeError("no free row")
    if "INCONSISTENT_FORMULA" in plant:
        r = row()
        ws[f"C{r}"] = rng.choice([f"=B{r - 1}*$B$4/12", f"=B{r}*$B$4/365*30", f"=B{r}*B4/12"])
        faults.append(_fault(sh, f"C{r}", "INCONSISTENT_FORMULA", "interest computed differently in one period"))
    if "HARDCODED_OVERRIDE" in plant:
        r = row()
        ws[f"F{r}"] = rng.randrange(10, 400) * 1000
        faults.append(_fault(sh, f"F{r}", "HARDCODED_OVERRIDE", "closing balance typed"))
    if "HARDCODED_PLUG" in plant:
        r = row()
        ws[f"D{r}"] = f"=$B$6+{rng.randrange(1, 20) * 25}"
        faults.append(_fault(sh, f"D{r}", "HARDCODED_PLUG", "extra payment typed into the formula"))
    if "SUM_OMITS_ROW" in plant:
        ws[f"C{tr}"] = f"=SUM(C{first}:C{last - 1})"
        faults.append(_fault(sh, f"C{tr}", "SUM_OMITS_ROW", "total interest leaves out the last period"))
    legit = [{"sheet": sh, "cell": f"B{first}", "what": "opening balance of the first period reads the principal"},
             {"sheet": sh, "cell": "B3:B5", "what": "typed inputs"},
             {"sheet": sh, "cell": f"A{first}:A{last}", "what": "typed period numbers"},
             {"sheet": sh, "cell": f"C{tr}:E{tr}", "what": "totals"}]
    return Book(name, _bytes(wb), faults, legit)


# -- consolidation (several sheets, a hidden helper sheet, a defined name) -------------------------------------

ACCOUNTS = ["Revenue", "Cost of goods sold", "Payroll", "Rent", "Marketing", "IT", "Professional fees", "Depreciation",
            "Interest", "Other expense"]


def consolidation(rng: random.Random, name: str, plant: set[str]) -> Book:
    wb = Workbook()
    entities = ["Entity A", "Entity B (UK)"]
    accts = rng.sample(ACCOUNTS, rng.randint(6, 9))
    r0 = rng.randint(3, 5)
    first, last = r0 + 1, r0 + len(accts)
    tot = last + 1
    faults: list[dict[str, Any]] = []
    legit: list[dict[str, Any]] = []
    for e_i, e in enumerate(entities):
        ws = wb.active if e_i == 0 else wb.create_sheet(e)
        ws.title = e
        ws.cell(1, 1, f"{e} trial balance by quarter")
        for q in range(4):
            ws.cell(r0, 2 + q, f"Q{q + 1}")
        ws.cell(r0, 6, "Year")
        for i, a in enumerate(accts):
            r = first + i
            ws.cell(r, 1, a)
            for q in range(4):
                ws.cell(r, 2 + q, rng.randrange(5, 900) * 100)
            ws.cell(r, 6, f"=SUM(B{r}:E{r})")
        ws.cell(tot, 1, "Total")
        for q in range(5):
            col = L(2 + q)
            ws[f"{col}{tot}"] = f"=SUM({col}{first}:{col}{last})"
        legit.append({"sheet": e, "cell": f"B{first}:E{last}", "what": "typed trial balance"})
    fx = wb.create_sheet("FX")
    fx["A2"], fx["B2"] = "GBP to USD", round(rng.uniform(1.2, 1.35), 4)
    fx.sheet_state = "hidden"
    wb.defined_names["FX_GBP"] = DefinedName("FX_GBP", attr_text="FX!$B$2")
    legit.append({"sheet": "FX", "cell": "B2", "what": "hidden rate sheet read through a defined name"})
    if "TEXT_NUMBER_IN_SUM" in plant:
        e = rng.choice(entities)
        r, q = rng.randrange(first, last + 1), rng.randrange(4)
        wb[e].cell(r, 2 + q, f"{rng.randrange(1, 90)},{rng.randrange(100, 999)}")
        faults.append(_fault(e, f"{L(2 + q)}{r}", "TEXT_NUMBER_IN_SUM", "amount pasted as text"))
    c = wb.create_sheet("Consolidation")
    c.cell(1, 1, "Consolidated, USD")
    for q in range(4):
        c.cell(r0, 2 + q, f"Q{q + 1}")
    c.cell(r0, 6, "Year")
    for i, a in enumerate(accts):
        r = first + i
        c.cell(r, 1, a)
        for q in range(4):
            col = L(2 + q)
            c[f"{col}{r}"] = f"='Entity A'!{col}{r}+'Entity B (UK)'!{col}{r}*FX_GBP"
        c[f"F{r}"] = f"=SUM(B{r}:E{r})"
    c.cell(tot, 1, "Total")
    for q in range(5):
        col = L(2 + q)
        c[f"{col}{tot}"] = f"=SUM({col}{first}:{col}{last})"
    used: set[tuple[int, int]] = set()

    def spot() -> tuple[int, int]:
        for tries in range(1000):
            r, q = rng.randrange(first + 1, last), rng.randrange(1, 3)
            near = (r - 1, r, r + 1) if tries < 500 else (r,)
            if not any((rr, qq) in used for rr in near for qq in (q - 1, q, q + 1)):
                used.add((r, q))
                return r, q
        raise RuntimeError("no free cell")
    if "INCONSISTENT_FORMULA" in plant:
        r, q = spot()
        col = L(2 + q)
        c[f"{col}{r}"] = f"='Entity A'!{col}{r}+'Entity B (UK)'!{col}{r + 1}*FX_GBP"
        faults.append(_fault("Consolidation", f"{col}{r}", "INCONSISTENT_FORMULA", "UK figure taken from the next account"))
    if "MISSING_SHEET" in plant:
        r, q = spot()
        col = L(2 + q)
        c[f"{col}{r}"] = f"='Entity A'!{col}{r}+'Entity B (UK)'!{col}{r}*FX_GBP+'Entity C'!{col}{r}"
        faults.append(_fault("Consolidation", f"{col}{r}", "MISSING_SHEET", "an entity sheet that was removed"))
    if "UNKNOWN_NAME" in plant:
        r, q = spot()
        col = L(2 + q)
        c[f"{col}{r}"] = f"='Entity A'!{col}{r}+'Entity B (UK)'!{col}{r}*FX_EUR"
        faults.append(_fault("Consolidation", f"{col}{r}", "UNKNOWN_NAME", "FX_EUR is not defined"))
    if "EXTERNAL_LINK" in plant:
        c.cell(r0, 8, "Prior year")
        for i in range(len(accts)):
            c[f"H{first + i}"] = f"='[Consolidation FY24.xlsx]Consolidation'!F{first + i}"
        faults.append(_fault("Consolidation", f"H{first}", "EXTERNAL_LINK", "prior-year workbook linked",
                             [f"H{first + i}" for i in range(1, len(accts))]))
    if "DOUBLE_COUNT" in plant:
        c[f"F{tot}"] = f"=SUM(F{first}:F{last})+SUM(B{tot}:E{tot})"
        # Not additive-only within one range: this is the "year total adds both ways" mistake, a plain risk.
        faults.append(_fault("Consolidation", f"F{tot}", "DOUBLE_COUNT", "year total adds the rows and the quarter totals"))
    legit.append({"sheet": "Consolidation", "cell": f"F{first}:F{last}", "what": "year column of row totals"})
    return Book(name, _bytes(wb), faults, legit)


# -- commission calculator (a lookup, thresholds, a loop) -------------------------------------------------------

REPS = ["Avery", "Blake", "Casey", "Devon", "Emerson", "Finley", "Gray", "Harper", "Jordan", "Kai", "Logan", "Morgan",
        "Parker", "Quinn", "Reese", "Rowan", "Sage", "Taylor"]


def commission(rng: random.Random, name: str, plant: set[str]) -> Book:
    wb = Workbook()
    rt = wb.active
    rt.title = "Rates"
    for i, (k, v) in enumerate([("Threshold", 250000), ("Base rate", 0.05), ("Accelerated rate", 0.08), ("Bonus pool share", 0.02)]):
        rt.cell(2 + i, 1, k)
        rt.cell(2 + i, 2, v).font = BLUE
    ws = wb.create_sheet("Commissions")
    reps = rng.sample(REPS, rng.randint(8, 14))
    h = 4
    for j, t in enumerate(["Rep", "Region", "Sales", "Rate", "Commission", "Rate %"]):
        ws.cell(h, 1 + j, t)
    first, last = h + 1, h + len(reps)
    for i, rep in enumerate(reps):
        r = first + i
        ws.cell(r, 1, rep)
        ws.cell(r, 2, rng.choice(["East", "West", "Central"]))
        ws.cell(r, 3, rng.randrange(80, 600) * 1000)
        ws.cell(r, 4, f"=IF(C{r}>Rates!$B$2,Rates!$B$4,Rates!$B$3)")
        ws.cell(r, 5, f"=C{r}*D{r}")
        ws.cell(r, 6, f"=IFERROR(E{r}/C{r}*100,0)")
    tr = last + 1
    ws.cell(tr, 1, "Total")
    ws[f"C{tr}"] = f"=SUM(C{first}:C{last})"
    ws[f"E{tr}"] = f"=SUM(E{first}:E{last})"
    faults: list[dict[str, Any]] = []
    used: set[int] = set()

    def row() -> int:
        for _ in range(1000):
            r = rng.randrange(first + 1, last)
            if not used & {r - 1, r, r + 1}:
                used.add(r)
                return r
        raise RuntimeError("no free row")
    if "INCONSISTENT_FORMULA" in plant:
        r = row()
        ws[f"D{r}"] = f"=IF(C{r}>Rates!$B$2,Rates!$B$4,Rates!$B$4)"
        faults.append(_fault("Commissions", f"D{r}", "INCONSISTENT_FORMULA", "accelerated rate on both branches"))
    if "HARDCODED_OVERRIDE" in plant:
        r = row()
        ws[f"E{r}"] = rng.randrange(5, 40) * 1000
        faults.append(_fault("Commissions", f"E{r}", "HARDCODED_OVERRIDE", "commission typed"))
    if "CIRCULAR_REFERENCE" in plant:
        ws.cell(tr + 2, 1, "Bonus pool")
        ws[f"E{tr + 2}"] = f"=E{tr}*Rates!$B$5"
        ws[f"E{tr}"] = f"=SUM(E{first}:E{last})+E{tr + 2}"
        faults.append(_fault("Commissions", f"E{tr}", "CIRCULAR_REFERENCE", "the pool is a share of a total that includes it",
                             cycle=[f"Commissions!E{tr}", f"Commissions!E{tr + 2}"]))
    elif "SUM_OMITS_ROW" in plant:
        ws[f"E{tr}"] = f"=SUM(E{first + 1}:E{last})"
        faults.append(_fault("Commissions", f"E{tr}", "SUM_OMITS_ROW", "total leaves out the first rep"))
    legit = [{"sheet": "Commissions", "cell": f"C{first}:C{last}", "what": "typed sales"},
             {"sheet": "Commissions", "cell": f"F{first}:F{last}", "what": "IFERROR and x100 for a percentage"},
             {"sheet": "Rates", "cell": "B2:B5", "what": "typed rates"}]
    return Book(name, _bytes(wb), faults, legit)


# -- version pairs ----------------------------------------------------------------------------------------------

def pair(rng: random.Random, name: str, year: int) -> Pair:
    s = _budget_spec(rng, name + "-v1", year)
    s.n_actual = max(2, s.n_actual)
    s.extra_sheet = "Old scenario" if rng.random() < 0.5 else None
    before_wb, before_lay = _build_budget(s)
    v1 = Book(f"{name}-v1.xlsx", _bytes(before_wb))
    s2 = BudgetSpec(**{**s.__dict__})
    s2.name = name + "-v1"  # same values
    s2.overrides = {}
    s2.sections = [(sec, list(items)) for sec, items in s.sections]
    sec_i = rng.randrange(len(s2.sections))
    sec, items = s2.sections[sec_i]
    pool = [x for x in SECTIONS[sec] if x not in items]
    new_item = pool[0] if pool else "New line"
    items.insert(rng.randrange(1, len(items)), new_item)
    s2.rates = [round(x * 1.5, 4) for x in s.rates]
    keep = [it for _, its in s.sections for it in its]
    renamed = rng.choice(keep)
    s2.renames = {renamed: renamed + " (all)"}
    changes: list[dict[str, Any]] = []
    first_fc = s.n_actual
    to_value, to_change = rng.sample(keep, 2)
    m1, m2 = rng.randrange(first_fc + 1, 11), rng.randrange(first_fc + 1, 11)
    s2.overrides[(to_value, m1)] = rng.randrange(50, 300) * 100

    def other_rate(ws: Any, r: int, col: int, k: int) -> None:
        ws.cell(r, col, f"={L(col - 1)}{r}*(1+Assumptions!$B${3 + ((k + 1) % len(s2.sections))})")
    s2.overrides[(to_change, m2)] = other_rate
    vf = rng.choice(keep)
    s2.overrides[(vf, 0)] = f"=ROUND({rng.randrange(20, 400) * 100}*1.02,0)"
    s2.extra_sheet = None if s.extra_sheet else "Notes"
    after_wb, lay = _build_budget(s2)
    v2 = Book(f"{name}-v2.xlsx", _bytes(after_wb))
    changes.append({"sheet": "Budget", "cell": lay.cell(to_value, m1), "kind": "FORMULA_TO_VALUE"})
    changes.append({"sheet": "Budget", "cell": lay.cell(to_change, m2), "kind": "FORMULA_CHANGED"})
    changes.append({"sheet": "Budget", "cell": lay.cell(vf, 0), "kind": "VALUE_TO_FORMULA"})
    if s.extra_sheet:
        changes.append({"sheet": s.extra_sheet, "cell": None, "kind": "SHEET_REMOVED"})
    else:
        changes.append({"sheet": "Notes", "cell": None, "kind": "SHEET_ADDED"})
    return Pair(v1, v2, changes, [f"row '{new_item}' inserted in {sec}; formulas below shifted",
                                   "growth rates changed on Assumptions", f"label '{renamed}' reworded"])


ALL_FAULTS = ["INCONSISTENT_FORMULA", "HARDCODED_OVERRIDE", "SUM_OMITS_ROW", "DOUBLE_COUNT", "TEXT_NUMBER_IN_SUM",
              "HARDCODED_PLUG", "EXTERNAL_LINK", "UNKNOWN_NAME", "MISSING_SHEET", "BROKEN_NAME", "CIRCULAR_REFERENCE",
              "REF_ERROR"]


def generate(seed: int) -> tuple[list[Book], list[Pair]]:
    rng = random.Random(seed)

    def plant(p: float) -> set[str]:
        return {k for k in ALL_FAULTS if rng.random() < p}
    books = [
        budget(rng, f"budget-{seed}-a.xlsx", 2026, plant(0.55)),
        budget(rng, f"budget-{seed}-b.xlsx", 2025, plant(0.55)),
        budget(rng, f"budget-{seed}-clean.xlsx", 2026, set()),
        loan(rng, f"loan-{seed}.xlsx", plant(0.6)),
        consolidation(rng, f"consolidation-{seed}.xlsx", plant(0.6)),
        commission(rng, f"commission-{seed}.xlsx", plant(0.6)),
    ]
    pairs = [pair(rng, f"forecast-{seed}-x", 2026), pair(rng, f"forecast-{seed}-y", 2027)]
    return books, pairs
