"""Matching: candidate generation, scoring and assignment, one layer at a time.

Layers, strongest evidence first. Each only sees records no earlier layer used.

  1  reference       one record each side with the same reference, same currency and sign,
                     within the reference date window. Equal amounts: matched. A difference
                     within the review tolerance: proposed, with the difference shown.
  1b reference group one record on one side, several on the other, all with the same
                     reference, adding up to it (a batch deposit, a split settlement).
  2  amount and date one-to-one by equal amount within the date window. Records are joined
                     into components (everything connected by a possible pairing):
                       - a component of exactly one record per side: matched
                       - otherwise: matched only when every record's best partner is unique,
                         mutual and clearly better than the next (assignment); if not, the
                         best overall assignment is proposed and the whole component goes
                         to review as ambiguous, instead of picking one arbitrarily
  3  sums            one record equal to the sum of 2..N on the other side, no reference
                     tying them: proposed only. A record with two possible subsets, or a
                     subset wanted by two records, is ambiguous and nothing is proposed.
  4  amount difference  one-to-one with the same counterparty or description and an amount
                     difference within the review tolerance: proposed.
  5  partial         records that share a reference but whose amounts are further apart than
                     the review tolerance (a partial payment, an overpayment), if no layer above
                     explained them: proposed, with the open balance shown. Last on purpose, so a
                     partial never takes a record a sum or another rule would explain.

Hard constraints are never traded for a score: currency, sign, date window and tolerance must
all hold before a pair is even a candidate. A similarity score only orders candidates that
already satisfy them. Results do not depend on the order of rows in the files.

The "greedy" strategy (take the best-scoring pair first, everywhere) is kept as the baseline
the evaluation compares against.
"""

from __future__ import annotations

import bisect
import itertools
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz

from finops.core.exceptions import ExceptionItem, Severity, exception_id
from finops.core.fingerprint import content_hash
from finops.core.money import Tolerance
from finops.core.policy import AutoDecision, Calibration

from .config import ReconProfile
from .model import MatchGroup, MatchStatus, Txn

ASSIGNMENT_MARGIN = 10.0  # score points: one day of date gap, or a description that agrees
EXACT_MAX = 12
SMALL_POOL = 14  # sum search with a non-zero tolerance tries combinations, so it keeps the pool small


@dataclass
class MatchOutput:
    groups: list[MatchGroup] = field(default_factory=list)
    exceptions: list[ExceptionItem] = field(default_factory=list)


def group_id(left: Iterable[str], right: Iterable[str]) -> str:
    return "m-" + content_hash([sorted(left), sorted(right)], 12)


def make_exception(code: str, severity: Severity, title: str, detail: str, recs: list[Txn],
                   evidence: dict | None = None, action: str = "", key: list[str] | None = None) -> ExceptionItem:
    """`key` adds identity beyond the records (e.g. which decision was invalidated), so two exceptions about the
    same (or no) records never share an id."""
    recs = sorted(recs, key=lambda r: r.id)
    return ExceptionItem(id=exception_id("recon", code, [f"{r.id}:{r.content_hash}" for r in recs] + (key or [])), engine="recon",
                         code=code, severity=severity, title=title, detail=detail, subjects=[r.id for r in recs],
                         evidence=evidence or {}, suggested_action=action)


def _gap(a: Txn, b: Txn) -> int:
    return abs((a.date - b.date).days)


def _same_sign(a: Decimal, b: Decimal) -> bool:
    return (a > 0) == (b > 0) and a != 0 and b != 0


GENERIC = {"ACH", "CREDIT", "DEBIT", "DEPOSIT", "WIRE", "IN", "OUT", "PAYMENT", "RECEIPT", "CUSTOMER", "VENDOR",
           "TRANSFER", "CHECK", "CHK", "CHEQUE", "MOBILE", "BRANCH", "CARD", "SETTLEMENT", "POS", "ONLINE", "FROM", "TO",
           "TRF", "XFER", "REF", "INV", "INVOICE", "THE", "OF", "AND", "FOR", "BANK", "PAYEE", "PAYER", "SALES", "ITEM",
           # what banks abbreviate those to, and their own codes
           "DBT", "DR", "CR", "CRDT", "CRED", "DEP", "DPST", "PMT", "PYMT", "PAYROLL", "PYRLL", "PPD", "CCD", "WEB", "ID",
           "MOB", "MBL", "STLMT", "SETL", "TRNSFR", "XFR"}


