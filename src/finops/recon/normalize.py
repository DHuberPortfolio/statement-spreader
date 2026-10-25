"""Source rows -> Txn records, under the profile's explicit column mapping.

A row that cannot be read (no date, an amount that is not a number, money in and money out
both filled) is not dropped and not guessed: it becomes an INVALID_RECORD blocker that names
the file, the row and the reason, and it takes no part in matching.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from finops.core.exceptions import ExceptionItem, Severity, exception_id
from finops.core.fingerprint import content_hash
from finops.core.money import currency_in, parse_money
from finops.core.tabular import TableRow, read_table

from .config import ReconProfile, ReferenceRules, SourceSpec
from .model import Txn


class ReconInputError(ValueError):
    """The file as a whole does not fit the profile (missing columns, unreadable)."""


def normalize_reference(text: str, rules: ReferenceRules) -> str:
    t = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    for p in sorted(rules.strip_prefixes, key=len, reverse=True):
        p = re.sub(r"[^A-Z0-9]", "", p.upper())
        if p and t.startswith(p) and len(t) > len(p) and t[len(p)].isdigit():
            t = t[len(p):]
            break
    if rules.strip_leading_zeros and t.isdigit():
        t = t.lstrip("0") or "0"
    return t if len(t) >= rules.min_length else ""


def parse_date(text: str, formats: list[str]) -> date | None:
    t = (text or "").strip()
    if not t:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}T", t):
        t = t[:10]
    for f in formats:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def _invalid(spec: SourceSpec, row: TableRow, reason: str) -> ExceptionItem:
    subject = f"{spec.name}:row{row.ref.row}"
    return ExceptionItem(
        id=exception_id("recon", "INVALID_RECORD", [subject, content_hash(row.values)]), engine="recon",
        code="INVALID_RECORD", severity=Severity.BLOCKER,
        title=f"{spec.label}: a row could not be read",
        detail=f"{row.ref.text()}: {reason}. It was left out of matching.",
        subjects=[subject], evidence={"row": row.ref.row, "file": row.ref.file, "cells": row.values},
        suggested_action="Correct the source file and rerun, or record why the row can be ignored.")


def load_source(file_name: str, data: bytes, spec: SourceSpec, profile: ReconProfile) -> tuple[list[Txn], list[ExceptionItem]]:
    header, rows = read_table(file_name, data, spec.sheet)
    missing = [c for c in spec.required_columns() if c not in header]
    if missing:
        raise ReconInputError(f"{spec.label} ({file_name}) has no column {', '.join(repr(m) for m in missing)}; "
                              f"its columns are {', '.join(repr(h) for h in header if h)}")
    txns: list[Txn] = []
    problems: list[ExceptionItem] = []
    seen_ids: dict[str, int] = {}
    for row in rows:
        v = row.values
        d = parse_date(v[spec.date_field], spec.date_formats)
        if d is None:
            problems.append(_invalid(spec, row, f"date '{v[spec.date_field]}' is not in a known format "
                                                f"({', '.join(spec.date_formats)})"))
            continue
        if spec.amount_field:
            amount, why = parse_money(v[spec.amount_field])
            if amount is None:
                problems.append(_invalid(spec, row, why or f"amount is blank in '{spec.amount_field}'"))
                continue
        else:
            assert spec.inflow_field and spec.outflow_field
            a_in, why_in = parse_money(v[spec.inflow_field])
            a_out, why_out = parse_money(v[spec.outflow_field])
            if why_in or why_out:
                problems.append(_invalid(spec, row, why_in or why_out or ""))
                continue
            if a_in and a_out:
                problems.append(_invalid(spec, row, f"both '{spec.inflow_field}' and '{spec.outflow_field}' are filled"))
                continue
            if a_in is None and a_out is None:
                problems.append(_invalid(spec, row, "no amount in either money-in or money-out column"))
                continue
            negative = (a_in is not None and a_in < 0) or (a_out is not None and a_out < 0)
            if negative and spec.negative_in_columns == "refuse":
                problems.append(_invalid(spec, row, f"a negative number in '{spec.inflow_field}' or '{spec.outflow_field}': "
                                                    "a reversal or a formatting habit? Set negative_in_columns in the profile"))
                continue
            if spec.negative_in_columns == "reverse":
                amount = (a_in or Decimal(0)) - (a_out or Decimal(0))
            else:
                amount = abs(a_in or Decimal(0)) - abs(a_out or Decimal(0))
        if spec.amount_sign == "negate":
            amount = -amount
        cells = [v[f] for f in (spec.amount_field, spec.inflow_field, spec.outflow_field) if f]
        in_cell = {c for c in (currency_in(x) for x in cells) if c}
        column = v[spec.currency_field].strip().upper() if spec.currency_field else ""
        if len(in_cell) > 1 or (in_cell and column and column not in in_cell):
            problems.append(_invalid(spec, row, f"the amount says {'/'.join(sorted(in_cell))} but the currency column says "
                                                f"'{column}'"))
            continue
        currency = column or (next(iter(in_cell)) if in_cell else "") or profile.currency
        if not re.fullmatch(r"[A-Z]{3}", currency):
            problems.append(_invalid(spec, row, f"currency '{currency}' is not a three-letter code"))
            continue
        ref = normalize_reference(v[spec.reference_field], profile.matching.references) if spec.reference_field else ""
        desc = re.sub(r"\s+", " ", v[spec.description_field]).strip() if spec.description_field else ""
        cpty = re.sub(r"\s+", " ", v[spec.counterparty_field]).strip() if spec.counterparty_field else ""
        chash = content_hash([d.isoformat(), str(amount), currency, ref, desc.upper(), cpty.upper()])
        if spec.id_field:
            own = v[spec.id_field].strip()
            if not own:
                problems.append(_invalid(spec, row, f"'{spec.id_field}' (the transaction id) is blank"))
                continue
            base = f"{spec.name}:{own}"
        else:
            base = f"{spec.name}:h{chash[:10]}"
        n = seen_ids.get(base, 0) + 1
        seen_ids[base] = n
        tid = base if n == 1 else f"{base}#{n}"
        if spec.id_field and n > 1:
            problems.append(ExceptionItem(
                id=exception_id("recon", "DUPLICATE_SOURCE_ID", [tid, chash]), engine="recon", code="DUPLICATE_SOURCE_ID",
                severity=Severity.WARNING, title=f"{spec.label}: the same transaction id appears twice",
                detail=f"{row.ref.text()} repeats id '{own}'. Kept as {tid}; check whether the file was exported twice.",
                subjects=[tid], evidence={"row": row.ref.row}, suggested_action="Confirm whether it is a separate transaction."))
        txns.append(Txn(id=tid, source=spec.name, file=file_name, row=row.ref.row, date=d, amount=amount,
                        currency=currency, reference=ref, description=desc, counterparty=cpty,
                        raw={k: val for k, val in v.items()}, content_hash=chash))
    return txns, problems
