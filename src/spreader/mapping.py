"""Which canonical line each statement row feeds, how sure we are, and why.

The cascade, strongest evidence first:

1. memory   a reviewer's earlier decision for this exact label (and section)        0.99
2. alias    the label is one of the line's aliases                                  1.00 / 0.95 with *
3. section  the label matches a rule that only applies under a section header      0.97 / 0.75 catch-all
4. fuzzy    the label is spelled almost like an alias                               0.85
5. structure  a total whose rows all feed one line feeds that line too              min of its rows
6. model    an optional language model, only for rows nothing above could place    model-reported, capped

Each rule respects the row's unit: a per-share row can only feed a per-share line.
Numbers never pass through a model; a model only ever picks a line id from a closed list.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from finops.core import policy

from . import ontology
from .contracts import MapMethod, RowMapping, RowRole, StatementRow, StatementTable, StatementType, ValueUnit
from .profile import LineDef, Profile, matches

FUZZY_ACCEPT = 93.0
FUZZY_CANDIDATE = 82.0
CONFIDENCE_REVIEW = 0.80  # a value-bearing row whose rule's measured lower bound is below this goes to review
CONFIDENCE_REVIEW_CRITICAL = 0.90


def calibrated(rule: str) -> float:
    """A mapping rule's confidence: the lower end of its measured accuracy (config/calibration/statements.json,
    scripts/calibrate.py), or 0 when it was never measured. Replaces the hand-set constants of D5; the policy is
    finops.core.policy."""
    c = policy.load("statements").confidence(rule)
    return 0.0 if c is None else c


@dataclass(frozen=True)
class MemoryKey:
    profile_id: str
    statement: str
    label: str
    section: str


Memory = dict[MemoryKey, str]  # -> canonical line id ("" means "exclude this row")
CompanyMemory = dict[tuple[str, str, str], str]  # (statement, label, section) -> line, from approved spreads
ModelMapper = Callable[[StatementTable, StatementRow, list[LineDef]], RowMapping | None]


# The parent's own equity total, named after the company ("Total AIG shareholders' equity", "FHN shareholders'
# equity"): no alias list can hold every company name, so the shape decides. Anything naming liabilities,
# noncontrolling interests or preferred stock, or joining two things with "and", is some other total.
_OWN_EQUITY = re.compile(r"^(total )?[a-z0-9 ]{2,60} (stockholders|shareholders) equity( deficit)?$")
_NOT_OWN_EQUITY = re.compile(r"\b(liabilities|noncontrolling|non controlling|preferred|and|including|total equity)\b")


def _own_equity_total(row: StatementRow, lab: str) -> bool:
    return row.role is RowRole.TOTAL and bool(_OWN_EQUITY.match(lab)) and not _NOT_OWN_EQUITY.search(lab)


# A row of basic or diluted earnings or shares. Filers word these every possible way, and a good many print one row for
# both, so the row's unit and these words decide rather than an alias list.
_BASIC = re.compile(r"\bbasic\b")
_DILUTED = re.compile(r"\bdilut\w*|assuming dilution")
_NOT_COMMON = re.compile(r"\b(preferred|class [b-z]\b|continuing|discontinu|adjusted|pro forma|non gaap)")


def _per_share_rule(row: StatementRow, lab: str, lines: list[LineDef]) -> RowMapping | None:
    if _NOT_COMMON.search(f"{lab} {row.section.lower()}") or row.unit not in (ValueUnit.PER_SHARE, ValueUnit.SHARES):
        return None
    basic, diluted = bool(_BASIC.search(lab)), bool(_DILUTED.search(lab))
    if not (basic or diluted):
        return None
    pair = ("eps_basic", "eps_diluted") if row.unit is ValueUnit.PER_SHARE else ("shares_basic", "shares_diluted")
    have = {ln.id for ln in lines}
    if not set(pair) <= have:
        return None
    if basic and diluted:
        return RowMapping(row_index=row.index, canonical=pair[0], also=[pair[1]], method=MapMethod.ALIAS,
                          confidence=calibrated("alias.pattern"), rule="alias.pattern",
                          reason="One printed row gives both the basic and the diluted figure.")
    line = pair[0] if basic else pair[1]
    return RowMapping(row_index=row.index, canonical=line, method=MapMethod.ALIAS, confidence=calibrated("alias.pattern"),
                      rule="alias.pattern", reason=f"'{lab}' is the {'basic' if basic else 'diluted'} per-share row.")


def _unit_ok(line: LineDef, row: StatementRow) -> bool:
    if row.unit is ValueUnit.PERCENT:
        return False
    return line.unit is row.unit


def _section_parts(row: StatementRow) -> list[str]:
    return [s for s in reversed(row.section.split(" > ")) if s] if row.section else []


def _from_ontology(row: StatementRow, found: ontology.Match, lab: str) -> RowMapping:
    """A row the ontology recognised. A disclosure is left off the template; a line is measured like any rule, so an
    unmeasured or ambiguous term goes to a person."""
    c = found.concept
    name = c.industry.replace("_", " ")
    if c.role == "disclosure":
        return RowMapping(row_index=row.index, canonical=None, method=MapMethod.STRUCTURE, confidence=0.95, excluded=True, concept=c.id,
                          rule="ontology.disclosure", reason=f"'{lab}' is {c.label}, a {name} measure, not a line of this statement.")
    confidence = calibrated("ontology.line")
    if c.review == "always":
        confidence = min(confidence, CONFIDENCE_REVIEW - 0.01)
    context = f" {c.context}" if c.context else ""
    return RowMapping(row_index=row.index, canonical=found.destination, method=MapMethod.ALIAS, confidence=confidence, concept=c.id,
                      contra=c.sign == "contra", rule="ontology.line", reason=f"'{lab}' means {c.label} ({name}).{context}")


def map_row(row: StatementRow, table: StatementTable, profile: Profile, memory: Memory | None = None,
            company: CompanyMemory | None = None, wrong_side: frozenset[str] = frozenset(),
            industries: frozenset[str] = frozenset()) -> RowMapping:
    """wrong_side: kinds of line this row cannot feed because of where it sits on the balance sheet.
    industries: what the document's own rows show it to be (spreader.ontology)."""
    sdef = profile.statements[table.statement]
    lines = [ln for ln in sdef.lines if _unit_ok(ln, row) and ln.kind not in wrong_side]
    lab = row.label_clean
    sections = _section_parts(row)

    if company:  # this company's confirmed mappings first (spreader.company); calibrated like any rule
        for sec in [sections[0] if sections else "", ""]:
            target = company.get((table.statement.value, lab, sec))
            if target and target in profile.lines and any(ln.id == target for ln in lines):
                return RowMapping(row_index=row.index, canonical=target, method=MapMethod.MEMORY,
                                  confidence=calibrated("memory.company"), rule="memory.company",
                                  reason="The company's approved spread placed this label here before.")

    if memory:
        for sec in [sections[0] if sections else "", ""]:
            key = MemoryKey(profile.id, table.statement.value, lab, sec)
            if key in memory:
                target = memory[key]
                if target == "":
                    return RowMapping(row_index=row.index, canonical=None, method=MapMethod.MEMORY, confidence=0.99,
                                      excluded=True, reason="A reviewer excluded this label before.", rule="memory")
                if target in profile.lines:
                    return RowMapping(row_index=row.index, canonical=target, method=MapMethod.MEMORY, confidence=0.99,
                                      reason="A reviewer mapped this label before.", rule="memory")

    if not lab:
        return RowMapping(row_index=row.index, canonical=None, method=MapMethod.NONE, confidence=0.0,
                          reason="The row has no label.", rule="none")

    if (share_row := _per_share_rule(row, lab, lines)) is not None:
        return share_row

    terms = ontology.load()
    line_ids = {ln.id for ln in lines}
    found = terms.match(lab, table.statement.value, sections, industries, line_ids, wrong_side)
    if found and found.concept.overrides_alias:  # in this industry these words mean something else than the alias says
        return _from_ontology(row, found, lab)

    if row.role is RowRole.TOTAL:
        for ln in lines:
            if any(matches(p, lab) for p in ln.total_aliases):
                return RowMapping(row_index=row.index, canonical=ln.id, method=MapMethod.ALIAS, confidence=calibrated("alias.total"),
                                  reason=f"'{lab}' is a total (its rows add up to it) worded like {ln.label}.", rule="alias.total")

    for sec in sections:
        if any(matches(p, sec) for p in sdef.ignore_sections):
            return RowMapping(row_index=row.index, canonical=None, method=MapMethod.STRUCTURE, confidence=0.95,
                              excluded=True, reason=f"Under '{sec}', a disclosure that is not part of the statement.", rule="structure.ignored_section")

    # Section rules with explicit labels come first: "marketable securities" under "Non-current
    # assets" is long-term even though the same words alone mean short-term, and "Other" under
    # "Investing activities" is other investing, not other operating.
    for sec in sections:
        for ln in lines:
            for rule in ln.sections:
                if "*" in rule.labels:
                    continue
                if any(matches(s, sec) for s in rule.section) and any(matches(p, lab) for p in rule.labels):
                    return RowMapping(row_index=row.index, canonical=ln.id, method=MapMethod.ALIAS,
                                      confidence=calibrated("alias.section"),
                                      reason=f"'{lab}' under '{sec}' is {ln.label}.", rule="alias.section")

    exact = [ln for ln in lines if lab in ln.aliases]
    if len(exact) == 1:
        return RowMapping(row_index=row.index, canonical=exact[0].id, method=MapMethod.ALIAS, confidence=calibrated("alias.exact"),
                          reason=f"'{lab}' is an alias of {exact[0].label}.", rule="alias.exact")

    if len(exact) > 1:
        # The same alias on two lines ("basic" for EPS and for shares); the section decides.
        return RowMapping(row_index=row.index, canonical=None, method=MapMethod.NONE, confidence=0.0,
                          candidates=[(ln.id, 0.5) for ln in exact],
                          reason=f"'{lab}' could be {', '.join(ln.label for ln in exact)}.", rule="none")

    wild: list[tuple[int, LineDef]] = []
    for ln in lines:
        for p in ln.aliases:
            if "*" in p and matches(p, lab):
                wild.append((len(p.replace("*", "")), ln))
    if wild:
        wild.sort(key=lambda t: -t[0])
        best_len, best = wild[0]
        rivals = {ln.id for n, ln in wild if n == best_len and ln.id != best.id}
        if not rivals:
            return RowMapping(row_index=row.index, canonical=best.id, method=MapMethod.ALIAS, confidence=calibrated("alias.pattern"),
                              candidates=[(ln.id, 0.9) for _, ln in wild[1:4]],
                              reason=f"'{lab}' matches an alias pattern of {best.label}.", rule="alias.pattern")

    if _own_equity_total(row, lab) and any(ln.id == "total_equity_parent" for ln in lines):
        return RowMapping(row_index=row.index, canonical="total_equity_parent", method=MapMethod.STRUCTURE,
                          confidence=calibrated("structure.own_equity_total"),
                          reason=f"'{lab}' is a total of the company's own shareholders' equity, named after the company.",
                          rule="structure.own_equity_total")

    if found and (found.destination or found.concept.role == "disclosure"):
        return _from_ontology(row, found, lab)

    choices = {(ln.id, a): a for ln in lines for a in ln.aliases if "*" not in a}
    if choices:
        hits = process.extract(lab, choices, scorer=fuzz.token_sort_ratio, limit=3)
        if hits and hits[0][1] >= FUZZY_ACCEPT:
            (line_id, alias) = hits[0][2]
            return RowMapping(row_index=row.index, canonical=line_id, method=MapMethod.FUZZY, confidence=calibrated("fuzzy"),
                              candidates=[(h[2][0], round(h[1] / 100, 2)) for h in hits],
                              reason=f"'{lab}' is spelled almost like '{alias}' ({hits[0][1]:.0f}/100).", rule="fuzzy")
        cands = [(h[2][0], round(h[1] / 100, 2)) for h in hits if h[1] >= FUZZY_CANDIDATE]
    else:
        cands = []

    for sec in sections:
        for ln in lines:
            for rule in ln.sections:
                if "*" in rule.labels and any(matches(s, sec) for s in rule.section):
                    return RowMapping(row_index=row.index, canonical=ln.id, method=MapMethod.STRUCTURE,
                                      confidence=calibrated(f"catchall:{ln.id}"), candidates=cands,
                                      reason=f"'{lab}' sits under '{sec}', which feeds {ln.label}.", rule=f"catchall:{ln.id}")

    return RowMapping(row_index=row.index, canonical=None, method=MapMethod.NONE, confidence=0.0, candidates=cands,
                      reason=f"No alias or rule matches '{lab}'.", rule="none")


