"""PDF (with a text layer) -> DocumentIR.

Financial statements in PDFs are rarely real tables: they are words placed on a page. This
reader rebuilds them the way a person reads the page:

1. Lines: words whose vertical centres are close are one line. Running headers and footers
   (page numbers, "Table of Contents", "Form 10-K") are dropped.
2. Cells: a line is split into cells at wide gaps (a label's words are close; the gap before a
   number column is wide). A number inside a label ("$0.01 par value; 50,000 shares
   authorized"), a date ("June 30") and a small footnote marker stay part of the text. A "$" or
   "(" printed apart from its number is merged into it.
3. Wrapped labels: a label that continues on the next line is one label (the next line starts
   in lower case, or the first ends unfinished: an open parenthesis, a comma, "and").
4. Statements: a page is split where a new statement title or a new row of column headers
   starts after figures. The lines above a statement's first figures are sorted into column
   headers (kept as rows, for the layout to read periods from), section labels (kept as rows),
   and the title, company name and unit statement, which become the table's context, as an HTML
   reader would find them in the text above a table.
5. Continued statements: a page that continues the previous page's statement (no title or
   headers of its own, or a "(continued)" title; same number columns; the previous part did not
   end with "See accompanying notes") is joined to it.

Every token keeps its page and bounding box, so the interface can draw a box around the exact
printed number. Pages without figures are skipped after a fast text pass (pdfium) so a 250-page
annual report is read in seconds, not minutes.

Scanned PDFs have no text layer. With the optional `ocr` extra installed, their pages are read by optical character
recognition (spreader.ingest.ocr, D42) into the same words with boxes, and everything above applies unchanged; every
OCR'd token carries its recognition confidence. Without the extra, a scan is refused with that reason rather than
read as empty.
"""

from __future__ import annotations

import io
import re
import statistics
from dataclasses import dataclass, field

import pdfplumber

from ..contracts import DocumentIR, RawRow, RawTable, SourceFormat, SourceRef, Token
from ..detect import document_unit_statements
from ..numbers import DASHES, clean_text, is_amount_like
from . import IngestError, doc_id_for

LINE_TOLERANCE = 3.0  # points: words within this vertical distance are on one line
MAX_PAGES = 600
MARGIN_BAND = 50.0  # points at the top and bottom of a page where running headers and footers sit
MIN_PAGE_NUMBERS = 4  # a page with fewer printed numbers holds no statement table
FOOTNOTE_SIZE = 0.8  # a number in a font this much smaller than the line's is a footnote marker

_FOOTER = re.compile(r"form\s+10-?[kq]\b|^\s*\d{1,3}\s*$|^page\s+\d+|^\s*table\s+of\s+contents\s*$|^\s*[a-z]-\d{1,3}\s*$",
                     re.I)
# The line printed under a statement: it has ended ("See accompanying notes", "Refer to Notes to
# Consolidated Financial Statements", "... are an integral part of these statements").
_END = re.compile(r"accompanying\s+notes|integral\s+part\s+of\s+(these|the)|^\s*(see|refer\s+to)\s+(the\s+)?notes\s+to\b", re.I)
_TITLE = re.compile(
    r"\bstatements?\s+of\s+(?:[\w’'.,&-]+\s+){0,4}?(?:income|operations|earnings|cash\s+flows?|financial\s+(?:position|condition)"
    r"|comprehensive|changes|equity|loss|profit|deficit|retained)"
    r"|\bbalance\s+sheets?\b|\bresults\s+of\s+operations\b|\bconsolidated\s+(?:financial\s+position|comprehensive\s+income)"
    r"|\bchanges\s+in\s+(?:consolidated\s+)?(?:shareholders|stockholders|shareowners)",
    re.I)
