"""Workbooks laid out the way the SEC's Financial_Report.xlsx is (DECISIONS D56), found on real workbooks:

- share counts sit among money rows and say so only in the label ("Common stock, shares issued (in shares)");
- a statement is followed by its breakdown ("Service" / "Revenues", "Product" / "Revenues") with no indentation, so the
  breakdown rows land on the same line as the statement's own row.
"""

from __future__ import annotations

import io
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from openpyxl import Workbook

from spreader.contracts import ParsedValue, ValueUnit
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.spread import _total_of_the_others
from spreader.structure import _unit

NBSP = "\xa0"


def _xlsx(title: str, rows: list[list[Any]], dates: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append([title, *dates[:1], *([None] * (len(dates) - 1))])
    ws.append([None, *dates])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


INCOME = [
    ["Revenues", 91361, 88898], ["Cost of revenues", -59000, -58000], ["Selling, general and administrative", -15759, -15336],
    ["Operating income", 16602, 15562], ["Interest expense, net", -1260, -1209], ["Income before income taxes", 15342, 14353],
    ["Income taxes", -1796, -1379], ["Net income", 13546, 12974],
    ["Service", NBSP, NBSP], ["Revenues", 81841, 79562], ["Product", NBSP, NBSP], ["Revenues", 9520, 9336],
]


def test_a_breakdown_under_the_statement_is_not_added_onto_its_total(profile: Any) -> None:
    data = _xlsx("CONSOLIDATED STATEMENTS OF INCOME - USD ($) $ in Millions", INCOME,
                 ["Sep. 28, 2024", "Sep. 30, 2023"])
    spread, _ = spread_document(read_document("income.xlsx", data), profile)
    rev = {v.period: v for v in spread.values if v.line == "revenue"}
    assert {p: v.value for p, v in rev.items()} == {"2024-09-28/12M": Decimal(91_361_000_000),
                                                    "2023-09-30/12M": Decimal(88_898_000_000)}
    assert any("equals the sum of the other 2 row(s)" in s.detail for s in rev["2024-09-28/12M"].steps)


BALANCE = [
    ["Cash and cash equivalents", 29943, 29965], ["Total assets", 364980, 352583],
    ["Total liabilities", 308030, 290437],
    ["Common stock, shares outstanding (in shares)", 15116786, 15550061],
    ["Common stock, shares issued (in shares)", 15116786, 15550061],
    ["Common stock and additional paid-in capital, $0.00001 par value: 50,400,000 shares authorized", 83276, 73812],
    ["Accumulated deficit", -19154, -214], ["Total shareholders' equity", 56950, 62146],
    ["Total liabilities and shareholders' equity", 364980, 352583],
]


def test_share_counts_that_say_so_are_not_money(profile: Any) -> None:
    data = _xlsx("CONSOLIDATED BALANCE SHEETS - USD ($) shares in Thousands, $ in Millions", BALANCE,
                 ["Sep. 28, 2024", "Sep. 30, 2023"])
    spread, _ = spread_document(read_document("bs.xlsx", data), profile)
    apic = spread.value("common_stock_apic", "2024-09-28/I")
    assert apic is not None and len(apic.source_rows) == 1, "the share counts are not added in"
    assert apic.value == Decimal(83_276_000_000), "and the title's '$ in Millions' is the unit"


def test_the_secs_title_states_the_money_unit_after_the_share_unit() -> None:
    from spreader.detect import detect_scale

    money, shares = detect_scale(["CONSOLIDATED BALANCE SHEETS - USD ($) shares in Thousands, $ in Millions"])
    assert (money.multiplier, money.evidence) == (1_000_000, "$ in Millions")
    assert shares is not None and shares.multiplier == 1_000
    money, shares = detect_scale(["Weighted average shares in thousands"])
    assert money.multiplier == 1, "a share unit alone is still not a money unit"
    # Apple's heading: the thousands after "shares, which are" are shares; an early version of this fix took them for
    # money and turned 146 right values of Apple's 10-K into 58 (caught on the real filing, not by a test until now)
    for texts in (["(In millions, except number of shares, which are reflected in thousands, and per-share amounts)"],
                  ["", "", "CONSOLIDATED STATEMENTS OF OPERATIONS (In millions, except number of shares, which are "
                               "reflected in thousands, and per-share amounts)"]):
        money, shares = detect_scale(texts)
        assert money.multiplier == 1_000_000 and shares is not None and shares.multiplier == 1_000


def test_a_stated_unit_decides_before_words_in_the_label() -> None:
    assert _unit("common stock shares authorized in shares", "", ["50,400,000"],
                 "Common stock, shares authorized (in shares)") is ValueUnit.SHARES
    assert _unit("common stock shares issued in shares", "", ["15,116,786"],
                 "Common stock, shares issued (in shares)") is ValueUnit.SHARES
    assert _unit("basic in dollars per share", "", ["2.72"], "Basic (in dollars per share)") is ValueUnit.PER_SHARE
    assert _unit("diluted shares", "", ["1,831"], "Diluted (shares)") is ValueUnit.SHARES
    # without a stated unit nothing changes: par value and authorized shares in a money label stay money
    assert _unit("common stock 0 01 par value 100 shares authorized", "", ["41"],
                 "Common stock, $0.01 par value, 100 shares authorized") is ValueUnit.MONEY


def _rows(values: dict[str, list[str | None]]) -> tuple[list[int], dict[int, Any], list[Any]]:
    periods = [SimpleNamespace(key=k) for k in ("a", "b")]
    by_index = {}
    for i, (_, vals) in enumerate(values.items()):
        by_index[i] = SimpleNamespace(label=f"row{i}", values={
            p.key: ParsedValue(raw=v or "", displayed=Decimal(v) if v is not None else None)
            for p, v in zip(periods, vals, strict=True)})
    return list(by_index), by_index, periods


def test_the_total_is_found_only_when_it_holds_in_every_period() -> None:
    src, rows, periods = _rows({"total": ["100", "90"], "p1": ["60", "50"], "p2": ["40", "40"]})
    assert _total_of_the_others(src, rows, periods) == 0
    src, rows, periods = _rows({"a": ["10", "20"], "b": ["10", "20"]})
    assert _total_of_the_others(src, rows, periods) == 0, "a figure printed twice is counted once"
    src, rows, periods = _rows({"total": ["100", "95"], "p1": ["60", "50"], "p2": ["40", "40"]})
    assert _total_of_the_others(src, rows, periods) is None, "one period disagrees: separate rows, added"
    src, rows, periods = _rows({"a": ["10", "5"], "b": ["7", "3"]})
    assert _total_of_the_others(src, rows, periods) is None, "independent rows are still added"
    src, rows, periods = _rows({"a": ["0", "0"], "b": ["0", "0"]})
    assert _total_of_the_others(src, rows, periods) is None, "nothing to tell from zeros"
    src, rows, periods = _rows({"eps": ["2.72", "1.29"], "c": ["2.72", "1.29"]})
    assert _total_of_the_others(src, rows, periods) == 0
    src, rows, periods = _rows({"total": ["100.1", None], "p1": ["60", "50"], "p2": ["40", "40"]})
    assert _total_of_the_others(src, rows, periods) == 0, "within the rounding of two parts printed to one decimal"
    src, rows, periods = _rows({"total": ["100.3", None], "p1": ["60", "50"], "p2": ["40", "40"]})
    assert _total_of_the_others(src, rows, periods) is None, "beyond printed rounding"
