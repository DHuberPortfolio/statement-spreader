"""Reading one formula: what it refers to, which functions it calls, which typed numbers it contains.

openpyxl's tokenizer splits the text (it is a parser, not a calculator: nothing is evaluated). This module turns
its operands into references with sheet, external workbook and coordinates, and writes the formula in relative
(R1C1) form: `=F14*(1+$B$2)` in G14 and `=G14*(1+$B$2)` in H14 are both `=RC[-1]*(1+R2C2)`, which is how
copied formulas are compared with their neighbours. This is the same notion Excel's own "inconsistent formula"
check uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from openpyxl.formula.tokenizer import Token, Tokenizer, TokenizerError
from openpyxl.utils.cell import column_index_from_string

MAX_COL, MAX_ROW = 16384, 1_048_576
_CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
_COLS = re.compile(r"^(\$?)([A-Z]{1,3}):(\$?)([A-Z]{1,3})$")
_ROWS = re.compile(r"^(\$?)(\d+):(\$?)(\d+)$")
_NAME = re.compile(r"^[A-Za-z_\\][A-Za-z0-9_.\\?]*$")
_EXT_FILE = re.compile(r"\.xl[a-z]{1,2}$", re.I)


@dataclass(frozen=True)
class Ref:
    """One reference. Coordinates are 1-based; None means 'whole column' (rows) or 'whole row' (columns)."""

    raw: str
    kind: str  # cell | range | name | table | error
    sheet: str | None = None  # None: the formula's own sheet
    external: str | None = None  # the other workbook, when the reference leaves this one
    sheets3d: tuple[str, str] | None = None  # Sheet1:Sheet3!A1
    r1: int | None = None
    c1: int | None = None
    r2: int | None = None
    c2: int | None = None
    abs_r1: bool = False
    abs_c1: bool = False
    abs_r2: bool = False
    abs_c2: bool = False
    name: str | None = None

    @property
    def is_area(self) -> bool:
        return self.kind in ("cell", "range")

    def box(self, max_row: int, max_col: int) -> tuple[int, int, int, int]:
        """(r1, c1, r2, c2) with whole rows or columns clipped to the sheet's used area."""
        return (self.r1 or 1, self.c1 or 1, self.r2 or max_row, self.c2 or max_col)

    def contains(self, r: int, c: int) -> bool:
        lo_r, lo_c = self.r1 or 1, self.c1 or 1
        hi_r, hi_c = self.r2 or MAX_ROW, self.c2 or MAX_COL
        return lo_r <= r <= hi_r and lo_c <= c <= hi_c


@dataclass
class Literal:
    value: float
    text: str
    additive_partner: bool  # added to or subtracted from a reference, a function or a bracketed expression
    multiplicative: bool  # next to * / ^ or followed by %
    in_function: str | None  # innermost function the number is a direct argument of


@dataclass
class Parsed:
    text: str
    ok: bool = True
    refs: list[Ref] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    literals: list[Literal] = field(default_factory=list)
    has_ref_error: bool = False
    # For every reference: the innermost function it is a direct argument of, and which argument (0-based).
    arg_of: list[tuple[str | None, int]] = field(default_factory=list)
    only_additive: bool = False  # the formula is references joined by + (and SUMs), nothing else
    total_range: Ref | None = None  # the formula is exactly =SUM(range) or =SUBTOTAL(9|109, range)
    tokens: list[Token] = field(default_factory=list)


def _split_sheet(operand: str) -> tuple[str | None, str]:
    """'Op Ex'!B5 -> ("Op Ex", "B5"). The last ! outside quotes separates sheet and reference."""
    quoted, cut = False, -1
    for i, ch in enumerate(operand):
        if ch == "'":
            quoted = not quoted
        elif ch == "!" and not quoted:
            cut = i
    if cut < 0:
        return None, operand
    sheet = operand[:cut]
    if sheet.startswith("'") and sheet.endswith("'") and len(sheet) >= 2:
        sheet = sheet[1:-1].replace("''", "'")
    return sheet, operand[cut + 1:]


def _external(sheet: str) -> tuple[str | None, str]:
    """'C:\\x\\[Rates.xlsx]FX' -> ("C:\\x\\Rates.xlsx", "FX"); '[1]FX' -> ("[1]", "FX")."""
    m = re.match(r"^(.*)\[([^\]]+)\](.*)$", sheet)
    if m:
        book = m.group(2)
        target = f"[{book}]" if book.isdigit() else (m.group(1) + book)
        return target, m.group(3)
    if _EXT_FILE.search(sheet):
        return sheet, ""
    return None, sheet