_UNIT = re.compile(r"\b(thousands|millions|billions)\b|\$\s*0{3}s?\b|\b0{3}s?\s+omitted", re.I)
_CONTINUED = re.compile(r"\(?\bcontinued\b\)?|\bcont[’'`]?d\b", re.I)
_YEARISH = re.compile(r"^(19|20)\d\d$")
_HAS_YEAR = re.compile(r"(?<!\d)(19|20)\d\d(?!\d)")
_MONTH = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?$", re.I)
_DAY = re.compile(r"^\d{1,2},?$")
_PERIOD_WORDS = re.compile(
    r"\b(?:years?|months?|weeks?|quarters?|ended|ending|fiscal|periods?|as\s+(?:of|at)|jan(?:uary)?|feb(?:ruary)?"
    r"|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
    r"|(?<!\d)(?:19|20)\d\d(?!\d)",
    re.I)
_MONTH_DAY_END = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?$", re.I)
# A wrapped label's second line starts in lower case ("activities:", "(net of tax ...)",
# "1,113,018,733 issued; 593,245,884 outstanding").
_CONTINUATION = re.compile(r"^[(\[]?[a-z]|^\$?[\d,.]+\s+[a-z]")
_FOOTNOTE_LINE = re.compile(r"^\(?([a-z]|\d{1,2}|[ivx]{1,4})\)\s|^\*")
_MARKER = re.compile(r"^(\(?(\d{1,2}|[a-z])\)|\*{1,3}|[†‡])$", re.I)
_CONNECTORS = {"and", "or", "of", "to", "by", "in", "at", "for", "from", "with", "on", "per", "than", "plus", "less",
               "including", "includes", "excluding", "approximately", "over", "under", "about"}
_PREFIXES = {"$", "€", "£", "(", "($", "$(", "(€", "(£"}
_SUFFIXES = {")", "%", ")%", "%)"}


# --------------------------------------------------------------------------------------- lines


def _lines(words: list[dict]) -> list[list[dict]]:
    words = sorted(words, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        mid = (w["top"] + w["bottom"]) / 2
        if lines:
            last = lines[-1]
            last_mid = statistics.fmean((x["top"] + x["bottom"]) / 2 for x in last)
            if abs(mid - last_mid) <= LINE_TOLERANCE:
                last.append(w)
                continue
        lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _is_footer(line: list[dict], page_height: float, edge: bool = False) -> bool:
    """Running headers and footers, and page numbers, are not statement rows.

    edge: the line is the first or last on its page (a footer printed where the text ends, not
    in the page margin).
    """
    text = _line_text(line)
    top = min(w["top"] for w in line)
    bottom = max(w["bottom"] for w in line)
    in_band = top > page_height - MARGIN_BAND or bottom < MARGIN_BAND
    if _FOOTER.search(text) and (in_band or len(text) < 60):
        return True
    if (in_band or edge) and len(text) < 100:
        # "38 The Procter & Gamble Company", "Company 2025 Annual Report 42": one small whole
        # number at either end of a short line of words is a page number.
        numbers = [w for w in line if is_amount_like(w["text"]) and not _YEARISH.match(w["text"])]
        words = sum(1 for w in line if re.search(r"[A-Za-z]{2}", w["text"]))
        if (len(numbers) == 1 and re.fullmatch(r"\d{1,3}", numbers[0]["text"]) and numbers[0] in (line[0], line[-1])
                and words >= (1 if in_band else 2)):
            return True
    return False


def _is_marker_line(line: list[dict], font: float) -> bool:
    """A superscript footnote marker ("*", "(1)") raised far enough to form a line of its own."""
    text = _line_text(line)
    small = all((w.get("size") or font) < FOOTNOTE_SIZE * font for w in line)
    return len(text) <= 6 and (bool(re.fullmatch(r"[*†‡]+", text.replace(" ", ""))) or small)


# --------------------------------------------------------------------------------------- cells


@dataclass
class _Cell:
    words: list[dict]

    @property
    def text(self) -> str:
        return clean_text(" ".join(w["text"] for w in self.words))

    @property
    def x0(self) -> float:
        return min(w["x0"] for w in self.words)

    @property
    def x1(self) -> float:
        return max(w["x1"] for w in self.words)

    @property
    def core_x0(self) -> float:
        """Left edge without a "$" printed apart from the figure (for column finding: the "$"
        of a right-hand column can sit right next to the column before it)."""
        core = [w for w in self.words if w["text"] not in _PREFIXES] or self.words
        return min(w["x0"] for w in core)

    @property
    def top(self) -> float:
        return min(w["top"] for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w["bottom"] for w in self.words)

    @property
    def is_year(self) -> bool:
        return bool(_YEARISH.match(self.text))

    @property
    def is_value(self) -> bool:
        return not self.is_year and is_amount_like(self.text)


@dataclass
class _Line:
    index: int  # line number on the page (the row index of the table it ends up in)
    cells: list[_Cell]
    words: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.cells)

    @property
    def top(self) -> float:
        return min(c.top for c in self.cells)

    @property
    def bottom(self) -> float:
        return max(c.bottom for c in self.cells)

    @property
    def values(self) -> list[_Cell]:
        return [c for c in self.cells if c.is_value]

    @property
    def is_data(self) -> bool:
        return any(c.is_value for c in self.cells)

    @property
    def label(self) -> _Cell | None:
        first = self.cells[0]
        return None if (first.is_value or first.is_year) else first


