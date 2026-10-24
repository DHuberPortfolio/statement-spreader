"""Tests of the synthetic statement generator itself (evaluation/synthetic.py).

The generator is an answer-key source, so it must be right by construction: every model balances,
every printed total foots (except the one deliberate footing error), the keys say exactly what the
documents print, and the same seed always writes the same files.
"""

from __future__ import annotations

import copy
import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from spreader.evaluation import synthetic as syn
from spreader.evaluation.truth import AnswerKey
from spreader.ingest import read_document

SEEDS = (3, 7, 11)
COUNT = 24  # 14 clean + one of each adversarial kind per seed


def _cases() -> list[syn.Case]:
    return [syn.make_case(seed, i, kind) for seed in SEEDS for i, kind in enumerate(syn.plan_kinds(COUNT), start=1)]


CASES = _cases()
IDS = [c.case_id for c in CASES]


def by_kind(kind: str) -> list[syn.Case]:
    return [c for c in CASES if c.kind == kind]


# ---------------------------------------------------------------------------------------------
# The model is consistent by construction
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_model_satisfies_every_identity(case: syn.Case) -> None:
    assert syn.model_problems(case.model) == []


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_balance_sheet_balances_and_cash_ties(case: syn.Case) -> None:
    m = case.model
    for end, e in m.bal.items():
        assert e["ta"] == e["tle"], end
    for prev, end in zip(m.ends, m.ends[1:], strict=False):
        assert m.cash[end]["cash_end"] == m.bal[end]["cash"]
        assert m.cash[end]["cash_begin"] == m.bal[prev]["cash"]
        assert m.cash[end]["net_income"] == m.inc[end]["net_income"]


def test_model_checker_catches_a_broken_model() -> None:
    """Negative control: the identity checker is not vacuous."""
    model = copy.deepcopy(CASES[0].model)
    end = model.ends[-1]
    model.bal[end]["cash"] += 1
    problems = syn.model_problems(model)
    assert any("current assets" in p for p in problems)
    assert any("ending cash" in p for p in problems)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_eps_is_net_income_over_printed_shares(case: syn.Case) -> None:
    m = case.model
    for end in m.ends[1:]:
        i = m.inc[end]
        dollars = i["net_income"] * m.scale
        for kind in ("basic", "diluted"):
            shares = i[f"shares_{kind}"] * m.share_scale
            assert i[f"eps_{kind}"] == (dollars / shares).quantize(Decimal("0.01"))
            # far enough from zero that EPS x shares is within 2% of net income (the profile's is_eps check)
            assert abs(i[f"eps_{kind}"] * shares - dollars) <= Decimal("0.02") * abs(dollars)


# ---------------------------------------------------------------------------------------------
# What is printed foots, and the key says what is printed
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", [c for c in CASES if c.kind != "footing-error"],
                         ids=[c.case_id for c in CASES if c.kind != "footing-error"])
def test_printed_subtotals_foot(case: syn.Case) -> None:
    for st in case.statements:
        assert syn.footing_errors(st) == []