def name_of(t: Txn) -> str:
    """The party a record names, without banking boilerplate ('ACH CREDIT NORTHWIND TRADERS' -> 'NORTHWIND TRADERS')."""
    text = t.counterparty or t.description
    words = [w for w in re.findall(r"[A-Z][A-Z&']+", text.upper()) if w not in GENERIC]
    return " ".join(words)


def name_similarity(a: Txn, b: Txn) -> int:
    """0-100: how alike the two records' party names are (0 when either names nobody)."""
    na, nb = name_of(a), name_of(b)
    return int(fuzz.token_set_ratio(na, nb)) if na and nb else 0


def _skeleton(text: str) -> str:
    """Words reduced to their first letter and consonants, the way banks abbreviate: MOREAU -> MR, TRADERS -> TRDRS."""
    return " ".join(w[0] + "".join(c for c in w[1:] if c not in "AEIOU") for w in text.split())


def names_agree(na: str, nb: str) -> bool:
    """The same party, allowing what bank exports do to names: truncation (FOU / FOURTH COFFEE), abbreviation
    (GUS MR / GUS MOREAU) and padding (NORTHWIND TRADERS PPD ID / NORTHWIND TRADERS)."""
    if not na or not nb:
        return False
    a, b = na.replace(" ", ""), nb.replace(" ", "")
    if min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)):
        return True
    if fuzz.token_set_ratio(na, nb) >= 70 or fuzz.partial_ratio(na, nb) >= 85:
        return True
    return fuzz.token_set_ratio(_skeleton(na), _skeleton(nb)) >= 85


def corroborated(a: Txn, b: Txn) -> str | None:
    """A second signal beyond amount and date, in words, or None: the references agree (a typo allowed) or the
    party names agree (a truncated or abbreviated bank description allowed)."""
    if a.reference and b.reference and fuzz.ratio(a.reference, b.reference) >= 75:
        return f"references {a.reference} and {b.reference} agree"
    na, nb = name_of(a), name_of(b)
    if names_agree(na, nb):
        return f"both name {nb.title()}"
    return None


def names_conflict(a: Txn, b: Txn) -> bool:
    """Both records name a party and the names have nothing in common."""
    na, nb = name_of(a), name_of(b)
    return bool(na and nb) and not names_agree(na, nb) and fuzz.token_set_ratio(na, nb) < 50


def similarity(a: Txn, b: Txn) -> int:
    ta = f"{a.counterparty} {a.description}".strip().upper()
    tb = f"{b.counterparty} {b.description}".strip().upper()
    if not ta or not tb:
        return 0
    return int(fuzz.token_set_ratio(ta, tb))


def money(x: Decimal) -> str:
    return f"{x:,.2f}"


