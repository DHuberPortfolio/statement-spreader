import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { DocumentRow, MoneyBlock, RoiLabel, RoiNumber, RoiReport, WorkSession } from "../api/types";
import { Layout } from "../components/Layout";
import { endActiveSession } from "../lib/session";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { can } from "../lib/auth";
import { formatDateTime, formatDuration, formatNumber } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { setSession, useSession } from "../lib/store";
import { useApi } from "../lib/useApi";
import { useSimulated } from "../lib/simulated";
import { FinopsRoiSection } from "./FinopsRoi";

// ---- labels ----

const LABELS: Record<RoiLabel, string> = {
  observed: "Measured in this application: timed sessions and tests.",
  estimated: "An observed number multiplied by an assumption.",
  hypothetical: "Rests mainly on assumptions (for example the money value of an avoided error).",
  verified: "A financial result someone recorded. This application never produces one.",
  assumption: "A figure your organisation entered.",
  default: "A placeholder still to be replaced with your organisation's figure.",
};

export const LABEL_WORDS: Record<RoiLabel, string> = {
  observed: "Measured",
  estimated: "Estimated",
  hypothetical: "Rough estimate",
  verified: "Confirmed",
  assumption: "Your figure",
  default: "Placeholder",
};

export function LabelBadge({ label }: { label: RoiLabel }) {
  const simulated = useSimulated();
  if (simulated && (label === "observed" || label === "estimated" || label === "hypothetical")) {
    return (
      <span className="roi-label roi-label-default" title="Worked out from made-up work in a simulated workspace. Not a measurement.">
        Simulated
      </span>
    );
  }
  return (
    <span className={`roi-label roi-label-${label}`} title={LABELS[label]}>
      {LABEL_WORDS[label]}
    </span>
  );
}

const TITLES: Record<string, string> = {
  baseline_minutes: "By hand, per document",
  assisted_minutes: "Assisted review, per document",
  minutes_saved: "Minutes saved per document",
  compute_seconds: "Processing time per document",
  compute_cost: "Electricity per document",
  baseline_error_rate: "Hand-keying error rate",
  silent_error_rate: "Wrong numbers no one was asked to check",
  monthly_costs: "Running costs",
  implementation_cost: "Implementation",
  capacity_hours: "Analyst hours released",
  capacity_value: "Value of the released hours",
  cash_savings: "Cash saved",
  net_monthly_cash: "Net monthly cash",
  net_monthly_capacity: "Net monthly capacity value",
  first_year_roi_cash: "First-year cash return",
  payback_months_cash: "Cash payback",
  errors_avoided_per_month: "Errors avoided",
  error_value_per_month: "Value of errors avoided",
  break_even_documents: "Break-even volume",
};

const ASSUMPTION_TITLES: Record<string, string> = {
  analyst_hourly_cost: "Analyst cost per hour",
  documents_per_month: "Documents per month",
  values_per_document: "Values per document",
  implementation_hours: "Implementation hours",
  engineer_hourly_cost: "Engineer cost per hour",
  maintenance_hours_per_month: "Maintenance hours per month",
  infrastructure_per_month: "Infrastructure per month",
  electricity_per_kwh: "Electricity per kWh",
  watts_while_processing: "Power while processing",
  cost_per_uncaught_error: "Cost of one uncaught error",
  cash_realization_share: "Cash realisation share",
};

function smallMoney(v: number): string {
  const a = Math.abs(v);
  if (a === 0) return "$0";
  if (a >= 100) return formatNumber(v, { prefix: "$" });
  if (a >= 1) return formatNumber(v, { prefix: "$", decimals: 2 });
  return `${v < 0 ? "−" : ""}$${a.toPrecision(2)}`;
}

