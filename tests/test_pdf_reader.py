"""The PDF reader on small PDFs printed with Edge from tiny HTML statements.

Each PDF is printed once per test session (about a second each); the tests are skipped when
headless Edge is not installed. A few tests feed hand-made word positions to the line splitter
and need no PDF at all.

What is checked: running footers and page numbers are dropped; a label that wraps onto a second
line is one label; a page holding two statements is split at the second title, and each part
keeps its own title and unit statement as context; a statement continued on the next page is
joined; every token keeps its page and bounding box (the interface draws its highlight from
them).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest

from spreader.ingest import pdf_tables
from spreader.pipeline import spread_document

EDGE_CANDIDATES = [
    os.environ.get("SPREADER_EDGE", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    shutil.which("msedge") or "",
    shutil.which("microsoft-edge") or "",
]
EDGE = next((p for p in EDGE_CANDIDATES if p and Path(p).exists()), None)
needs_edge = pytest.mark.skipif(EDGE is None, reason="headless Edge is not installed")

STYLE = """
<style>
  body { font-family: 'Times New Roman', serif; font-size: 10pt; margin: 0; }
  h1, h2 { font-size: 10pt; text-align: center; margin: 2pt 0; }
  p.unit { text-align: center; margin: 2pt 0 8pt 0; }
  table { border-collapse: collapse; width: 100%; }
  td { padding: 1pt 2pt; vertical-align: bottom; }
  td.label { width: 55%; }
  td.narrow { width: 30%; }
  td.num { text-align: right; width: 12%; }
  td.cur { width: 2%; }
  .footer { position: fixed; bottom: 0; left: 0; right: 0; text-align: center; font-size: 8pt; }
  .break { page-break-before: always; }
</style>
"""


def _row(label: str, *values: str, cls: str = "label") -> str:
    """A statement row in SEC style: "$" in its own cell, left of the right-aligned figure."""
    cells = "".join(f'<td class="cur">{"$" if v.startswith("$") else ""}</td><td class="num">{v.lstrip("$")}</td>'
                    for v in values)
    return f'<tr><td class="{cls}">{label}</td>{cells}</tr>'


def _header(*cols: str) -> str:
    return "<tr><td></td>" + "".join(f'<td colspan="2" class="num">{c}</td>' for c in cols) + "</tr>"


TWO_STATEMENTS = f"""<html><head>{STYLE}</head><body>
<div class="footer">Example Holdings Corp. | 2025 Form 10-K | 37</div>
<h1>EXAMPLE HOLDINGS CORP.</h1>
<h2>CONSOLIDATED STATEMENTS OF OPERATIONS</h2>
<p class="unit">(In millions, except per share amounts)</p>
<table>
  <tr><td></td><td colspan="4" class="num" style="text-align:center">Years ended December 31,</td></tr>
  {_header("2025", "2024")}
  {_row("Net sales", "$1,250", "$1,100")}
  {_row("Cost of sales", "700", "650")}
  {_row("Gross profit", "550", "450")}
  {_row("Selling, general and administrative expenses including the costs of operating the regional "
        "distribution network", "200", "180", cls="narrow")}
  {_row("Operating income", "350", "270")}
  {_row("Provision for income taxes", "70", "54")}
  {_row("Net income", "$280", "$216")}
</table>
<h2 style="margin-top:24pt">CONSOLIDATED BALANCE SHEETS</h2>
<p class="unit">(In thousands)</p>
<table>
  {_header("December 31, 2025", "December 31, 2024")}
  {_row("Cash and cash equivalents", "$4,321", "$3,210")}
  {_row("Accounts receivable, net", "987", "876")}
  {_row("Total current assets", "5,308", "4,086")}
  {_row("Total assets", "$9,876", "$8,765")}
</table>
<p>See accompanying notes to the consolidated financial statements.</p>
</body></html>"""

CONTINUED = f"""<html><head>{STYLE}</head><body>
<h2>CONSOLIDATED BALANCE SHEETS</h2>
<p class="unit">(In millions)</p>
<table>
  {_header("2025", "2024")}
  {_row("Cash and cash equivalents", "$4,321", "$3,210")}
  {_row("Accounts receivable, net", "987", "876")}
  {_row("Inventories", "1,111", "999")}
  {_row("Total current assets", "6,419", "5,085")}
</table>
<table class="break">
  {_row("Property, plant and equipment, net", "2,222", "2,100")}
  {_row("Total assets", "$8,641", "$7,185")}
  {_row("Accounts payable", "$1,500", "$1,400")}
  {_row("Total liabilities", "4,000", "3,800")}