def parse_ref(operand: str) -> Ref:
    if "#REF!" in operand.upper():  # checked first: the "!" of #REF! is not a sheet separator
        sheet = operand[:operand.upper().index("#REF!")].rstrip("!").strip("'") or None
        return Ref(operand, "error", sheet)
    sheet, rest = _split_sheet(operand)
    external = None
    sheets3d = None
    if sheet is not None:
        external, sheet = _external(sheet)
        if external is None and ":" in sheet:
            first, last = sheet.split(":", 1)
            sheets3d = (first, last)
    up = rest.upper()
    parts = up.split(":")
    if len(parts) == 1 and (m := _CELL.match(up)):
        r, c = int(m.group(4)), column_index_from_string(m.group(2))
        if r <= MAX_ROW and c <= MAX_COL:
            return Ref(operand, "cell", sheet or None, external, sheets3d, r, c, r, c,
                       bool(m.group(3)), bool(m.group(1)), bool(m.group(3)), bool(m.group(1)))
    if len(parts) == 2:
        a, b = _CELL.match(parts[0]), _CELL.match(parts[1])
        if a and b:
            r1, c1 = int(a.group(4)), column_index_from_string(a.group(2))
            r2, c2 = int(b.group(4)), column_index_from_string(b.group(2))
            if max(r1, r2) <= MAX_ROW and max(c1, c2) <= MAX_COL:
                return Ref(operand, "range", sheet or None, external, sheets3d, min(r1, r2), min(c1, c2), max(r1, r2),
                           max(c1, c2), bool(a.group(3)), bool(a.group(1)), bool(b.group(3)), bool(b.group(1)))
        if mc := _COLS.match(up):
            c1, c2 = column_index_from_string(mc.group(2)), column_index_from_string(mc.group(4))
            return Ref(operand, "range", sheet or None, external, sheets3d, None, min(c1, c2), None, max(c1, c2),
                       False, bool(mc.group(1)), False, bool(mc.group(3)))
        if mr := _ROWS.match(up):
            r1, r2 = int(mr.group(2)), int(mr.group(4))
            return Ref(operand, "range", sheet or None, external, sheets3d, min(r1, r2), None, max(r1, r2), None,
                       bool(mr.group(1)), False, bool(mr.group(3)), False)
    if "[" in rest:
        return Ref(operand, "table", sheet or None, external, name=rest.split("[", 1)[0])
    return Ref(operand, "name", sheet or None, external, name=rest)


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def parse(formula: str) -> Parsed:
    """Parse a formula's text (with or without the leading '='). Never raises: a formula the tokenizer cannot read
    comes back with ok=False."""
    text = formula if formula.startswith("=") else "=" + formula
    out = Parsed(text)
    try:
        toks = [t for t in Tokenizer(text).items if t.type != Token.WSPACE]
    except (TokenizerError, ValueError, IndexError):
        out.ok = False
        return out
    out.tokens = toks
    stack: list[list] = []  # [function name or None for a bracket, argument index]
    additive = True
    for i, t in enumerate(toks):
        if t.type == Token.FUNC and t.subtype == Token.OPEN:
            name = t.value[:-1].upper()
            if name.startswith("_XLFN."):
                name = name[6:]
            out.functions.append(name)
            stack.append([name, 0])
            if name not in ("SUM",):
                additive = False
        elif t.type == Token.PAREN and t.subtype == Token.OPEN:
            stack.append([None, 0])
        elif t.subtype == Token.CLOSE and stack:
            stack.pop()
        elif t.type == Token.SEP and t.subtype == Token.ARG and stack:
            stack[-1][1] += 1
        elif t.type == Token.OPERAND and t.subtype == Token.RANGE:
            ref = parse_ref(t.value)
            out.refs.append(ref)
            if ref.kind == "error":
                out.has_ref_error = True
            out.arg_of.append((stack[-1][0], stack[-1][1]) if stack and stack[-1][0] is not None else (None, 0))
        elif t.type == Token.OPERAND and t.subtype == Token.ERROR:
            if t.value.upper() == "#REF!":
                out.has_ref_error = True
            additive = False
        elif t.type == Token.OPERAND and t.subtype == Token.NUMBER:
            v = _number(t.value)
            if v is None:
                continue
            prev = toks[i - 1] if i > 0 else None
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            out.literals.append(Literal(v, t.value, _additive_partner(toks, i), _multiplicative(prev, nxt),
                                        stack[-1][0] if stack and stack[-1][0] is not None and _is_arg(prev, nxt) else None))
            additive = False
        elif (t.type == Token.OP_IN and t.value != "+") or t.type in (Token.OP_PRE, Token.OP_POST) or                 (t.type == Token.OPERAND and t.subtype in (Token.TEXT, Token.LOGICAL)):
            additive = False
    out.only_additive = additive and bool(out.refs)
    out.total_range = _total_range(toks)
    return out


def _is_infix(t: Token | None, ops: str) -> bool:
    return t is not None and t.type == Token.OP_IN and t.value in ops