def _numeric_word(text: str) -> bool:
    return is_amount_like(text) or text in {")", "%"} or text in _PREFIXES


def _cells(line: list[dict]) -> list[_Cell]:
    """Group a line's words into cells: a wide gap or a number after text starts a new cell."""
    sizes = [w["bottom"] - w["top"] for w in line] or [10.0]
    gap_limit = max(3.5, 0.6 * statistics.median(sizes))
    font = statistics.median((w.get("size") or (w["bottom"] - w["top"])) for w in line)
    groups: list[list[dict]] = []
    for i, w in enumerate(line):
        t = w["text"]
        if groups:
            group = groups[-1]
            prev = group[-1]
            gap = w["x0"] - prev["x1"]
            joined = " ".join(x["text"] for x in group)
            numeric_now = _numeric_word(t)
            numeric_before = is_amount_like(joined) or joined in _PREFIXES
            if t in _PREFIXES and is_amount_like(joined):
                # "$ 10,270 $ 10,828": a "$" opens the next figure; it never ends the last one
                groups.append([w])
                continue
            if gap <= gap_limit:
                if not numeric_now or numeric_before or joined.endswith(("$", "€", "£", "(")):
                    group.append(w)
                    continue
                # A number right after text at word spacing. It stays in the text when it is a
                # footnote marker (smaller font), part of a date ("June 30", "June 30, 2025"),
                # followed by more words ("$0.01 par value; 50,000 shares authorized"), or ends
                # a phrase like "restricted cash of $0.4 and $0.3".
                small = (w.get("size") or font) < FOOTNOTE_SIZE * font
                date = (_MONTH.match(prev["text"]) and _DAY.match(t)) or (
                    _YEARISH.match(t.rstrip(",.;:")) and _MONTH_DAY_END.search(joined))
                nxt = line[i + 1] if i + 1 < len(line) else None
                more_words = nxt is not None and nxt["x0"] - w["x1"] <= gap_limit and not _numeric_word(nxt["text"])
                connector = prev["text"].lower().rstrip(",;:") in _CONNECTORS
                dash = t in DASHES  # "Non-cash items –": punctuation, not a nil figure
                if small or date or more_words or connector or dash:
                    group.append(w)
                    continue
            if t in _SUFFIXES and gap <= gap_limit * 2:
                group.append(w)
                continue
        groups.append([w])
    if len(groups) >= 2 and _MARKER.match(_line_text(groups[0])) and not _numeric_word(groups[1][0]["text"]):
        # "(1) Basic net earnings per share are calculated ...": a footnote's marker, not a figure
        # (figures follow their label; nothing is printed to the left of a row's label).
        groups[1] = groups[0] + groups[1]
        groups.pop(0)
    cells: list[_Cell] = []
    pending: list[dict] | None = None  # a "$" or "(" printed apart from its number
    for g in groups:
        text = clean_text(" ".join(x["text"] for x in g))
        if text in _PREFIXES:
            pending = g if pending is None else pending + g
            continue
        if pending is not None:
            g = pending + g
            pending = None
        cells.append(_Cell(g))
    return cells