class Matcher:
    def __init__(self, profile: ReconProfile, records: dict[str, Txn], locked: set[str],
                 forbidden: set[frozenset[str]], calibration: Calibration | None = None):
        self.p = profile
        self.m = profile.matching
        self.calibration = calibration  # None: rules as configured, uncalibrated (only to fit the calibration)
        self.auto_basis: dict[str, AutoDecision] = {}
        self.recs = records
        self.used: set[str] = set(locked)
        self.forbidden = forbidden
        self.out = MatchOutput()
        self.flagged: set[str] = set()  # records already named by a matching exception
        self.partials: list[tuple[str, list[Txn], list[Txn]]] = []  # (reference, left, right), proposed last
        # Records a person rejected a pairing for: their next pairing is proposed, never automatic, because the
        # rejection removed a candidate, not the doubt (one bank line, two equal ledger lines, one rejected).
        self.rejected_ids: set[str] = {m for f in forbidden for m in f}
        # Records that share a reference with a record on the other side whose amount differs (a partial payment
        # waiting for the last layer): an equal amount elsewhere is more likely a coincidence than their match.
        self.claimed: set[str] = set()

    # -- helpers -------------------------------------------------------------------------------

    def free(self, source: str) -> list[Txn]:
        return sorted((t for t in self.recs.values() if t.source == source and t.id not in self.used), key=lambda t: t.id)

    def _allowed(self, members: Iterable[str]) -> bool:
        return frozenset(members) not in self.forbidden

    def _add(self, left: list[Txn], right: list[Txn], rule: str, status: MatchStatus, why: list[str]) -> MatchGroup:
        diff = sum((t.amount for t in left), Decimal(0)) - sum((t.amount for t in right), Decimal(0))
        gap = max(_gap(a, b) for a in left for b in right)
        if rule in self.auto_basis:  # say why the rule may (or may not) settle matches on its own
            why = [*why, self.auto_basis[rule].reason]
        g = MatchGroup(id=group_id([t.id for t in left], [t.id for t in right]), left=sorted(t.id for t in left),
                       right=sorted(t.id for t in right), rule=rule, status=status, difference=diff,
                       date_gap_days=gap, explanation=why)
        for t in left + right:
            if t.id in self.used:  # a bug guard: a record can never be in two matches
                raise RuntimeError(f"record {t.id} would be matched twice")
            self.used.add(t.id)
        self.out.groups.append(g)
        return g

    def _auto(self, rule: str) -> MatchStatus:
        if rule not in self.m.auto_accept:
            return MatchStatus.PROPOSED
        if self.calibration is None:
            return MatchStatus.AUTO
        d = self.auto_basis.setdefault(rule, self.calibration.decide(rule, self.m.auto_accept_min_precision))
        return MatchStatus.AUTO if d.auto else MatchStatus.PROPOSED

    def _flag(self, code: str, sev: Severity, title: str, detail: str, recs: list[Txn], evidence: dict | None = None,
              action: str = "") -> None:
        self.out.exceptions.append(make_exception(code, sev, title, detail, recs, evidence, action))
        self.flagged.update(r.id for r in recs)

    def _difference_proposal(self, left: list[Txn], right: list[Txn], why: str) -> None:
        g = self._add(left, right, "amount_difference", MatchStatus.PROPOSED, [why])
        recs = left + right
        hint = ""
        if g.difference < 0 and len(left) == 1 and left[0].amount > 0:
            hint = " Less money arrived than was recorded: a deducted bank or card fee, or a short payment."
        self._flag("AMOUNT_DIFFERENCE", Severity.WARNING, f"Proposed match differs by {money(abs(g.difference))}",
                   f"{why} {self.p.left.label} {money(sum((t.amount for t in left), Decimal(0)))} vs "
                   f"{self.p.right.label} {money(sum((t.amount for t in right), Decimal(0)))}: difference "
                   f"{money(g.difference)}.{hint}", recs,
                   {"group": g.id, "difference": str(g.difference)},
                   "Accept the match and book the difference (e.g. a fee), or reject it.")

    # -- layer 1 and 1b: shared references -----------------------------------------------------

    def by_reference(self) -> None:
        L, R = defaultdict(list), defaultdict(list)
        for t in self.free(self.p.left.name):
            if t.reference:
                L[t.reference].append(t)
        for t in self.free(self.p.right.name):
            if t.reference:
                R[t.reference].append(t)
        for ref in sorted(set(L) & set(R)):
            ls, rs = L[ref], R[ref]
            if len(ls) == 1 and len(rs) == 1:
                self._reference_pair(ref, ls[0], rs[0])
            elif len(ls) == 1 or len(rs) == 1:
                self._reference_group(ref, ls, rs)

    def _reference_pair(self, ref: str, a: Txn, b: Txn) -> None:
        if a.currency != b.currency:
            self._flag("CURRENCY_MISMATCH", Severity.WARNING, f"Same reference {ref}, different currencies",
                       f"{a.id} is {a.currency} {money(a.amount)} and {b.id} is {b.currency} {money(b.amount)}. "
                       "Different currencies are never matched automatically.", [a, b], {"reference": ref},
                       "Check the conversion and match them by hand if they are the same payment.")
            return
        if not _same_sign(a.amount, b.amount) or _gap(a, b) > self.m.reference_date_window_days:
            return
        if not self._allowed([a.id, b.id]):
            return
        why = f"Both carry reference {ref}; dates {a.date} and {b.date} ({_gap(a, b)} days apart)."
        if self.m.amount_tolerance.within(a.amount, b.amount):
            self._add([a], [b], "reference", self._auto("reference"), [why + f" Amounts agree ({money(a.amount)})."])
        elif self.m.review_tolerance.within(a.amount, b.amount):
            self._difference_proposal([a], [b], why)
        else:
            self.partials.append((ref, [a], [b]))
            self.claimed.update((a.id, b.id))

    def _reference_group(self, ref: str, ls: list[Txn], rs: list[Txn]) -> None:
        one, many, one_left = (ls[0], rs, True) if len(ls) == 1 else (rs[0], ls, False)
        rule_name = "one_to_many" if one_left else "many_to_one"
        rule = self.m.one_to_many if one_left else self.m.many_to_one
        if not rule.enabled or len(many) > rule.max_items:
            return
        if any(t.currency != one.currency or not _same_sign(t.amount, one.amount)
               or _gap(t, one) > self.m.reference_date_window_days for t in many):
            return
        total = sum((t.amount for t in many), Decimal(0))
        left, right = ([one], many) if one_left else (many, [one])
        if not self._allowed([t.id for t in left + right]):
            return
        why = f"All {len(many) + 1} records carry reference {ref}; {len(many)} add up to {money(total)}."
        if self.m.amount_tolerance.within(one.amount, total):
            self._add(left, right, rule_name, self._auto(rule_name), [why])
        elif self.m.review_tolerance.within(one.amount, total):
            self._difference_proposal(left, right, why)
        else:
            self.partials.append((ref, left, right))
            self.claimed.update(t.id for t in left + right)

    # -- layer 2: one-to-one by amount and date --------------------------------------------------

    def _score(self, a: Txn, b: Txn) -> float:
        s = 100.0 - 10.0 * _gap(a, b)
        if a.reference and a.reference == b.reference:
            s += 30
        s += similarity(a, b) / 10.0
        if names_conflict(a, b):
            s -= 40  # an ACME payment is not BETA's, however close the dates
        return s

    def _edges(self, ls: list[Txn], rs: list[Txn], tol_ok, window: int,
               search: Tolerance | None = None) -> list[tuple[float, Txn, Txn]]:
        """Pairs that pass `tol_ok`; `search` is the widest tolerance `tol_ok` can accept (sets the lookup window)."""
        rs_sorted = sorted(rs, key=lambda t: (t.amount, t.id))
        amounts = [t.amount for t in rs_sorted]
        tol = search or self.m.amount_tolerance
        edges = []
        for a in ls:
            pad = (tol.abs or Decimal(0)) + (tol.pct or Decimal(0)) * abs(a.amount) * 2 + Decimal("0.01")
            lo = bisect.bisect_left(amounts, a.amount - pad)
            hi = bisect.bisect_right(amounts, a.amount + pad)
            for b in rs_sorted[lo:hi]:
                if (a.currency == b.currency and _same_sign(a.amount, b.amount) and _gap(a, b) <= window
                        and tol_ok(a.amount, b.amount) and self._allowed([a.id, b.id])):
                    edges.append((self._score(a, b), a, b))
        return edges

    def one_to_one(self) -> None:
        ls, rs = self.free(self.p.left.name), self.free(self.p.right.name)
        edges = self._edges(ls, rs, self.m.amount_tolerance.within, self.m.date_window_days)
        if self.m.strategy == "greedy":
            for s, a, b in sorted(edges, key=lambda e: (-e[0], e[1].id, e[2].id)):
                if a.id not in self.used and b.id not in self.used:
                    self._add([a], [b], "greedy", self._auto("unique_amount_date"),
                              [f"Best-scoring pair ({s:.0f}): {money(a.amount)} on {a.date} and {b.date}."])
            return
        for comp in _components(edges):
            self._resolve_component(comp)

    def _resolve_component(self, edges: list[tuple[float, Txn, Txn]]) -> None:
        lefts = sorted({e[1].id: e[1] for e in edges}.values(), key=lambda t: t.id)
        rights = sorted({e[2].id: e[2] for e in edges}.values(), key=lambda t: t.id)
        if len(edges) == 1:
            s, a, b = edges[0]
            why = (f"The only record on either side with {money(a.amount)} within {self.m.date_window_days} days "
                   f"({a.date} and {b.date}).")
            self._pair(a, b, "unique_amount_date", why)
            return
        score = {(a.id, b.id): s for s, a, b in edges}
        if len(lefts) == len(rights):
            pairs = _mutual_best(score, [t.id for t in lefts], [t.id for t in rights])
            if pairs is not None:
                for a_id, b_id in pairs:
                    a, b = self.recs[a_id], self.recs[b_id]
                    self._pair(a, b, "assignment", f"{len(lefts)} records on each side share amount {money(a.amount)}; "
                                                   f"each pair is the other's clear best (dates {a.date} and {b.date}).")
                return
        if self._settle_by_evidence(edges):
            return
        best = _best_assignment(score, [t.id for t in lefts], [t.id for t in rights])
        proposed = []
        for a_id, b_id in best:
            a, b = self.recs[a_id], self.recs[b_id]
            g = self._add([a], [b], "ambiguous", MatchStatus.PROPOSED,
                          [f"One of several possible pairings for {money(a.amount)}; the best overall assignment "
                           f"by date and description, not a certain one."])
            proposed.append(g.id)
        members = lefts + rights
        self._flag("AMBIGUOUS_CANDIDATES", Severity.WARNING,
                   f"{len(lefts)} vs {len(rights)} records could pair up for {money(lefts[0].amount)}",
                   f"{len(edges)} possible pairings among {', '.join(t.id for t in members)}. No pairing is clearly "
                   "best, so none was accepted automatically; the best overall assignment is proposed.", members,
                   {"candidates": [[a.id, b.id, round(s, 1)] for s, a, b in sorted(edges, key=lambda e: (-e[0], e[1].id, e[2].id))],
                    "proposed_groups": proposed},
                   "Pick the right pairing (accept or reject each proposal); look for a duplicate posting.")

    def late_by_name(self) -> None:
        """Same amount and same party, further apart than the date window but within the reference window (a cheque
        that cleared late and lost its reference in the export). Proposed only, and only when unique both ways."""
        ls, rs = self.free(self.p.left.name), self.free(self.p.right.name)
        cands = [(s, a, b) for s, a, b in self._edges(ls, rs, self.m.amount_tolerance.within, self.m.reference_date_window_days)
                 if _gap(a, b) > self.m.date_window_days and names_agree(name_of(a), name_of(b))]
        count: dict[str, int] = defaultdict(int)
        for _, a, b in cands:
            count[a.id] += 1
            count[b.id] += 1
        for _, a, b in sorted(cands, key=lambda e: (e[1].id, e[2].id)):
            if count[a.id] == 1 and count[b.id] == 1:
                g = self._add([a], [b], "late_by_name", MatchStatus.PROPOSED,
                              [f"Same amount ({money(a.amount)}) and party ({name_of(b).title()}), but {_gap(a, b)} days apart, "
                               f"beyond the {self.m.date_window_days}-day window: possibly a late-clearing payment."])
                self._flag("LATE_MATCH", Severity.WARNING, f"Possible late-clearing match, {_gap(a, b)} days apart",
                           f"{a.id} ({a.date}) and {b.id} ({b.date}) have the same amount and party but no common reference.",
                           [a, b], {"group": g.id}, "Accept if the bank's item is the same payment; otherwise reject.")

    def _settle_by_evidence(self, edges: list[tuple[float, Txn, Txn]]) -> bool:
        """In a mixed component (equal amounts that could pair several ways), settle the pairs that other evidence
        identifies: each record's ONLY candidate whose name or reference agrees, mutually. Several identical payroll
        payments to different people pair by name; two identical postings to the same customer stay ambiguous.
        The rest of the component is resolved again without them. Returns True when it settled anything."""
        good = [(s, a, b) for s, a, b in edges if not names_conflict(a, b) and corroborated(a, b)]
        count: dict[str, int] = defaultdict(int)
        for _, a, b in good:
            count[a.id] += 1
            count[b.id] += 1
        settle = [(a, b) for _, a, b in good if count[a.id] == 1 and count[b.id] == 1]
        if not settle:
            return False
        for a, b in settle:
            self._pair(a, b, "assignment", f"Of the records sharing {money(a.amount)}, these two are each other's only "
                                           f"candidate whose name or reference agrees (dates {a.date} and {b.date}).")
        rest = [e for e in edges if e[1].id not in self.used and e[2].id not in self.used]
        for comp in _components(rest):
            self._resolve_component(comp)
        return True

    def _pair(self, a: Txn, b: Txn, rule: str, why: str) -> None:
        """An amount-and-date pairing: automatic only if nothing argues against it."""
        if names_conflict(a, b):
            self._add([a], [b], rule, MatchStatus.PROPOSED, [why + f" But the names differ ('{name_of(a)}' vs '{name_of(b)}')."])
            self._flag("NAME_MISMATCH", Severity.WARNING, "Same amount and dates, different parties",
                       f"{a.id} names '{name_of(a)}' and {b.id} names '{name_of(b)}'. The amount and dates fit, so the "
                       "pairing is proposed, not accepted.", [a, b], {}, "Accept only if the remittance confirms it.")
        elif {a.id, b.id} & self.rejected_ids:
            self._add([a], [b], rule, MatchStatus.PROPOSED,
                      [why + " A person rejected another pairing for one of these records, so this one is only proposed."])
        elif {a.id, b.id} & self.claimed:
            self._add([a], [b], rule, MatchStatus.PROPOSED,
                      [why + " One of them shares a reference with another record whose amount differs (a possible partial "
                             "payment), so this pairing is only proposed."])
        elif self.m.require_corroboration and (second := corroborated(a, b)) is None:
            self._add([a], [b], rule, MatchStatus.PROPOSED,
                      [why + " Only the amount and date agree (no name or reference to confirm it), so it is proposed."])
        else:
            extra = f" Also {second}." if self.m.require_corroboration else ""
            self._add([a], [b], rule, self._auto(rule), [why + extra])

    # -- layer 3: sums -------------------------------------------------------------------------

    def sums(self, one_left: bool) -> None:
        rule = self.m.one_to_many if one_left else self.m.many_to_one
        if not rule.enabled:
            return
        ones = self.free(self.p.left.name if one_left else self.p.right.name)
        pool = self.free(self.p.right.name if one_left else self.p.left.name)
        tol = self.m.amount_tolerance
        solutions: dict[str, list[tuple[str, ...]]] = {}
        for one in ones:
            cands = [t for t in pool if t.currency == one.currency and _same_sign(t.amount, one.amount)
                     and abs(t.amount) < abs(one.amount) and _gap(t, one) <= self.m.date_window_days]
            cands = sorted(cands, key=lambda t: (_gap(t, one), t.id))[: rule.max_candidates]
            exact = tol.allowed(one.amount, one.amount) == 0
            found = [ids for ids in (_exact_subsets(one, cands, rule.max_items) if exact
                                     else _tolerant_subsets(one, cands[:SMALL_POOL], rule.max_items, tol))
                     if self._allowed((one.id,) + ids)][:2]
            if found:
                solutions[one.id] = found
        wanted: dict[str, set[str]] = defaultdict(set)
        for one_id, sols in solutions.items():
            for sol in sols:
                for m in sol:
                    wanted[m].add(one_id)
        name = "one_to_many" if one_left else "many_to_one"
        for one_id in sorted(solutions):
            sols = solutions[one_id]
            one = self.recs[one_id]
            contested = any(len(wanted[m]) > 1 for sol in sols for m in sol)
            if len(sols) == 1 and not contested:
                many = [self.recs[i] for i in sols[0]]
                left, right = ([one], many) if one_left else (many, [one])
                g = self._add(left, right, name, MatchStatus.PROPOSED,
                              [f"{len(many)} records add up to {money(one.amount)} within {self.m.date_window_days} days, "
                               "but no reference ties them, so a person must confirm."])
                self._flag("PROPOSED_GROUP", Severity.WARNING, f"{len(many)} records add up to {money(one.amount)}",
                           f"{', '.join(t.id for t in many)} sum to {one.id}. A sum can match by coincidence; "
                           "nothing else (a reference) links them.", [one] + many, {"group": g.id},
                           "Accept if the remittance or deposit slip confirms it; otherwise reject.")
            else:
                members = [one] + [self.recs[i] for sol in sols for i in sol if i not in self.used]
                members = list({t.id: t for t in members}.values())
                self._flag("AMBIGUOUS_CANDIDATES", Severity.WARNING,
                           f"Several combinations could make up {money(one.amount)}",
                           f"{one.id} could be the sum of more than one set of records, or its records are also "
                           "wanted by another total. Nothing was proposed.", members,
                           {"subsets": [list(s) for s in sols]}, "Match by hand using the remittance detail.")

    # -- layer 4: amount differences between clearly related records -----------------------------

    def differences(self) -> None:
        ls, rs = self.free(self.p.left.name), self.free(self.p.right.name)

        def ok(x: Decimal, y: Decimal) -> bool:
            return self.m.review_tolerance.within(x, y) and not self.m.amount_tolerance.within(x, y)

        cands = [(s, a, b) for s, a, b in self._edges(ls, rs, ok, self.m.date_window_days, self.m.review_tolerance)
                 if max(similarity(a, b), name_similarity(a, b)) >= self.m.description_similarity]
        count: dict[str, int] = defaultdict(int)
        for _, a, b in cands:
            count[a.id] += 1
            count[b.id] += 1
        for _, a, b in sorted(cands, key=lambda e: (e[1].id, e[2].id)):
            if count[a.id] == 1 and count[b.id] == 1:
                self._difference_proposal([a], [b], f"Same counterparty or description ({max(similarity(a, b), name_similarity(a, b))}/100 alike), "
                                                    f"dates {a.date} and {b.date}.")

    # -- layer 5: partial payments and overpayments, under a shared reference ----------------------

    def partial(self) -> None:
        for ref, left, right in self.partials:
            if any(t.id in self.used for t in left + right):
                continue  # an earlier layer explained them
            lsum = sum((t.amount for t in left), Decimal(0))
            rsum = sum((t.amount for t in right), Decimal(0))
            g = self._add(left, right, "partial", MatchStatus.PROPOSED,
                          [f"All carry reference {ref}, but {money(lsum)} vs {money(rsum)}: a partial payment or an "
                           "overpayment. The open balance stays visible."])
            bigger = self.p.left.label if abs(lsum) > abs(rsum) else self.p.right.label
            self._flag("PARTIAL_MATCH", Severity.WARNING, f"Partly settled: {money(abs(g.difference))} remains open",
                       f"Reference {ref}: {self.p.left.label} {money(lsum)} vs {self.p.right.label} {money(rsum)}. "
                       f"The {bigger} side is larger by {money(abs(g.difference))}; that balance stays open if the "
                       f"match is accepted. Beyond the review tolerance ({self.m.review_tolerance.describe()}), so a "
                       "keying error is possible too.", left + right,
                       {"group": g.id, "reference": ref, "open_balance": str(g.difference)},
                       "Accept as a partial (with a note on how the balance is handled) or reject and correct the source.")

    def run(self) -> MatchOutput:
        self.by_reference()
        self.one_to_one()
        self.sums(one_left=True)
        self.sums(one_left=False)
        self.differences()
        self.late_by_name()
        self.partial()
        return self.out


