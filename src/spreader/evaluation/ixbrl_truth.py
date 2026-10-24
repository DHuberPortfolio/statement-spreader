"""Answer keys from SEC inline XBRL: what each printed number in a filing's statements really is.

An inline XBRL filing tags every number in its financial statements with a concept
("us-gaap:CostOfGoodsAndServicesSold"), a context (the period, and any segment it belongs to),
a scale and a sign. The pipeline never reads these tags; this module does, to grade it.

Independence: the key finds each statement's table by its tagged concepts, never by the labels
the pipeline reads, and maps concepts to template lines with its own crosswalk (CROSSWALK
below), never with the profile's aliases.

What is compared, and how signs work:
- Row truth: every tagged number in a statement table, as printed (a number in parentheses is
  negative whatever its tag says, because a "negated label" prints a positive fact negative).
- Spread truth for a template line: the printed values of the untagged-by-segment rows whose
  concept maps to that line (a total of the same line wins over its parts). Cost lines use the
  tagged value, which is positive for a cost however it is printed; the pipeline spreads costs
  as positive too.
- Rows tagged only with a company-specific concept, or a concept the crosswalk does not list,
  have no known template line: they are scored for value and period, not for mapping, and the
  lines they might feed are not scored at spread level ("unknown_lines").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from ..ingest.paths import element_path
from ..profile import Profile
from .truth import AnswerKey, TruthCell, TruthValue

NS = {"ix": "http://www.xbrl.org/2013/inlineXBRL", "xbrli": "http://www.xbrl.org/2003/instance",
      "xbrldi": "http://xbrl.org/2006/xbrldi", "x": "http://www.w3.org/1999/xhtml"}

# us-gaap concept (local name) -> template line. Only concepts whose meaning is unambiguous for
# the template are listed; anything else is "unknown" and not used to grade mapping.
CROSSWALK: dict[str, str] = {}


def _cw(line: str, *concepts: str) -> None:
    for c in concepts:
        CROSSWALK[c] = line


_cw("revenue", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense", "OperatingRevenue", "RevenueNet")
_cw("cogs", "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
    "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization")
_cw("gross_profit", "GrossProfit")
_cw("rnd", "ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost")
_cw("sga", "SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense", "SellingAndMarketingExpense",
    "SellingExpense", "MarketingAndAdvertisingExpense", "MarketingExpense")
_cw("dna_opex", "DepreciationAndAmortization", "DepreciationDepletionAndAmortization", "AmortizationOfIntangibleAssets",
    "Depreciation", "DepreciationAmortizationAndAccretionNet")
_cw("other_opex", "RestructuringCharges", "GoodwillImpairmentLoss", "AssetImpairmentCharges", "OtherOperatingIncomeExpenseNet",
    "OtherCostAndExpenseOperating", "RestructuringSettlementAndImpairmentProvisions", "BusinessCombinationAcquisitionRelatedCosts",
    "ImpairmentOfIntangibleAssetsExcludingGoodwill", "LitigationSettlementExpense", "GainLossOnDispositionOfAssets")
_cw("total_opex", "OperatingExpenses")
_cw("total_costs", "CostsAndExpenses", "OperatingCostsAndExpenses")
_cw("operating_income", "OperatingIncomeLoss")
_cw("interest_expense", "InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense",
    "InterestExpenseNet")
_cw("interest_income", "InvestmentIncomeInterest", "InterestIncomeOther", "InvestmentIncomeInterestAndDividend",
    "InterestAndOtherIncome", "InvestmentIncomeNonoperating")
_cw("other_nonoperating", "NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense", "OtherNonoperatingIncome",
    "OtherNonoperatingExpense", "IncomeLossFromEquityMethodInvestments", "GainLossOnInvestments",
    "DebtInstrumentConvertibleBeneficialConversionFeature", "GainsLossesOnExtinguishmentOfDebt",
    "InterestIncomeExpenseNonoperatingNet", "OtherNonoperatingIncomeExpenseNet")
_cw("pretax_income", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic", "IncomeLossBeforeIncomeTaxes")
_cw("income_tax", "IncomeTaxExpenseBenefit", "IncomeTaxExpenseBenefitContinuingOperations")
_cw("discontinued_ops", "IncomeLossFromDiscontinuedOperationsNetOfTax",
    "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity")
_cw("net_income", "ProfitLoss", "NetIncomeLossIncludingPortionAttributableToNoncontrollingInterest")
_cw("nci_net_income", "NetIncomeLossAttributableToNoncontrollingInterest", "MinorityInterestInNetIncomeLossOfConsolidatedEntities")
_cw("net_income_parent", "NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic")
_cw("eps_basic", "EarningsPerShareBasic", "IncomeLossFromContinuingOperationsPerBasicShare")
_cw("eps_diluted", "EarningsPerShareDiluted", "IncomeLossFromContinuingOperationsPerDilutedShare", "EarningsPerShareBasicAndDiluted")
_cw("shares_basic", "WeightedAverageNumberOfSharesOutstandingBasic")
_cw("shares_diluted", "WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfShareOutstandingBasicAndDiluted")

_cw("cash", "CashAndCashEquivalentsAtCarryingValue", "Cash", "CashAndDueFromBanks", "CashCashEquivalentsAndShortTermInvestments")
_cw("st_investments", "MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "RestrictedCashCurrent", "RestrictedCashAndCashEquivalentsAtCarryingValue", "OtherShortTermInvestments")
_cw("receivables", "AccountsReceivableNetCurrent", "NontradeReceivablesCurrent", "ReceivablesNetCurrent",
    "AccountsNotesAndLoansReceivableNetCurrent", "AccountsAndOtherReceivablesNetCurrent", "AccountsReceivableGrossCurrent")
_cw("inventory", "InventoryNet", "InventoryFinishedGoodsNetOfReserves", "InventoryGross", "RetailRelatedInventoryMerchandise")
_cw("other_current_assets", "OtherAssetsCurrent", "PrepaidExpenseAndOtherAssetsCurrent", "PrepaidExpenseCurrent",
    "IncomeTaxesReceivable", "AssetsHeldForSaleCurrent", "DisposalGroupIncludingDiscontinuedOperationAssetsCurrent")
_cw("total_current_assets", "AssetsCurrent")
_cw("ppe_net", "PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization")
_cw("goodwill", "Goodwill")
_cw("intangibles", "IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet", "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
    "IntangibleAssetsNetIncludingGoodwill")
_cw("lt_investments", "MarketableSecuritiesNoncurrent", "LongTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
    "EquityMethodInvestments", "OtherLongTermInvestments")
_cw("operating_lease_rou", "OperatingLeaseRightOfUseAsset")
_cw("deferred_tax_assets", "DeferredIncomeTaxAssetsNet", "DeferredTaxAssetsNetNoncurrent")
_cw("other_noncurrent_assets", "OtherAssetsNoncurrent")
_cw("total_noncurrent_assets", "AssetsNoncurrent")
_cw("total_assets", "Assets")
_cw("payables", "AccountsPayableCurrent", "AccountsPayableTradeCurrent")
_cw("accrued_liabilities", "AccruedLiabilitiesCurrent", "EmployeeRelatedLiabilitiesCurrent", "AccruedIncomeTaxesCurrent",
    "TaxesPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent")
_cw("deferred_revenue_current", "ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent")
_cw("st_debt", "CommercialPaper", "LongTermDebtCurrent", "ShortTermBorrowings", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "OtherLongTermDebtCurrent", "NotesPayableCurrent", "LinesOfCreditCurrent", "ShortTermDebtAndCurrentPortionOfLongTermDebt")
_cw("operating_lease_liab_current", "OperatingLeaseLiabilityCurrent")
_cw("other_current_liabilities", "OtherLiabilitiesCurrent", "AccruedLiabilitiesAndOtherLiabilities")
_cw("total_current_liabilities", "LiabilitiesCurrent")
_cw("lt_debt", "LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "OtherLongTermDebtNoncurrent",
    "SeniorNotes", "ConvertibleNotesPayable", "LongTermNotesPayable", "ConvertibleDebtNoncurrent")
_cw("operating_lease_liab_noncurrent", "OperatingLeaseLiabilityNoncurrent")
_cw("deferred_tax_liabilities", "DeferredIncomeTaxLiabilitiesNet", "DeferredTaxLiabilitiesNoncurrent")
_cw("other_noncurrent_liabilities", "OtherLiabilitiesNoncurrent", "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent",
    "AccruedIncomeTaxesNoncurrent", "ContractWithCustomerLiabilityNoncurrent", "DeferredRevenueNoncurrent")
_cw("total_noncurrent_liabilities", "LiabilitiesNoncurrent")
_cw("total_liabilities", "Liabilities")
_cw("temporary_equity", "TemporaryEquityCarryingAmountAttributableToParent", "RedeemableNoncontrollingInterestEquityCarryingAmount",
    "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests")
_cw("common_stock_apic", "CommonStocksIncludingAdditionalPaidInCapital", "CommonStockValue", "AdditionalPaidInCapital",
    "AdditionalPaidInCapitalCommonStock", "PreferredStockValue", "CommonStockSharesSubscribedButUnissuedSubscriptionsReceivable")
_cw("retained_earnings", "RetainedEarningsAccumulatedDeficit")
_cw("aoci", "AccumulatedOtherComprehensiveIncomeLossNetOfTax")
_cw("treasury_stock", "TreasuryStockValue", "TreasuryStockCommonValue")
_cw("total_equity_parent", "StockholdersEquity")
_cw("nci_equity", "MinorityInterest")
_cw("total_equity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
_cw("total_liabilities_equity", "LiabilitiesAndStockholdersEquity")

_cw("cf_dna", "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet")
_cw("cf_sbc", "ShareBasedCompensation", "AllocatedShareBasedCompensationExpense")
_cw("cf_deferred_tax", "DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits")
_cw("cf_working_capital", "IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInInventories", "IncreaseDecreaseInAccountsPayable",
    "IncreaseDecreaseInOtherOperatingAssets", "IncreaseDecreaseInOtherOperatingLiabilities", "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets",
    "IncreaseDecreaseInAccruedLiabilities", "IncreaseDecreaseInContractWithCustomerLiability", "IncreaseDecreaseInOperatingCapital",
    "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities", "IncreaseDecreaseInNontradeReceivables", "IncreaseDecreaseInIncomeTaxesPayableNetOfIncomeTaxesReceivable",
    "IncreaseDecreaseInAccruedIncomeTaxesPayable", "IncreaseDecreaseInEmployeeRelatedLiabilities", "IncreaseDecreaseInOtherCurrentAssets",
    "IncreaseDecreaseInOtherNoncurrentAssets", "IncreaseDecreaseInOtherNoncurrentLiabilities", "IncreaseDecreaseInOtherCurrentLiabilities",
    "IncreaseDecreaseInDeferredRevenue", "IncreaseDecreaseInReceivables", "IncreaseDecreaseInOtherOperatingCapitalNet")
_cw("cfo", "NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")
_cw("capex", "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements")
_cw("acquisitions", "PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross")
_cw("cf_investments_net", "PaymentsToAcquireAvailableForSaleSecuritiesDebt", "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities",
    "ProceedsFromSaleOfAvailableForSaleSecuritiesDebt", "PaymentsToAcquireMarketableSecurities", "ProceedsFromSaleMaturityAndCollectionsOfInvestments",
    "PaymentsToAcquireInvestments", "PaymentsToAcquireShortTermInvestments", "ProceedsFromSaleOfShortTermInvestments",
    "ProceedsFromMaturitiesPrepaymentsAndCallsOfShortTermInvestments", "PaymentsToAcquireAvailableForSaleSecurities",
    "ProceedsFromSaleAndMaturityOfMarketableSecurities", "PaymentsForProceedsFromInvestments")
_cw("cfi", "NetCashProvidedByUsedInInvestingActivities", "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations")
_cw("debt_issued", "ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt", "ProceedsFromIssuanceOfSeniorLongTermDebt",
    "ProceedsFromLongTermLinesOfCredit", "ProceedsFromLinesOfCredit", "ProceedsFromConvertibleDebt", "ProceedsFromIssuanceOfUnsecuredDebt",
    "ProceedsFromBankDebt", "ProceedsFromNotesPayable")
_cw("debt_repaid", "RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "RepaymentsOfLinesOfCredit", "RepaymentsOfSeniorDebt",
    "RepaymentsOfLongTermLinesOfCredit", "RepaymentsOfNotesPayable", "RepaymentsOfConvertibleDebt", "RepaymentsOfBankDebt")
_cw("cf_commercial_paper_net", "ProceedsFromRepaymentsOfCommercialPaper", "ProceedsFromRepaymentsOfShortTermDebt",
    "ProceedsFromShortTermDebt", "RepaymentsOfShortTermDebt")
_cw("dividends_paid", "PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends")
_cw("buybacks", "PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity")
_cw("stock_issued", "ProceedsFromIssuanceOfCommonStock", "ProceedsFromStockOptionsExercised", "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans",
    "ProceedsFromEmployeeStockPurchasePlan")
_cw("cf_other_financing", "PaymentsRelatedToTaxWithholdingForShareBasedCompensation", "ProceedsFromPaymentsForOtherFinancingActivities",
    "PaymentsOfDebtIssuanceCosts", "FinanceLeasePrincipalPayments", "PaymentsToMinorityShareholders")
_cw("fx_effect", "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "EffectOfExchangeRateOnCashAndCashEquivalents",
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations")
_cw("net_change_cash", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
    "CashAndCashEquivalentsPeriodIncreaseDecrease", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect")
# Ending and beginning cash share one concept; the key tells them apart by period (instant at the
# period's end vs at its start).
CASH_ROLL = {"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsAndRestrictedCash", "Cash"}

# Concepts that identify each statement's table (truth side, independent of labels).
STATEMENT_MARKERS = {
    "balance_sheet": {"Assets", "LiabilitiesAndStockholdersEquity"},
    "income_statement": {"EarningsPerShareBasic", "EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted",
                         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                         "OperatingIncomeLoss", "IncomeTaxExpenseBenefit"},
    "cash_flow": {"NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInInvestingActivities",
                  "NetCashProvidedByUsedInFinancingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"},
}
STATEMENT_EXCLUDE = {
    "income_statement": {"ComprehensiveIncomeNetOfTax", "OtherComprehensiveIncomeLossNetOfTax", "Assets",
                         "NetCashProvidedByUsedInOperatingActivities"},
    "balance_sheet": {"NetCashProvidedByUsedInOperatingActivities", "EarningsPerShareBasic"},
    "cash_flow": {"Assets", "EarningsPerShareBasic"},
}


@dataclass
class Context:
    id: str
    start: date | None
    end: date
    instant: bool
    dimensional: bool


@dataclass
class Fact:
    concept: str  # local name
    prefix: str
    context: Context
    value: Decimal  # the fact's value (sign from the tag), scaled to units
    printed: Decimal  # as printed: negative when shown in parentheses or with a minus
    decimals: int | None
    td_xpath: str | None
    row_label: str
    table_index: int  # index among ALL <table> elements in the document
    row_index: int


@dataclass
class StatementTruth:
    statement: str
    table_index: int
    facts: list[Fact] = field(default_factory=list)


def _local(name: str) -> tuple[str, str]:
    if ":" in name:
        p, n = name.split(":", 1)
        return p, n
    return "", name


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.strip()[:10])


def _contexts(root: etree._Element) -> dict[str, Context]:
    out: dict[str, Context] = {}
    for c in root.iterfind(".//xbrli:context", NS):
        cid = c.get("id") or ""
        period = c.find("xbrli:period", NS)
        if period is None:
            continue
        dims = c.find(".//xbrldi:explicitMember", NS) is not None or c.find(".//xbrldi:typedMember", NS) is not None
        inst = period.find("xbrli:instant", NS)
        if inst is not None and inst.text:
            out[cid] = Context(cid, None, _parse_date(inst.text), True, dims)
            continue
        s, e = period.find("xbrli:startDate", NS), period.find("xbrli:endDate", NS)
        if s is not None and e is not None and s.text and e.text:
            out[cid] = Context(cid, _parse_date(s.text), _parse_date(e.text), False, dims)
    return out


_NUM = re.compile(r"[\d.,]+")


def _fact_number(el: etree._Element) -> Decimal | None:
    text = "".join(el.itertext()).strip()
    fmt = (el.get("format") or "").lower()
    if any(z in fmt for z in ("zerodash", "fixed-zero", "fixedzero", "numwordsen", "nocontent")):
        return Decimal(0)
    m = _NUM.search(text)
    if not m:
        return Decimal(0) if text in {"-", "—", "–", ""} else None
    raw = m.group(0)
    if "comma-decimal" in fmt or "numcommadecimal" in fmt:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _months(ctx: Context) -> int:
    assert ctx.start is not None
    days = (ctx.end - ctx.start).days
    return max(1, round(days / 30.44))


def period_key(ctx: Context) -> str:
    if ctx.instant:
        return f"{ctx.end.isoformat()}/I"
    return f"{ctx.end.isoformat()}/{_months(ctx)}M"


def _cell_printed_negative(td: etree._Element, fact_el: etree._Element) -> bool:
    """Is the number shown in parentheses or with a minus sign? Looks at the cell and its neighbour."""
    texts = ["".join(td.itertext())]
    nxt = td.getnext()
    if nxt is not None:
        texts.append("".join(nxt.itertext()))
    prev = td.getprevious()
    before = "".join(prev.itertext()) if prev is not None else ""
    cell = texts[0]
    fact_text = "".join(fact_el.itertext()).strip()
    pos = cell.find(fact_text) if fact_text else -1
    left = (before + cell[: max(pos, 0)]).strip()
    right = (cell[pos + len(fact_text):] if pos >= 0 else "") + (texts[1] if len(texts) > 1 else "")
    paren = left.endswith("(") or left.endswith("($") or left.endswith("$(") or left.replace(" ", "").endswith("($")
    paren = paren and right.strip().startswith(")")
    minus = left.rstrip("$ ").endswith(("-", "−", "–"))
    return paren or minus


def _row_label(tr: etree._Element) -> str:
    for td in tr:
        t = re.sub(r"\s+", " ", "".join(td.itertext())).strip()
        if t and not re.fullmatch(r"[\s$()\d,.\-—–%]+", t):
            return t
    return ""


def read_facts(data: bytes) -> tuple[list[Fact], int]:
    parser = etree.XMLParser(huge_tree=True, recover=True, resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(data, parser=parser)
    if root is None:
        raise ValueError("not an XML (inline XBRL) document")

    contexts = _contexts(root)
    tables = list(root.iter("{http://www.w3.org/1999/xhtml}table"))
    t_index = {id(t): i for i, t in enumerate(tables)}
    facts: list[Fact] = []
    for el in root.iterfind(".//ix:nonFraction", NS):
        ctx = contexts.get(el.get("contextRef") or "")
        if ctx is None:
            continue
        num = _fact_number(el)
        if num is None:
            continue
        scale = int(el.get("scale") or 0)
        value = num * (Decimal(10) ** scale)
        if el.get("sign") == "-":
            value = -value
        td = next((a for a in el.iterancestors() if a.tag == "{http://www.w3.org/1999/xhtml}td"), None)
        tr = next((a for a in el.iterancestors() if a.tag == "{http://www.w3.org/1999/xhtml}tr"), None)
        table = next((a for a in el.iterancestors() if a.tag == "{http://www.w3.org/1999/xhtml}table"), None)
        if td is None or tr is None or table is None:
            continue
        printed_neg = _cell_printed_negative(td, el)
        printed = -abs(value) if printed_neg else abs(value)
        dec = el.get("decimals")
        prefix, concept = _local(el.get("name") or "")
        rows = [r for r in table.iter("{http://www.w3.org/1999/xhtml}tr")]
        facts.append(Fact(concept=concept, prefix=prefix, context=ctx, value=value, printed=printed,
                          decimals=None if dec in (None, "INF") else int(dec), td_xpath=element_path(td),
                          row_label=_row_label(tr), table_index=t_index[id(table)], row_index=rows.index(tr)))
    return facts, len(tables)


def find_statements(facts: list[Fact]) -> dict[str, StatementTruth]:
    """Pick each statement's table by its tagged concepts (most marker facts, none excluded)."""
    by_table: dict[int, list[Fact]] = {}
    for f in facts:
        by_table.setdefault(f.table_index, []).append(f)
    out: dict[str, StatementTruth] = {}
    for stmt, markers in STATEMENT_MARKERS.items():
        best, best_score = None, 0
        for ti, fs in by_table.items():
            concepts = {f.concept for f in fs if not f.context.dimensional}
            if concepts & STATEMENT_EXCLUDE[stmt]:
                continue
            hits = len(concepts & markers)
            if not hits:
                continue
            score = hits * 10 + len(concepts)
            if score > best_score:
                best, best_score = ti, score
        if best is not None:
            out[stmt] = StatementTruth(stmt, best, [f for f in by_table[best] if f.prefix])
    return out