# ------------------------------------------------------------------------------ wrapped labels


_UNFINISHED = re.compile(r"[,;(]$|\b(and|or|of|to|for|the|by|from|with|including|excluding)$", re.I)


def _unfinished(label: str) -> bool:
    """A label that cannot end here: an open parenthesis, or a trailing comma or connector
    ("Common stock (10,000 shares authorized; issued: 2026 - 4,009.2," / "2025 - 4,009.2)")."""
    text = label.strip()
    return text.count("(") > text.count(")") or bool(_UNFINISHED.search(text))


def _join_wrapped(lines: list[_Line]) -> list[_Line]:
    """A label that wraps onto the next line is one label.

    The next line continues the label when it starts in lower case, near the label's left edge
    (the same indent, a deeper one, or a hanging indent), and carries no column headers. Figures
    may sit on either line: on the last (bottom-aligned cells, the usual case) or on the first
    (top-aligned cells). A number printed right against the end of the first line ("900,000,000
    shares authorized; 443,266,000" / "and 443,000,000 issued ...") is part of the label.
    """
    out: list[_Line] = []
    for line in lines:
        prev = out[-1] if out else None
        head = line.label
        if prev is not None and head is not None and prev.label is not None and len(prev.cells) >= 1:
            starts = (_CONTINUATION.match(head.text) or _unfinished(prev.label.text)) and not _FOOTNOTE_LINE.match(head.text)
            aligned = abs(head.x0 - prev.label.x0) <= 30  # same indent, deeper, or a hanging indent
            close = line.top - prev.bottom < 1.2 * max(1.0, line.bottom - line.top)
            no_years = not any(c.is_year for c in line.cells) and not any(c.is_year for c in prev.cells)
            if starts and aligned and close and no_years:
                height = max(1.0, prev.label.bottom - prev.label.top)
                while len(prev.cells) > 1 and prev.cells[1].is_value and prev.cells[1].x0 - prev.label.x1 <= 0.6 * height:
                    prev.label.words.extend(prev.cells.pop(1).words)
                if not prev.is_data:
                    # label on top, figures (if any) on the continuation line
                    prev.label.words.extend(head.words)
                    prev.cells.extend(line.cells[1:])
                    prev.words.extend(line.words)
                    continue
                if not line.is_data and len(line.cells) == 1:
                    # figures on the first line, the label's last words below it
                    prev.label.words.extend(head.words)
                    prev.words.extend(line.words)
                    continue
        out.append(line)
    return out


# ---------------------------------------------------------------------------------- statements


def _is_title(line: _Line) -> bool:
    text = line.text
    return not line.is_data and len(text) < 150 and bool(_TITLE.search(text)) and not text.rstrip().endswith(":")


def _is_header(line: _Line) -> bool:
    """A row of column headers: two or more cells naming years ("2025", "December 31, 2025")."""
    return not line.is_data and sum(1 for c in line.cells if _HAS_YEAR.search(c.text)) >= 2


def _is_end(line: _Line) -> bool:
    return not line.is_data and bool(_END.search(line.text))


def _segments(lines: list[_Line]) -> list[list[_Line]]:
    """Split a page into statements: a new title, or new column headers, after figures.

    Lines between the last figures of one statement and the next statement's title or headers
    (its company name, title and unit statement) go with the next statement; an end marker
    ("See accompanying notes") stays with the statement it ends.
    """
    segs: list[list[_Line]] = [[]]
    seen_data = False
    for line in lines:
        if seen_data and (_is_title(line) or _is_header(line)):
            cur = segs[-1]
            last_data = max(i for i, ln in enumerate(cur) if ln.is_data)
            tail = cur[last_data + 1:]
            ends = [i for i, ln in enumerate(tail) if _is_end(ln)]
            cut = last_data + 1 + (ends[-1] + 1 if ends else 0)
            segs[-1] = cur[:cut]
            segs.append(cur[cut:])
            seen_data = False
        segs[-1].append(line)
        if line.is_data:
            seen_data = True
    return [s for s in segs if s]


