"""From a laid-out table to statement rows: sections, units, values per period, and totals.

Totals are found by footing, the way an accountant ticks a schedule: a row is a total when it
equals the sum of the rows directly above it in every period column. A label that says "Total"
is not trusted on its own, and a total that does not foot is reported, because either the
extraction misread a number or the document itself does not add up.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .contracts import (
    ParsedValue,
    Period,
    RawTable,
    RowRole,
    StatementRow,
    StatementTable,
    StatementType,
    ValueUnit,
)
from .detect import detect_scale, parse_period
from .layout import Layout
from .numbers import clean_label, parse_amount

_PER_SHARE = re.compile(r"per (common )?share|\beps\b|per unit\b|per diluted share|per basic share", re.I)
# A share count row, not a money row that mentions shares ("Common stock, $0.01 par value, 100
# shares authorized" is money; "Payments for taxes related to net share settlement" is money).
_SHARES = re.compile(r"weighted average|shares used|number of (common )?shares|shares outstanding|"
                     r"^(basic|diluted)( shares)?$|^(basic|diluted) weighted|common shares outstanding|units outstanding",
                     re.I)
_MONEY_WORDS = re.compile(r"par value|paid in|capital|authorized|payments?|proceeds|repurchase|issuance|"
                          r"settlement|compensation|dividend|treasury|stock based|share based", re.I)
_PER_SHARE_SECTION = re.compile(r"per (common )?share|\beps\b|earnings loss per|net income loss per", re.I)
_SHARES_SECTION = re.compile(r"shares used|weighted average|shares outstanding|number of shares|share count", re.I)
_NOT_PERIOD = re.compile(r"%|\bchange\b|\bvariance\b|\bnotes?\b|\bref\b|previously reported|as originally|\bbudget|"
                         r"\bforecast|\bplan\b|pro\s*forma|\bprojected|\btarget", re.I)
_EUROPEAN_MULTI = re.compile(r"^\(?[$€£]?\s*-?\d{1,3}(\.\d{3}){2,}(,\d+)?\)?$|^\(?[$€£]?\s*-?\d{1,3}(\.\d{3})+,\d+\)?$")
_EUROPEAN_SINGLE = re.compile(r"^\(?[$€£]?\s*-?\d{1,3}\.\d{3}\)?$")

MAX_FOOTING_RUN = 30


def build_statement(table: RawTable, layout: Layout, statement: StatementType, doc_id: str,
                    score: float) -> StatementTable:
    warnings = list(layout.warnings)
    # Periods, one per value column. Columns that are not periods (a "% change" column, a
    # "Note" column) are dropped and said so.
    periods: list[Period | None] = []
    month_days: list[tuple[int, int]] = []
    # Most specific first: the header row's own label cell, the title rows, then the text above.
    title = " | ".join([layout.header_label_text, layout.title_text, table.context[-250:]])
    for slot in layout.slots:
        if _NOT_PERIOD.search(slot.header or ""):
            periods.append(None)
            warnings.append(f"Column '{slot.header}' is not a period and was left out.")
            continue
        p = parse_period(slot.header, statement, title=title)
        periods.append(p)
        if p and not p.assumed:
            y, mo, d = p.end.split("-")
            month_days.append((int(mo), int(d)))
    # Year-only columns borrow the month and day printed over another column.
    if month_days:
        for i, slot in enumerate(layout.slots):
            p = periods[i]
            if p is not None and p.assumed and any("Only the year" in a for a in p.assumed):
                periods[i] = parse_period(slot.header, statement, fallback_month_day=month_days[0], title=title)
    if not any(periods):
        # No headers at all: the columns exist but their periods are unknown.
        warnings.append("No period headers were found; columns are numbered instead.")
        periods = [Period(key=f"col{i + 1}", end=f"col{i + 1}", months=None if statement is StatementType.BALANCE else 12,
                          label=f"Column {i + 1}", assumed=["The column has no period header."])
                   for i in range(len(layout.slots))]
    seen: dict[str, int] = {}
    for i, p in enumerate(periods):
        if p is None:
            continue
        if p.key in seen:
            warnings.append(f"DUPLICATE_PERIOD:{p.key}: two columns read as the same period ({p.key}); the second "
                            "was left out. Confirm which column is the one to spread.")
            periods[i] = None
        else:
            seen[p.key] = i

    texts = [layout.title_text + " " + layout.header_label_text,
             " ".join(" ".join(t.text for t in r.tokens) for r in layout.header_rows),
             table.context[-400:], table.context]
    scale, share_scale = detect_scale(texts)

    # European grouping ("1.234.567", "1.234,5") anywhere in the table means a lone "719.147" is
    # 719 thousand, not 719.147: refuse every such number in the table instead of misreading it.
    european = any(_EUROPEAN_MULTI.match(t.text.strip()) for lo in layout.rows for t in lo.values.values())

    rows: list[StatementRow] = []
    section_stack: list[tuple[float, str]] = []
    for lo in layout.rows:
        label = lo.label
        lab = clean_label(label)
        values: dict[str, ParsedValue] = {}
        for si, tok in lo.values.items():
            p = periods[si]
            if p is None:
                continue
            amount, why = parse_amount(tok.text)
            if european and _EUROPEAN_SINGLE.match(tok.text.strip()):
                amount, why = None, f"'{tok.text}' uses European number grouping, which is not supported"
            values[p.key] = ParsedValue(
                raw=tok.text,
                displayed=amount.displayed if amount else None,
                negative_display=amount.negative_display if amount else False,
                dash=amount.dash if amount else False,
                ref=tok.ref,
                note=why,
            )
        has_values = any(v.displayed is not None for v in values.values())
        if not label and not has_values:
            continue
        indent = lo.row.indent
        if not has_values:
            # A section header. Close sections at the same or deeper indentation.
            while section_stack and section_stack[-1][0] >= indent:
                section_stack.pop()
            section_stack.append((indent, lab))
            rows.append(StatementRow(index=lo.row.index, label=label, label_clean=lab,
                                     section=" > ".join(s for _, s in section_stack[:-1]),
                                     indent=indent, bold=lo.row.bold, role=RowRole.HEADER,
                                     label_ref=lo.label_token.ref if lo.label_token else None))
            continue
        # A total closes the section it totals ("Total current assets" ends "Current assets:").
        section = " > ".join(s for _, s in section_stack)
        unit = _unit(lab, section, [lo.values[si].text for si in lo.values if periods[si] is not None])
        if unit in (ValueUnit.MONEY, ValueUnit.SHARES):
            # A money amount printed with exactly three decimals ("719.147") is how European
            # statements write 719,147. US statements print money as whole numbers, so this is
            # ambiguous: refuse it rather than read it either way.
            for k, pv in values.items():
                if pv.displayed is not None and _EUROPEAN_SINGLE.match(pv.raw.strip()):
                    values[k] = pv.model_copy(update={"displayed": None, "note": (
                        f"'{pv.raw}' is ambiguous: three decimals on an amount is how European statements write "
                        "thousands (719.147 = 719,147); not read")})
        rows.append(StatementRow(index=lo.row.index, label=label, label_clean=lab, section=section, indent=indent,
                                 bold=lo.row.bold, unit=unit, values=values,
                                 label_ref=lo.label_token.ref if lo.label_token else None))
        if lab.startswith("total") and section_stack:
            words = set(lab.replace("total", "").split())
            if words and words <= set(section_stack[-1][1].split()) | {"net"}:
                section_stack.pop()
        elif lab and section_stack and indent < section_stack[-1][0]:  # an unlabelled subtotal closes nothing
            while section_stack and indent < section_stack[-1][0]:
                section_stack.pop()

    kept = [p for p in periods if p is not None]
    st = StatementTable(doc_id=doc_id, table_index=table.index, statement=statement,
                        title=layout.title_text[:200] or statement.value.replace("_", " "),
                        periods=kept, scale=scale, share_scale=share_scale, rows=rows,
                        detection_score=score, warnings=warnings)
    find_totals(st)
    return st


_FYE = re.compile(r"(?:fiscal\s+)?(?:year|period)\s+ended\s*:?\s*((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{1,2}\s*,?\s*\d{4})",
                  re.I)


def fiscal_year_end(preface: str) -> str | None:
    """The fiscal year-end a filing's cover page states ("For the fiscal year ended January 3, 2026")."""
    from .detect import parse_period

    m = _FYE.search(preface or "")
    if not m:
        return None
    p = parse_period(m.group(1), StatementType.BALANCE)
    return p.end if p and not p.assumed else None