</table>
<h2 class="break">CONSOLIDATED STATEMENTS OF SHAREHOLDERS' EQUITY</h2>
<p class="unit">(In millions)</p>
<table>
  {_header("2025", "2024")}
  {_row("Total shareholders' equity, beginning balances", "$3,385", "$3,100")}
  {_row("Net income", "280", "216")}
  {_row("Dividends declared", "(19)", "(16)")}
  {_row("Total shareholders' equity, ending balances", "$3,646", "$3,300")}
</table>
<h1 class="break">EXAMPLE HOLDINGS CORP.</h1>
<h2>CONSOLIDATED STATEMENTS OF CASH FLOWS</h2>
<p class="unit">(In millions)</p>
<table>
  <tr><td></td><td colspan="4" class="num" style="text-align:center">Years ended</td></tr>
  {_header("December 31,", "December 31,")}
  {_header("2025", "2024")}
  {_row("Net income", "$280", "$216")}
  {_row("Depreciation and amortization", "90", "85")}
  {_row("Net cash provided by operating activities", "370", "301")}
</table>
</body></html>"""


def _print(html: str, out: Path) -> Path:
    src = out.with_suffix(".html")
    src.write_text(html, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="edge-profile-") as profile:
        subprocess.run([str(EDGE), "--headless", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                        f"--user-data-dir={profile}", f"--print-to-pdf={out.resolve()}", src.resolve().as_uri()],
                       capture_output=True, timeout=120, check=False)
    if not out.exists() or out.stat().st_size < 500:
        pytest.skip("Edge did not print the test PDF")
    return out


@pytest.fixture(scope="module")
def two_statements(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _print(TWO_STATEMENTS, tmp_path_factory.mktemp("pdf") / "two.pdf")


@pytest.fixture(scope="module")
def continued(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _print(CONTINUED, tmp_path_factory.mktemp("pdf") / "continued.pdf")


def _read(path: Path):  # type: ignore[no-untyped-def]
    return pdf_tables.read_pdf(path.name, path.read_bytes())


def _texts(table) -> list[str]:  # type: ignore[no-untyped-def]
    return [t.text for r in table.rows for t in r.tokens]


def _labels(table) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.tokens[0].text for r in table.rows if r.tokens]


@needs_edge
def test_footer_and_page_number_are_dropped(two_statements: Path) -> None:
    with pdfplumber.open(two_statements) as pdf:
        assert "Form 10-K" in (pdf.pages[0].extract_text() or "")  # the footer is printed
    doc = _read(two_statements)
    every = [t for table in doc.tables for t in _texts(table)] + [table.context for table in doc.tables]
    assert not any("Form 10-K" in t or t == "37" for t in every)


@needs_edge
def test_page_with_two_statements_is_split_at_the_second_title(two_statements: Path) -> None:
    doc = _read(two_statements)
    assert len(doc.tables) == 2
    ops, bs = doc.tables
    assert "STATEMENTS OF OPERATIONS" in ops.context and "In millions" in ops.context
    assert "BALANCE SHEETS" in bs.context and "In thousands" in bs.context
    assert "BALANCE SHEETS" not in ops.context and "In millions" not in bs.context
    assert "Net income" in _labels(ops) and "Cash and cash equivalents" not in _labels(ops)
    assert "Cash and cash equivalents" in _labels(bs) and "Net income" not in _labels(bs)
    # the end marker is not a row
    assert not any("accompanying notes" in t for t in _texts(bs))


@needs_edge
def test_wrapped_label_is_one_row_with_its_values(two_statements: Path) -> None:
    with pdfplumber.open(two_statements) as pdf:
        words = pdf.pages[0].extract_words()
    tops = {round(w["top"]) for w in words if w["text"] in {"Selling,", "distribution"}}
    assert len(tops) == 2  # the label really is printed on two lines
    ops = _read(two_statements).tables[0]
    row = next(r for r in ops.rows if r.tokens[0].text.startswith("Selling, general"))
    assert row.tokens[0].text.endswith("regional distribution network")
    assert [t.text for t in row.tokens[1:]] == ["200", "180"]


@needs_edge
def test_tokens_keep_page_and_bbox(two_statements: Path) -> None:
    with pdfplumber.open(two_statements) as pdf:
        page = pdf.pages[0]
        width, height = float(page.width), float(page.height)
        printed = next(w for w in page.extract_words() if w["text"] == "4,321")
    doc = _read(two_statements)
    for table in doc.tables:
        for r in table.rows:
            for t in r.tokens:
                assert t.ref.page == 1 and t.ref.table == table.index and t.ref.row == r.index
                x0, top, x1, bottom = t.ref.bbox
                assert 0 <= x0 <= x1 <= width and 0 <= top <= bottom <= height
    cash = next(t for t in _texts_tokens(doc.tables[1]) if t.text.endswith("4,321"))
    x0, top, x1, bottom = cash.ref.bbox
    # the box covers the printed number (and the "$" printed apart from it, to its left)
    assert x0 <= printed["x0"] + 0.01 and abs(x1 - printed["x1"]) < 0.01
    assert abs(top - printed["top"]) < 0.5 and abs(bottom - printed["bottom"]) < 0.5


def _texts_tokens(table):  # type: ignore[no-untyped-def]
    return [t for r in table.rows for t in r.tokens]


@needs_edge
def test_spread_reads_units_and_periods_from_the_pdf(two_statements: Path, profile) -> None:  # type: ignore[no-untyped-def]
    spread, _ = spread_document(_read(two_statements), profile)
    income = spread.statements["income_statement"].table
    assert income.scale.multiplier == 1_000_000 and not income.scale.assumed
    assert [p.key for p in income.periods] == ["2025-12-31/12M", "2024-12-31/12M"]
    assert not any(p.assumed for p in income.periods)  # "Years ended" spans both columns
    v = spread.value("net_income", "2025-12-31/12M")
    assert v is not None and v.value == Decimal("280000000")


@needs_edge
def test_statement_continued_on_next_page_is_joined(continued: Path) -> None:
    """Page 2 continues the balance sheet. Page 3 is a one-page equity statement; page 4 starts
    a new statement whose year headers come below its company name, title, unit and "Years
    ended" lines (the case that glued Apple's cash flow statement onto its equity statement)."""
    doc = _read(continued)
    assert len(doc.tables) == 3  # balance sheet (two pages), equity statement, cash flow statement
    bs, equity, cf = doc.tables
    labels = _labels(bs)
    assert "Inventories" in labels and "Total liabilities" in labels
    assert {t.ref.page for t in _texts_tokens(bs)} == {1, 2}
    assert all(t.ref.table == 0 for t in _texts_tokens(bs))
    assert {t.ref.page for t in _texts_tokens(equity)} == {3}
    assert "Depreciation and amortization" in _labels(cf) and "Depreciation and amortization" not in _labels(equity)
    assert "CASH FLOWS" in cf.context
    assert [w for w in doc.warnings if "continues the statement" in w] == [
        "Page 2 continues the statement on page 1; read as one table."]


