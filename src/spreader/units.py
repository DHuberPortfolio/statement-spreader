"""Each statement's unit (thousands, millions) and currency, decided from evidence through the uncertainty policy (D39).

A unit misread by a factor of 1,000 makes every value in the statement wrong, so where it comes from is recorded and
measured like any other rule:

- scale.table: a unit statement at the table, in any of its wordings ("(In millions, except per share amounts)",
  "$ in thousands", "(In U.S. dollars)");
- scale.document: a unit stated once for the whole document ("All amounts are presented in millions of U.S.
  dollars", Deere), used only when every such statement in the document names the same unit;
- scale.sibling: no statement at the table, but every other primary statement in the document prints the same unit;
- scale.none: nothing found; the values are taken as printed. Never accepted without a person (never_auto).

A rule's unit is accepted without a person only when its measured accuracy (config/calibration/units.json, fitted by
scripts/eval_units.py on the dev filings against the filers' XBRL tags) has a 95% lower bound of at least 80%. Otherwise
the statement keeps its best guess and a blocking review item asks for a confirmation: a person sees the guess and
the evidence, not a blank.

Currency: named in the unit statement or headings ("EUR millions", "U.S. dollars"), else a "$" printed in the cells
(read as USD: every measured document is a US filing), else not known. A currency other than the profile's, or
statements in different currencies, is a review item; nothing is converted (a conversion needs a rate source and a
rate date that a person chooses).
"""

from __future__ import annotations

from collections.abc import Iterable

from finops.core import policy

from .contracts import StatementTable, StatementType
from .detect import detect_currency, doc_unit_multiplier

BAR = 0.80
REPORTING_CURRENCY = "USD"
_WORDS = {1: "units", 1_000: "thousands", 1_000_000: "millions", 1_000_000_000: "billions"}


def calibration() -> policy.Calibration:
    cal = policy.load("units")
    if "scale.none" not in cal.never_auto:
        cal = cal.model_copy(update={"never_auto": [*cal.never_auto, "scale.none"]})
    return cal


def document_unit(statements: Iterable[str]) -> tuple[int, str] | None:
    found = {doc_unit_multiplier(s): s for s in statements}
    if len(found) != 1:
        return None
    mult, words = next(iter(found.items()))
    return mult, words


def resolve_units(tables: dict[StatementType, StatementTable], contexts: dict[StatementType, list[str]],
                  unit_statements: list[str]) -> None:
    """Sets each table's scale (rule, confidence, assumed) and currency in place. contexts: the text at each table,
    nearest first (title, headings, the text above it)."""
    cal = calibration()
    printed = {st: t.scale.multiplier for st, t in tables.items() if t.scale.rule == "scale.table"}
    document = document_unit(unit_statements)
    for st, t in tables.items():
        scale = t.scale
        if scale.rule == "scale.none":
            siblings = {m for other, m in printed.items() if other is not st}
            if document is not None:
                mult, words = document
                why = f"No unit statement at the table; the document states once: '{words}'."
                if len(siblings) == 1 and mult not in siblings:
                    why += f" The other statements print {_WORDS.get(next(iter(siblings)), '?')}, so this is doubtful."
                    scale = scale.model_copy(update={"multiplier": mult, "evidence": why, "rule": "scale.conflict"})
                else:
                    scale = scale.model_copy(update={"multiplier": mult, "evidence": why, "rule": "scale.document"})
            elif len(siblings) == 1:
                mult = next(iter(siblings))
                scale = scale.model_copy(update={
                    "multiplier": mult, "rule": "scale.sibling",
                    "evidence": f"No unit statement at the table; the document's other statements are all in "
                                f"{_WORDS.get(mult, mult)}."})
        decision = cal.decide(scale.rule, BAR)
        currency, cur_words = detect_currency(contexts.get(st, []))
        if currency is None and not cur_words:
            currency, cur_words = detect_currency([s for s in unit_statements])
        if currency is None and not cur_words and _dollar_in_cells(t):
            currency, cur_words = REPORTING_CURRENCY, "'$' printed in the cells"
        t.scale = scale.model_copy(update={"assumed": not decision.auto, "confidence": decision.confidence,
                                           "currency": currency, "currency_evidence": cur_words})


def _dollar_in_cells(t: StatementTable) -> bool:
    return any("$" in (pv.raw or "") for r in t.rows[:40] for pv in r.values.values())


def unit_reason(t: StatementTable) -> str:
    """Why a statement's unit needs a person, for its review item."""
    s = t.scale
    if s.rule == "scale.none":
        return f"{s.evidence} Values were taken as printed (units)."
    guess = _WORDS.get(s.multiplier, str(s.multiplier))
    measured = calibration().methods.get(s.rule)
    record = (f"this way of reading a unit was right {measured.right} of {measured.total} times when measured (at least "
              f"{measured.low:.0%}; the bar is {BAR:.0%})" if measured else "this way of reading a unit has not been "
              "measured yet")
    return f"{s.evidence} Best guess: {guess}; {record}."
