"""Records left unmatched become named exceptions, so a reviewer sees why, not just that.

Checked in this order for each unmatched record (a record can get more than one):

  REVERSAL           the same amount with the opposite sign in the same source, within days
                     (a returned deposit, a reversed payment)
  UNRECORDED_FEE     a bank charge, fee or interest line with nothing in the ledger
  POSSIBLE_DUPLICATE the same amount, date (within days) and reference or description as
                     another record in the same source
  TIMING_DIFFERENCE  a right-side item dated in the last days of the period: likely not yet
                     cleared (outstanding cheque, deposit in transit)
  UNMATCHED          none of the above: on one side and not the other

Every one of these is a suggestion with its evidence. None changes a balance or posts an entry.
"""

from __future__ import annotations

from datetime import date, timedelta

from finops.core.exceptions import ExceptionItem, Severity

from .config import ReconProfile
from .matcher import make_exception, money, similarity
from .model import Txn

REVERSAL_WORDS = ("return", "reversal", "reversed", "nsf", "chargeback", "refund", "void")


def classify(profile: ReconProfile, records: dict[str, Txn], matched: set[str], flagged: set[str],
             period_end: date | None) -> list[ExceptionItem]:
    rules = profile.exceptions
    out: list[ExceptionItem] = []
    free = sorted((t for t in records.values() if t.id not in matched), key=lambda t: (t.date, t.id))
    by_source: dict[str, list[Txn]] = {}
    for t in sorted(records.values(), key=lambda t: (t.date, t.id)):
        by_source.setdefault(t.source, []).append(t)
    labels = {profile.left.name: profile.left.label, profile.right.name: profile.right.label}
    other = {profile.left.name: profile.right.label, profile.right.name: profile.left.label}
    named: set[str] = set(flagged)
    paired: set[str] = set()

    for t in free:
        if t.id in paired:
            continue
        for s in by_source[t.source]:
            if s.id == t.id or s.id in paired or s.amount != -t.amount or abs((s.date - t.date).days) > rules.reversal_days:
                continue
            words = any(w in f"{t.description} {s.description}".lower() for w in REVERSAL_WORDS)
            if not (words or (t.reference and t.reference == s.reference) or similarity(s, t) >= 80):
                continue
            pair = [t] + ([s] if s.id not in matched else [])
            out.append(make_exception(
                "REVERSAL", Severity.WARNING, f"{labels[t.source]}: {money(abs(t.amount))} in and out again",
                f"{t.id} ({money(t.amount)}, {t.date}) reverses {s.id} ({money(s.amount)}, {s.date})"
                f"{' which is matched' if s.id in matched else ''}. Nothing on the {other[t.source]} records the reversal.",
                pair, {"reverses": s.id}, "Book the reversal (e.g. a returned deposit) or confirm both sides net to zero."))
            paired.update(x.id for x in pair)
            named.update(x.id for x in pair)
            break

    keywords = [k.lower() for k in rules.fee_keywords]
    for t in free:
        if any(k in t.description.lower() for k in keywords) and t.id not in paired:
            out.append(make_exception(
                "UNRECORDED_FEE", Severity.WARNING, f"{labels[t.source]}: charge not recorded ({money(t.amount)})",
                f"{t.id} '{t.description}' ({money(t.amount)}, {t.date}) looks like a fee, charge or interest, and the "
                f"{other[t.source]} has no matching entry.", [t], {},
                "Post the charge to the right expense or income account, then rerun."))
            named.add(t.id)

    for t in free:
        for s in by_source[t.source]:
            if s.id == t.id or s.amount != t.amount or abs((s.date - t.date).days) > rules.duplicate_date_days:
                continue
            same_ref = bool(t.reference) and t.reference == s.reference
            if same_ref or (t.description and similarity(s, t) >= 90):
                out.append(make_exception(
                    "POSSIBLE_DUPLICATE", Severity.WARNING, f"{labels[t.source]}: possible duplicate of {s.id}",
                    f"{t.id} and {s.id} have the same amount ({money(t.amount)}), dates {t.date} and {s.date}, and the "
                    f"same {'reference' if same_ref else 'description'}. {s.id} is "
                    f"{'matched' if s.id in matched else 'also unmatched'}.", [t], {"twin": s.id},
                    "Confirm whether it was recorded twice; reverse the duplicate if so."))
                named.add(t.id)
                break

    if period_end is not None:
        cutoff = period_end - timedelta(days=rules.timing_days)
        for t in free:
            if t.source == profile.right.name and t.date > cutoff and t.id not in named:
                out.append(make_exception(
                    "TIMING_DIFFERENCE", Severity.INFO, f"In the {labels[t.source]} near period end, not yet on the {other[t.source]}",
                    f"{t.id} ({money(t.amount)}, {t.date}) is within {rules.timing_days} days of the period end "
                    f"({period_end}); it has likely not cleared yet (outstanding payment or deposit in transit).", [t], {},
                    "Carry it as a reconciling item and check it clears next period."))
                named.add(t.id)

    for t in free:
        if t.id not in named:
            out.append(make_exception(
                "UNMATCHED", Severity.WARNING, f"In the {labels[t.source]}, not in the {other[t.source]}",
                f"{t.id} ({money(t.amount)}, {t.date}, '{t.description or t.reference}') has no counterpart that meets "
                "the matching rules.", [t], {"side": t.source},
                "Find the missing entry, or match it by hand with a note."))
    return out
