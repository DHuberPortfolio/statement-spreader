"""One reconciliation run: deterministic, given the two files, the profile and prior decisions.

Prior human decisions are applied before any rule runs:
- an accepted match whose records are unchanged (same content hash) is kept, and its records
  are locked so no rule can use them again;
- an accepted match whose records changed or disappeared is NOT silently kept or dropped: it
  becomes a DECISION_INVALIDATED blocker naming what changed, and its records are matched afresh;
- a rejected pairing is never proposed again while its records are unchanged;
- an exception resolution carries over only to an exception with the same id (same code, same
  records, same content).

The run ends with completeness checks that prove no record was used twice or lost, and that the
difference between the two sides is fully explained by matches and open items.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from finops import __version__
from finops.core.exceptions import ExceptionStatus, Resolution, Severity

from .classify import classify
from .config import ReconProfile
from .matcher import Matcher, group_id, make_exception, money
from .model import MatchGroup, MatchStatus, ReconResult, Txn
from .normalize import load_source

ENGINE_VERSION = f"recon-{__version__}"


@dataclass
class Decisions:
    """The current effect of every human decision, replayed in order from the decision log."""

    accepted: list[dict[str, Any]] = field(default_factory=list)  # {left, right, hashes, actor, note, kind}
    rejected: list[dict[str, Any]] = field(default_factory=list)  # {members, hashes}
    resolutions: dict[str, Resolution] = field(default_factory=dict)


def reconcile(left_name: str, left_data: bytes, right_name: str, right_data: bytes, profile: ReconProfile,
              config_version: str, decisions: Decisions | None = None) -> ReconResult:
    t0 = time.perf_counter()
    decisions = decisions or Decisions()
    left, bad_l = load_source(left_name, left_data, profile.left, profile)
    right, bad_r = load_source(right_name, right_data, profile.right, profile)
    records: dict[str, Txn] = {t.id: t for t in left + right}
    t_load = time.perf_counter()

    groups: list[MatchGroup] = []
    exceptions = bad_l + bad_r
    locked: set[str] = set()
    for d in decisions.accepted:
        members = d["left"] + d["right"]
        changed = [m for m in members if m not in records or records[m].content_hash != d["hashes"].get(m)]
        if changed or locked & set(members):
            present = [records[m] for m in members if m in records]
            what = "; ".join(f"{m} {'is no longer in the files' if m not in records else 'changed'}" for m in changed)
            exceptions.append(make_exception(
                "DECISION_INVALIDATED", Severity.BLOCKER, "A match a person accepted no longer fits the data",
                f"{d['actor']} accepted {', '.join(members)} ({d.get('note') or 'no note'}). Since then: "
                f"{what or 'a record is in another accepted match'}. The records were matched afresh.", present,
                {"decision": d, "members": members}, "Review the changed records and decide again.",
                key=["decision", str(d.get("decision_id", "")), *sorted(members)]))
            continue
        lrecs, rrecs = [records[m] for m in d["left"]], [records[m] for m in d["right"]]
        diff = sum((t.amount for t in lrecs), Decimal(0)) - sum((t.amount for t in rrecs), Decimal(0))
        groups.append(MatchGroup(
            id=group_id(d["left"], d["right"]), left=sorted(d["left"]), right=sorted(d["right"]),
            rule="manual" if d.get("kind") == "manual" else "accepted", status=MatchStatus.ACCEPTED,
            decided_by=d["actor"], note=d.get("note", ""), difference=diff,
            date_gap_days=max(abs((a.date - b.date).days) for a in lrecs for b in rrecs),
            explanation=[f"Accepted by {d['actor']}" + (f": {d['note']}" if d.get("note") else ".")]))
        locked.update(members)
    forbidden = {frozenset(r["members"]) for r in decisions.rejected
                 if all(m in records and records[m].content_hash == r["hashes"].get(m) for m in r["members"])}

    matcher = Matcher(profile, records, locked, forbidden)
    out = matcher.run()
    groups += out.groups
    exceptions += out.exceptions
    t_match = time.perf_counter()

    in_group = {m for g in groups for m in g.left + g.right}
    period_end = max((t.date for t in left), default=None)
    exceptions += classify(profile, records, in_group, matcher.flagged, period_end)

    seen: set[str] = set()
    unique = []
    for e in exceptions:
        if e.id in seen:
            continue
        seen.add(e.id)
        if e.id in decisions.resolutions:
            e = e.model_copy(update={"status": ExceptionStatus.RESOLVED, "resolution": decisions.resolutions[e.id]})
        unique.append(e)

    totals, checks = _totals_and_checks(profile, records, groups)
    groups.sort(key=lambda g: (g.status != MatchStatus.PROPOSED, g.left + g.right))
    sev_order = {Severity.BLOCKER: 0, Severity.WARNING: 1, Severity.INFO: 2}
    unique.sort(key=lambda e: (e.status != ExceptionStatus.OPEN, sev_order[e.severity], e.code, e.id))
    return ReconResult(
        profile_id=profile.id, config_version=config_version, engine_version=ENGINE_VERSION,
        left_name=profile.left.name, right_name=profile.right.name, left_label=profile.left.label,
        right_label=profile.right.label, period_end=period_end, records=records, groups=groups, exceptions=unique,
        totals=totals, checks=checks,
        timings_ms={"load": round((t_load - t0) * 1000, 1), "match": round((t_match - t_load) * 1000, 1),
                    "total": round((time.perf_counter() - t0) * 1000, 1)})


def _totals_and_checks(profile: ReconProfile, records: dict[str, Txn], groups: list[MatchGroup]
                       ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    where: dict[str, list[str]] = defaultdict(list)
    for g in groups:
        for m in g.left + g.right:
            where[m].append(g.id)
    twice = sorted(m for m, gs in where.items() if len(gs) > 1)
    checks: list[dict[str, Any]] = [{
        "name": "No record is used by two matches", "status": "pass" if not twice else "fail",
        "detail": "Every record is in at most one match." if not twice else f"Used twice: {', '.join(twice)}"}]

    status_of = {m: g.status for g in groups for m in g.left + g.right}
    sides = [profile.left.name, profile.right.name]
    per_currency: dict[str, Any] = {}
    for cur in sorted({t.currency for t in records.values()}):
        b: dict[str, dict[str, Any]] = {}
        for side in sides:
            recs = [t for t in records.values() if t.source == side and t.currency == cur]

            def tot(xs: list[Txn]) -> dict[str, Any]:
                return {"count": len(xs), "amount": str(sum((t.amount for t in xs), Decimal(0)))}

            b[side] = {
                "all": tot(recs),
                "matched": tot([t for t in recs if status_of.get(t.id) in (MatchStatus.AUTO, MatchStatus.ACCEPTED)]),
                "proposed": tot([t for t in recs if status_of.get(t.id) is MatchStatus.PROPOSED]),
                "unmatched": tot([t for t in recs if t.id not in status_of]),
            }
        diff = Decimal(b[sides[0]]["all"]["amount"]) - Decimal(b[sides[1]]["all"]["amount"])
        cur_groups = [g for g in groups if records[(g.left + g.right)[0]].currency == cur]
        in_matched = sum((g.difference for g in cur_groups if g.status is not MatchStatus.PROPOSED), Decimal(0))
        in_proposed = sum((g.difference for g in cur_groups if g.status is MatchStatus.PROPOSED), Decimal(0))
        open_items = Decimal(b[sides[0]]["unmatched"]["amount"]) - Decimal(b[sides[1]]["unmatched"]["amount"])
        explained = in_matched + in_proposed + open_items
        per_currency[cur] = {"sides": b, "difference": str(diff), "in_matches": str(in_matched),
                             "in_proposals": str(in_proposed), "open_items": str(open_items)}
        checks.append({
            "name": f"{cur}: the difference between the two sides is fully explained",
            "status": "pass" if explained == diff else "fail",
            "detail": f"{profile.left.label} minus {profile.right.label} = {money(diff)}: {money(in_matched)} inside "
                      f"matches, {money(in_proposed)} inside proposals, {money(open_items)} in unmatched items."})
        accounted = sum(b[s][k]["count"] for s in sides for k in ("matched", "proposed", "unmatched"))
        total = sum(b[s]["all"]["count"] for s in sides)
        checks.append({"name": f"{cur}: every record is accounted for", "status": "pass" if accounted == total else "fail",
                       "detail": f"{accounted} of {total} records are matched, proposed or listed as unmatched."})
    tol = profile.matching.amount_tolerance
    bad = [g.id for g in groups if g.status is MatchStatus.AUTO
           and not tol.within(sum((records[m].amount for m in g.left), Decimal(0)), sum((records[m].amount for m in g.right), Decimal(0)))]
    checks.append({"name": "Automatic matches balance within the amount tolerance", "status": "pass" if not bad else "fail",
                   "detail": f"Tolerance: {tol.describe()}." if not bad else f"Out of tolerance: {', '.join(bad)}"})
    return {"currencies": per_currency}, checks


def summary(result: ReconResult) -> dict[str, Any]:
    """Counts a person reads first."""
    by_status: dict[str, int] = defaultdict(int)
    for g in result.groups:
        by_status[g.status.value] += 1
    open_by_sev: dict[str, int] = defaultdict(int)
    for e in result.exceptions:
        if e.status is ExceptionStatus.OPEN:
            open_by_sev[e.severity.value] += 1
    return {"records": len(result.records), "groups": dict(by_status), "open_exceptions": dict(open_by_sev),
            "checks_failed": sum(1 for c in result.checks if c["status"] == "fail")}


__all__ = ["reconcile", "Decisions", "summary", "ENGINE_VERSION", "date"]