# ---------------------------------------------------------------- line splitting, no PDF needed


def _words(*spec: tuple[str, float, float]) -> list[dict]:
    return [{"text": t, "x0": x0, "x1": x1, "top": 100.0, "bottom": 110.0, "size": 10.0} for t, x0, x1 in spec]


def test_cells_keep_numbers_that_belong_to_the_label() -> None:
    line = _words(("Common", 30, 62), ("stock,", 64, 88), ("$0.01", 90, 112), ("par", 114, 126), ("value;", 128, 152),
                  ("50,000", 154, 180), ("shares", 182, 206), ("authorized", 208, 250),
                  ("1,234", 420, 444), ("1,100", 500, 524))
    cells = [c.text for c in pdf_tables._cells(line)]
    assert cells == ["Common stock, $0.01 par value; 50,000 shares authorized", "1,234", "1,100"]


def test_cells_keep_dates_and_footnote_markers_with_text() -> None:
    line = _words(("fiscal", 30, 52), ("years", 54, 76), ("ended", 78, 102), ("June", 104, 122), ("30", 124, 134),
                  ("2026", 420, 440), ("2025", 500, 520))
    assert [c.text for c in pdf_tables._cells(line)] == ["fiscal years ended June 30", "2026", "2025"]
    marker = _words(("Net", 30, 44), ("earnings", 46, 80), ("(1)", 82, 92), ("6.75", 420, 440))
    marker[2]["size"] = 6.0  # printed as a superscript
    assert [c.text for c in pdf_tables._cells(marker)] == ["Net earnings (1)", "6.75"]


def test_cells_merge_a_dollar_sign_printed_apart_but_never_end_a_figure_with_one() -> None:
    line = _words(("Cash", 30, 50), ("$", 380, 386), ("10,270", 470, 500), ("$", 503, 509), ("10,828", 560, 590))
    assert [c.text for c in pdf_tables._cells(line)] == ["Cash", "$ 10,270", "$ 10,828"]


def test_running_header_with_page_number_is_a_footer() -> None:
    header = _words(("38", 34, 42), ("The", 44, 56), ("Example", 58, 90), ("Company", 92, 130))
    for w in header:
        w["top"], w["bottom"] = 28.0, 36.0
    assert pdf_tables._is_footer(header, page_height=792.0)
    row = _words(("Net", 34, 50), ("sales", 52, 75), ("38", 420, 430), ("41", 500, 510))
    assert not pdf_tables._is_footer(row, page_height=792.0)