def _exact_subsets(one: Txn, cands: list[Txn], max_items: int, limit: int = 3) -> list[tuple[str, ...]]:
    """Every set of 2..max_items candidates (up to `limit`) summing exactly to one.amount.

    Amounts become integer cents, so sums are exact. Pairs are found with a lookup table and
    3- and 4-item sets by meeting in the middle (pair sums), so the work grows with the square
    of the candidate count, not its fourth power: 40 candidates cost ~800 pair sums, not 90,000.
    """
    target = int(one.amount * 100)
    cents = [int(t.amount * 100) for t in cands]
    n = len(cands)
    out: list[tuple[str, ...]] = []

    def add(idx: tuple[int, ...]) -> bool:
        ids = tuple(sorted(cands[i].id for i in idx))
        if ids not in out:
            out.append(ids)
        return len(out) >= limit

    pairs: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for i in range(n):
        for j in range(i + 1, n):
            pairs[cents[i] + cents[j]].append((i, j))
    for i, j in pairs.get(target, []):
        if add((i, j)):
            return out
    if max_items >= 3:
        pos: dict[int, list[int]] = defaultdict(list)
        for i, c in enumerate(cents):
            pos[c].append(i)
        for (i, j) in sorted(p for ps in pairs.values() for p in ps):
            for k in pos.get(target - cents[i] - cents[j], []):
                if k > j and add((i, j, k)):
                    return out
    if max_items >= 4:
        for s, ps in sorted(pairs.items()):
            for (i, j) in ps:
                for (k, m) in pairs.get(target - s, []):
                    if j < k and add((i, j, k, m)):
                        return out
    return out