def _balance_sheet_sides(table: StatementTable) -> dict[int, frozenset[str]]:
    """Rows above "Total assets" are assets and rows below it are claims on them, whatever a label could mean elsewhere:
    "Deferred income taxes" below the line is a liability. Empty when the table has no such row."""
    if table.statement is not StatementType.BALANCE:
        return {}
    at = next((i for i, r in enumerate(table.rows) if r.label_clean == "total assets" or r.label_clean.startswith("total assets ")), None)
    if at is None:  # no such row: the first liabilities heading marks the same place
        at = next((i - 1 for i, r in enumerate(table.rows) if "liabilit" in r.label_clean and r.role is RowRole.HEADER), None)
    if at is None:
        return {}
    return {r.index: frozenset({"liability", "equity"}) if i <= at else frozenset({"asset"}) for i, r in enumerate(table.rows)}


def _name_the_concepts(table: StatementTable, out: dict[int, RowMapping], profile: Profile, industries: frozenset[str],
                       sides: dict[int, frozenset[str]]) -> None:
    """Give a row placed by any rule its detailed concept, when one means the same line here. The template rolls lease
    operating expenses and property operating expenses into one line; the concept keeps them apart."""
    terms = ontology.load()
    lines = set(profile.lines)
    for row in table.rows:
        m = out.get(row.index)
        if m is None or m.concept or not m.canonical:
            continue
        sections = _section_parts(row)
        for c in terms.candidates(row.label_clean, table.statement.value, sections, industries, sides.get(row.index, frozenset())):
            if terms.resolve(c, sections, lines, table.statement.value) == m.canonical:
                out[row.index] = m.model_copy(update={"concept": c.id})
                break


