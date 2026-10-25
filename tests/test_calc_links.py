"""The answer key uses each filing's calculation links to tell a total from its parts (2026-10-24, evening).

Without them, a filing that tags "total revenues" and "net sales" (a part of it) on lines mapped to the same template
line got a key value of both added together (Walmart's revenue key was about twice its revenue).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from spreader.evaluation.ixbrl_truth import Context, Fact, calc_descendants, drop_parts_of_totals

CAL = b"""<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
 <link:calculationLink xlink:type="extended" xlink:role="http://example.com/role/IncomeStatement">
  <link:loc xlink:type="locator" xlink:href="x.xsd#us-gaap_Revenues" xlink:label="rev"/>
  <link:loc xlink:type="locator" xlink:href="x.xsd#us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax" xlink:label="sales"/>
  <link:loc xlink:type="locator" xlink:href="x.xsd#us-gaap_OtherIncome" xlink:label="other"/>
  <link:loc xlink:type="locator" xlink:href="x.xsd#abc_ProductSales" xlink:label="prod"/>
  <link:calculationArc xlink:type="arc" xlink:from="rev" xlink:to="sales" weight="1"/>
  <link:calculationArc xlink:type="arc" xlink:from="rev" xlink:to="other" weight="1"/>
  <link:calculationArc xlink:type="arc" xlink:from="sales" xlink:to="prod" weight="1"/>
 </link:calculationLink>
</link:linkbase>"""

CTX = Context(id="c", start=date(2025, 2, 1), end=date(2026, 1, 31), instant=False, dimensional=False)


def fact(prefix: str, concept: str, value: str) -> Fact:
    return Fact(concept=concept, prefix=prefix, context=CTX, value=Decimal(value), printed=Decimal(value), decimals=-6,
                td_xpath=None, row_label="", table_index=0, row_index=0)


def test_descendants_are_transitive_and_keep_prefixes() -> None:
    d = calc_descendants(CAL)
    assert d["us-gaap:Revenues"] == {"us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:OtherIncome",
                                     "abc:ProductSales"}
    assert d["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"] == {"abc:ProductSales"}


def test_a_total_and_its_part_keep_only_the_total() -> None:
    d = calc_descendants(CAL)
    fs = [fact("us-gaap", "Revenues", "713163"), fact("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "706413")]
    assert [f.concept for f in drop_parts_of_totals(fs, d)] == ["Revenues"]


def test_unrelated_concepts_are_left_to_the_old_rule() -> None:
    d = calc_descendants(CAL)
    fs = [fact("us-gaap", "SellingExpense", "10"), fact("us-gaap", "GeneralAndAdministrativeExpense", "5")]
    assert drop_parts_of_totals(fs, d) == fs  # not linked: the key still adds them (selling + G&A)
    assert drop_parts_of_totals(fs[:1], d) == fs[:1]


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "eval" / "sec" / "cal" / "WMT_cal.xml").exists(),
                    reason="calculation linkbases not downloaded (scripts/fetch_sec_calc.py)")
def test_walmart_revenue_is_a_total_of_net_sales_and_other_income() -> None:
    d = calc_descendants((Path(__file__).resolve().parents[1] / "eval" / "sec" / "cal" / "WMT_cal.xml").read_bytes())
    assert "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" in d["us-gaap:Revenues"]


CASH = b"""<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
 <link:calculationLink xlink:type="extended" xlink:role="http://example.com/role/BalanceSheet">
  <link:loc xlink:type="locator" xlink:href="x.xsd#us-gaap_CashCashEquivalentsAndShortTermInvestments" xlink:label="tot"/>
  <link:loc xlink:type="locator" xlink:href="x.xsd#us-gaap_CashAndCashEquivalentsAtCarryingValue" xlink:label="cash"/>
  <link:loc xlink:type="locator" xlink:href="x.xsd#us-gaap_MarketableSecuritiesCurrent" xlink:label="ms"/>
  <link:calculationArc xlink:type="arc" xlink:from="tot" xlink:to="cash" weight="1"/>
  <link:calculationArc xlink:type="arc" xlink:from="tot" xlink:to="ms" weight="1"/>
 </link:calculationLink>
</link:linkbase>"""


def test_a_subtotal_across_template_lines_keeps_the_part() -> None:
    """Cash and marketable securities both map to "cash" in the crosswalk, but marketable securities is its own
    template line: for "cash" the key is cash and equivalents (Alphabet, Microsoft)."""
    from spreader.evaluation.ixbrl_truth import _template_line

    d = calc_descendants(CASH)
    fs = [fact("us-gaap", "CashCashEquivalentsAndShortTermInvestments", "95657"),
          fact("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "23466")]
    assert [f.concept for f in drop_parts_of_totals(fs, d, "cash", _template_line)] == ["CashAndCashEquivalentsAtCarryingValue"]
    rev = calc_descendants(CAL)
    fs = [fact("us-gaap", "Revenues", "713163"), fact("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "706413")]
    assert [f.concept for f in drop_parts_of_totals(fs, rev, "revenue", _template_line)] == ["Revenues"]


def test_net_income_to_common_counts_only_without_net_income() -> None:
    """Net income less preferred dividends is a calculation total of net income, but not the net income line."""
    from spreader.evaluation.ixbrl_truth import drop_fallbacks

    both = [fact("us-gaap", "NetIncomeLoss", "17087"), fact("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic", "16984")]
    assert [f.concept for f in drop_fallbacks(both)] == ["NetIncomeLoss"]
    assert drop_fallbacks(both[1:]) == both[1:]  # a filer that tags only this one still gets a key value


SEC = Path(__file__).resolve().parents[1] / "eval" / "sec"


@pytest.mark.skipif(not list((SEC / "raw").glob("AAPL-*")), reason="Apple filing not downloaded")
def test_a_rebuilt_key_is_byte_for_byte_the_same() -> None:
    """Rebuilding the keys reshuffled every key file (a set's order follows Python's per-process hash seed), which
    buried the real changes in a diff of 50 files."""
    import subprocess
    import sys

    code = ("import sys; from pathlib import Path; from spreader.evaluation.ixbrl_truth import build_key; "
            "from spreader.profile import load_profile; p = next(Path(sys.argv[1]).glob('AAPL-*')); "
            "sys.stdout.write(build_key(p.name, p.read_bytes(), load_profile())[0].model_dump_json())")
    outs = {subprocess.run([sys.executable, "-c", code, str(SEC / "raw")], capture_output=True, check=True,
                           env={**__import__("os").environ, "PYTHONHASHSEED": seed}).stdout for seed in ("1", "2", "3")}
    assert len(outs) == 1


@pytest.mark.skipif(not (SEC / "cal" / "ORCL_cal.xml").exists() or not list((SEC / "raw").glob("ORCL-*")),
                    reason="Oracle filing or its calculation links not downloaded")
def test_oracle_net_income_key_is_net_income_not_net_income_to_common() -> None:
    from spreader.evaluation.ixbrl_truth import build_key
    from spreader.profile import load_profile

    raw = next((SEC / "raw").glob("ORCL-*"))
    key, _ = build_key(raw.name, raw.read_bytes(), load_profile(), (SEC / "cal" / "ORCL_cal.xml").read_bytes())
    got = {(v.line, v.period): v.value for v in key.spread}
    assert got[("net_income_parent", "2026-05-31/12M")] == Decimal("17087000000")
    assert got[("net_income", "2026-05-31/12M")] == Decimal("17087000000")