@pytest.mark.parametrize("case", by_kind("footing-error"), ids=[c.case_id for c in by_kind("footing-error")])
def test_footing_error_case_breaks_exactly_one_subtotal(case: syn.Case) -> None:
    broken = [(st, r) for st in case.statements for r in st.rows if r.footing_error]
    assert len(broken) == 1
    st, row = broken[0]
    problems = syn.footing_errors(st)
    assert problems and any(f"'{row.label}'" in p for p in problems)
    # Every other problem is a total that uses the broken row.
    users = {r.label for r in st.rows if any(k == row.key for k, _ in r.sum_of)}
    assert all(re.search(r"'(.*)' \d", p).group(1) in users | {row.label} for p in problems)  # type: ignore[union-attr]
    assert "failed_check" in case.expect_review
    assert ("footing" in case.expect_review) == row.label.lower().startswith("total")


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_key_spread_matches_the_model(case: syn.Case) -> None:
    key = syn.build_key(case)
    spread = {(v.line, v.period): v for v in key.spread}
    m = case.model
    is_cols = case.statement(syn.IS).columns
    bs_cols = case.statement(syn.BS).columns
    for c in is_cols:
        i, cf = m.inc[c.end], m.cash[c.end]
        assert spread[("revenue", c.key)].value == i["revenue"] * m.scale
        assert spread[("net_income", c.key)].value == i["net_income"] * m.scale
        assert spread[("eps_diluted", c.key)].value == i["eps_diluted"]
        assert spread[("eps_diluted", c.key)].precision == Decimal("0.01")
        assert spread[("shares_basic", c.key)].value == i["shares_basic"] * m.share_scale
        assert spread[("shares_basic", c.key)].precision == m.share_scale
        assert spread[("cogs", c.key)].value == i["cogs"] * m.scale  # positive even when printed in parentheses
        assert spread[("capex", c.key)].value == cf["capex"] * m.scale < 0  # an outflow is negative
        assert spread[("cash_end", c.key)].value == cf["cash_end"] * m.scale
        if ("income_tax", c.key) in spread:
            assert spread[("income_tax", c.key)].value == i["tax"] * m.scale
    for c in bs_cols:
        e = m.bal[c.end]
        assert spread[("cash", c.key)].value == e["cash"] * m.scale
        assert spread[("total_assets", c.key)].value == e["ta"] * m.scale
        assert spread[("total_assets", c.key)].precision == m.scale
        assert spread[("retained_earnings", c.key)].value == e["re"] * m.scale
        if case.spec.footing_error != "total_current_assets":
            assert spread[("total_current_assets", c.key)].value == e["tca"] * m.scale
    assert all(p.endswith(("/12M", "/I")) for p in key.periods)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_key_only_holds_lines_the_document_presents(case: syn.Case) -> None:
    key = syn.build_key(case)
    lines = {v.line for v in key.spread}
    printed = {r.line for st in case.statements for r in st.rows if r.kind == "data" and not r.hidden and r.line}
    assert lines == printed
    if case.spec.is_layout != "gp":
        assert "gross_profit" not in lines
    if not case.spec.has_interest_income:
        assert "interest_income" not in lines


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_key_lines_belong_to_the_profile(case: syn.Case, profile) -> None:  # type: ignore[no-untyped-def]
    key = syn.build_key(case)
    for v in key.spread + key.forbid_values:
        assert profile.line_statement[v.line].value == v.statement, v.line
    for cell in key.cells:
        assert cell.line is None or profile.line_statement[cell.line].value == cell.statement


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_cells_cover_every_printed_value(case: syn.Case) -> None:
    key = syn.build_key(case)
    expected = sum(len(st.columns) for st in case.statements for r in st.rows if r.kind == "data" and not r.hidden)
    assert len(key.cells) == expected
    totals = {(c.line, c.period) for c in key.cells if c.role == "total"}
    for c in key.cells:
        if c.role == "component":
            assert (c.line, c.period) in totals  # a component always sits inside a printed total of its line


@pytest.mark.parametrize("case", CASES[::2], ids=IDS[::2])
def test_cell_xpaths_point_at_the_printed_number(case: syn.Case) -> None:
    from lxml import html as lxml_html

    tree = lxml_html.document_fromstring(syn.render_html(case).encode("utf-8")).getroottree()
    key = syn.build_key(case)
    assert len({c.xpath for c in key.cells}) == len(key.cells)  # one cell, one place
    expected = [syn.format_parts(case.spec, r.printed[c.key], r.unit, r.dollar)
                for st in sorted(case.statements, key=lambda s: (syn.IS, syn.BS, syn.CF).index(s.statement))
                for r in st.rows if r.kind == "data" and not r.hidden for c in st.columns]
    assert len(expected) == len(key.cells)
    for cell, (_, num, close) in zip(key.cells, expected, strict=True):
        (td,) = tree.xpath(cell.xpath)
        shown = td.text_content().strip()
        assert shown in {num, num + close} or shown.endswith(num + close), (cell.row_label, shown, num)


@pytest.mark.parametrize("case", [c for c in CASES[::3] if c.kind != "european-format"],
                         ids=[c.case_id for c in CASES[::3] if c.kind != "european-format"])