def _tolerant_subsets(one: Txn, cands: list[Txn], max_items: int, tol: Tolerance) -> list[tuple[str, ...]]:
    """With a non-zero amount tolerance, try combinations over a small candidate pool."""
    out: list[tuple[str, ...]] = []
    for k in range(2, min(max_items, len(cands)) + 1):
        for combo in itertools.combinations(cands, k):
            if tol.within(one.amount, sum((t.amount for t in combo), Decimal(0))):
                out.append(tuple(sorted(t.id for t in combo)))
                if len(out) >= 3:
                    return out
    return out


def _components(edges: list[tuple[float, Txn, Txn]]) -> list[list[tuple[float, Txn, Txn]]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, a, b in edges:
        ra, rb = find(a.id), find(b.id)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    comps: dict[str, list[tuple[float, Txn, Txn]]] = defaultdict(list)
    for e in edges:
        comps[find(e[1].id)].append(e)
    return [sorted(c, key=lambda e: (e[1].id, e[2].id)) for _, c in sorted(comps.items())]


def _mutual_best(score: dict[tuple[str, str], float], lefts: list[str], rights: list[str]) -> list[tuple[str, str]] | None:
    """Pairs where each side's best partner is unique, mutual, and ASSIGNMENT_MARGIN ahead of the next."""
    def best(node: str, options: list[tuple[float, str]]) -> str | None:
        options = sorted(options, reverse=True)
        if not options:
            return None
        if len(options) > 1 and options[0][0] - options[1][0] < ASSIGNMENT_MARGIN:
            return None
        return options[0][1]

    pairs = []
    for a in lefts:
        b = best(a, [(s, r) for (lt, r), s in score.items() if lt == a])
        if b is None or best(b, [(s, lt) for (lt, r), s in score.items() if r == b]) != a:
            return None
        pairs.append((a, b))
    return pairs


def _best_assignment(score: dict[tuple[str, str], float], lefts: list[str], rights: list[str]) -> list[tuple[str, str]]:
    """The pairing with the highest total score (exact for small components, greedy beyond)."""
    small, large, flip = (lefts, rights, False) if len(lefts) <= len(rights) else (rights, lefts, True)

    def s(x: str, y: str) -> float | None:
        return score.get((y, x) if flip else (x, y))

    chosen: list[tuple[str, str]] = []
    if len(large) <= EXACT_MAX:
        # Exact maximum-weight assignment by dynamic programming over which large-side records
        # are taken: (most pairs, then highest total score). 2^12 states at most.
        dp: dict[int, tuple[int, float, list[tuple[str, str]]]] = {0: (0, 0.0, [])}
        for x in small:
            nxt = dict(dp)
            for mask, (n, tot, pairs) in dp.items():
                for j, y in enumerate(large):
                    v = s(x, y)
                    if v is None or mask & (1 << j):
                        continue
                    cand = (n + 1, tot + v, pairs + [(x, y)])
                    cur = nxt.get(mask | (1 << j))
                    if cur is None or cand[:2] > cur[:2]:
                        nxt[mask | (1 << j)] = cand
            dp = nxt
        chosen = max(dp.values(), key=lambda t: (t[0], t[1]))[2]
    else:
        used: set[str] = set()
        ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
        for (lt, r), _ in ranked:
            x, y = (r, lt) if flip else (lt, r)
            if x not in used and y not in used:
                chosen.append((x, y))
                used.update((x, y))
    return [((y, x) if flip else (x, y)) for x, y in chosen]
