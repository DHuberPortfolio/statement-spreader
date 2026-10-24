"""Return on investment, built from measurements where they exist and labelled assumptions where not.

Every number the ROI report shows carries one of four labels:

    observed      measured in this application (timed work sessions, runs, evaluations)
    estimated     an observed number multiplied by an assumption (minutes saved x monthly volume)
    hypothetical  rests mainly on assumptions (the money value of an avoided error)
    verified      a realised financial outcome someone recorded (never produced by this code)

Rules that keep the report honest:
- Time saved per document is the difference between timed by-hand spreading (baseline mode) and
  timed review of an automated spread (assisted mode), active time only, with a range. With fewer
  than 3 sessions in either mode it is reported as "not measured", never as zero or a default.
- Released capacity is hours, not money saved. It becomes cash only through the "cash
  realisation" share a finance owner enters (default 0%: hours freed are not payroll cut).
- Review effort counts against the tool: assisted time includes every minute spent checking.
- Payback is only shown when the monthly net benefit is positive.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

# Defaults are placeholders to be replaced, labelled "default" wherever they appear.
DEFAULT_ASSUMPTIONS: dict[str, tuple[float, str]] = {
    "analyst_hourly_cost": (75.0, "Fully loaded cost of one analyst hour (wage / 0.70). Placeholder: replace with your figure."),
    "documents_per_month": (40.0, "Statement packages spread per month. Placeholder: count yours."),
    "values_per_document": (120.0, "Template values per spread (used for error costs)."),
    "implementation_hours": (120.0, "One-time hours to configure, connect and validate for a deployment."),
    "engineer_hourly_cost": (95.0, "Fully loaded cost of one engineering hour."),
    "maintenance_hours_per_month": (6.0, "Ongoing hours: new label aliases, profile updates, monitoring."),
    "infrastructure_per_month": (0.0, "Hosting and licences per month. Local prototype: 0."),
    "electricity_per_kwh": (0.15, "Price of a kWh, for local compute energy."),
    "watts_while_processing": (150.0, "Machine power draw while processing (measure with a meter or nvidia-smi)."),
    "cost_per_uncaught_error": (0.0, "Money cost of one wrong value reaching a decision. Default 0: not claimed until set."),
    "cash_realization_share": (0.0, "Share of released analyst hours that becomes cash saved (overtime, contractors, "
                                    "hiring avoided). Default 0: freed time is capacity, not savings."),
}

MIN_SESSIONS = 3


@dataclass
class Number:
    value: float | None
    label: str  # observed | estimated | hypothetical | verified | assumption | default
    unit: str
    explanation: str
    low: float | None = None
    high: float | None = None
    n: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "label": self.label, "unit": self.unit, "explanation": self.explanation,
                "low": self.low, "high": self.high, "n": self.n}


@dataclass
class Session:
    mode: str  # baseline | assisted
    document_id: str
    active_seconds: float
    corrections: int = 0
    values_entered: int = 0
    errors_found: int | None = None
    values_checked: int | None = None


@dataclass
class RoiInputs:
    assumptions: dict[str, tuple[float, str]]  # key -> (value, source: entered | default)
    sessions: list[Session]
    compute_seconds: list[float]  # pipeline processing time per run (observed)
    silent_error: tuple[int, int] | None = None  # (wrong auto-accepted, auto-accepted) from the evaluation
    silent_error_source: str = ""
    synthetic_sessions: bool = False  # sessions on demo documents by the developer, not real work


@dataclass
class RoiReport:
    numbers: dict[str, Number] = field(default_factory=dict)
    scenarios: dict[str, dict[str, float | None]] = field(default_factory=dict)
    sensitivity: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"numbers": {k: v.as_dict() for k, v in self.numbers.items()}, "scenarios": self.scenarios,
                "sensitivity": self.sensitivity, "warnings": self.warnings}


def _t_crit(df: int) -> float:
    """Two-sided 95% critical value of Student's t (exact table for small df, normal beyond)."""
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
             12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}
    if df <= 0:
        return math.inf
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def mean_range(xs: list[float]) -> tuple[float, float, float]:
    m = statistics.fmean(xs)
    if len(xs) < 2:
        return m, -math.inf, math.inf
    se = statistics.stdev(xs) / math.sqrt(len(xs))
    t = _t_crit(len(xs) - 1)
    return m, m - t * se, m + t * se