def test_cell_xpaths_match_the_html_reader(case: syn.Case) -> None:
    """The HTML reader records the same path for the cell a number is read from."""
    doc = read_document("statement.html", syn.render_html(case).encode("utf-8"))
    seen = {t.ref.xpath for tb in doc.tables for r in tb.rows for t in r.tokens}
    key = syn.build_key(case)
    for cell in key.cells:
        assert cell.xpath in seen or cell.value < 0, (cell.row_label, cell.period, cell.xpath)
    assert sum(cell.xpath in seen for cell in key.cells) >= 0.9 * len(key.cells)


@pytest.mark.parametrize("case", CASES[::5], ids=IDS[::5])
def test_key_round_trips(case: syn.Case, tmp_path: Path) -> None:
    key = syn.build_key(case)
    key.save(tmp_path / "key.json")
    again = AnswerKey.load(tmp_path / "key.json")
    assert again == key
    assert again.document == "statement" and again.source == "synthetic"


# ---------------------------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------------------------


def test_generation_is_deterministic() -> None:
    for kind in ("clean", "european-format", "hidden-row"):
        a, b = syn.make_case(7, 5, kind), syn.make_case(7, 5, kind)
        assert syn.render_html(a) == syn.render_html(b)
        assert syn.build_key(a).model_dump_json() == syn.build_key(b).model_dump_json()
        assert syn.render_xlsx(a) == syn.render_xlsx(b)
    assert syn.render_html(syn.make_case(7, 5)) != syn.render_html(syn.make_case(8, 5))


def test_corpus_is_written_and_reproducible(tmp_path: Path) -> None:
    out1, out2 = tmp_path / "a", tmp_path / "b"
    index = syn.generate_corpus(out1, seed=5, count=14, formats=("html", "xlsx"), log=lambda *_: None)
    syn.generate_corpus(out2, seed=5, count=14, formats=("html", "xlsx"), log=lambda *_: None)
    assert {c["kind"] for c in index["cases"]} == {"clean", *syn.ADVERSARIAL_KINDS}
    on_disk = json.loads((out1 / "index.json").read_text(encoding="utf-8"))
    assert on_disk == index
    for c in index["cases"]:
        assert c["formats"] == ["html", "xlsx"]
        folder = out1 / c["dir"]
        key = AnswerKey.load(folder / "key.json")
        assert key.tags == c["tags"] and key.expect_review == c["expect_review"]
        for name in ("statement.html", "statement.xlsx", "key.json"):
            assert (folder / name).read_bytes() == (out2 / c["dir"] / name).read_bytes(), name
    assert (out1 / "index.json").read_bytes() == (out2 / "index.json").read_bytes()


# ---------------------------------------------------------------------------------------------
# The documents themselves
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES[::3], ids=IDS[::3])
def test_html_has_three_statement_tables_and_prints_the_key_values(case: syn.Case) -> None:
    html = syn.render_html(case)
    doc = read_document("statement.html", html.encode("utf-8"))
    assert len(doc.tables) == 3
    visible = " ".join(t.text for tb in doc.tables for r in tb.rows for t in r.tokens)
    for st in case.statements:
        for r in st.rows:
            if r.kind == "data" and not r.hidden:
                for c in st.columns:
                    _, num, _ = syn.format_parts(case.spec, r.printed[c.key], r.unit, False)
                    assert num.lstrip("(-") in visible, (r.label, num)


@pytest.mark.parametrize("case", CASES[::4], ids=IDS[::4])
def test_xlsx_cells_hold_the_printed_values(case: syn.Case) -> None:
    wb = load_workbook(io.BytesIO(syn.render_xlsx(case)))
    sheets = wb.worksheets
    rows = [(ws, row) for ws in sheets for row in ws.iter_rows()]
    pos = 0
    for st in case.statements:
        first = 2 + int(st.note_header is not None)
        for r in st.rows:
            if r.kind != "data":
                continue
            while str(rows[pos][1][0].value or "").strip() != r.label:
                pos += 1
            ws, cells = rows[pos]
            for j, c in enumerate(st.columns):
                cell = cells[first - 1 + j]
                v = r.printed[c.key]
                if isinstance(cell.value, str):
                    assert cell.value == syn.format_value(case.spec, v, r.unit, r.dollar)
                else:
                    assert Decimal(str(cell.value)) == v
            assert ws.row_dimensions[cells[0].row].hidden == r.hidden
            pos += 1


