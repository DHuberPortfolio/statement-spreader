"""The industry ontology (D67): the same words mean different things by industry, statement and place on the page."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from spreader.contracts import ParsedValue, RowRole, Scale, StatementRow, StatementTable, StatementType
from spreader.mapping import map_row, map_table
from spreader.ontology import SIGNATURE_MIN, clean, load
from spreader.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
ONT = load()
PROFILE = load_profile(None)
LINES = set(PROFILE.lines) | set(load_profile(ROOT / "config/profiles/us-bank.yaml").lines) | set(load_profile(ROOT / "config/profiles/us-insurer.yaml").lines)
ENERGY, REIT = frozenset({"energy"}), frozenset({"real_estate"})


def _row(label: str, section: str = "", index: int = 1, role: RowRole = RowRole.DETAIL, value: str | None = None, **kw) -> StatementRow:
    values = {"p": ParsedValue(raw=value, displayed=Decimal(value))} if value else {}
    return StatementRow(index=index, label=label, label_clean=clean(label), section=section, role=role, values=values, **kw)


def _table(stype: StatementType, *rows: StatementRow) -> StatementTable:
    return StatementTable(doc_id="d", table_index=0, statement=stype, title="t", rows=list(rows), periods=[], scale=Scale(multiplier=1, evidence="t"))


def _place(label: str, stype: StatementType, industries: frozenset[str], section: str = ""):
    row = _row(label, section)
    return map_row(row, _table(stype, row), PROFILE, industries=industries)


def test_every_term_devin_listed_resolves_to_a_concept() -> None:
    terms = [t.strip() for t in (ROOT / "tests/fixtures/ontology_requested_terms.txt").read_text(encoding="utf-8").splitlines()]
    missing = [t for t in terms if t and not t.startswith("#") and not ONT._hits(clean(re.sub(r"\s*\([^)]*\)", "", t)))]
    assert missing == []


def test_every_concept_has_the_twelve_fields_it_promises() -> None:
    assert len(ONT.concepts) > 450
    for c in ONT.concepts:
        assert c.label and c.industry and c.family and c.statement and c.unit and c.sign and c.review and c.source, c.id
        assert c.role == "disclosure" or c.destination or c.current or c.noncurrent, c.id


def test_every_destination_is_a_real_template_line() -> None:
    for c in ONT.concepts:
        for d in [*c.destination, c.current, c.noncurrent, c.in_cash_flow]:
            assert d is None or d in LINES, (c.id, d)


def test_three_operating_expenses_share_a_family_but_stay_three_concepts() -> None:
    a = ONT.by_id["energy.lease_operating_expenses"]
    b = ONT.by_id["real_estate.property_operating_expenses"]
    c = ONT.by_id["utilities.utility_operating_expenses"]
    assert a.family == b.family == c.family == "operating_expense"
    assert len({a.id, b.id, c.id}) == 3


def test_gross_and_net_rental_revenue_are_not_synonyms() -> None:
    gross, net = ONT.by_id["real_estate.rental_revenue"], ONT.by_id["real_estate.net_rental_income"]
    assert "net rental income" not in gross.terms
    assert ONT.match("net rental income", "income_statement", [], REIT, LINES).concept.id == net.id


def test_a_term_only_applies_in_its_own_industry() -> None:
    assert _place("Lease operating expenses", StatementType.INCOME, ENERGY).concept == "energy.lease_operating_expenses"
    assert _place("Lease operating expenses", StatementType.INCOME, REIT).concept is None


def test_two_signature_terms_are_needed_to_name_an_industry() -> None:
    assert SIGNATURE_MIN == 2
    assert "energy" not in ONT.industries(["lease operating expenses"])
    assert "energy" in ONT.industries(["lease operating expenses", "exploration expenses"])


def test_the_same_words_follow_the_statement() -> None:
    assert _place("Depletion, depreciation and amortization", StatementType.INCOME, ENERGY).canonical == "dna_opex"
    assert _place("Depletion, depreciation and amortization", StatementType.CASH_FLOW, ENERGY).canonical == "cf_dna"


def test_current_and_noncurrent_follow_the_section() -> None:
    assert _place("Regulatory assets", StatementType.BALANCE, frozenset({"utilities"}), "current assets").canonical == "other_current_assets"
    assert _place("Regulatory assets", StatementType.BALANCE, frozenset({"utilities"}), "other assets").canonical == "other_noncurrent_assets"


def test_a_disclosure_never_lands_on_a_line() -> None:
    m = _place("Funds from operations", StatementType.INCOME, REIT)
    assert m.canonical is None and m.excluded and m.rule == "ontology.disclosure"


def test_rooms_is_revenue_under_revenue_and_a_cost_under_expenses() -> None:
    assert _place("Rooms", StatementType.INCOME, REIT, "revenues").canonical == "revenue"
    assert _place("Rooms", StatementType.INCOME, REIT, "operating expenses").canonical == "other_opex"


def test_concepts_that_disagree_are_left_for_a_person() -> None:
    both = frozenset({"energy", "transportation"})
    assert ONT.match("transportation revenue", "income_statement", [], both, LINES).destination == "revenue"  # same place: fine
    assert ONT.match("fuel", "income_statement", [], frozenset({"transportation"}), LINES).destination == "other_opex"


def test_an_ambiguous_term_stays_with_a_person_however_well_the_rule_measures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spreader.mapping.calibrated", lambda rule: 0.99)
    assert _place("Rental income", StatementType.INCOME, REIT).confidence == 0.99
    assert _place("Net rental income", StatementType.INCOME, REIT).confidence < 0.80


def test_an_unmeasured_rule_starts_at_zero_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spreader.mapping.calibrated", lambda rule: 0.0)
    assert _place("Rental income", StatementType.INCOME, REIT).confidence == 0.0


def test_a_part_larger_than_its_total_goes_to_a_person() -> None:
    part = _row("Rental income", index=1, value="150")
    total = _row("Total revenues", index=2, role=RowRole.TOTAL, value="100", children=[])
    out = map_table(_table(StatementType.INCOME, part, total), PROFILE, industries=REIT)
    assert out[0].canonical is None and out[0].rule == "ontology.part_exceeds_total"


def test_a_general_alias_still_wins_and_the_row_gets_its_concept() -> None:
    row = _row("Depreciation and amortization", index=1)
    m = map_table(_table(StatementType.INCOME, row), PROFILE, industries=frozenset())[0]
    assert m.rule.startswith("alias") and m.canonical == "dna_opex" and m.concept == "cross_industry.depreciation_and_amortization"


def test_ffo_beats_any_general_wording_in_a_reit() -> None:
    assert ONT.by_id["real_estate.ffo"].overrides_alias


def test_subscription_under_cost_of_revenue_is_a_cost_not_revenue() -> None:
    tech = frozenset({"technology"})
    assert ONT.match("subscription", "income_statement", ["revenues"], tech, LINES).destination == "revenue"
    assert ONT.match("subscription", "income_statement", ["cost of revenue"], tech, LINES) is None