def _columns(cells: list[_Cell], tolerance: float = 2.0) -> list[tuple[float, float, int]]:
    """Number columns: overlapping extents of figures, with how many figures each holds."""
    spans = sorted((c.core_x0, c.x1) for c in cells)
    groups: list[list[float]] = []
    for x0, x1 in spans:
        if groups and x0 - tolerance < groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], x1)
            groups[-1][2] += 1
        else:
            groups.append([x0, x1, 1])
    return [(g[0], g[1], int(g[2])) for g in groups]


def _value_left(columns: list[tuple[float, float, int]]) -> float:
    """Where the number columns begin: the left edge of the leftmost real column (a lone figure
    left of the columns, such as a stray dash or a number in a label, does not move it)."""
    most = max(n for _, _, n in columns)
    return next(x0 for x0, _, n in columns if n >= min(most, max(2, 0.2 * most)))


@dataclass
class _Part:
    """One statement (or other table) found on a page, before continued pages are joined."""

    table: RawTable
    page: int
    last_page: int
    title: bool  # has a statement title of its own
    continued: bool  # its title says "(continued)"
    header_rows: set[int]  # row indexes of its column-header rows
    header_years: tuple[str, ...]
    ended: bool  # an end marker ("See accompanying notes") follows its figures
    first_on_page: bool = False
    last_on_page: bool = False


def _part(seg: list[_Line], doc_id: str, t_index: int, page: int) -> _Part | None:
    data = [i for i, ln in enumerate(seg) if ln.is_data]
    if not data:
        return None
    first = data[0]
    value_cells = [c for ln in seg for c in ln.values]
    columns = _columns(value_cells)
    vx = _value_left(columns)
    labels = [ln.label.x0 for ln in seg[first:] if ln.label is not None]
    lx = min(labels) if labels else vx
    pre = seg[:first]
    headers = _header_lines(pre, vx, lx)
    last_header = max(headers, default=-1)
    context: list[_Line] = []
    rows: list[_Line] = []
    header_rows: set[int] = set()
    for i, ln in enumerate(pre):
        if i in headers:
            rows.append(ln)
            header_rows.add(ln.index)
            if _UNIT.search(ln.text):
                context.append(ln)  # "Amounts in millions; years ended June 30 | 2026 | 2025"
        elif _is_title(ln) or _UNIT.search(ln.text) or _is_end(ln):
            context.append(ln)
        elif (i > last_header and ln.label is not None and ln.label.x0 <= lx + 60
              and not any(c.x1 > vx - 2 for c in ln.cells)):
            rows.append(ln)  # a section label between the headers and the first figures ("Net sales:")
        else:
            context.append(ln)  # company name, centred headings, text above the statement
    ended = False
    for ln in seg[first:]:
        if _is_end(ln):
            ended = True
            continue
        rows.append(ln)

    raw_rows: list[RawRow] = []
    for ln in rows:
        spans = _header_spans(ln, columns, vx, lx) if ln.index in header_rows else {}
        toks = [_token(c, doc_id, t_index, ln.index, page, spans.get(id(c))) for c in ln.cells]
        first_tok = toks[0]
        indent = max(0.0, first_tok.x0 - lx) if ln.label is not None else 0.0
        raw_rows.append(RawRow(index=ln.index, tokens=toks, indent=round(indent, 1), bold=_is_bold(ln)))
    numbers = sum(len(ln.values) for ln in rows)
    if numbers < 4:
        return None
    ctx = clean_text(" ".join(ln.text for ln in context))
    years = tuple(c.text for i in sorted(header_rows) for ln in rows if ln.index == i for c in ln.cells
                  if _HAS_YEAR.search(c.text))
    table = RawTable(index=t_index, rows=raw_rows, context=ctx, page=page)
    return _Part(table=table, page=page, last_page=page, title=any(_is_title(ln) for ln in context),
                 continued=bool(_CONTINUED.search(ctx)), header_rows=header_rows, header_years=years, ended=ended)


