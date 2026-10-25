"""Two HTML reader bugs found by an outside test run (2026-10-24, evening).

1. lxml 6 wheels built on libxml2 2.14 (Linux, macOS) stop parsing at the first </html>: a file holding two
   statements, one document after the other, lost the second without a word. The Windows wheel bundles libxml2
   2.11, which reads on, so it never showed here; the fixture below parses the way the newer library does.
2. Deckers' 10-K wraps every page in a font-size:0 element and sizes the text inside. The reader took font-size:0
   to hide everything inside it, found "no tables with numbers" and dropped the filing from the holdout.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import html as lxml_html

from conftest import statement_html
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from test_pipeline import BS_ROWS, IS_ROWS, _doc
from test_redteam import FAKE, HEAD, IS


@pytest.fixture
def stops_at_first_html_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parse the way lxml 6 on libxml2 2.14 does: nothing after the first </html> survives."""
    real = lxml_html.document_fromstring

    def parse(data, *args, **kwargs):  # type: ignore[no-untyped-def]
        m = re.search(rb"</html\s*>", data, re.I) if isinstance(data, bytes) else None
        return real(data[: m.end()] if m else data, *args, **kwargs)

    monkeypatch.setattr(lxml_html, "document_fromstring", parse)


def test_a_second_document_in_the_file_is_read(profile, stops_at_first_html_end) -> None:  # type: ignore[no-untyped-def]
    two = _doc(IS_ROWS, ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]) + _doc(
        BS_ROWS, ["December 31, 2025", "December 31, 2024"], title="CONSOLIDATED BALANCE SHEETS")
    ir = read_document("t.htm", two.encode())
    assert len(ir.tables) == 2
    spread, _ = spread_document(ir, profile)
    assert set(spread.statements) == {"income_statement", "balance_sheet"}


def _inner(page: str) -> str:
    return page.removeprefix("<html><body>").removesuffix("</body></html>")


def test_text_sized_inside_a_zero_font_wrapper_is_read(profile) -> None:  # type: ignore[no-untyped-def]
    page = _inner(statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, IS))
    doc = f'<html><body><div style="font-size:0"><div style="font-size:0pt"><div style="font-size:8pt">{page}</div></div></div></body></html>'
    spread, _ = spread_document(read_document("d.htm", doc.encode()), profile)
    assert spread.value("revenue", "2025-12-31/12M").value == Decimal(400_000)


@pytest.mark.parametrize("hide", ['style="font-size:0"', 'style="font-size:0.0pt"', 'class="z"'])
def test_zero_font_text_stays_hidden_inside_sized_text(profile, hide: str) -> None:  # type: ignore[no-untyped-def]
    fake = _inner(statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, FAKE))
    real = _inner(statement_html("STATEMENTS OF OPERATIONS", "(In thousands)", HEAD, IS))
    doc = (f'<html><head><style>.z {{ font-size: 0 }}</style></head><body><div style="font-size:10pt">'
           f"<div {hide}>{fake}</div>{real}</div></body></html>")
    spread, _ = spread_document(read_document("h.htm", doc.encode()), profile)
    assert spread.value("revenue", "2025-12-31/12M").value == Decimal(400_000)


RAW = Path(__file__).resolve().parents[1] / "eval" / "sec" / "raw"


@pytest.mark.skipif(not list(RAW.glob("DECK-*")), reason="Deckers filing not downloaded (scripts/fetch_sec.py)")
def test_deckers_filing_is_read(profile) -> None:  # type: ignore[no-untyped-def]
    p = next(RAW.glob("DECK-*"))
    spread, _ = spread_document(read_document(p.name, p.read_bytes()), profile)
    assert set(spread.statements) == {"income_statement", "balance_sheet", "cash_flow"}