def build_key(document: str, data: bytes, profile: Profile) -> tuple[AnswerKey, dict[str, StatementTruth]]:
    facts, _ = read_facts(data)
    statements = find_statements(facts)
    key = AnswerKey(document=document, source="sec", description="Answer key from the filing's inline XBRL tags")
    periods: set[str] = set()
    unknown: set[str] = set()
    for stmt, st in statements.items():
        line_values: dict[tuple[str, str], list[Fact]] = {}
        for f in st.facts:
            if f.context.dimensional:
                # A segment's part of a line (Products, Services): a component, not the line's total.
                line = CROSSWALK.get(f.concept) if f.prefix == "us-gaap" else None
                key.cells.append(TruthCell(statement=stmt, row_label=f.row_label, period=period_key(f.context),
                                           value=f.printed, line=line, role="component"))
                continue
            pk = period_key(f.context)
            line = CROSSWALK.get(f.concept) if f.prefix == "us-gaap" else None
            if f.concept in CASH_ROLL and stmt == "cash_flow" and f.prefix == "us-gaap":
                line = "cash_end"  # resolved to cash_begin below when its date is a period start
            if stmt == "cash_flow" and line in {"cash", "st_investments"}:
                line = "cash_end"
            if stmt == "cash_flow" and f.concept in {"ProfitLoss", "NetIncomeLoss"}:
                line = "cf_net_income"
            if stmt == "cash_flow" and line == "dna_opex":
                line = "cf_dna"
            if stmt == "income_statement" and line in {"cf_dna"}:
                line = "dna_opex"
            if (f.concept == "NonoperatingIncomeExpense" and stmt == "income_statement"
                    and {"OtherNonoperatingIncomeExpense", "InterestExpense", "InterestExpenseNonoperating",
                         "InvestmentIncomeInterest", "InterestIncomeOther"} & {g.concept for g in st.facts}):
                line = None
            if line is not None and line not in profile.lines:
                line = None
            if line is not None and profile.line_statement[line].value != stmt:
                # A concept used on a different statement than the template expects: leave unjudged.
                line = None
            if line is None:
                unknown.add(f"{f.prefix}:{f.concept}")
            if not f.context.instant:
                periods.add(pk)
            key.cells.append(TruthCell(statement=stmt, row_label=f.row_label, period=pk, value=f.printed, line=line,
                                       role="detail", xpath=f.td_xpath))
            if line is not None:
                line_values.setdefault((line, pk), []).append(f)
        # Cash flow: ending vs beginning cash share a concept; instants equal to a flow period's
        # start are beginning balances.
        if stmt == "cash_flow":
            starts = {f.context.start for f in st.facts if not f.context.instant and f.context.start}
            ends = {f.context.end for f in st.facts if not f.context.instant}
            fixed: dict[tuple[str, str], list[Fact]] = {}
            for (line, pk), fs in line_values.items():
                if line == "cash_end":
                    for f in fs:
                        d = f.context.end
                        # A beginning balance is dated the day before a period starts.
                        is_begin = any((s - d).days in (0, 1) for s in starts) and d not in ends
                        flow_key = _flow_key_for_instant(d, st, begin=is_begin)
                        if flow_key:
                            fixed.setdefault(("cash_begin" if is_begin else "cash_end", flow_key), []).append(f)
                else:
                    fixed.setdefault((line, pk), []).extend(fs)
            line_values = fixed
        for (line, pk), fs in line_values.items():
            ldef = profile.lines[line]
            vals = [(f.value if ldef.kind == "cost" else f.printed) for f in fs]
            uniq = list(dict.fromkeys(vals))
            if len(uniq) > 1:
                total = sum(uniq[1:], Decimal(0))
                # One value that is the sum of the others is their total.
                biggest = max(uniq, key=abs)
                rest = [v for v in uniq if v is not biggest]
                value = biggest if abs(sum(rest, Decimal(0)) - biggest) <= len(rest) * _precision(fs) else sum(uniq, Decimal(0))
                del total
            else:
                value = uniq[0]
            key.spread.append(TruthValue(statement=stmt, line=line, period=pk, value=value, precision=_precision(fs)))
    _equivalents(key)
    key.periods = sorted(periods)
    key.unknown_lines = sorted(unknown)
    return key, statements