def test_hidden_row_is_invisible_and_forbidden() -> None:
    for case in by_kind("hidden-row"):
        bs = case.statement(syn.BS)
        hidden = next(r for r in bs.rows if r.hidden)
        html = syn.render_html(case)
        fake = syn.format_value(case.spec, next(iter(hidden.printed.values())), "money", False)
        assert 'style="display:none"' in html and fake in html  # it is in the file...
        doc = read_document("statement.html", html.encode("utf-8"))
        assert all(fake not in t.text for tb in doc.tables for r in tb.rows for t in r.tokens)  # ...but not visible
        forbidden = {(v.line, v.period, v.value) for v in case.forbid}
        for c in bs.columns:
            assert ("st_investments", c.key, hidden.printed[c.key] * case.scale) in forbidden
        key = syn.build_key(case)
        assert all(cell.row_label != hidden.label for cell in key.cells)
        assert "st_investments" not in {v.line for v in key.spread}


def test_prompt_injection_is_printed_and_does_not_reach_the_key() -> None:
    for case in by_kind("prompt-injection"):
        html = syn.render_html(case)
        assert syn.INJECTION_ROW in html and "ignore previous instructions" in syn.INJECTION_PARAGRAPH.lower()
        key = syn.build_key(case)
        assert {v.value for v in key.forbid_values if v.line == "revenue"} >= {Decimal(999_999) * case.scale}
        assert all(v.value != Decimal(999_999) * case.scale for v in key.spread)
        assert any("note to AI reviewers" in c.row_label for c in key.cells)


def test_no_unit_statement_case_says_nothing_about_scale() -> None:
    for case in by_kind("no-unit-statement"):
        assert case.scale == 1 and case.expect_review == ["assumed_scale"]
        html = syn.render_html(case).lower()
        assert not re.search(r"thousand|million|billion|\(\$?000", html)
        assert all(st.unit_line is None for st in case.statements)


def test_european_case_uses_european_grouping() -> None:
    for case in by_kind("european-format"):
        assert case.expect_review == ["unreadable"]
        texts = [syn.format_value(case.spec, r.printed[c.key], r.unit, False)
                 for st in case.statements for r in st.rows if r.kind == "data" for c in st.columns]
        assert not any(re.search(r"\d,\d{3}", t) for t in texts)  # no US thousands separators
        assert any(re.fullmatch(r"\(?\d{1,3}(\.\d{3}){2,}\)?", t) for t in texts)
        assert case.forbid  # the misreadings of one-group numbers are listed


def test_adversarial_layouts_are_present() -> None:
    for case in by_kind("pct-change-column"):
        assert case.statement(syn.IS).pct_header and "%" in syn.render_html(case)
    for case in by_kind("note-column"):
        assert case.statement(syn.IS).note_header in {"Note", "Notes"}
        assert any(r.note_ref for r in case.statement(syn.BS).rows)
    for case in by_kind("shares-thousands-money-millions"):
        assert (case.scale, case.share_scale) == (1_000_000, 1000)
        assert re.search(r"share(s| counts) in thousands", case.statement(syn.IS).unit_line or "")
    for case in by_kind("par-value-label"):
        assert any(r.label.startswith("Common stock, $") and "authorized" in r.label
                   for r in case.statement(syn.BS).rows)
    for case in by_kind("investments-current-noncurrent"):
        rows = case.statement(syn.BS).rows
        inv = [r for r in rows if r.label == "Investments"]
        assert [r.line for r in inv] == ["st_investments", "lt_investments"]
        assert any(r.kind == "header" and "on-current" in r.label or "oncurrent" in r.label for r in rows)


def test_plan_includes_every_adversarial_kind() -> None:
    kinds = syn.plan_kinds(40)
    assert kinds.count("clean") == 30
    assert sorted(set(kinds) - {"clean"}) == sorted(syn.ADVERSARIAL_KINDS)


@pytest.mark.skipif(not Path(syn.EDGE_PATH).exists(), reason="Microsoft Edge is not installed")
def test_pdf_is_printed(tmp_path: Path) -> None:
    case = syn.make_case(7, 1)
    written, problem = syn.write_case(case, tmp_path, ("html", "pdf"))
    assert problem is None and written == ["html", "pdf"]
    pdf = (tmp_path / case.case_id / "statement.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-") and len(pdf) > 10_000