def wilson(n: int, d: int) -> tuple[float, float]:
    z = 1.96
    p = n / d
    den = 1 + z * z / d
    c = (p + z * z / (2 * d)) / den
    h = z * math.sqrt(p * (1 - p) / d + z * z / (4 * d * d)) / den
    return max(0.0, c - h), min(1.0, c + h)


def compute(inp: RoiInputs) -> RoiReport:
    rep = RoiReport()
    A = {k: v for k, (v, _) in inp.assumptions.items()}
    src = {k: s for k, (_, s) in inp.assumptions.items()}
    for k, (v, s) in inp.assumptions.items():
        rep.numbers[f"assumption.{k}"] = Number(v, "assumption" if s == "entered" else "default",
                                                _unit_of(k), DEFAULT_ASSUMPTIONS.get(k, (0, ""))[1])
    if inp.synthetic_sessions:
        rep.warnings.append("Timed sessions were recorded on demonstration documents by the developer, not by analysts "
                            "doing real work. They show the method works; they are not evidence of savings.")

    base = [s.active_seconds / 60 for s in inp.sessions if s.mode == "baseline" and s.active_seconds > 0]
    assist = [s.active_seconds / 60 for s in inp.sessions if s.mode == "assisted" and s.active_seconds > 0]
    if len(base) >= MIN_SESSIONS:
        m, lo, hi = mean_range(base)
        rep.numbers["baseline_minutes"] = Number(m, "observed", "minutes per document",
                                                 "Active minutes to spread a document by hand (baseline sessions).", lo, hi, len(base))
    else:
        rep.numbers["baseline_minutes"] = Number(None, "observed", "minutes per document",
                                                 f"Not measured: {len(base)} baseline session(s); at least {MIN_SESSIONS} needed.",
                                                 n=len(base))
    if len(assist) >= MIN_SESSIONS:
        m, lo, hi = mean_range(assist)
        rep.numbers["assisted_minutes"] = Number(m, "observed", "minutes per document",
                                                 "Active minutes to review and approve an automated spread, including "
                                                 "every correction (assisted sessions).", lo, hi, len(assist))
    else:
        rep.numbers["assisted_minutes"] = Number(None, "observed", "minutes per document",
                                                 f"Not measured: {len(assist)} assisted session(s); at least {MIN_SESSIONS} needed.",
                                                 n=len(assist))

    # Paired difference when the same documents were done both ways (the stronger design).
    by_doc: dict[str, dict[str, list[float]]] = {}
    for s in inp.sessions:
        by_doc.setdefault(s.document_id, {}).setdefault(s.mode, []).append(s.active_seconds / 60)
    diffs = [statistics.fmean(d["baseline"]) - statistics.fmean(d["assisted"]) for d in by_doc.values()
             if d.get("baseline") and d.get("assisted")]
    saved: Number
    if len(diffs) >= MIN_SESSIONS:
        m, lo, hi = mean_range(diffs)
        saved = Number(m, "observed", "minutes per document",
                       "Paired: the same documents timed by hand and assisted. Order effects (seeing a document twice) "
                       "make this optimistic unless different people or a wash-out period were used.", lo, hi, len(diffs))
    elif rep.numbers["baseline_minutes"].value is not None and rep.numbers["assisted_minutes"].value is not None:
        b, a = rep.numbers["baseline_minutes"], rep.numbers["assisted_minutes"]
        m = b.value - a.value  # type: ignore[operator]
        lo = (b.low or 0) - (a.high or 0)
        hi = (b.high or 0) - (a.low or 0)
        saved = Number(m, "observed", "minutes per document",
                       "Difference of the two means (different documents in each mode); the range is conservative.", lo, hi,
                       min(len(base), len(assist)))
    else:
        saved = Number(None, "observed", "minutes per document",
                       "Not measured yet: time at least three documents by hand and three in assisted mode.")
    rep.numbers["minutes_saved"] = saved

    if inp.compute_seconds:
        cs = statistics.fmean(inp.compute_seconds)
        rep.numbers["compute_seconds"] = Number(cs, "observed", "seconds per document",
                                                "Processing time of the pipeline per run (median machine, local).",
                                                min(inp.compute_seconds), max(inp.compute_seconds), len(inp.compute_seconds))
        kwh = cs / 3600 * A["watts_while_processing"] / 1000
        rep.numbers["compute_cost"] = Number(kwh * A["electricity_per_kwh"], "estimated", "$ per document",
                                             "Processing seconds x assumed power x assumed electricity price.")
    # Quality: hand-keying errors (baseline sessions checked against the approved spread) vs the
    # silent error rate of the automated spread (evaluation).
    checked = [s for s in inp.sessions if s.mode == "baseline" and s.values_checked]
    if checked:
        n = sum(s.errors_found or 0 for s in checked)
        d = sum(s.values_checked or 0 for s in checked)
        lo, hi = wilson(n, d)
        rep.numbers["baseline_error_rate"] = Number(n / d, "observed", "share of values",
                                                    "Hand-keyed values that disagreed with the approved spread.", lo, hi, d)
    if inp.silent_error:
        n, d = inp.silent_error
        if d:
            lo, hi = wilson(n, d)
            rep.numbers["silent_error_rate"] = Number(n / d, "observed", "share of values",
                                                      f"Wrong values that no review item flagged ({inp.silent_error_source}). "
                                                      "Measured on the evaluation set, not on this organisation's documents.",
                                                      lo, hi, d)

    # Money.
    vol = A["documents_per_month"]

    monthly_costs = A["maintenance_hours_per_month"] * A["engineer_hourly_cost"] + A["infrastructure_per_month"]
    if "compute_cost" in rep.numbers and rep.numbers["compute_cost"].value is not None:
        monthly_costs += rep.numbers["compute_cost"].value * vol
    rep.numbers["monthly_costs"] = Number(monthly_costs, "estimated", "$ per month",
                                          "Maintenance hours x engineer cost + infrastructure + compute energy.")
    implementation = A["implementation_hours"] * A["engineer_hourly_cost"]
    rep.numbers["implementation_cost"] = Number(implementation, "estimated", "$ one-time",
                                                "Implementation hours x engineer cost.")

    def money(minutes_saved: float | None, a: dict[str, float]) -> dict[str, float | None]:
        if minutes_saved is None:
            return {"capacity_hours": None, "capacity_value": None, "cash_savings": None, "net_monthly_cash": None,
                    "net_monthly_capacity": None, "first_year_roi_cash": None, "payback_months_cash": None}
        hours = minutes_saved * a["documents_per_month"] / 60
        capacity_value = hours * a["analyst_hourly_cost"]
        cash = capacity_value * a["cash_realization_share"]
        costs = a["maintenance_hours_per_month"] * a["engineer_hourly_cost"] + a["infrastructure_per_month"]
        impl = a["implementation_hours"] * a["engineer_hourly_cost"]
        net_cash = cash - costs
        net_cap = capacity_value - costs
        roi = (12 * net_cash - impl) / impl if impl > 0 else None
        payback = impl / net_cash if net_cash > 0 else None
        return {"capacity_hours": hours, "capacity_value": capacity_value, "cash_savings": cash,
                "net_monthly_cash": net_cash, "net_monthly_capacity": net_cap, "first_year_roi_cash": roi,
                "payback_months_cash": payback}

    expected = money(saved.value, A)
    for k, v in expected.items():
        label = "estimated"
        expl = {
            "capacity_hours": "Minutes saved per document x documents per month / 60. Hours freed, not money.",
            "capacity_value": "Released hours x analyst cost: what the freed time is worth if it goes to other work.",
            "cash_savings": "Released capacity value x cash realisation share (default 0%).",
            "net_monthly_cash": "Cash savings minus monthly running costs.",
            "net_monthly_capacity": "Capacity value minus monthly running costs (economic value, not cash).",
            "first_year_roi_cash": "(12 x net monthly cash - implementation) / implementation.",
            "payback_months_cash": "Implementation / net monthly cash; shown only when net monthly cash is positive.",
        }[k]
        unit = {"capacity_hours": "hours per month", "first_year_roi_cash": "ratio", "payback_months_cash": "months"}.get(k, "$ per month")
        rep.numbers[k] = Number(v, label, unit, expl)
    if expected["payback_months_cash"] is None and expected["net_monthly_cash"] is not None:
        rep.warnings.append("No payback: the cash benefit does not cover the running costs at these assumptions "
                            "(with cash realisation at its default of 0%, no cash saving is claimed).")

    if "baseline_error_rate" in rep.numbers and "silent_error_rate" in rep.numbers:
        be, se = rep.numbers["baseline_error_rate"].value or 0, rep.numbers["silent_error_rate"].value or 0
        avoided = (be - se) * A["values_per_document"] * vol
        rep.numbers["errors_avoided_per_month"] = Number(avoided, "hypothetical", "values per month",
                                                         "(hand-keying error rate - silent error rate) x values x volume. "
                                                         "Negative means the tool lets more errors through than hand-keying.")
        rep.numbers["error_value_per_month"] = Number(avoided * A["cost_per_uncaught_error"], "hypothetical", "$ per month",
                                                      "Errors avoided x assumed cost of an uncaught error (default 0).")

    # Scenarios: the range of minutes saved, with volume +-25%.
    if saved.value is not None:
        low_a, high_a = dict(A), dict(A)
        low_a["documents_per_month"] *= 0.75
        high_a["documents_per_month"] *= 1.25
        rep.scenarios = {"low": money(saved.low if saved.low is not None and math.isfinite(saved.low) else None, low_a),
                         "expected": expected,
                         "high": money(saved.high if saved.high is not None and math.isfinite(saved.high) else None, high_a)}
        # One-way sensitivity of monthly capacity net benefit to each assumption (+-25%).
        base_net = expected["net_monthly_capacity"] or 0.0
        for k in ("analyst_hourly_cost", "documents_per_month", "maintenance_hours_per_month", "engineer_hourly_cost"):
            lo_a, hi_a = dict(A), dict(A)
            lo_a[k] *= 0.75
            hi_a[k] *= 1.25
            rep.sensitivity.append({"assumption": k,
                                    "low": (money(saved.value, lo_a)["net_monthly_capacity"] or 0) - base_net,
                                    "high": (money(saved.value, hi_a)["net_monthly_capacity"] or 0) - base_net})
        rep.sensitivity.sort(key=lambda s: -abs(s["high"] - s["low"]))
        if saved.value > 0 and expected["capacity_value"]:
            per_doc_value = saved.value / 60 * A["analyst_hourly_cost"]
            if per_doc_value > 0:
                rep.numbers["break_even_documents"] = Number(monthly_costs / per_doc_value, "estimated", "documents per month",
                                                             "Monthly running costs / capacity value of one document.")
    if any(s == "default" for s in src.values()):
        rep.warnings.append("Some assumptions are still placeholders (labelled 'default'). Replace them with your "
                            "organisation's figures before showing money numbers to anyone.")
    return rep


def _unit_of(key: str) -> str:
    if "share" in key:
        return "share"
    if key.endswith("_cost") or key.startswith("infrastructure") or key.startswith("electricity") or key.startswith("cost"):
        return "$"
    if "hours" in key:
        return "hours"
    if key.startswith("watts"):
        return "W"
    return "count"