def harmonize_periods(tables: list[StatementTable], preface: str = "") -> None:
    """Give year-only columns the exact fiscal year-end another statement prints.

    An income statement headed "2025 | 2024" next to a balance sheet headed "September 27, 2025"
    ends on September 27, not on an assumed December 31. Changes are recorded on the period.
    """
    exact: dict[str, str] = {}
    for t in tables:
        for p in t.periods:
            if not any("Only the year" in a or "assumed to end" in a for a in p.assumed):
                exact.setdefault(p.end[:4], p.end)
    fye = fiscal_year_end(preface)
    if fye and not exact:
        # Only the years are printed anywhere; the cover page names the latest year-end. A year
        # ending early in January (a 52/53-week year) is labelled by the year before it.
        label_year = int(fye[:4]) - 1 if fye[5:7] == "01" and int(fye[8:10]) <= 10 else int(fye[:4])
        years = {p.end[:4] for t in tables for p in t.periods}
        if str(label_year) in years:
            for t in tables:
                rename: dict[str, str] = {}
                new_periods = []
                for p in t.periods:
                    if not any("Only the year" in a for a in p.assumed):
                        new_periods.append(p)
                        continue
                    shift = int(p.end[:4]) - label_year
                    end = f"{int(fye[:4]) + shift:04d}{fye[4:]}"
                    key = f"{end}/{'I' if p.months is None else f'{p.months}M'}"
                    kept = [a for a in p.assumed if "Only the year" not in a]
                    notes = list(p.notes)
                    if shift == 0:
                        notes.append(f"The column prints {p.end[:4]}; the cover page says the fiscal year ended {fye}.")
                    else:
                        kept.append(f"The column prints {p.end[:4]}; its end date is assumed to fall on the same day as the "
                                    f"latest year-end ({fye}); 52/53-week years can differ by a few days.")
                    rename[p.key] = key
                    new_periods.append(p.model_copy(update={"key": key, "end": end, "assumed": kept, "notes": notes}))
                t.periods = new_periods
                for r in t.rows:
                    r.values = {rename.get(k, k): v for k, v in r.values.items()}
            return
    for t in tables:
        rename: dict[str, str] = {}
        new_periods = []
        for p in t.periods:
            year_only = any("Only the year" in a for a in p.assumed)
            if year_only and p.end[:4] in exact and exact[p.end[:4]] != p.end:
                end = exact[p.end[:4]]
                key = f"{end}/{'I' if p.months is None else f'{p.months}M'}"
                note = f"The column prints only {p.end[:4]}; the date {end} is taken from another statement in the document."
                kept = [a for a in p.assumed if "Only the year" not in a]
                rename[p.key] = key
                new_periods.append(p.model_copy(update={"key": key, "end": end, "assumed": kept, "notes": p.notes + [note]}))
            elif year_only and p.end[:4] in exact:
                kept = [a for a in p.assumed if "Only the year" not in a]
                new_periods.append(p.model_copy(update={"assumed": kept}))
            else:
                new_periods.append(p)
        t.periods = new_periods
        if rename:
            for r in t.rows:
                r.values = {rename.get(k, k): v for k, v in r.values.items()}