function formatRoiValue(v: number | null | undefined, unit: string): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "";
  if (unit.startsWith("$")) return smallMoney(v) + (unit.length > 1 ? ` ${unit.slice(2)}` : "");
  switch (unit) {
    case "share":
    case "share of values":
      return formatNumber(v * 100, { decimals: Math.abs(v) < 0.01 && v !== 0 ? 2 : 1, suffix: "%", parens: false });
    case "ratio":
      return formatNumber(v * 100, { decimals: 0, suffix: "%", parens: false });
    case "minutes per document":
      return formatNumber(v, { decimals: 1, suffix: " min", parens: false });
    case "seconds per document":
      return `${v < 1 ? v.toPrecision(2) : formatNumber(v, { decimals: 1, parens: false })} s`;
    case "hours":
    case "hours per month":
      return formatNumber(v, { decimals: 1, suffix: " h", parens: false }) + (unit === "hours per month" ? " / month" : "");
    case "months":
      return formatNumber(v, { decimals: 1, suffix: " months", parens: false });
    case "W":
      return formatNumber(v, { suffix: " W", parens: false });
    case "documents per month":
    case "values per month":
      return formatNumber(v, { decimals: 1, parens: false }) + ` ${unit.replace(" per month", "")} / month`;
    default:
      return formatNumber(v, { decimals: Number.isInteger(v) ? 0 : 2, parens: false });
  }
}

export function NumberCard({ id, n, emphasis }: { id: string; n: RoiNumber | undefined; emphasis?: boolean }) {
  if (!n) return null;
  const finite = (x: number | null) => x !== null && Number.isFinite(x);
  return (
    <div className={`roi-num ${emphasis ? "is-emphasis" : ""}`}>
      <div className="roi-num-head">
        <span className="roi-num-title">{TITLES[id] ?? id}</span>
        <LabelBadge label={n.label} />
      </div>
      <div className={`roi-num-value num ${n.value === null ? "is-none" : ""}`}>
        {n.value === null ? (n.label === "observed" ? "Not measured" : "Not available") : formatRoiValue(n.value, n.unit)}
      </div>
      {(finite(n.low) || finite(n.high) || n.n != null) && (
        <div className="small roi-num-range">
          {finite(n.low) && finite(n.high) && (
            <>
              likely {formatRoiValue(n.low, n.unit)} to {formatRoiValue(n.high, n.unit)}
            </>
          )}
          {n.n != null && (
            <span className="muted">
              {finite(n.low) && finite(n.high) ? " · " : ""}based on {n.n}
            </span>
          )}
        </div>
      )}
      <p className="small muted">{n.explanation}</p>
    </div>
  );
}

// ---- assumptions ----

function AssumptionsEditor({ report, onSaved }: { report: RoiReport; onSaved: (r: RoiReport) => void }) {
  const entries = Object.entries(report.numbers).filter(([k]) => k.startsWith("assumption."));
  const isShare = (k: string) => k.endsWith("_share");
  const shown = (k: string, v: number | null) => (v === null ? "" : isShare(k) ? String(+(v * 100).toFixed(4)) : String(v));
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "error" | "success"; text: string } | null>(null);

  const changed = entries.filter(([k, n]) => {
    const key = k.slice("assumption.".length);
    return drafts[key] !== undefined && drafts[key] !== shown(key, n.value);
  });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, number> = {};
    for (const [k] of changed) {
      const key = k.slice("assumption.".length);
      const raw = drafts[key]!.replace(/[, $%]/g, "");
      const num = Number(raw);
      if (raw === "" || !Number.isFinite(num)) {
        setMsg({ kind: "error", text: `${ASSUMPTION_TITLES[key] ?? key}: enter a number.` });
        return;
      }
      body[key] = isShare(key) ? num / 100 : num;
    }
    if (!Object.keys(body).length) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.setAssumptions(body);
      setDrafts({});
      onSaved(r);
      setMsg({ kind: "success", text: `Saved ${Object.keys(body).length} assumption${Object.keys(body).length === 1 ? "" : "s"}. Every number below was recalculated.` });
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} className="assumptions">
      <div className="grid-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Assumption</th>
              <th scope="col" className="num">
                Value
              </th>
              <th scope="col">Source</th>
              <th scope="col">What it means</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([k, n]) => {
              const key = k.slice("assumption.".length);
              const id = `as-${key}`;
              const unit = isShare(key) ? "%" : n.unit === "count" ? "" : n.unit;
              const draft = drafts[key];
              const dirty = draft !== undefined && draft !== shown(key, n.value);
              return (
                <tr key={k} className={dirty ? "is-dirty" : ""}>
                  <th scope="row">
                    <label htmlFor={id}>{ASSUMPTION_TITLES[key] ?? key}</label>
                  </th>
                  <td className="num nowrap">
                    {unit === "$" && <span className="unit-prefix">$</span>}
                    <input
                      id={id}
                      className="num-input"
                      type="text"
                      inputMode="decimal"
                      value={draft ?? shown(key, n.value)}
                      onChange={(e) => setDrafts((d) => ({ ...d, [key]: e.target.value }))}
                    />
                    {unit && unit !== "$" && <span className="unit-suffix">{unit}</span>}
                  </td>
                  <td>
                    <LabelBadge label={n.label} />
                  </td>
                  <td className="small">{n.explanation}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="form-row">
        <button type="submit" className="btn btn-primary" disabled={busy || changed.length === 0}>
          {busy ? "Saving…" : changed.length ? `Save ${changed.length} change${changed.length === 1 ? "" : "s"}` : "No changes"}
        </button>
        {changed.length > 0 && (
          <button type="button" className="btn btn-quiet" onClick={() => setDrafts({})}>
            Discard
          </button>
        )}
      </div>
      {msg && (
        <InlineMessage kind={msg.kind} onDismiss={() => setMsg(null)}>
          {msg.text}
        </InlineMessage>
      )}
    </form>
  );
}