def _parts_within_their_total(table: StatementTable, out: dict[int, RowMapping], profile: Profile) -> None:
    """A concept that is part of a line cannot be larger than that line's total in any period. If it is, the words meant
    something else here, so the row goes to a person."""
    terms = ontology.load()
    by_index = {r.index: r for r in table.rows}
    totals = {m.canonical: by_index[i] for i, m in out.items() if m.canonical and by_index[i].role is RowRole.TOTAL}
    for i, m in list(out.items()):
        c = terms.by_id.get(m.concept or "")
        total = totals.get(c.part_of) if c and c.part_of else None
        if total is None or total.index == i:
            continue
        for key, v in by_index[i].values.items():
            t = total.values.get(key)
            if v.displayed is not None and t is not None and t.displayed is not None and abs(v.displayed) > abs(t.displayed):
                out[i] = m.model_copy(update={"canonical": None, "confidence": 0.0, "candidates": [(m.canonical, 0.5)], "rule": "ontology.part_exceeds_total",
                                              "reason": f"'{by_index[i].label}' reads as part of {profile.lines[c.part_of].label}, but it is larger than the total."})
                break


def map_table(table: StatementTable, profile: Profile, memory: Memory | None = None,
              model: ModelMapper | None = None, company: CompanyMemory | None = None,
              industries: frozenset[str] = frozenset()) -> list[RowMapping]:
    by_index = {r.index: r for r in table.rows}
    out: dict[int, RowMapping] = {}
    sides = _balance_sheet_sides(table)
    for row in table.rows:
        if row.role is RowRole.HEADER:
            continue
        out[row.index] = map_row(row, table, profile, memory, company, sides.get(row.index, frozenset()), industries)

    # A printed subtotal of rows already placed on different lines ("Total cash, cash equivalents
    # and short-term investments") is not a template line: placing it anywhere counts its rows
    # twice. It is left out, unless an alias names it as a template total.
    for row in table.rows:
        if row.role is not RowRole.TOTAL:
            continue
        m = out[row.index]
        targets = {out[c].canonical for c in row.children if c in out and out[c].canonical}
        # "Cash and cash equivalents" over "Cash" and "Interest-bearing deposits": worded like one of its own rows' lines,
        # but placing it there counts the other row twice.
        worded_like_a_part = (m.method is MapMethod.ALIAS and m.rule != "alias.total" and m.canonical in targets
                              and profile.lines[m.canonical].kind in {"asset", "liability"})
        if (m.method not in (MapMethod.STRUCTURE, MapMethod.NONE, MapMethod.FUZZY) and not worded_like_a_part) or m.rule == "structure.own_equity_total":
            continue
        if len(targets) >= 2:
            names = ", ".join(sorted(profile.lines[t].label for t in targets))
            out[row.index] = RowMapping(row_index=row.index, canonical=None, method=MapMethod.STRUCTURE, confidence=0.95,
                                        excluded=True,
                                        reason=f"A subtotal of rows already placed on {names}; left out so they are "
                                               "not counted twice (its footing is still checked).", rule="structure.cross_line_subtotal")

    # Structure: a total whose rows all feed one line feeds it too (when nothing else placed it).
    for row in table.rows:
        if row.role is not RowRole.TOTAL:
            continue
        m = out[row.index]
        child_maps = [out[c] for c in row.children if c in out]
        targets = {cm.canonical for cm in child_maps if cm.canonical}
        if m.canonical is None and not m.excluded and len(targets) == 1 and all(cm.canonical for cm in child_maps):
            target = targets.pop()
            out[row.index] = RowMapping(row_index=row.index, canonical=target, method=MapMethod.STRUCTURE,
                                        confidence=min(cm.confidence for cm in child_maps),
                                        reason=f"It is the total of rows that all feed {profile.lines[target].label}.", rule="structure.total_of_children")
        # "Total costs and expenses" that includes cost of revenue is not operating expenses.
        elif m.canonical == "total_opex" and any(cm.canonical == "cogs" for cm in child_maps) and "total_costs" in profile.lines:
            out[row.index] = m.model_copy(update={"canonical": "total_costs", "confidence": min(m.confidence, 0.95),
                                                  "reason": m.reason + " Its rows include cost of revenue, so it is total costs and expenses."})

    # Per-share figures never add: several rows on one line (continuing operations, then the total) mean the last one is
    # the company's figure.
    seen: dict[str, int] = {}
    for row in table.rows:
        m = out.get(row.index)
        if m and m.canonical and profile.lines[m.canonical].unit is ValueUnit.PER_SHARE and not m.excluded:
            earlier = seen.get(m.canonical)
            if earlier is not None:
                out[earlier] = out[earlier].model_copy(update={"canonical": None, "also": [], "excluded": True, "rule": "structure.per_share_superseded",
                                                                "reason": f"A later row gives {profile.lines[m.canonical].label} for the whole company."})
            seen[m.canonical] = row.index

    _name_the_concepts(table, out, profile, industries, sides)
    _parts_within_their_total(table, out, profile)

    if model is not None:
        sdef = profile.statements[table.statement]
        for idx, m in list(out.items()):
            if m.canonical is None and not m.excluded:
                row = by_index[idx]
                suggestion = model(table, row, [ln for ln in sdef.lines if _unit_ok(ln, row)])
                if suggestion is not None and suggestion.canonical in profile.lines:
                    out[idx] = suggestion
    return [out[r.index] for r in table.rows if r.index in out]
