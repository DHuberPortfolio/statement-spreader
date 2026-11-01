"""The same number printed twice counts as one confirmation, beside a check (D60).

Measured on the dev sets before building: with a repeated number counted, right values accepted alone went from 489 to
1,169 with none wrong. Counting a printed total's footing too let wrong values through (it proves the reading, not the
line), and so did a repeated number on a catch-all line, or with no check at all.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from conftest import statement_html
from spreader.contracts import CheckResult, CheckStatus, Echo, SourceFormat, SourceRef, SpreadValue, ValueStatus
from spreader.ingest import read_document
from spreader.pipeline import spread_document
from spreader.review import unconfirmed_items

HEAD = ["Year Ended December 31, 2025", "Year Ended December 31, 2024"]
P = "2025-12-31/12M"


def _body(title: str, rows: list[tuple]) -> str:
    return statement_html(title, "(in thousands)", HEAD, rows).split("<body>", 1)[1].rsplit("</body>", 1)[0]


INCOME = _body("CONSOLIDATED STATEMENTS OF INCOME", [
    ("Net sales", "10,000", "9,000"), ("Cost of sales", "(6,000)", "(5,500)"), ("Gross profit", "4,000", "3,500"),
    ("Selling, general and administrative", "(1,500)", "(1,400)"), ("Research and development", "(700)", "(650)"),
    ("Operating income", "1,800", "1,450"), ("Other income, net", "125", "110"), ("Income before income taxes", "1,925", "1,560"),
    ("Income tax expense", "(404)", "(328)"), ("Net income", "1,521", "1,232")])


def _note(rows: list[tuple]) -> str:
    return _body("NOTE 12. SEGMENT INFORMATION", rows)


def _spread(note_rows: list[tuple], profile: Any):  # type: ignore[no-untyped-def]
    html = f"<html><body>{INCOME}<p>Notes</p>{_note(note_rows)}</body></html>"
    spread, _ = spread_document(read_document("co.htm", html.encode()), profile)
    return spread


def test_a_number_printed_again_under_a_similar_label_is_an_echo(profile: Any) -> None:
    spread = _spread([("Research and development expense", "700", "650"), ("Capital expenditures", "300", "280")], profile)
    assert {(e.line, e.period) for e in spread.echoes} == {("rnd", P), ("rnd", "2024-12-31/12M")}
    v = spread.value("rnd", P)
    assert v is not None and any(s.kind == "confirm" and "research and development" in s.detail for s in v.steps)


def test_no_echo_for_a_different_label_a_catch_all_line_or_a_small_number(profile: Any) -> None:
    spread = _spread([("Freight costs", "700", "650"), ("Other income, net", "125", "110"),
                      ("Selling, general and administrative", "1,500", "1,400")], profile)
    lines = {e.line for e in spread.echoes}
    assert not any(ln.startswith("other_") for ln in lines), "a catch-all line is never confirmed by an echo"
    assert "sga" in lines and len({e.period for e in spread.echoes if e.line == "sga"}) == 2
    assert all(e.label != "freight costs" for e in spread.echoes)


def test_the_statements_own_table_is_not_an_echo(profile: Any) -> None:
    html = f"<html><body>{INCOME}</body></html>"
    spread, _ = spread_document(read_document("co.htm", html.encode()), profile)
    assert spread.echoes == []


def _echo(line: str, value: str = "5") -> Echo:
    return Echo(line=line, period=P, value=Decimal(value), label="x",
                ref=SourceRef(doc_id="d", format=SourceFormat.HTML, table=3, row=1, text=value))


def _v(line: str, value: str = "5") -> SpreadValue:
    return SpreadValue(line=line, period=P, value=Decimal(value), status=ValueStatus.EXTRACTED)


def _lines(values: list[SpreadValue], echoes: list[Echo], profile: Any) -> set[str]:
    checks = [CheckResult(id="is_net", title="t", period=P, status=CheckStatus.PASS,
                          lines=["net_income", "pretax_income", "income_tax"])]
    return {ln for it in unconfirmed_items(values, checks, [], profile, 2, echoes) for ln in it.lines}


def test_an_echo_and_a_check_confirm_but_an_echo_alone_does_not(profile: Any) -> None:
    values = [_v("income_tax"), _v("sga")]
    assert _lines(values, [], profile) == {"income_tax", "sga"}
    assert _lines(values, [_echo("income_tax"), _echo("sga")], profile) == {"sga"}


def test_an_echo_of_a_value_since_changed_confirms_nothing(profile: Any) -> None:
    assert _lines([_v("income_tax", "6")], [_echo("income_tax", "5")], profile) == {"income_tax"}