def _header_lines(pre: list[_Line], vx: float, lx: float) -> set[int]:
    """Which of the lines above a statement's first figures are column headers.

    A column header has text over the number columns that names a period: a year ("2025",
    "December 31, 2025") or period words ("Years ended", "September 27,"). From the first such
    line down, every line with text over the columns is a header too ("Better (Worse)",
    "Successor"). A title, a company name or a unit statement centred above the columns is not,
    nor is a subtitle running from the label column into the number columns ("Fiscal years
    ended December 27, 2025, December 28, 2024 and ..."): that is read as context.
    """
    def over(ln: _Line) -> list[_Cell]:
        if any(c.x0 < (lx + vx) / 2 and c.x1 > vx + 10 for c in ln.cells):
            return []  # runs from the labels into the columns: a subtitle, not a column header
        if _is_header(ln):
            return [c for c in ln.cells if c.x1 > vx - 2]
        # A single heading must be centred over the columns, not on the page like the title
        # block above it ("Fiscal Years Ended in December" between the title and the unit).
        return [c for c in ln.cells if c.x1 > vx - 2 and (c.x0 + c.x1) / 2 >= vx - 10]

    def names_period(ln: _Line) -> bool:
        return _is_header(ln) or any(_PERIOD_WORDS.search(c.text) for c in over(ln))

    start = next((i for i, ln in enumerate(pre) if over(ln) and not _is_title(ln) and names_period(ln)), None)
    if start is None:
        # No period headers: only text set entirely within the number columns ("Amount").
        return {i for i, ln in enumerate(pre) if ln.cells and all(c.x0 >= vx - 20 for c in ln.cells)
                and not _is_title(ln) and not _UNIT.search(ln.text)}
    return {i for i, ln in enumerate(pre) if i >= start and over(ln) and not _is_title(ln)
            and (names_period(ln) or not _UNIT.search(ln.text))}


def _header_spans(line: _Line, columns: list[tuple[float, float, int]], vx: float,
                  lx: float) -> dict[int, tuple[float, float]]:
    """Horizontal extents for column headers that span several columns.

    In HTML a header like "Years ended" spans its columns with colspan; in a PDF it is printed
    once, centred over them, and a date header may be centred over a "$ 1,234" cell wider than
    the figures. Each header cell over the columns is snapped to the columns it belongs to: a
    cell naming a year to the one column nearest its centre; any other heading to every column
    nearer to it than to the line's other headings. The layout then stacks it over exactly
    those columns. Only the layout extent changes; the bounding box stays as printed.
    """
    cols = [(x0, x1) for x0, x1, _ in columns if x1 >= vx]
    # Header text over the columns, or nearer them than the labels (a date centred over a
    # "$ 1,234" cell can start left of the figures).
    over = [c for c in line.cells if c.x1 > vx - 2 or (c.x0 + c.x1) / 2 > (lx + vx) / 2]
    if not cols or not over:
        return {}

    def centre(a: float, b: float) -> float:
        return (a + b) / 2

    owner: dict[int, list[tuple[float, float]]] = {}
    for col in cols:
        nearest = min(over, key=lambda c: abs(centre(c.x0, c.x1) - centre(*col)))
        owner.setdefault(id(nearest), []).append(col)
    out: dict[int, tuple[float, float]] = {}
    for c in over:
        mine = owner.get(id(c), [])
        if _HAS_YEAR.search(c.text) or not mine:
            col = min(cols, key=lambda k: abs(centre(*k) - centre(c.x0, c.x1)))
            out[id(c)] = col
        else:
            out[id(c)] = (min(a for a, _ in mine), max(b for _, b in mine))
    return out


def _token(cell: _Cell, doc_id: str, t_index: int, r_index: int, page: int,
           span: tuple[float, float] | None = None) -> Token:
    text = cell.text
    scores = [w["ocr_confidence"] for w in cell.words if w.get("ocr_confidence") is not None]
    ref = SourceRef(doc_id=doc_id, format=SourceFormat.PDF, table=t_index, row=r_index, page=page,
                    bbox=(round(cell.x0, 2), round(cell.top, 2), round(cell.x1, 2), round(cell.bottom, 2)), text=text,
                    ocr_confidence=round(min(scores), 4) if scores else None)
    if span:
        x0, x1 = span
    else:
        x0, x1 = (cell.core_x0 if cell.is_value else cell.x0), cell.x1
    return Token(text=text, x0=x0, x1=x1, ref=ref)


