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

from collections.abc import Callable
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .contracts import MapMethod, RowMapping, RowRole, StatementRow, StatementTable, ValueUnit
from .profile import LineDef, Profile, matches

FUZZY_ACCEPT = 93.0
FUZZY_CANDIDATE = 82.0
CONFIDENCE_REVIEW = 0.80  # a value-bearing row below this goes to review
CONFIDENCE_REVIEW_CRITICAL = 0.90


@dataclass(frozen=True)
class MemoryKey:
    profile_id: str
    statement: str
    label: str
    section: str


Memory = dict[MemoryKey, str]  # -> canonical line id ("" means "exclude this row")
ModelMapper = Callable[[StatementTable, StatementRow, list[LineDef]], RowMapping | None]


def _unit_ok(line: LineDef, row: StatementRow) -> bool:
    if row.unit is ValueUnit.PERCENT:
        return False
    return line.unit is row.unit


def _section_parts(row: StatementRow) -> list[str]:
    return [s for s in reversed(row.section.split(" > ")) if s] if row.section else []


def map_row(row: StatementRow, table: StatementTable, profile: Profile, memory: Memory | None = None) -> RowMapping:
    sdef = profile.statements[table.statement]
    lines = [ln for ln in sdef.lines if _unit_ok(ln, row)]
    lab = row.label_clean
    sections = _section_parts(row)

    if memory:
        for sec in [sections[0] if sections else "", ""]:
            key = MemoryKey(profile.id, table.statement.value, lab, sec)
            if key in memory:
                target = memory[key]
                if target == "":
                    return RowMapping(row_index=row.index, canonical=None, method=MapMethod.MEMORY, confidence=0.99,
                                      excluded=True, reason="A reviewer excluded this label before.")
                if target in profile.lines:
                    return RowMapping(row_index=row.index, canonical=target, method=MapMethod.MEMORY, confidence=0.99,
                                      reason="A reviewer mapped this label before.")

    if not lab:
        return RowMapping(row_index=row.index, canonical=None, method=MapMethod.NONE, confidence=0.0,
                          reason="The row has no label.")

    for sec in sections:
        if any(matches(p, sec) for p in sdef.ignore_sections):
            return RowMapping(row_index=row.index, canonical=None, method=MapMethod.STRUCTURE, confidence=0.95,
                              excluded=True, reason=f"Under '{sec}', a disclosure that is not part of the statement.")

    # Section rules with explicit labels come first: "marketable securities" under "Non-current
    # assets" is long-term even though the same words alone mean short-term, and "Other" under
    # "Investing activities" is other investing, not other operating.
    for depth, sec in enumerate(sections):
        for ln in lines:
            for rule in ln.sections:
                if "*" in rule.labels:
                    continue
                if any(matches(s, sec) for s in rule.section) and any(matches(p, lab) for p in rule.labels):
                    return RowMapping(row_index=row.index, canonical=ln.id, method=MapMethod.ALIAS,
                                      confidence=0.97 - 0.02 * depth,
                                      reason=f"'{lab}' under '{sec}' is {ln.label}.")

    exact = [ln for ln in lines if lab in ln.aliases]
    if len(exact) == 1:
        return RowMapping(row_index=row.index, canonical=exact[0].id, method=MapMethod.ALIAS, confidence=1.0,
                          reason=f"'{lab}' is an alias of {exact[0].label}.")

    if len(exact) > 1:
        # The same alias on two lines ("basic" for EPS and for shares); the section decides.
        return RowMapping(row_index=row.index, canonical=None, method=MapMethod.NONE, confidence=0.0,
                          candidates=[(ln.id, 0.5) for ln in exact],
                          reason=f"'{lab}' could be {', '.join(ln.label for ln in exact)}.")

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
            return RowMapping(row_index=row.index, canonical=best.id, method=MapMethod.ALIAS, confidence=0.95,
                              candidates=[(ln.id, 0.9) for _, ln in wild[1:4]],
                              reason=f"'{lab}' matches an alias pattern of {best.label}.")

    choices = {(ln.id, a): a for ln in lines for a in ln.aliases if "*" not in a}
    if choices:
        hits = process.extract(lab, choices, scorer=fuzz.token_sort_ratio, limit=3)
        if hits and hits[0][1] >= FUZZY_ACCEPT:
            (line_id, alias) = hits[0][2]
            return RowMapping(row_index=row.index, canonical=line_id, method=MapMethod.FUZZY, confidence=0.85,
                              candidates=[(h[2][0], round(h[1] / 100, 2)) for h in hits],
                              reason=f"'{lab}' is spelled almost like '{alias}' ({hits[0][1]:.0f}/100).")
        cands = [(h[2][0], round(h[1] / 100, 2)) for h in hits if h[1] >= FUZZY_CANDIDATE]
    else:
        cands = []

    for depth, sec in enumerate(sections):
        for ln in lines:
            for rule in ln.sections:
                if "*" in rule.labels and any(matches(s, sec) for s in rule.section):
                    base = rule.confidence if rule.confidence is not None else 0.75
                    return RowMapping(row_index=row.index, canonical=ln.id, method=MapMethod.STRUCTURE,
                                      confidence=base - 0.03 * depth, candidates=cands,
                                      reason=f"'{lab}' sits under '{sec}', which feeds {ln.label}.")

    return RowMapping(row_index=row.index, canonical=None, method=MapMethod.NONE, confidence=0.0, candidates=cands,
                      reason=f"No alias or rule matches '{lab}'.")


def map_table(table: StatementTable, profile: Profile, memory: Memory | None = None,
              model: ModelMapper | None = None) -> list[RowMapping]:
    by_index = {r.index: r for r in table.rows}
    out: dict[int, RowMapping] = {}
    for row in table.rows:
        if row.role is RowRole.HEADER:
            continue
        out[row.index] = map_row(row, table, profile, memory)

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
                                        reason=f"It is the total of rows that all feed {profile.lines[target].label}.")
        # "Total costs and expenses" that includes cost of revenue is not operating expenses.
        elif m.canonical == "total_opex" and any(cm.canonical == "cogs" for cm in child_maps) and "total_costs" in profile.lines:
            out[row.index] = m.model_copy(update={"canonical": "total_costs", "confidence": min(m.confidence, 0.95),
                                                  "reason": m.reason + " Its rows include cost of revenue, so it is total costs and expenses."})

    if model is not None:
        sdef = profile.statements[table.statement]
        for idx, m in list(out.items()):
            if m.canonical is None and not m.excluded:
                row = by_index[idx]
                suggestion = model(table, row, [ln for ln in sdef.lines if _unit_ok(ln, row)])
                if suggestion is not None and suggestion.canonical in profile.lines:
                    out[idx] = suggestion
    return [out[r.index] for r in table.rows if r.index in out]
