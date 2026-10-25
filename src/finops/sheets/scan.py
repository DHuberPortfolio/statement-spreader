"""The checks: definite errors, likely risks and low-confidence anomalies, each with cell-level evidence.

How a typed number or an odd formula is told apart from a legitimate input (the mandate's "do not label every
hardcoded value as an error"): a cell is compared with its neighbours only inside a run of formulas that agree
with each other on both sides of it. Input rows, actual columns before forecast columns, opening balances and
full-year columns sit at the edge of a run or outside one, so they are never compared. Inside a run:
- a typed number is a HARDCODED_OVERRIDE, unless the model marks it as an input (its input font colour, or a
  comment explaining it): then it is a DOCUMENTED_OVERRIDE, an anomaly. A typed number whose neighbours across
  the run are typed numbers too is part of an input block and is not reported;
- a different formula is an INCONSISTENT_FORMULA, unless it agrees with the cells across from it (a whole row of
  subtotals cutting through a column of items, a row-specific rate): then it is a PATTERN_BREAK, an anomaly.

Severity follows from what is certain. #REF!, a missing sheet or name, a circular chain and a number stored as text
inside a sum are broken whatever the author meant ("error"). An odd formula or a short total is probably wrong
("risk"). A typed rate inside a formula, INDIRECT, a hidden sheet are worth knowing and often deliberate
("anomaly"); they are listed but not counted in the precision figures.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import deque
from typing import Any

from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter
from pydantic import BaseModel, Field

from finops.core.fingerprint import content_hash

from .config import KINDS, ScanSpec, Severity
from .formula import Ref, parse
from .workbook import _ERRORS, Cell, Sheet, Workbook

ENGINE_VERSION = "sheets-1"
_TEXT_NUMBER = re.compile(r"^\s*[-+]?\(?\s*[$€£]?\s*(\d{1,3}(,\d{3})+|\d+)(\.\d+)?\s*\)?\s*%?\s*$")
_RANGE_ARGS = {"SUM": None, "SUBTOTAL": None, "AGGREGATE": None, "AVERAGE": None, "MIN": None, "MAX": None,
               "PRODUCT": None, "SUMPRODUCT": None, "SUMIF": {2}, "SUMIFS": {0}, "AVERAGEIF": {2}, "AVERAGEIFS": {0}}

_GROUPABLE = {"SUM_OMITS_ROW", "DOUBLE_COUNT", "HARDCODED_PLUG", "EXTERNAL_LINK", "REF_ERROR", "MISSING_SHEET",
              "UNKNOWN_NAME", "CONSTANT_IN_FORMULA", "VOLATILE_REFERENCE", "CACHED_ERROR", "CACHED_NA", "PATTERN_BREAK"}

Node = tuple[str, int, int]
_AGGREGATE = re.compile(r"(SUM|SUBTOTAL|AGGREGATE|SUMIFS?)\(")
_ROUNDING = {"ROUND", "ROUNDUP", "ROUNDDOWN", "MROUND", "CEILING", "FLOOR", "INT", "TRUNC"}


def addr(r: int, c: int) -> str:
    return f"{get_column_letter(c)}{r}"


def node_text(n: Node) -> str:
    return f"{n[0]}!{addr(n[1], n[2])}"


class Finding(BaseModel):
    id: str  # unique in this scan: KIND:Sheet!A1
    key: str  # stable across versions of the workbook (labels, not addresses), for carrying a person's review
    kind: str
    severity: Severity
    title: str
    detail: str
    sheet: str | None = None
    cell: str | None = None
    cells: list[str] = Field(default_factory=list)  # every cell involved (a loop, the omitted rows)
    group: list[str] = Field(default_factory=list)  # more cells with the same problem in the same copied formula
    formula: str | None = None
    value: str | None = None
    expected: str | None = None  # what the neighbours say this cell would be
    row_label: str = ""
    column_label: str = ""
    precedents: list[str] = Field(default_factory=list)
    dependents: int = 0  # formulas that read this cell directly
    downstream: int = 0  # formulas affected through any chain
    feeds: list[str] = Field(default_factory=list)  # end results it flows into
    evidence: dict[str, Any] = Field(default_factory=dict)


# -- labels ------------------------------------------------------------------------------------------------------

def row_label(sh: Sheet, r: int, c: int) -> str:
    for col in sh.rows.get(r, []):
        if col >= c:
            break
        cell = sh.cells[(r, col)]
        if cell.kind == "text" and str(cell.value).strip():
            return str(cell.value).strip()[:80]
    return ""


def column_label(sh: Sheet, r: int, c: int, years: tuple[int, int]) -> str:
    for row in range(r - 1, max(0, r - 60), -1):
        cell = sh.get(row, c)
        if cell is None:
            continue
        if cell.kind == "text" and str(cell.value).strip():
            return str(cell.value).strip()[:40]
        if cell.kind == "date":
            return str(cell.value)[:10]
        if cell.is_number and float(cell.value).is_integer() and years[0] <= cell.value <= years[1]:
            return str(int(cell.value))
    return ""


def _counting(sh: Sheet, cell: Cell) -> bool:
    """Part of a row or column of typed whole numbers counting up by one (0, 1, 2, 3: a period heading)."""
    for dr, dc in ((0, 1), (1, 0)):
        seq = [cell]
        for step in (-1, 1):
            k = 1
            while (n := sh.get(cell.row + step * k * dr, cell.col + step * k * dc)) is not None and n.is_number:
                seq.append(n)
                k += 1
        nums = sorted(float(n.value) for n in seq)
        if len(nums) >= 3 and all(v.is_integer() for v in nums) and all(b - a == 1 for a, b in zip(nums, nums[1:], strict=False)):
            return True
    return False


def _year_like(cell: Cell, years: tuple[int, int]) -> bool:
    return cell.is_number and float(cell.value).is_integer() and years[0] <= cell.value <= years[1]


# -- dependency graph ------------------------------------------------------------------------------------------

class Graph:
    """Who reads whom. Ranges are expanded to the cells that exist in them; past the configured limit the graph is
    marked partial and the findings say their impact counts are incomplete."""

    def __init__(self, wb: Workbook, spec: ScanSpec):
        self.wb = wb
        self.prec: dict[Node, list[Node]] = {}
        self.dep: dict[Node, list[Node]] = {}
        self.partial = False
        self._row_keys = {name: sorted(sh.rows) for name, sh in wb.sheets.items()}
        budget = spec.max_expanded_references
        for name, sh in wb.sheets.items():
            for (r, c), cell in sh.cells.items():
                if cell.kind != "formula" or cell.parsed is None:
                    continue
                me = (name, r, c)
                out: list[Node] = []
                for ref in cell.parsed.refs:
                    for target in self.resolve(ref, name):
                        if budget <= 0:
                            self.partial = True
                            break
                        cells = self.cells_in(*target)
                        budget -= len(cells)
                        out.extend(cells)
                self.prec[me] = out
                for p in out:
                    self.dep.setdefault(p, []).append(me)

    def resolve(self, ref: Ref, own: str) -> list[tuple[str, int, int, int, int]]:
        """(sheet, r1, c1, r2, c2) boxes a reference covers inside this workbook; names are followed once."""
        if ref.external:
            return []
        if ref.kind == "name":
            definition = None
            if ref.sheet:
                definition = self.wb.local_names.get((ref.sheet.lower(), (ref.name or "").lower()))
            definition = definition or self.wb.local_names.get((own.lower(), (ref.name or "").lower())) \
                or self.wb.names.get((ref.name or "").lower())
            if not definition:
                return []
            p = parse(definition)
            return [b for r in p.refs if r.kind in ("cell", "range") for b in self.resolve(r, own)]
        if not ref.is_area:
            return []
        names = [own] if ref.sheet is None else [ref.sheet]
        if ref.sheets3d:
            order = [s.lower() for s in self.wb.sheet_order]
            a, b = ref.sheets3d[0].lower(), ref.sheets3d[1].lower()
            if a in order and b in order:
                i, j = sorted((order.index(a), order.index(b)))
                names = self.wb.sheet_order[i:j + 1]
        out = []
        for n in names:
            sh = self.wb.sheet(n)
            if sh is None:
                continue
            r1, c1, r2, c2 = ref.box(sh.max_row, sh.max_col)
            out.append((sh.name, r1, c1, r2, c2))
        return out

    def cells_in(self, sheet: str, r1: int, c1: int, r2: int, c2: int) -> list[Node]:
        sh = self.wb.sheets[sheet]
        keys = self._row_keys[sheet]
        out: list[Node] = []
        for r in keys[bisect_left(keys, r1):bisect_right(keys, r2)]:
            cols = sh.rows[r]
            for c in cols[bisect_left(cols, c1):bisect_right(cols, c2)]:
                out.append((sheet, r, c))
        return out

    def downstream(self, start: Node, limit: int = 20000) -> tuple[int, list[Node]]:
        seen: set[Node] = set()
        ends: list[Node] = []
        q = deque(self.dep.get(start, []))
        while q and len(seen) < limit:
            n = q.popleft()
            if n in seen:
                continue
            seen.add(n)
            nxt = self.dep.get(n, [])
            if not nxt:
                ends.append(n)
            q.extend(nxt)
        return len(seen), ends

    def cycles(self) -> list[list[Node]]:
        """Strongly connected groups of formulas (Tarjan, iterative), including a formula that reads itself."""
        index: dict[Node, int] = {}
        low: dict[Node, int] = {}
        on: set[Node] = set()
        stack: list[Node] = []
        out: list[list[Node]] = []
        counter = 0
        formula = set(self.prec)
        for root in sorted(formula):
            if root in index:
                continue
            work: list[tuple[Node, int]] = [(root, 0)]
            while work:
                v, i = work.pop()
                if i == 0:
                    index[v] = low[v] = counter
                    counter += 1
                    stack.append(v)
                    on.add(v)
                succ = [w for w in self.prec.get(v, []) if w in formula]
                recurse = False
                for j in range(i, len(succ)):
                    w = succ[j]
                    if w not in index:
                        work.append((v, j + 1))
                        work.append((w, 0))
                        recurse = True
                        break
                    if w in on:
                        low[v] = min(low[v], index[w])
                if recurse:
                    continue
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1 or v in self.prec.get(v, []):
                        out.append(sorted(comp))
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
        return out


# -- the scan ---------------------------------------------------------------------------------------------------

class Scanner:
    def __init__(self, wb: Workbook, spec: ScanSpec):
        self.wb, self.spec = wb, spec
        self.graph = Graph(wb, spec)
        self.found: dict[str, Finding] = {}
        self.inputs = {c.upper() for c in spec.input_font_colors}
        self._cover_memo: dict[Node, frozenset[Node]] = {}

    def add(self, kind: str, sheet: str | None, r: int | None, c: int | None, detail: str, **kw: Any) -> None:
        sev = kw.pop("severity", None) or self.spec.severity_of(kind)
        cell = addr(r, c) if r and c else kw.pop("cell", None)
        fid = f"{kind}:{sheet or ''}!{cell or ''}"
        if fid in self.found:
            return
        sh = self.wb.sheets.get(sheet) if sheet else None
        rl = row_label(sh, r, c) if sh and r and c else ""
        cl = column_label(sh, r, c, self.spec.year_range) if sh and r and c else ""
        here = sh.get(r, c) if sh and r and c else None
        formula = here.value if here is not None and here.kind == "formula" else None
        value = None if here is None or here.kind == "formula" else str(here.value)
        if here is not None and here.kind == "formula" and here.cached is not None:
            value = str(here.cached)
        stable = [kind, sheet, rl, cl, here.sig if here is not None and here.kind == "formula" else (here.kind if here else "")]
        if not (rl or cl):
            stable.append(cell)
        f = Finding(id=fid, key=content_hash(stable, 16), kind=kind, severity=sev, title=KINDS[kind][1], detail=detail,
                    sheet=sheet, cell=cell, formula=formula, value=value, row_label=rl, column_label=cl, **kw)
        if sh and r and c:
            node = (sh.name, r, c)
            if here is not None and here.kind == "formula" and here.parsed is not None:
                f.precedents = f.precedents or [x.raw for x in here.parsed.refs][:12]
            f.dependents = len(self.graph.dep.get(node, []))
            f.downstream, ends = self.graph.downstream(node)
            ends.sort(key=lambda n: (n[0] == sh.name, n))
            f.feeds = f.feeds or [node_text(n) for n in ends[:3]]
        self.found[fid] = f

    def run(self) -> list[Finding]:
        self.references()
        self.names()
        self.runs()
        self.totals()
        self.text_numbers()
        self.constants()
        self.circular()
        self.cached_errors()
        self.hidden()
        order = {"error": 0, "risk": 1, "anomaly": 2}
        sheet_pos = {n: i for i, n in enumerate(self.wb.sheet_order)}
        return sorted(self._grouped(), key=lambda f: (order[f.severity], sheet_pos.get(f.sheet or "", -1), f.kind, f.id))

    def _grouped(self) -> list[Finding]:
        """One finding for one mistake: a total row whose every column omits the same row is one problem, copied
        across. Findings of the same kind on adjacent cells holding the same (relative) formula are merged; the
        first cell carries it, the others are listed in `group`."""
        keep: list[Finding] = []
        buckets: dict[tuple[str, str, str], list[tuple[int, int, Finding]]] = {}
        for f in self.found.values():
            sh = self.wb.sheets.get(f.sheet or "")
            cell = None
            if f.kind in _GROUPABLE and sh is not None and f.cell and not f.cell.startswith("name:"):
                col, row = coordinate_from_string(f.cell)
                cell = sh.get(row, column_index_from_string(col))
            if cell is None or cell.kind != "formula" or cell.sig is None:
                keep.append(f)
                continue
            buckets.setdefault((f.kind, f.sheet or "", cell.sig), []).append((cell.row, cell.col, f))
        for items in buckets.values():
            pos = {(r, c): f for r, c, f in items}
            seen: set[tuple[int, int]] = set()
            for start in sorted(pos):
                if start in seen:
                    continue
                comp, stack = [], [start]
                while stack:
                    p = stack.pop()
                    if p in seen or p not in pos:
                        continue
                    seen.add(p)
                    comp.append(p)
                    stack.extend([(p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)])
                comp.sort()
                head = pos[comp[0]]
                if len(comp) > 1:
                    head.group = [addr(*p) for p in comp[1:]]
                    head.cells = sorted({c for p in comp for c in pos[p].cells}, key=lambda a: (len(a), a))[:50]
                    head.detail += f" The same formula repeats in {len(comp) - 1} more cell(s): {', '.join(head.group[:6])}" \
                                   f"{' ...' if len(comp) > 7 else ''}."
                keep.append(head)
        return keep

    # -- references: #REF!, missing sheets, unknown names, other workbooks, volatile functions

    def references(self) -> None:
        wb = self.wb
        for name, sh in wb.sheets.items():
            for (r, c), cell in sh.cells.items():
                if cell.kind != "formula" or cell.parsed is None:
                    continue
                p = cell.parsed
                if not p.ok:
                    self.add("UNPARSEABLE_FORMULA", name, r, c, f"{cell.value} could not be read; it was not checked.")
                    continue
                if p.has_ref_error:
                    self.add("REF_ERROR", name, r, c, f"{cell.value} contains #REF!: it points at something that was "
                             "deleted, so it cannot calculate.")
                for ref in p.refs:
                    if ref.external:
                        target = wb.external_links.get(ref.external, ref.external)
                        self.add("EXTERNAL_LINK", name, r, c, f"Reads {ref.raw} in another workbook ({target}). The value "
                                 "depends on that file being present, current and unchanged.",
                                 evidence={"target": target})
                        continue
                    for s in ([ref.sheet] if ref.sheet else []) + (list(ref.sheets3d) if ref.sheets3d else []):
                        if ref.sheets3d and s == ref.sheet:
                            continue
                        if wb.sheet(s) is None:
                            self.add("MISSING_SHEET", name, r, c, f"{cell.value} refers to sheet '{s}', which is not in "
                                     "this workbook.", evidence={"sheet": s})
                    if ref.kind == "name" and not self._name_known(ref, name):
                        self.add("UNKNOWN_NAME", name, r, c, f"{cell.value} uses the name '{ref.name}', which is not "
                                 "defined in this workbook (Excel shows #NAME?).", evidence={"name": ref.name})
                    if ref.kind == "table" and (ref.name or "").lower() not in wb.tables and not self._name_known(ref, name):
                        self.add("UNKNOWN_NAME", name, r, c, f"{cell.value} uses the table '{ref.name}', which is not in "
                                 "this workbook.", evidence={"name": ref.name})
                vol = sorted(set(p.functions) & {f.upper() for f in self.spec.volatile_functions})
                if vol:
                    self.add("VOLATILE_REFERENCE", name, r, c, f"Uses {', '.join(vol)}: what it reads is decided while "
                             "calculating, so its dependencies are not traced.")

    def _name_known(self, ref: Ref, own: str) -> bool:
        n = (ref.name or "").lower()
        if ref.sheet:
            return (ref.sheet.lower(), n) in self.wb.local_names or n in self.wb.names
        return (own.lower(), n) in self.wb.local_names or n in self.wb.names or n in self.wb.tables

    def names(self) -> None:
        for low, definition in sorted(self.wb.names.items()):
            display = self.wb.name_display.get(low, low)
            if display.lower().startswith("_xlnm."):
                continue
            bad = "#REF!" in definition.upper()
            missing = []
            if not bad:
                p = parse(definition)
                for ref in p.refs:
                    if ref.sheet and not ref.external and self.wb.sheet(ref.sheet) is None:
                        missing.append(ref.sheet)
            if bad or missing:
                why = "points at #REF!" if bad else f"points at sheet '{missing[0]}', which is not in this workbook"
                users = [node_text((s, r, c)) for s, sh in self.wb.sheets.items() for (r, c), cell in sh.cells.items()
                         if cell.kind == "formula" and cell.parsed is not None
                         and any(x.kind == "name" and (x.name or "").lower() == low for x in cell.parsed.refs)]
                self.add("BROKEN_NAME", None, None, None, f"The defined name '{display}' ({definition}) {why}."
                         + (f" Used by {len(users)} formula(s)." if users else " No formula uses it."),
                         cell=f"name:{display}", cells=users[:20], evidence={"definition": definition})

    # -- runs: inconsistent formulas and typed-over values

    def _lines(self, sh: Sheet) -> list[tuple[str, list[Cell]]]:
        """Unbroken sequences of formulas and typed numbers, along each row and down each column."""
        out: list[tuple[str, list[Cell]]] = []
        for r, cols in sh.rows.items():
            seg: list[Cell] = []
            for c in cols:
                cell = sh.cells[(r, c)]
                if cell.kind in ("formula", "number") and (not seg or seg[-1].col == c - 1):
                    seg.append(cell)
                else:
                    if len(seg) >= self.spec.min_run:
                        out.append(("row", seg))
                    seg = [cell] if cell.kind in ("formula", "number") else []
            if len(seg) >= self.spec.min_run:
                out.append(("row", seg))
        by_col: dict[int, list[Cell]] = {}
        for (_r, c), cell in sorted(sh.cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            by_col.setdefault(c, []).append(cell)
        for cells in by_col.values():
            seg = []
            for cell in cells:
                if cell.kind in ("formula", "number") and (not seg or seg[-1].row == cell.row - 1):
                    seg.append(cell)
                else:
                    if len(seg) >= self.spec.min_run:
                        out.append(("column", seg))
                    seg = [cell] if cell.kind in ("formula", "number") else []
            if len(seg) >= self.spec.min_run:
                out.append(("column", seg))
        return out

    def _structural(self, sh: Sheet, lines: list[tuple[str, list[Cell]]]) -> dict[tuple[str, int], int]:
        """How many lines break their pattern at the same column (along rows) or row (down columns). A half-year
        column between quarters, or interest and tax rows between subtotal rows, breaks every line it crosses:
        that is how the model is built, not a mistake in one cell."""
        breaks: dict[tuple[str, int], int] = {}
        crossings: dict[tuple[str, int], int] = {}
        for direction, seg in lines:
            for a, x, b in zip(seg, seg[1:], seg[2:], strict=False):
                key = (direction, x.col if direction == "row" else x.row)
                crossings[key] = crossings.get(key, 0) + 1
                if a.sig == b.sig and x.sig != a.sig:
                    breaks[key] = breaks.get(key, 0) + 1
        # Structural: most of the lines crossing it break there. Two or three unrelated mistakes that happen to share
        # a column break only a few of the lines crossing it.
        return {k: n for k, n in breaks.items() if n >= 2 and 2 * n > crossings[k]}

    def runs(self) -> None:
        for sh in self.wb.sheets.values():
            lines = self._lines(sh)
            structural = self._structural(sh, lines)
            for direction, seg in lines:
                groups: list[list[Cell]] = []
                for cell in seg:
                    if groups and groups[-1][0].sig == cell.sig:
                        groups[-1].append(cell)
                    else:
                        groups.append([cell])
                for i, left in enumerate(groups):
                    s = left[0].sig
                    if s == "#" or s is None:
                        continue
                    odd: list[Cell] = []
                    for j in range(i + 1, len(groups)):
                        g = groups[j]
                        if g[0].sig == s:
                            # The weakest evidence, one agreeing cell on each side, counts only for a single odd cell
                            # between two copies of a formula that is not a total: two separate totals of the same
                            # shape (a subtotal and a grand total three rows apart) are not a copied run.
                            thin = len(left) == 1 and len(g) == 1
                            if thin and (len(odd) > 1 or _AGGREGATE.search(s or "")):
                                break
                            if odd and len(left) + len(g) >= self.spec.min_run:
                                where = [(direction, x.col if direction == "row" else x.row) for x in odd]
                                lines_at = max(structural.get(w, 0) for w in where)
                                for x in odd:
                                    self._odd(sh, x, left[-1], direction, len(left) + len(g), lines_at)
                            break
                        odd.extend(g)
                        if len(odd) > self.spec.max_odd_group:
                            break

    def _odd(self, sh: Sheet, x: Cell, neighbour: Cell, direction: str, agreeing: int, structural: int = 0) -> None:
        """x breaks a run of `agreeing` identical formulas (neighbour is one of them) along `direction`. `structural`:
        how many lines break at this column or row (0 when it is only this one, or two)."""
        across = [sh.get(x.row - 1, x.col), sh.get(x.row + 1, x.col)] if direction == "row" else \
            [sh.get(x.row, x.col - 1), sh.get(x.row, x.col + 1)]
        expected = None
        try:
            expected = Translator(str(neighbour.value), origin=addr(neighbour.row, neighbour.col)).translate_formula(addr(x.row, x.col))
        except Exception:  # noqa: BLE001 - the translation is only a hint for the reader
            expected = None
        ev = {"direction": direction, "agreeing_cells": agreeing, "neighbour": addr(neighbour.row, neighbour.col),
              "neighbour_formula": neighbour.value}
        where = "this row" if direction == "row" else "this column"
        if x.kind == "number":
            if all(a is not None and a.kind == "number" for a in across) or structural:
                return  # part of a line of typed inputs (actuals, an input row) or of a structural row or column
            documented = (x.font_color or "").upper() in self.inputs or (self.spec.comment_documents_override and x.comment)
            if documented:
                how = "a cell comment" if x.comment else "the input colour"
                self.add("DOCUMENTED_OVERRIDE", sh.name, x.row, x.col, f"Typed {x.value} where {agreeing} cells along {where} "
                         f"calculate ({neighbour.value} next to it); documented with {how}.", expected=expected,
                         evidence={**ev, "comment": x.comment or ""})
            else:
                self.add("HARDCODED_OVERRIDE", sh.name, x.row, x.col, f"Typed {x.value} where {agreeing} cells along {where} "
                         f"calculate ({addr(neighbour.row, neighbour.col)}: {neighbour.value}). If the formula was "
                         "overwritten, the value no longer updates.", expected=expected, evidence=ev)
            return
        if x.kind != "formula":
            return
        if structural:
            kind_of = "column" if direction == "row" else "row"
            self.add("PATTERN_BREAK", sh.name, x.row, x.col, f"{x.value} differs from {agreeing} matching formulas along "
                     f"{where}, but this {kind_of} breaks the pattern in {structural} lines: a structural {kind_of} (a "
                     "half-year or total column, rows between subtotals), not a single odd cell.", expected=expected, evidence=ev)
            return
        if any(a is not None and a.kind == "formula" and a.sig == x.sig for a in across):
            self.add("PATTERN_BREAK", sh.name, x.row, x.col, f"{x.value} differs from {agreeing} matching formulas along "
                     f"{where}, but the cells across from it use the same formula: probably a deliberate row or column.",
                     expected=expected, evidence=ev)
            return
        self.add("INCONSISTENT_FORMULA", sh.name, x.row, x.col, f"{x.value} differs from {agreeing} matching formulas along "
                 f"{where} ({addr(neighbour.row, neighbour.col)}: {neighbour.value}).", expected=expected, evidence=ev)

    # -- totals: short ranges and double counting

    def _is_total(self, sh: Sheet, cell: Cell) -> bool:
        if cell.kind != "formula" or cell.parsed is None:
            return False
        if {"SUM", "SUBTOTAL", "AGGREGATE"} & set(cell.parsed.functions):
            return True
        return "total" in row_label(sh, cell.row, cell.col).lower()

    def _belongs(self, sh: Sheet, cand: Cell | None, sample: Cell | None) -> bool:
        """Could cand be one more item of the block that sample is in?"""
        if cand is None or cand.kind not in ("number", "formula"):
            return False
        if cand.kind == "formula" and sample is not None and cand.sig == sample.sig:
            return True  # the same formula as the items (row totals in a full-year column, say)
        if self._is_total(sh, cand):
            return False
        if cand.is_number and _year_like(cand, self.spec.year_range) and not (sample and _year_like(sample, self.spec.year_range)):
            return False
        if cand.is_number and _counting(sh, cand):
            return False
        return sample is None or ("%" in cand.number_format) == ("%" in sample.number_format)

    def totals(self) -> None:
        for name, sh in self.wb.sheets.items():
            for cell in sh.cells.values():
                if cell.kind != "formula" or cell.parsed is None or not cell.parsed.ok:
                    continue
                tr = cell.parsed.total_range
                if tr is not None and (tr.sheet is None or tr.sheet.lower() == name.lower()):
                    self._short(sh, cell, tr)
                self._double(sh, cell)

    def _short(self, sh: Sheet, x: Cell, rng: Ref) -> None:
        assert rng.r1 and rng.c1 and rng.r2 and rng.c2
        if rng.c1 == rng.c2 == x.col and not (rng.r1 <= x.row <= rng.r2):
            line = [(rr, x.col) for rr in range(rng.r1, rng.r2 + 1)]
            if x.row > rng.r2:
                near, far = [(rr, x.col) for rr in range(rng.r2 + 1, x.row)], (rng.r1 - 1, x.col)
            else:
                near, far = [(rr, x.col) for rr in range(x.row + 1, rng.r1)], (rng.r2 + 1, x.col)
        elif rng.r1 == rng.r2 == x.row and not (rng.c1 <= x.col <= rng.c2):
            line = [(x.row, cc) for cc in range(rng.c1, rng.c2 + 1)]
            if x.col > rng.c2:
                near, far = [(x.row, cc) for cc in range(rng.c2 + 1, x.col)], (x.row, rng.c1 - 1)
            else:
                near, far = [(x.row, cc) for cc in range(x.col + 1, rng.c1)], (x.row, rng.c2 + 1)
        else:
            return
        inside = [sh.get(*p) for p in line]
        items = [i for i in inside if i is not None and i.kind in ("number", "formula")]
        if len(items) < 2:
            return
        sample = items[-1] if far[0] < x.row or far[1] < x.col else items[0]
        inside_nodes = [(sh.name, i.row, i.col) for i in items]
        already = set().union(*(self._covered(n) for n in inside_nodes))  # what the range's own subtotals include
        omitted = [p for p in near if (sh.name, *p) not in already and self._belongs(sh, sh.get(*p), sample)]
        far_cell = sh.get(*far) if far[0] >= 1 and far[1] >= 1 else None
        edge = items[0] if (far[0] < line[0][0] or far[1] < line[0][1]) else items[-1]
        if far_cell is not None and (sh.name, *far) not in already and self._belongs(sh, far_cell, edge)                 and far_cell.kind == edge.kind:
            if rng.c1 == rng.c2 and not row_label(sh, far[0], far[1]):
                pass  # a number with no label beside it is rarely an item of the block
            else:
                omitted.append(far)
        if omitted:
            cells = [addr(*p) for p in omitted]
            these = f"{cells[0]}, next to the range, holds a number of the same block and is" if len(cells) == 1 else                 f"{', '.join(cells)}, next to the range, hold numbers of the same block and are"
            self.add("SUM_OMITS_ROW", sh.name, x.row, x.col, f"{x.value} adds {rng.raw}, but {these} left out.", cells=cells,
                     evidence={"range": rng.raw, "omitted": cells})

    def _covered(self, n: Node, depth: int = 0, memo: dict[Node, frozenset[Node]] | None = None) -> frozenset[Node]:
        """The cells an amount is made of: itself, plus, if it is a sum of other cells (only SUM and +), everything
        those are made of. A formula that does more than add (a growth formula, a price times a quantity) is an
        amount of its own, so shared inputs such as a rate never make two amounts overlap."""
        memo = self._cover_memo
        if n in memo:
            return memo[n]
        cell = self.wb.sheets[n[0]].cells.get((n[1], n[2]))
        out = {n}
        prec = self.graph.prec.get(n, [])
        # A formula that only points at one cell (=B6, a link) is a copy of that amount, not a sum of others.
        if depth < 12 and cell is not None and cell.kind == "formula" and cell.parsed is not None and cell.parsed.only_additive                 and len(set(prec)) >= 2:
            memo[n] = frozenset(out)  # guards against loops
            for p in prec:
                out |= self._covered(p, depth + 1)
                if len(out) > 20000:
                    break
        memo[n] = frozenset(out)
        return memo[n]

    def _double(self, sh: Sheet, x: Cell) -> None:
        """A sum whose parts overlap: a range that takes in a subtotal and its items, or row totals added to the
        column totals of the same block."""
        p = x.parsed
        assert p is not None
        if not p.only_additive or {"SUBTOTAL", "AGGREGATE"} & set(p.functions):
            return  # SUBTOTAL skips nested SUBTOTALs by design
        me = (sh.name, x.row, x.col)
        parts = [n for n in dict.fromkeys(self.graph.prec.get(me, [])) if n != me]
        if len(parts) < 2 or len(parts) > 5000:
            return
        owner: dict[Node, Node] = {}
        twice: dict[Node, set[Node]] = {}
        for part in parts:
            for leaf in self._covered(part):
                first = owner.setdefault(leaf, part)
                if first != part:
                    twice.setdefault(first, set()).add(part)
        if not twice:
            return
        # Name the parts that are sums of other parts (the subtotals), not every item under them.
        subtotals = sorted({a for a, bs in twice.items() for a in [a, *bs]
                            if len(self._covered(a)) > 1}, key=lambda n: (n[0], n[2], n[1]))
        names = [addr(n[1], n[2]) if n[0] == sh.name else node_text(n) for n in subtotals][:8]
        self.add("DOUBLE_COUNT", sh.name, x.row, x.col, f"{x.value} adds amounts twice: "
                 f"{', '.join(names)} already include other cells this formula also adds.",
                 cells=names, evidence={"subtotals": names})

    # -- numbers stored as text inside a sum

    def text_numbers(self) -> None:
        skipped: dict[Node, list[str]] = {}
        for name, sh in self.wb.sheets.items():
            for (r, c), cell in sh.cells.items():
                if cell.kind != "formula" or cell.parsed is None:
                    continue
                for ref, (fn, idx) in zip(cell.parsed.refs, cell.parsed.arg_of, strict=False):
                    if fn not in _RANGE_ARGS or not ref.is_area and ref.kind != "name":
                        continue
                    allowed = _RANGE_ARGS[fn]
                    if (allowed is not None and idx not in allowed) or (fn in ("SUBTOTAL", "AGGREGATE") and idx == 0):
                        continue
                    for box in self.graph.resolve(ref, name):
                        target = self.wb.sheets[box[0]]
                        for n in self.graph.cells_in(*box):
                            t = target.cells[(n[1], n[2])]
                            if t.kind == "text" and _TEXT_NUMBER.match(str(t.value)) and not (
                                    re.fullmatch(r"\d{4}", str(t.value).strip())
                                    and self.spec.year_range[0] <= int(str(t.value).strip()) <= self.spec.year_range[1]):
                                skipped.setdefault(n, []).append(node_text((name, r, c)))
        for n, totals in sorted(skipped.items()):
            v = self.wb.sheets[n[0]].cells[(n[1], n[2])].value
            self.add("TEXT_NUMBER_IN_SUM", n[0], n[1], n[2], f"'{v}' is text that looks like a number; "
                     f"{', '.join(totals[:3])}{' and others' if len(totals) > 3 else ''} skip it, so the total is short by "
                     "that amount.", feeds=totals[:3], evidence={"totals": totals[:10]})

    # -- typed numbers inside formulas

    def constants(self) -> None:
        addends = set(self.spec.allowed_addends)
        factors = set(self.spec.allowed_multipliers)
        for name, sh in self.wb.sheets.items():
            for (r, c), cell in sh.cells.items():
                if cell.kind != "formula" or cell.parsed is None or not cell.parsed.ok:
                    continue
                p = cell.parsed
                if not any(ref.is_area or ref.kind == "name" for ref in p.refs):
                    continue
                rounding = bool(_ROUNDING & set(p.functions))
                plugs = [lit for lit in p.literals if lit.additive_partner and lit.value not in addends and lit.in_function is None
                         and not (rounding and abs(lit.value) < 1)]  # =ROUND(x,0)-0.01: a price ending in .99
                if plugs and not self._dates_involved(sh, cell):
                    nums = ", ".join(lit.text for lit in plugs)
                    if cell.comment and self.spec.comment_documents_override:
                        self.add("DOCUMENTED_OVERRIDE", name, r, c, f"{cell.value} adds a typed {nums}; explained in a cell "
                                 "comment.", evidence={"constants": nums, "comment": cell.comment})
                    else:
                        self.add("HARDCODED_PLUG", name, r, c, f"{cell.value} adds or subtracts a typed {nums}. A plug like "
                                 "this hides a difference instead of explaining it, and does not update.",
                                 evidence={"constants": nums})
                    continue
                odd = [lit for lit in p.literals if lit.in_function is None and not lit.additive_partner
                       and lit.value not in factors and lit.value not in addends]
                if odd:
                    nums = ", ".join(lit.text for lit in odd)
                    self.add("CONSTANT_IN_FORMULA", name, r, c, f"{cell.value} contains the typed number(s) {nums}. If it is "
                             "an assumption (a rate, a price), a labelled input cell is easier to check and change.",
                             evidence={"constants": nums})

    def _dates_involved(self, sh: Sheet, cell: Cell) -> bool:
        assert cell.parsed is not None
        for ref in cell.parsed.refs:
            if ref.kind != "cell":
                continue
            target = self.wb.sheet(ref.sheet) if ref.sheet else sh
            t = target.get(ref.r1 or 0, ref.c1 or 0) if target else None
            if t is not None and (t.kind == "date" or any(k in t.number_format.lower() for k in ("yy", "mmm", "dd"))):
                return True
            if t is not None and t.kind == "formula" and t.parsed is not None and {"DATE", "EDATE", "EOMONTH", "TODAY"} & set(t.parsed.functions):
                return True
        return False

    # -- loops, saved error values, hidden sheets

    def circular(self) -> None:
        for comp in self.graph.cycles():
            first = comp[0]
            cells = [node_text(n) for n in comp]
            note = (" Iterative calculation is switched on in this workbook, so the loop may be deliberate (interest on an "
                    "average balance, for example); check that it converges.") if self.wb.iterative else ""
            self.add("CIRCULAR_REFERENCE", first[0], first[1], first[2],
                     f"{len(comp)} cell(s) depend on themselves: {', '.join(cells[:8])}{' ...' if len(cells) > 8 else ''}.{note}",
                     severity="risk" if self.wb.iterative else None, cells=cells[:50], evidence={"cycle": cells[:200]})

    def cached_errors(self) -> None:
        if not self.wb.has_cached_values:
            return
        for name, sh in self.wb.sheets.items():
            for (r, c), cell in sh.cells.items():
                if cell.kind != "formula" or not isinstance(cell.cached, str) or cell.cached not in _ERRORS:
                    continue
                if cell.parsed is not None and cell.parsed.has_ref_error:
                    continue
                me = (name, r, c)
                upstream = [n for n in self.graph.prec.get(me, []) if isinstance(self._cached(n), str) and self._cached(n) in _ERRORS]
                if upstream:
                    continue  # the error comes from a precedent, reported there
                kind = "CACHED_NA" if cell.cached == "#N/A" else "CACHED_ERROR"
                n, _ = self.graph.downstream(me)
                self.add(kind, name, r, c, f"{cell.value} shows {cell.cached} (as last saved by Excel); "
                         f"{n} formula(s) downstream depend on it.", evidence={"error": cell.cached})

    def _cached(self, n: Node) -> Any:
        cell = self.wb.sheets[n[0]].cells.get((n[1], n[2]))
        return cell.cached if cell is not None and cell.kind == "formula" else None

    def hidden(self) -> None:
        for name, sh in self.wb.sheets.items():
            if sh.state == "visible":
                continue
            readers = sorted({node_text(d) for n in self.graph.dep for d in self.graph.dep[n]
                              if n[0] == name and self.wb.sheets[d[0]].state == "visible"})
            if readers:
                self.add("HIDDEN_SHEET", name, None, None, f"Sheet '{name}' is {sh.state}, and {len(readers)} visible "
                         "formula(s) read it.", cell=None, cells=readers[:20])


def scan_workbook(wb: Workbook, spec: ScanSpec) -> tuple[list[Finding], list[str]]:
    s = Scanner(wb, spec)
    findings = s.run()
    notes = []
    if wb.formula_count and not wb.has_cached_values:
        notes.append("The file holds no calculated values (it was written by a program, or saved without calculating): "
                     "checks of the values Excel shows were skipped.")
    if wb.macros:
        notes.append("The workbook contains macros. They were not run or inspected.")
    if wb.iterative:
        notes.append("Iterative calculation is on, so circular references are reported as risks rather than errors.")
    if s.graph.partial:
        notes.append("The workbook has more references than the tracing limit; dependent counts are incomplete.")
    if wb.external_links:
        notes.append(f"Links to {len(wb.external_links)} other workbook(s): {', '.join(sorted(set(wb.external_links.values())))[:300]}.")
    return findings, notes
