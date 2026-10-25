"""Comparing two versions of a workbook: which formulas changed in meaning, not which addresses moved.

Inserting a row shifts every formula below it (`=SUM(C5:C12)` becomes `=SUM(C5:C13)`), and a cell-by-cell
comparison would report all of them. So rows and columns are first aligned between the versions, the way a text
diff aligns lines: by their labels where they have them, by their shape where they do not. A formula then counts
as changed only if it differs after its old references are moved to where those rows and columns now are. A range
that grew to take in rows inserted inside or at the edge of it has not changed meaning.

Material (shown as findings): a formula's logic changed, a formula was replaced by a typed number or removed, a
typed number became a formula, a sheet was added or removed. Not material (counted, not listed one by one): typed
inputs that changed value, rows or columns added or removed, labels reworded.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from .formula import Ref
from .scan import addr, column_label, row_label
from .workbook import Cell, Sheet, Workbook

MATERIAL = {"FORMULA_CHANGED", "FORMULA_TO_VALUE", "FORMULA_REMOVED", "VALUE_TO_FORMULA", "SHEET_ADDED", "SHEET_REMOVED"}


class Change(BaseModel):
    kind: str
    material: bool
    sheet: str
    cell: str | None = None  # address in the newer version (the older one for removals)
    before_cell: str | None = None
    before: str | None = None
    after: str | None = None
    row_label: str = ""
    column_label: str = ""
    detail: str = ""


class Comparison(BaseModel):
    changes: list[Change] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


def _key(sh: Sheet, cells: list[Cell], label: str) -> tuple[Any, ...]:
    if label:
        return ("L", label.lower().strip())
    return ("S",) + tuple((c.sig if c.kind == "formula" else c.kind) for c in cells[:24])


def _row_keys(sh: Sheet) -> tuple[list[int], list[tuple[Any, ...]], list[str]]:
    rows = list(range(1, sh.max_row + 1))
    keys, labels = [], []
    for r in rows:
        cells = [sh.cells[(r, col)] for col in sh.rows.get(r, [])]
        label = next((str(c.value).strip() for c in cells if c.kind == "text" and str(c.value).strip()), "")
        keys.append(_key(sh, cells, label) if cells else ("B",))
        labels.append(label)
    return rows, keys, labels


def _col_keys(sh: Sheet) -> tuple[list[int], list[tuple[Any, ...]], list[str]]:
    by_col: dict[int, list[Cell]] = {}
    for (_r, c), cell in sorted(sh.cells.items()):
        by_col.setdefault(c, []).append(cell)
    cols = list(range(1, sh.max_col + 1))
    keys, labels = [], []
    for c in cols:
        cells = by_col.get(c, [])
        label = next((str(x.value).strip() for x in cells[:12] if x.kind in ("text", "date") and str(x.value).strip()), "")
        if not label:  # a typed year heading
            label = next((str(int(x.value)) for x in cells[:6] if x.is_number and float(x.value).is_integer()
                          and 1900 <= x.value <= 2200), "")
        keys.append(_key(sh, cells, label) if cells else ("B",))
        labels.append(label)
    return cols, keys, labels


def align(a: list[int], ka: list[Any], la: list[str], b: list[int], kb: list[Any], lb: list[str]) -> dict[int, int]:
    """Old index -> new index, for rows (or columns) that are the same line in both versions."""
    out: dict[int, int] = {}
    sm = SequenceMatcher(None, ka, kb, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[a[i1 + k]] = b[j1 + k]
        elif tag == "replace":
            # Reworded labels or edited lines: pair them in order where they still look alike.
            j = j1
            for i in range(i1, i2):
                for jj in range(j, j2):
                    same_shape = ka[i][0] != "L" and ka[i] == kb[jj]
                    similar = bool(la[i] and lb[jj] and fuzz.ratio(la[i].lower(), lb[jj].lower()) >= 75)
                    if same_shape or similar or (i2 - i1 == j2 - j1 and jj - j1 == i - i1 and (ka[i][0] == kb[jj][0])):
                        out[a[i]] = b[jj]
                        j = jj + 1
                        break
    return out


class _SheetMap:
    def __init__(self, old: Sheet, new: Sheet):
        ra, rka, rla = _row_keys(old)
        rb, rkb, rlb = _row_keys(new)
        ca, cka, cla = _col_keys(old)
        cb, ckb, clb = _col_keys(new)
        self.rows = align(ra, rka, rla, rb, rkb, rlb)
        self.cols = align(ca, cka, cla, cb, ckb, clb)
        self.new_rows = set(rb) - set(self.rows.values())
        self.new_cols = set(cb) - set(self.cols.values())
        self.old_rows_gone = set(ra) - set(self.rows)
        self.old_cols_gone = set(ca) - set(self.cols)
        self.old, self.new = old, new


def _map_ref(ref: Ref, own_old: str, maps: dict[str, _SheetMap], renames: dict[str, str]) -> tuple[Any, ...]:
    if ref.kind not in ("cell", "range") or ref.external or ref.sheets3d:
        return ("raw", ref.raw.upper())
    sheet = ref.sheet or own_old
    m = next((v for k, v in maps.items() if k.lower() == sheet.lower()), None)
    if m is None:
        return ("raw", ref.raw.upper())

    def mv(table: dict[int, int], v: int | None) -> int | None | str:
        if v is None:
            return None
        return table.get(v, "gone")

    return (renames.get(sheet, sheet).lower() if ref.sheet else "", ref.kind, mv(m.rows, ref.r1), mv(m.cols, ref.c1),
            mv(m.rows, ref.r2), mv(m.cols, ref.c2))


def _new_ref(ref: Ref, own_new: str) -> tuple[Any, ...]:
    if ref.kind not in ("cell", "range") or ref.external or ref.sheets3d:
        return ("raw", ref.raw.upper())
    return ((ref.sheet or "").lower() if ref.sheet else "", ref.kind, ref.r1, ref.c1, ref.r2, ref.c2)


def _grew_into_new(old: tuple[Any, ...], new: tuple[Any, ...], m: _SheetMap | None) -> bool:
    """The new range is the old one, widened only by rows or columns that did not exist before."""
    if m is None or old[0] != new[0] or old[1] != "range" or new[1] != "range" or "gone" in old:
        return False
    _, _, r1, c1, r2, c2 = old
    _, _, n1, d1, n2, d2 = new
    if None in (r1, r2, n1, n2) or None in (c1, c2, d1, d2):
        return False
    if not (n1 <= r1 and n2 >= r2 and d1 <= c1 and d2 >= c2):
        return False
    extra_rows = set(range(n1, r1)) | set(range(r2 + 1, n2 + 1))
    extra_cols = set(range(d1, c1)) | set(range(c2 + 1, d2 + 1))
    return extra_rows <= m.new_rows and extra_cols <= m.new_cols


def _same_formula(old: Cell, new: Cell, old_sheet: str, new_sheet: str, maps: dict[str, _SheetMap],
                  renames: dict[str, str]) -> bool:
    po, pn = old.parsed, new.parsed
    if po is None or pn is None or not po.ok or not pn.ok:
        return str(old.value).replace(" ", "").upper() == str(new.value).replace(" ", "").upper()
    # Same text once every reference is replaced by a placeholder, and the same references after moving them.
    def skeleton(p: Any) -> str:
        out = []
        for t in p.tokens:
            out.append("§" if t.type == "OPERAND" and t.subtype == "RANGE" else t.value.upper())
        return "".join(out)
    if skeleton(po) != skeleton(pn) or len(po.refs) != len(pn.refs):
        return False
    for ro, rn in zip(po.refs, pn.refs, strict=True):
        a, b = _map_ref(ro, old_sheet, maps, renames), _new_ref(rn, new_sheet)
        if a[0] == "raw" or b[0] == "raw":
            if a != b:
                return False
            continue
        if a[0] == "" and b[0] == "":
            pass
        if a != b:
            sheet_of = (rn.sheet or new_sheet)
            m = next((v for k, v in maps.items() if renames.get(k, k).lower() == sheet_of.lower()), None)
            if not _grew_into_new(a, b, m):
                return False
    return True


def compare(old: Workbook, new: Workbook) -> Comparison:
    out = Comparison()
    old_names = {n.lower(): n for n in old.sheet_order}
    new_names = {n.lower(): n for n in new.sheet_order}
    removed = [old_names[k] for k in old_names if k not in new_names]
    added = [new_names[k] for k in new_names if k not in old_names]
    renames: dict[str, str] = {}
    # A removed and an added sheet that look the same are one sheet, renamed.
    for gone in list(removed):
        best: tuple[float, str] | None = None
        for extra in added:
            trial = _SheetMap(old.sheets[gone], new.sheets[extra])
            share = len(trial.rows) / max(1, max(old.sheets[gone].max_row, new.sheets[extra].max_row))
            if share >= 0.8 and (best is None or share > best[0]):
                best = (share, extra)
        if best:
            renames[gone] = best[1]
            removed.remove(gone)
            added.remove(best[1])
    for gone in removed:
        out.changes.append(Change(kind="SHEET_REMOVED", material=True, sheet=gone, detail=f"Sheet '{gone}' is no longer in the workbook."))
    for extra in added:
        out.changes.append(Change(kind="SHEET_ADDED", material=True, sheet=extra, detail=f"Sheet '{extra}' is new."))
    pairs = {o: renames.get(o, new_names.get(o.lower())) for o in old.sheet_order if o not in removed}
    maps = {o: _SheetMap(old.sheets[o], new.sheets[n]) for o, n in pairs.items() if n}
    inputs_changed = 0
    summary_rows: dict[str, Any] = {}
    for o, m in maps.items():
        n = pairs[o]
        assert n is not None
        so, sn = old.sheets[o], new.sheets[n]
        if renames.get(o):
            out.changes.append(Change(kind="SHEET_RENAMED", material=False, sheet=n, detail=f"Sheet '{o}' is now called '{n}'."))
        summary_rows[n] = {"rows_added": len(m.new_rows), "rows_removed": len(m.old_rows_gone),
                           "columns_added": len(m.new_cols), "columns_removed": len(m.old_cols_gone)}
        seen_new: set[tuple[int, int]] = set()
        for (r, c), oc in sorted(so.cells.items()):
            nr, nc = m.rows.get(r), m.cols.get(c)
            if nr is None or nc is None:
                if oc.kind == "formula" and (r in m.old_rows_gone or c in m.old_cols_gone):
                    continue  # the whole row or column went; counted in the summary
                continue
            seen_new.add((nr, nc))
            ncell = sn.get(nr, nc)
            where = {"sheet": n, "cell": addr(nr, nc), "before_cell": addr(r, c), "row_label": row_label(sn, nr, nc),
                     "column_label": column_label(sn, nr, nc, (1990, 2100))}
            if oc.kind == "formula":
                if ncell is None:
                    out.changes.append(Change(kind="FORMULA_REMOVED", material=True, before=oc.value, **where,
                                              detail=f"{oc.value} was deleted; the cell is now empty."))
                elif ncell.kind == "formula":
                    if not _same_formula(oc, ncell, o, n, maps, renames):
                        out.changes.append(Change(kind="FORMULA_CHANGED", material=True, before=oc.value, after=ncell.value, **where,
                                                  detail=f"{oc.value} (was {addr(r, c)}) is now {ncell.value}."))
                else:
                    out.changes.append(Change(kind="FORMULA_TO_VALUE", material=True, before=oc.value, after=str(ncell.value), **where,
                                              detail=f"{oc.value} was replaced by the typed value {ncell.value}: it no longer updates."))
            elif ncell is not None and ncell.kind == "formula":
                out.changes.append(Change(kind="VALUE_TO_FORMULA", material=True, before=str(oc.value), after=ncell.value, **where,
                                          detail=f"The typed value {oc.value} is now the formula {ncell.value}."))
            elif ncell is not None and oc.kind == ncell.kind == "number" and oc.value != ncell.value:
                inputs_changed += 1
        for (r, c), ncell in sorted(sn.cells.items()):
            if (r, c) in seen_new or ncell.kind != "formula" or r in m.new_rows or c in m.new_cols:
                continue
            out.changes.append(Change(kind="FORMULA_ADDED", material=False, sheet=n, cell=addr(r, c), after=ncell.value,
                                      row_label=row_label(sn, r, c), detail=f"New formula {ncell.value} in a cell that was empty."))
    name_changes = sorted(k for k in set(old.names) | set(new.names) if old.names.get(k) != new.names.get(k))
    out.summary = {"typed_values_changed": inputs_changed, "sheets": summary_rows, "names_changed": name_changes,
                   "material": sum(1 for c in out.changes if c.material)}
    return out