def _is_arg(prev: Token | None, nxt: Token | None) -> bool:
    """The number stands alone as a function argument: f(…, 2, …)."""
    def edge(t: Token | None) -> bool:
        return t is not None and ((t.type == Token.SEP and t.subtype == Token.ARG) or
                                  (t.type == Token.FUNC and t.subtype in (Token.OPEN, Token.CLOSE)))
    return edge(prev) and edge(nxt)


def _multiplicative(prev: Token | None, nxt: Token | None) -> bool:
    return _is_infix(prev, "*/^") or _is_infix(nxt, "*/^") or (nxt is not None and nxt.type == Token.OP_POST)


def _operand_like(t: Token | None, before: bool) -> bool:
    """A reference, a function call or a bracketed expression on that side of the operator (not another number)."""
    if t is None:
        return False
    if t.type == Token.OPERAND:
        return t.subtype == Token.RANGE
    if before:
        return t.subtype == Token.CLOSE
    return t.subtype == Token.OPEN


def _additive_partner(toks: list[Token], i: int) -> bool:
    prev = toks[i - 1] if i > 0 else None
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if nxt is not None and (nxt.type == Token.OP_POST or _is_infix(nxt, "*/^")):
        return False  # 5% or 2*x: a factor, not a plug
    if _is_infix(prev, "+-") and not _is_infix(toks[i - 2] if i > 1 else None, "*/^") and _operand_like(toks[i - 2] if i > 1 else None, True):
        return True
    if prev is not None and prev.type == Token.OP_PRE and prev.value == "-":
        prev = toks[i - 2] if i > 1 else None
    if _is_infix(nxt, "+-") and (prev is None or prev.type in (Token.SEP,) or prev.subtype == Token.OPEN or _is_infix(prev, "+-")):
        return _operand_like(toks[i + 2] if i + 2 < len(toks) else None, False)
    return False


def _total_range(toks: list[Token]) -> Ref | None:
    """=SUM(C5:C12) or =SUBTOTAL(9,C5:C12): the shape of a total over one block."""
    vals = [(t.type, t.subtype, t.value.upper()) for t in toks]
    if len(vals) == 3 and vals[0][2] == "SUM(" and vals[1][:2] == (Token.OPERAND, Token.RANGE) and vals[2][1] == Token.CLOSE:
        ref = parse_ref(toks[1].value)
    elif (len(vals) == 5 and vals[0][2] == "SUBTOTAL(" and vals[1][2] in ("9", "109") and vals[2][0] == Token.SEP
          and vals[3][:2] == (Token.OPERAND, Token.RANGE) and vals[4][1] == Token.CLOSE):
        ref = parse_ref(toks[3].value)
    else:
        return None
    return ref if ref.kind == "range" and ref.external is None and ref.r1 and ref.c1 else None


def r1c1(p: Parsed, row: int, col: int, own_sheet: str) -> str:
    """The formula in relative form, for comparing copies. References to the formula's own sheet drop the sheet name,
    so `=Sheet1!B5` and `=B5` written on Sheet1 compare equal."""
    if not p.ok:
        return "?" + p.text
    out: list[str] = []
    refs = iter(p.refs)
    for t in p.tokens:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            ref = next(refs)
            out.append(_ref_r1c1(ref, row, col, own_sheet))
        elif t.type == Token.FUNC and t.subtype == Token.OPEN:
            out.append(t.value.upper())
        else:
            out.append(t.value.upper() if t.type == Token.OPERAND and t.subtype == Token.LOGICAL else t.value)
    return "=" + "".join(out)


def _ref_r1c1(ref: Ref, row: int, col: int, own_sheet: str) -> str:
    prefix = ""
    if ref.external:
        prefix = f"[{ref.external}]{ref.sheet or ''}!"
    elif ref.sheets3d:
        prefix = f"{ref.sheets3d[0].lower()}:{ref.sheets3d[1].lower()}!"
    elif ref.sheet and ref.sheet.lower() != own_sheet.lower():
        prefix = ref.sheet.lower() + "!"
    if ref.kind in ("name", "table"):
        return prefix + (ref.raw.split("!")[-1]).upper()
    if ref.kind == "error":
        return prefix + "#REF!"

    def part(v: int | None, absolute: bool, here: int, letter: str) -> str:
        if v is None:
            return ""
        return f"{letter}{v}" if absolute else (letter if v == here else f"{letter}[{v - here}]")

    a = part(ref.r1, ref.abs_r1, row, "R") + part(ref.c1, ref.abs_c1, col, "C")
    if ref.kind == "cell":
        return prefix + a
    b = part(ref.r2, ref.abs_r2, row, "R") + part(ref.c2, ref.abs_c2, col, "C")
    return prefix + a + ":" + b


def is_name(text: str) -> bool:
    return bool(_NAME.match(text))
