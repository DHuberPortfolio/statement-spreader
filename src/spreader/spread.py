"""Assembling the spread: one value per canonical line and period, each with its provenance.

Rules, in order:
- A row that is inside a total feeding the same line is a component: it is checked (footing)
  but not added again. Otherwise "Products" + "Services" + "Total net sales" would triple-count.
- Several separate rows feeding one line are added, and the value says it is a sum.
- Cost lines printed in parentheses (a presentation choice some companies make) are spread as
  positive costs, but only when the statement prints costs that way consistently; a single
  negative tax line is a tax benefit, not a presentation choice.
- The printed scale is applied last, and the value records the scale's evidence.
"""

from __future__ import annotations

from decimal import Decimal

from .contracts import (
    MapMethod,
    Period,
    ProvenanceStep,
    RowMapping,
    RowRole,
    SourceRef,
    SpreadValue,
    StatementTable,
    ValueStatus,
    ValueUnit,
)
from .profile import Profile


def _fmt(v: Decimal) -> str:
    return f"{v:,}"


def costs_shown_negative(table: StatementTable, mappings: list[RowMapping], profile: Profile) -> bool:
    by_index = {r.index: r for r in table.rows}
    neg = pos = 0
    for m in mappings:
        if not m.canonical or profile.lines[m.canonical].kind != "cost":
            continue
        for v in by_index[m.row_index].values.values():
            if v.displayed is None or v.displayed == 0:
                continue
            if v.negative_display:
                neg += 1
            else:
                pos += 1
    return neg >= 3 and neg >= 2 * pos


def assemble_statement(table: StatementTable, mappings: list[RowMapping], profile: Profile) -> list[SpreadValue]:
    by_index = {r.index: r for r in table.rows}
    mapping_of = {m.row_index: m for m in mappings}
    flip_costs = costs_shown_negative(table, mappings, profile)
    # A row the statement itself adds into a printed total as a negative number is a deduction
    # ("Interest expense (10)" between operating income and pre-tax income).
    parent_total = {c: r for r in table.rows if r.role is RowRole.TOTAL for c in r.children}

    # Rows feeding each line, minus components of a total that feeds the same line.
    feeding: dict[str, list[int]] = {}
    for m in mappings:
        if m.canonical and not m.excluded:
            feeding.setdefault(m.canonical, []).append(m.row_index)
    components: set[int] = set()
    for line, idxs in feeding.items():
        for i in idxs:
            row = by_index[i]
            if row.role is RowRole.TOTAL:
                for c in row.children:
                    if mapping_of.get(c) and mapping_of[c].canonical == line:
                        components.add(c)
    # Nested: a component's own children are components too.
    changed = True
    while changed:
        changed = False
        for i in list(components):
            for c in by_index[i].children:
                if c not in components and mapping_of.get(c) and mapping_of[c].canonical == mapping_of[i].canonical:
                    components.add(c)
                    changed = True

    out: list[SpreadValue] = []
    for line, idxs in feeding.items():
        ldef = profile.lines[line]
        sources = [i for i in idxs if i not in components]
        for period in table.periods:
            parts = [(i, by_index[i].values.get(period.key)) for i in sources]
            parts = [(i, v) for i, v in parts if v is not None and v.displayed is not None]
            if not parts:
                continue
            steps: list[ProvenanceStep] = []
            refs: list[SourceRef] = []
            total = Decimal(0)
            for i, v in parts:
                assert v.displayed is not None
                refs.append(v.ref) if v.ref else None
                shown = "a dash (nothing)" if v.dash else f"'{v.raw}'"
                steps.append(ProvenanceStep(kind="read", detail=f"Row '{by_index[i].label}': {shown} read as {_fmt(v.displayed)}"))
                total += v.displayed
            if len(parts) > 1:
                steps.append(ProvenanceStep(kind="sum", detail=f"Added {len(parts)} rows: {_fmt(total)}"))
            status = ValueStatus.EXTRACTED if len(parts) == 1 else ValueStatus.NORMALIZED
            if ldef.deduction and flip_costs:
                total = -total
                steps.append(ProvenanceStep(kind="sign", detail="This statement prints costs and tax in parentheses; "
                                                                "spread with tax expense positive"))
                status = ValueStatus.NORMALIZED
            elif ldef.kind == "cost" and total < 0:
                parents = {parent_total[i].label for i, _ in parts if i in parent_total}
                if flip_costs:
                    total = -total
                    steps.append(ProvenanceStep(kind="sign", detail="This statement prints costs in parentheses; spread as a positive cost"))
                    status = ValueStatus.NORMALIZED
                elif parents:
                    total = -total
                    steps.append(ProvenanceStep(kind="sign", detail=f"Printed as a deduction inside '{sorted(parents)[0]}'; "
                                                                    "spread as a positive cost"))
                    status = ValueStatus.NORMALIZED
            unit = by_index[parts[0][0]].unit
            mult, evidence, assumed = _multiplier(table, unit)
            if mult != 1:
                steps.append(ProvenanceStep(kind="scale", detail=f"Multiplied by {mult:,} ({evidence})"))
            elif assumed:
                steps.append(ProvenanceStep(kind="scale", detail=f"No unit statement found; taken as printed ({evidence})"))
            value = total * mult
            confs = [mapping_of[i].confidence for i, _ in parts]
            methods = {mapping_of[i].method for i, _ in parts}
            m0 = mapping_of[parts[0][0]]
            steps.append(ProvenanceStep(kind="map", detail=f"Mapped to {ldef.label} by {m0.method.value}: {m0.reason}"))
            if MapMethod.MODEL in methods:
                status = ValueStatus.AI_MAPPED
            if assumed or any(period.assumed):
                status = ValueStatus.ASSUMED
            out.append(SpreadValue(line=line, period=period.key, value=value, status=status, confidence=min(confs),
                                   source_rows=[i for i, _ in parts], refs=refs, steps=steps))
    return out


def _multiplier(table: StatementTable, unit: ValueUnit) -> tuple[int, str, bool]:
    if unit is ValueUnit.PER_SHARE or unit is ValueUnit.PERCENT:
        return 1, "per-share amounts are not scaled", False
    if unit is ValueUnit.SHARES:
        if table.share_scale is not None:
            return table.share_scale.multiplier, table.share_scale.evidence, table.share_scale.assumed
        return table.scale.multiplier, f"{table.scale.evidence}; no separate unit for share counts", True
    return table.scale.multiplier, table.scale.evidence, table.scale.assumed


def merge_periods(tables: list[StatementTable]) -> list[Period]:
    """All periods across statements, newest first."""
    seen: dict[str, Period] = {}
    for t in tables:
        for p in t.periods:
            seen.setdefault(p.key, p)
    return sorted(seen.values(), key=lambda p: (p.end, p.months or 0), reverse=True)