def _is_bold(line: _Line) -> bool:
    words = line.cells[0].words[:3] if line.cells else []
    return any("bold" in (w.get("fontname") or "").lower() for w in words)


# --------------------------------------------------------------------------------------- pages


def _figure_pages(data: bytes) -> tuple[list[int], int] | None:
    """Pages (0-based) with at least a few printed numbers, and the text-layer size, from a
    fast pdfium text pass. None when pdfium is unavailable or cannot read the file."""
    try:
        import pypdfium2 as pdfium
    except ImportError:  # pragma: no cover - pypdfium2 is a dependency
        return None
    try:
        doc = pdfium.PdfDocument(data)
    except Exception:  # damaged file: let pdfplumber report it
        return None
    keep: list[int] = []
    chars = 0
    try:
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            chars += len(text.strip())
            if sum(1 for w in text.split() if is_amount_like(w)) >= MIN_PAGE_NUMBERS:
                keep.append(i)
            textpage.close()
            page.close()
    except Exception:
        return None
    finally:
        doc.close()
    return keep, chars


def _page_lines(page: pdfplumber.page.Page) -> list[_Line]:
    """A page's lines of cells: running headers, footers and stray markers removed, wrapped
    labels joined."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["fontname", "size"])
    return _lines_from_words(words, float(page.height))


def _lines_from_words(words: list[dict], height: float) -> list[_Line]:
    if not words:
        return []
    font = statistics.median((w.get("size") or (w["bottom"] - w["top"])) for w in words)
    raw = _lines(words)
    last = len(raw) - 1
    kept = [ln for k, ln in enumerate(raw)
            if not _is_footer(ln, height, edge=k in (0, last)) and not _is_marker_line(ln, font)]
    lines = [_Line(index=i, cells=_cells(ln), words=list(ln)) for i, ln in enumerate(kept)]
    return _join_wrapped([ln for ln in lines if ln.cells])


def _page_parts(page: pdfplumber.page.Page, pno: int, doc_id: str, first_index: int) -> list[_Part]:
    return _parts_from_lines(_page_lines(page), pno, doc_id, first_index)


def _parts_from_lines(lines: list[_Line], pno: int, doc_id: str, first_index: int) -> list[_Part]:
    parts: list[_Part] = []
    for seg in _segments(lines):
        part = _part(seg, doc_id, first_index + len(parts), pno)
        if part is not None:
            parts.append(part)
    if parts:
        parts[0].first_on_page = True
        parts[-1].last_on_page = True
    return parts


def read_pdf(filename: str, data: bytes) -> DocumentIR:
    doc_id = doc_id_for(data)
    warnings: list[str] = []
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfminer raises many types on a damaged file
        raise IngestError(f"Could not open the PDF: {type(exc).__name__}") from exc
    parts: list[_Part] = []
    unit_statements: list[str] = []
    with pdf:
        n_pages = len(pdf.pages)
        if n_pages > MAX_PAGES:
            raise IngestError(f"The PDF has {n_pages} pages; the limit is {MAX_PAGES}")
        scan = _figure_pages(data)
        if scan is not None and scan[1] == 0:
            return _read_scan(filename, data, doc_id, n_pages)
        pages = scan[0] if scan is not None else list(range(n_pages))
        text_pages = 0
        for i in pages:
            page = pdf.pages[i]
            if scan is None and page.chars:
                text_pages += 1
            parts.extend(_page_parts(page, i + 1, doc_id, len(parts)))
            if len(unit_statements) < 50:
                unit_statements.extend(document_unit_statements(page.extract_text() or ""))
        if scan is None and text_pages == 0:
            return _read_scan(filename, data, doc_id, n_pages)
    tables = _join_continued(parts, warnings)
    if not tables:
        raise IngestError("No pages with figures were found in this PDF")
    return DocumentIR(doc_id=doc_id, filename=filename, format=SourceFormat.PDF, tables=tables, warnings=warnings,
                      unit_statements=unit_statements[:50])


def _read_scan(filename: str, data: bytes, doc_id: str, n_pages: int) -> DocumentIR:
    """A PDF with no text layer: read by OCR when the extra is installed, refused with the reason otherwise."""
    from . import ocr

    if not ocr.available():
        raise IngestError("The PDF has no text layer (it is probably a scan). Reading scans needs the optional OCR "
                          "component (install with: pip install -e .[ocr]).")
    if n_pages > ocr.MAX_PAGES:
        raise IngestError(f"The PDF is a scan of {n_pages} pages; OCR reads at most {ocr.MAX_PAGES} "
                          "(SPREADER_OCR_MAX_PAGES). Split out the statement pages and upload those.")
    parts: list[_Part] = []
    unit_statements: list[str] = []
    for i in range(n_pages):
        try:
            words, _, height = ocr.page_words(data, i)
        except ocr.OCRError as exc:
            raise IngestError(f"{exc}. Try again, or upload a text PDF.") from exc
        if sum(1 for w in words if is_amount_like(w["text"])) < MIN_PAGE_NUMBERS:
            continue
        parts.extend(_parts_from_lines(_lines_from_words(words, height), i + 1, doc_id, len(parts)))
        if len(unit_statements) < 50:
            unit_statements.extend(document_unit_statements(" ".join(w["text"] for w in words)))
    warnings = [f"OCR: this PDF has no text layer, so its {n_pages} page(s) were read by optical character "
                + ("recognition; every value read from it is flagged for review." if ocr.REVIEW_ALL else
                   f"recognition; every value read with less than {ocr.MIN_CONFIDENCE:.0%} confidence is flagged for review.")]
    tables = _join_continued(parts, warnings)
    if not tables:
        raise IngestError("The PDF has no text layer and OCR found no pages with figures.")
    return DocumentIR(doc_id=doc_id, filename=filename, format=SourceFormat.PDF, tables=tables, warnings=warnings,
                      unit_statements=unit_statements[:50])


def _value_columns(table: RawTable) -> list[int]:
    return sorted({round(tok.x1) for r in table.rows for tok in r.tokens if is_amount_like(tok.text)
                   and not _YEARISH.match(tok.text)})


def _join_continued(parts: list[_Part], warnings: list[str]) -> list[RawTable]:
    """Join a page that continues the previous page's statement.

    It continues it when it comes straight after it (next page, nothing in between), has no
    title of its own (or a "(continued)" one), no new column headers (or the same years again),
    and its figures sit in the same columns; and the previous part did not end with "See
    accompanying notes". Repeated column-header rows of the continuation are left out.
    """
    out: list[_Part] = []
    for p in parts:
        if out:
            prev = out[-1]
            prev_cols, cols = _value_columns(prev.table), _value_columns(p.table)
            same_cols = bool(prev_cols) and bool(cols) and all(any(abs(c - q) <= 4 for q in prev_cols) for c in cols[:6])
            own_heading = (p.title or bool(p.header_rows)) and not p.continued
            same_years = bool(p.header_years) and p.header_years == prev.header_years
            follows = p.page == prev.last_page + 1 and p.first_on_page and prev.last_on_page and not prev.ended
            if follows and same_cols and (not own_heading or (not p.title and same_years)):
                t, base = p.table, prev.table
                offset = 1000 * p.page
                for r in t.rows:
                    if r.index in p.header_rows:
                        continue
                    r.index += offset
                    for tok in r.tokens:
                        tok.ref.row = r.index
                        tok.ref.table = base.index
                    base.rows.append(r)
                prev.last_page = p.page
                prev.ended = p.ended
                prev.last_on_page = p.last_on_page
                warnings.append(f"Page {p.page} continues the statement on page {prev.page}; read as one table.")
                continue
        out.append(p)
    tables: list[RawTable] = []
    for i, p in enumerate(out):
        p.table.index = i
        for r in p.table.rows:
            for tok in r.tokens:
                tok.ref.table = i
        tables.append(p.table)
    return tables