// ---- scenarios & sensitivity ----

const MONEY_ROWS: { key: keyof MoneyBlock; label: string; unit: string; kind: "capacity" | "cash" }[] = [
  { key: "capacity_hours", label: "Analyst hours released", unit: "hours per month", kind: "capacity" },
  { key: "capacity_value", label: "Value of released hours (not cash)", unit: "$ per month", kind: "capacity" },
  { key: "net_monthly_capacity", label: "Net monthly capacity value", unit: "$ per month", kind: "capacity" },
  { key: "cash_savings", label: "Cash saved", unit: "$ per month", kind: "cash" },
  { key: "net_monthly_cash", label: "Net monthly cash", unit: "$ per month", kind: "cash" },
  { key: "first_year_roi_cash", label: "First-year cash ROI", unit: "ratio", kind: "cash" },
  { key: "payback_months_cash", label: "Cash payback", unit: "months", kind: "cash" },
];

function Scenarios({ report }: { report: RoiReport }) {
  const cols = (["low", "expected", "high"] as const).filter((c) => report.scenarios[c]);
  if (!cols.length)
    return <p className="muted">No scenarios yet: they need a measured number of minutes saved (three timed sessions in each mode).</p>;
  return (
    <div className="grid-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Per month</th>
            {cols.map((c) => (
              <th key={c} scope="col" className="num">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {MONEY_ROWS.map((r) => (
            <tr key={r.key} className={`scenario-${r.kind}`}>
              <th scope="row">
                {r.label} <span className="small muted">({r.kind === "cash" ? "cash" : "capacity"})</span>
              </th>
              {cols.map((c) => {
                const v = report.scenarios[c]?.[r.key];
                return (
                  <td key={c} className="num">
                    {v == null ? <span className="muted">not shown</span> : formatRoiValue(v, r.unit)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">Low and high use the ends of the minutes-saved range and volume −25% / +25%. Payback appears only when net monthly cash is positive.</p>
    </div>
  );
}

function Sensitivity({ report }: { report: RoiReport }) {
  if (!report.sensitivity.length) return <p className="muted">Sensitivity needs a measured number of minutes saved.</p>;
  const max = Math.max(1, ...report.sensitivity.flatMap((s) => [Math.abs(s.low), Math.abs(s.high)]));
  const pct = (v: number) => `${(Math.abs(v) / max) * 50}%`;
  return (
    <div className="tornado" role="table" aria-label="Sensitivity of net monthly capacity value">
      <div className="tornado-row tornado-head" role="row">
        <span role="columnheader">Assumption</span>
        <span role="columnheader" className="tornado-axis">
          <span>−</span>
          <span>0</span>
          <span>+</span>
        </span>
        <span role="columnheader" className="num">
          −25% / +25%
        </span>
      </div>
      {report.sensitivity.map((s) => (
        <div key={s.assumption} className="tornado-row" role="row">
          <span role="rowheader">{ASSUMPTION_TITLES[s.assumption] ?? s.assumption}</span>
          <span role="cell" className="tornado-track" aria-hidden="true">
            {[s.low, s.high].map((v, i) => (
              <span
                key={i}
                className={`tornado-bar ${i === 0 ? "is-low" : "is-high"}`}
                style={v < 0 ? { right: "50%", width: pct(v) } : { left: "50%", width: pct(v) }}
              />
            ))}
          </span>
          <span role="cell" className="num small">
            {formatNumber(s.low, { prefix: "$" })} / {formatNumber(s.high, { prefix: "$" })}
          </span>
        </div>
      ))}
      <p className="small muted">
        Change in net monthly capacity value when one assumption is 25% lower (left shade) or higher (right shade), the others unchanged.
      </p>
    </div>
  );
}

// ---- timing tool ----

function TimingTool({ docs, sessions, reloadSessions }: { docs: DocumentRow[]; sessions: WorkSession[]; reloadSessions: () => void }) {
  const active = useSession();
  const usable = docs.filter((d) => d.run_id && d.run_status === "succeeded");
  const [docId, setDocId] = useState("");
  const mode = "baseline" as const;
  const [difficulty, setDifficulty] = useState("");
  const [experience, setExperience] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!docId && usable[0]) setDocId(usable[0].id);
  }, [usable, docId]);
  const byId = useMemo(() => new Map(docs.map((d) => [d.id, d])), [docs]);

  const start = async (e: FormEvent) => {
    e.preventDefault();
    const doc = byId.get(docId);
    if (!doc || !doc.run_id) {
      setErr("Choose a document with a finished run.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const res = await api.startSession({
        mode,
        document_id: doc.id,
        run_id: doc.run_id,
        ...(difficulty ? { difficulty } : {}),
        ...(experience ? { analyst_experience: experience } : {}),
      });
      setSession({
        id: res.id,
        mode,
        documentId: doc.id,
        runId: doc.run_id,
        filename: doc.label || doc.filename,
        startedAt: new Date().toISOString(),
        activeSeconds: 0,
        corrections: 0,
      });
      navigate(`/sessions/${res.id}/baseline`);
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="timing">
      {active ? (
        <InlineMessage kind="info">
          Session #{active.id} ({active.mode}) on {active.filename} is running: {formatDuration(active.activeSeconds)} acknowledged so far.{" "}
          {active.mode === "assisted" ? (
            <>
              <Link to={`/runs/${active.runId}`}>Open the run</Link>{" "}
              <button
                type="button"
                className="btn btn-small"
                onClick={async () => {
                  await endActiveSession();
                  reloadSessions();
                }}
              >
                End session
              </button>
            </>
          ) : (
            <Link to={`/sessions/${active.id}/baseline`}>Open the by-hand form</Link>
          )}
        </InlineMessage>
      ) : usable.length === 0 ? (
        <p className="muted">Upload a document first; timing needs a finished run.</p>
      ) : (
        <form className="timing-form" onSubmit={start}>
          <div className="form-grid">
            <label htmlFor="timing-doc">Document</label>
            <select id="timing-doc" value={docId} onChange={(e) => setDocId(e.target.value)}>
              {usable.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.company_name || d.label || d.filename}
                </option>
              ))}
            </select>
            <label htmlFor="timing-difficulty">Difficulty</label>
            <select id="timing-difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="">not rated</option>
              <option value="low">low: clean, one unit, two periods</option>
              <option value="medium">medium: three periods, a unit change or over 60 lines</option>
              <option value="high">high: restated columns, unusual labels or a scan</option>
            </select>
            <label htmlFor="timing-experience">Your experience</label>
            <select id="timing-experience" value={experience} onChange={(e) => setExperience(e.target.value)}>
              <option value="">not given</option>
              <option value="under 1 year">under 1 year</option>
              <option value="1-3 years">1-3 years</option>
              <option value="3-5 years">3-5 years</option>
              <option value="over 5 years">over 5 years</option>
            </select>
          </div>
          <div className="form-row">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Starting…" : "Start timing"}
            </button>
          </div>
          <p className="small muted">
            Only active time counts: the tab must be visible and the mouse or keyboard used in the last minute.
          </p>
        </form>
      )}
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      <h3 className="subsection-title">Recorded sessions</h3>
      {sessions.length === 0 ? (
        <p className="muted small">None yet.</p>
      ) : (
        <div className="grid-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col" className="num">
                  #
                </th>
                <th scope="col">Mode</th>
                <th scope="col">Document</th>
                <th scope="col">Started</th>
                <th scope="col" className="num">
                  Active
                </th>
                <th scope="col" className="num">
                  Corrections
                </th>
                <th scope="col" className="num">
                  Keyed values wrong
                </th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td className="num">{s.id}</td>
                  <td>{s.mode}</td>
                  <td>{byId.get(s.document_id)?.filename ?? s.document_id.slice(0, 10)}</td>
                  <td className="nowrap">{formatDateTime(s.started_at)}</td>
                  <td className="num">{formatDuration(s.active_seconds)}</td>
                  <td className="num">{s.mode === "assisted" ? s.corrections ?? 0 : ""}</td>
                  <td className="num">{s.values_checked != null ? `${s.errors_found ?? 0} of ${s.values_checked}` : ""}</td>
                  <td>{s.ended_at ? "ended" : <span className="pill pill-warn">open</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---- page ----

export type RoiView = "summary" | "value" | "costs" | "errors" | "scenarios" | "areas" | "assumptions" | "timing";

const VIEWS: Record<RoiView, { title: string; lede: string }> = {
  summary: {
    title: "Time saved",
    lede: "What the platform saves, built from measurements where they exist and clearly labelled assumptions where they do not.",
  },
  value: {
    title: "Hours and cash",
    lede: "Hours freed for other work are not money saved. They become cash only through the share a finance owner enters.",
  },
  costs: { title: "Costs", lede: "What it costs to set up and run." },
  errors: { title: "Errors avoided", lede: "A comparison: how often numbers go wrong keyed by hand, against how often a wrong number gets past the platform unflagged." },
  scenarios: { title: "What-if scenarios", lede: "How the result moves if the numbers turn out lower or higher than expected." },
  areas: { title: "Reconciliation and other areas", lede: "Hours and value for reconciliation, invoices, data quality and spreadsheets." },
  assumptions: { title: "Assumptions", lede: "The figures only your organisation knows. Replace the placeholders and every result updates." },
  timing: {
    title: "Time a document",
    lede: "Review time is recorded in the background and only people with this page see it. Spreading by hand still needs timing here, to compare against.",
  },
};

const TILES: { view: RoiView; text: string }[] = [
  { view: "value", text: "Hours released, what they are worth, and cash payback." },
  { view: "costs", text: "Setup and monthly running costs." },
  { view: "errors", text: "Keying errors prevented and their value." },
  { view: "scenarios", text: "Low, expected and high cases." },
  { view: "areas", text: "Results outside statement spreading." },
  { view: "assumptions", text: "Change hourly costs, volumes and other figures." },
  { view: "timing", text: "Start a timed session." },
];

function Summary({ r }: { r: RoiReport }) {
  return (
    <>
      <p className="small muted">
        Timed so far: {r.sessions.baseline} by hand, {r.sessions.assisted} assisted. At least three of each are needed.
      </p>
      <div className="roi-cards">
        <NumberCard id="minutes_saved" n={r.numbers.minutes_saved} emphasis />
        <NumberCard id="capacity_hours" n={r.numbers.capacity_hours} />
        <NumberCard id="cash_savings" n={r.numbers.cash_savings} />
        <NumberCard id="payback_months_cash" n={r.numbers.payback_months_cash} />
      </div>
      <nav className="link-tiles" aria-label="More on time saved">
        {TILES.map((t) => (
          <Link key={t.view} to={`/roi/${t.view}`} className="link-tile">
            <strong>{VIEWS[t.view].title}</strong>
            <span className="small muted">{t.text}</span>
          </Link>
        ))}
      </nav>
      {r.warnings.length > 0 && (
        <details className="legend-box">
          <summary>Limits of these numbers ({r.warnings.length})</summary>
          <ul>
            {r.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
      <details className="legend-box">
        <summary>How each number is labelled</summary>
        <ul className="legend legend-labels">
          {(Object.keys(LABELS) as RoiLabel[]).map((l) => (
            <li key={l}>
              <LabelBadge label={l} /> <span className="small">{LABELS[l]}</span>
            </li>
          ))}
        </ul>
      </details>
    </>
  );
}

function ValueView({ r }: { r: RoiReport }) {
  return (
    <>
      <section className="roi-section" aria-labelledby="roi-time">
        <h2 id="roi-time" className="section-title">
          Time per document
        </h2>
        <div className="roi-cards">
          <NumberCard id="baseline_minutes" n={r.numbers.baseline_minutes} />
          <NumberCard id="assisted_minutes" n={r.numbers.assisted_minutes} />
          <NumberCard id="minutes_saved" n={r.numbers.minutes_saved} emphasis />
        </div>
      </section>
      <div className="roi-split">
        <div className="roi-split-col">
          <h3>Hours released</h3>
          <p className="small">
            Hours freed for other work. <strong>This is not money saved</strong>: payroll does not fall because a task got faster.
          </p>
          <NumberCard id="capacity_hours" n={r.numbers.capacity_hours} emphasis />
          <NumberCard id="capacity_value" n={r.numbers.capacity_value} />
          <NumberCard id="net_monthly_capacity" n={r.numbers.net_monthly_capacity} />
          <NumberCard id="break_even_documents" n={r.numbers.break_even_documents} />
        </div>
        <div className="roi-split-col is-cash">
          <h3>Cash saved</h3>
          <p className="small">
            Only the share of released hours that turns into cash (overtime, contractors or hiring avoided), currently{" "}
            <strong>{formatRoiValue(r.numbers["assumption.cash_realization_share"]?.value ?? 0, "share")}</strong>.{" "}
            <Link to="/roi/assumptions">Change it</Link>
          </p>
          <NumberCard id="cash_savings" n={r.numbers.cash_savings} emphasis />
          <NumberCard id="net_monthly_cash" n={r.numbers.net_monthly_cash} />
          <NumberCard id="first_year_roi_cash" n={r.numbers.first_year_roi_cash} />
          <NumberCard id="payback_months_cash" n={r.numbers.payback_months_cash} />
        </div>
      </div>
    </>
  );
}

function ErrorsView({ r }: { r: RoiReport }) {
  const hand = r.numbers.baseline_error_rate;
  const tool = r.numbers.silent_error_rate;
  const avoided = r.numbers.errors_avoided_per_month;
  const value = r.numbers.error_value_per_month;
  const rate = (n: RoiNumber | undefined) => (n?.value == null ? "Not measured yet" : formatRoiValue(n.value, "share"));
  return (
    <>
      <div className="compare-pair">
        <div className="compare-side">
          <h2>Keyed by hand</h2>
          <p className={`num compare-value ${hand ? "" : "is-none"}`}>{rate(hand)}</p>
          <p className="small muted">Numbers keyed wrong, out of all keyed.</p>
        </div>
        <span className="compare-vs" aria-hidden="true">vs</span>
        <div className="compare-side">
          <h2>With the platform</h2>
          <p className={`num compare-value ${tool ? "" : "is-none"}`}>{rate(tool)}</p>
          <p className="small muted">
            Wrong numbers that went through with no flag{tool?.n != null ? `, out of ${formatNumber(tool.n)} that went straight through` : ""}.
            From test filings, not your documents.
          </p>
        </div>
      </div>
      <p className="small muted">Both are error rates, so lower is better. Neither box is a saving on its own: the saving is the gap between them.</p>
      {avoided?.value != null ? (
        <>
          <h2 className="section-title">The result</h2>
          <p>
            {avoided.value >= 0
              ? `About ${formatNumber(avoided.value, { parens: false })} fewer wrong numbers a month than keying by hand.`
              : `About ${formatNumber(Math.abs(avoided.value), { parens: false })} more wrong numbers a month than keying by hand: the platform is letting more through.`}
          </p>
          <NumberCard id="error_value_per_month" n={value} />
          <p className="small muted">
            The dollar value uses the cost of one uncaught error from <Link to="/roi/assumptions">Assumptions</Link>.
          </p>
        </>
      ) : (
        <InlineMessage kind="info">
          The saving can't be worked out yet because the by-hand side has no measurement. <Link to="/roi/timing">Time one document by hand</Link> to
          fill it in; the number of errors avoided each month and their dollar value then appear here.
        </InlineMessage>
      )}
    </>
  );
}

function TimingView({ reload }: { reload: () => void }) {
  const docs = useApi(() => api.documents(), []);
  const sessions = useApi(() => api.sessions(), []);
  if (docs.error) return <ErrorState error={docs.error} onRetry={docs.reload} />;
  if (!docs.data) return <Loading />;
  return (
    <TimingTool
      docs={docs.data}
      sessions={sessions.data ?? []}
      reloadSessions={() => {
        sessions.reload();
        reload();
      }}
    />
  );
}

export function RoiPage({ view }: { view: RoiView }) {
  if (!can("roi")) {
    return (
      <Layout>
        <EmptyState title="This page is for managers">
          <p>Ask an administrator if you need access.</p>
        </EmptyState>
      </Layout>
    );
  }
  return <RoiPages view={view} />;
}

function RoiPages({ view }: { view: RoiView }) {
  const roi = useApi(() => api.roi(), []);
  const r = roi.data;
  const needsReport = view !== "areas" && view !== "timing";
  return (
    <Layout>
      <div className="page page-roi">
        <header className="page-head">
          {view !== "summary" && <p className="eyebrow">Time saved</p>}
          <h1>{VIEWS[view].title}</h1>
          <p className="lede">{VIEWS[view].lede}</p>
        </header>
        {needsReport && roi.loading && !r && <Loading label="Calculating" />}
        {needsReport && roi.error && <ErrorState error={roi.error} onRetry={roi.reload} />}
        {r && view === "summary" && <Summary r={r} />}
        {r && view === "value" && <ValueView r={r} />}
        {r && view === "costs" && (
          <div className="roi-cards">
            <NumberCard id="monthly_costs" n={r.numbers.monthly_costs} />
            <NumberCard id="implementation_cost" n={r.numbers.implementation_cost} />
          </div>
        )}
        {r && view === "errors" && <ErrorsView r={r} />}
        {r && view === "scenarios" && (
          <>
            <Scenarios report={r} />
            <section className="roi-section" aria-labelledby="roi-sens">
              <h2 id="roi-sens" className="section-title">
                What moves the result most
              </h2>
              <Sensitivity report={r} />
            </section>
          </>
        )}
        {r && view === "assumptions" && (
          <>
            <AssumptionsEditor report={r} onSaved={roi.setData} />
            <FinopsRoiSection view="assumptions" />
          </>
        )}
        {view === "areas" && <FinopsRoiSection view="results" />}
        {view === "timing" && <TimingView reload={roi.reload} />}
      </div>
    </Layout>
  );
}

export function TechnicalProcessingPage() {
  const roi = useApi(() => api.roi(), []);
  const r = roi.data;
  return (
    <Layout>
      <div className="page page-roi">
        <header className="page-head">
          <p className="eyebrow">For engineers</p>
          <h1>Processing</h1>
          <p className="lede">Compute time and energy per document, from the recorded runs.</p>
        </header>
        {roi.loading && !r && <Loading label="Calculating" />}
        {roi.error && <ErrorState error={roi.error} onRetry={roi.reload} />}
        {r && (
          <div className="roi-cards">
            <NumberCard id="compute_seconds" n={r.numbers.compute_seconds} />
            <NumberCard id="compute_cost" n={r.numbers.compute_cost} />
          </div>
        )}
      </div>
    </Layout>
  );
}