def _precision(fs: list[Fact]) -> Decimal:
    decs = [f.decimals for f in fs if f.decimals is not None]
    if not decs:
        return Decimal(1)
    return Decimal(10) ** (-min(decs))


def _flow_key_for_instant(d: date, st: StatementTruth, begin: bool) -> str | None:
    """The flow period a cash balance belongs to: ending balance -> period ending on d; beginning
    balance -> period starting the day after d."""
    for f in st.facts:
        if f.context.instant or f.context.start is None:
            continue
        if begin and (f.context.start - d).days in (0, 1):
            return period_key(f.context)
        if not begin and f.context.end == d:
            return period_key(f.context)
    return None


def _equivalents(key: AnswerKey) -> None:
    """Without noncontrolling interests, net income and net income to the company are one number.

    Filers tag that one row NetIncomeLoss (the company's share); the template has both lines.
    Likewise total equity and the company's equity. The key states both so neither is unjudged.
    """
    have = {(v.line, v.period): v for v in key.spread}
    pairs = [("net_income", "net_income_parent", "nci_net_income"),
             ("total_equity", "total_equity_parent", "nci_equity")]
    for a, b, nci in pairs:
        periods = {v.period for v in key.spread if v.line in (a, b)}
        for p in periods:
            if (nci, p) in have:
                continue
            if (a, p) in have and (b, p) not in have:
                key.spread.append(have[(a, p)].model_copy(update={"line": b}))
            elif (b, p) in have and (a, p) not in have:
                key.spread.append(have[(b, p)].model_copy(update={"line": a}))