def _unit(lab: str, section: str, period_texts: list[str]) -> ValueUnit:
    raw_vals = " ".join(period_texts)
    if "%" in raw_vals:
        return ValueUnit.PERCENT
    if _PER_SHARE.search(lab) and not _MONEY_WORDS.search(lab):
        return ValueUnit.PER_SHARE
    if _MONEY_WORDS.search(lab):
        return ValueUnit.MONEY
    nearest = section.split(" > ")[-1] if section else ""
    if _SHARES.search(lab) and not re.fullmatch(r"(basic|diluted)", lab):
        return ValueUnit.SHARES
    if _PER_SHARE_SECTION.search(nearest) and not _SHARES_SECTION.search(nearest):
        return ValueUnit.PER_SHARE
    if _SHARES_SECTION.search(nearest):
        return ValueUnit.SHARES
    return ValueUnit.MONEY


def _val(row: StatementRow, key: str) -> Decimal | None:
    v = row.values.get(key)
    if v is None:
        return None
    return v.displayed


def find_totals(st: StatementTable) -> None:
    """Mark rows that foot (equal the sum of a run of rows directly above them in every period)."""
    keys = [p.key for p in st.periods]
    money_rows = [i for i, r in enumerate(st.rows) if r.role is not RowRole.HEADER and r.unit is ValueUnit.MONEY]
    consumed: set[int] = set()  # positions (in st.rows) already counted inside a total
    for pos in money_rows:
        row = st.rows[pos]
        row_keys = [k for k in keys if _val(row, k) is not None]
        if not row_keys:
            continue
        if all(_val(row, k) == 0 for k in row_keys):
            continue
        # Units above: each earlier money row not inside an earlier total, nearest first.
        units: list[int] = []
        j = pos - 1
        while j >= 0 and len(units) < MAX_FOOTING_RUN:
            r = st.rows[j]
            if r.role is RowRole.HEADER or r.unit is not ValueUnit.MONEY:
                j -= 1
                continue
            if j not in consumed:
                units.append(j)
            j -= 1
        total = {k: Decimal(0) for k in row_keys}
        for n, u in enumerate(units, start=1):
            for k in row_keys:
                total[k] += _val(st.rows[u], k) or Decimal(0)
            if n < 2:
                continue
            tol = Decimal(n) * Decimal("0.5") * _last_digit_unit(row, row_keys)
            if all(abs(total[k] - (_val(row, k) or 0)) <= tol for k in row_keys):
                single_period = len(row_keys) < 2
                looks_total = row.label_clean.startswith("total") or row.bold
                if single_period and not looks_total:
                    break
                row.role = RowRole.TOTAL
                row.children = [st.rows[u].index for u in reversed(units[:n])]
                consumed.update(units[:n])
                break


def _last_digit_unit(row: StatementRow, keys: list[str]) -> Decimal:
    """The size of one unit in the last printed digit (1 for '1,234', 0.01 for '7.49')."""
    smallest = Decimal(1)
    for k in keys:
        v = row.values[k]
        if "." in v.raw:
            decimals = len(v.raw.split(".")[-1].rstrip(")%* "))
            smallest = min(smallest, Decimal(1).scaleb(-decimals))
    return smallest
