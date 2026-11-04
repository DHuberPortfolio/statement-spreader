import { useState } from "react";
import { api } from "../api/client";
import type { EvalReport, Rate } from "../api/types";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { formatNumber } from "../lib/format";
import { useApi } from "../lib/useApi";

const RATE_INFO: Record<string, { label: string; good: "low" | "high"; explain: string }> = {
  silent_error_rate: {
    label: "Silent error rate",
    good: "low",
    explain: "Wrong values with no review item, out of all values that would go out without review.",
  },
  accuracy: { label: "Values right", good: "high", explain: "Spread values that match the answer key, out of every value in the answer keys." },
  silent_omission_rate: {
    label: "Silent omissions",
    good: "low",
    explain: "Answer-key values missing from the spread with nothing flagging the gap.",
  },
  review_rate: { label: "Sent to review", good: "low", explain: "Values present in the spread that a person is asked to look at." },
  catch_rate: { label: "Wrong values caught", good: "high", explain: "Wrong values that review items do flag, out of all wrong values." },
  unnecessary_review_rate: {
    label: "Right values sent to review",
    good: "low",
    explain: "Correct values that were flagged anyway (review effort spent on nothing).",
  },
  coverage: { label: "Coverage", good: "high", explain: "Answer-key values present in the spread at all." },
};
const RATE_ORDER = ["silent_error_rate", "accuracy", "catch_rate", "silent_omission_rate", "review_rate", "unnecessary_review_rate", "coverage"];

const BUCKETS: { key: string; label: string; explain: string; tone: "ok" | "warn" | "bad" | "muted" }[] = [
  { key: "correct_auto", label: "Right, auto-accepted", explain: "Right and nothing flagged it.", tone: "ok" },
  { key: "correct_review", label: "Right, sent to review", explain: "Right, but a person was asked to look.", tone: "muted" },
  { key: "wrong_review", label: "Wrong, caught", explain: "Wrong, and a review item makes a person look before it is used.", tone: "warn" },
  { key: "wrong_auto", label: "Wrong, silent", explain: "Wrong and nothing says so: the silent errors.", tone: "bad" },
  { key: "missing_flagged", label: "Missing, flagged", explain: "Absent, and the run says rows were left unplaced or a check failed.", tone: "warn" },
  { key: "missing_silent", label: "Missing, silent", explain: "Absent and nothing says so.", tone: "bad" },
];

const SHOWN_FIRST = 6;

const pct = (x: number | null | undefined, d = 1) => (x == null ? "" : formatNumber(x * 100, { decimals: d, suffix: "%" }));

function IntervalBar({ rate }: { rate: Rate }) {
  if (rate.rate == null) return null;
  const lo = (rate.low ?? rate.rate) * 100;
  const hi = (rate.high ?? rate.rate) * 100;
  return (
    <span className="interval" aria-hidden="true">
      <span className="interval-range" style={{ left: `${lo}%`, width: `${Math.max(0.6, hi - lo)}%` }} />
      <span className="interval-point" style={{ left: `${rate.rate * 100}%` }} />
    </span>
  );
}

function ReportView({ r }: { r: EvalReport }) {
  const silent = r.rates.silent_error_rate;
  const totalBuckets = Object.values(r.buckets ?? {}).reduce((a, b) => a + b, 0);
  const kinds = Object.entries(r.error_kinds ?? {}).sort((a, b) => b[1] - a[1]);
  const maxKind = Math.max(1, ...kinds.map(([, n]) => n));
  return (
    <article className="eval-report" aria-labelledby={`ev-${r.file}`}>
      <header className="eval-head">
        <h2 id={`ev-${r.file}`}>
          {r.name} <span className="muted small">({r.file})</span>
        </h2>
        <p className="small muted">
          {r.documents} documents{r.crashed ? `, ${r.crashed} crashed` : ""} · profile {r.profile}
          {r.seconds != null && ` · ${formatNumber(r.seconds, { decimals: 1 })} s`}
        </p>
      </header>

      {silent && silent.rate != null && (
        <div className="silent-callout">
          <div className="silent-figure">
            <span className="num big">{pct(silent.rate)}</span>
            <span className="small">silent error rate</span>
          </div>
          <div>
            <p>
              Of the <strong className="num">{formatNumber(silent.d)}</strong> values that would have gone out <em>without anyone looking</em> (no
              review item on them), <strong className="num">{formatNumber(silent.n)}</strong> were wrong. That is the number that matters most:
              those are the errors a reviewer has no reason to catch.
            </p>
            <p className="small muted">
              Likely between {pct(silent.low)} and {pct(silent.high)} (95% Wilson interval). Measured on this evaluation set, not on your
              organisation's documents.
            </p>
          </div>
        </div>
      )}

      <div className="grid-scroll">
        <table className="data-table eval-table">
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col" className="num">
                Value
              </th>
              <th scope="col" className="interval-col">
                Likely range (0–100%)
              </th>
              <th scope="col" className="num">
                Count
              </th>
            </tr>
          </thead>
          <tbody>
            {RATE_ORDER.filter((k) => r.rates[k]).map((k) => {
              const rate = r.rates[k]!;
              const info = RATE_INFO[k];
              return (
                <tr key={k} className={k === "silent_error_rate" ? "is-key" : ""}>
                  <th scope="row">
                    {info?.label ?? k}
                    <span className="small muted block">
                      {info?.explain} {info && <>({info.good === "low" ? "lower is better" : "higher is better"})</>}
                    </span>
                  </th>
                  <td className="num strong">{rate.rate == null ? "not measured" : pct(rate.rate)}</td>
                  <td className="interval-col">
                    <IntervalBar rate={rate} />
                    {rate.rate != null && (
                      <span className="small muted num">
                        {pct(rate.low)} – {pct(rate.high)}
                      </span>
                    )}
                  </td>
                  <td className="num small">
                    {formatNumber(rate.n)} of {formatNumber(rate.d)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {r.buckets && totalBuckets > 0 && (
        <section aria-label="Where every answer-key value ended up" className="buckets">
          <h3 className="subsection-title">Where every answer-key value ended up</h3>
          <div className="bucket-bar" aria-hidden="true">
            {BUCKETS.map((b) => {
              const n = r.buckets?.[b.key] ?? 0;
              return n ? <span key={b.key} className={`bucket-seg tone-${b.tone}`} style={{ width: `${(n / totalBuckets) * 100}%` }} title={`${b.label}: ${n}`} /> : null;
            })}
          </div>
          <table className="data-table compact">
            <tbody>
              {BUCKETS.map((b) => (
                <tr key={b.key}>
                  <th scope="row">
                    <span className={`swatch tone-${b.tone}`} aria-hidden="true" /> {b.label}
                    <span className="small muted block">{b.explain}</span>
                  </th>
                  <td className="num">{formatNumber(r.buckets?.[b.key] ?? 0)}</td>
                  <td className="num small muted">{pct((r.buckets?.[b.key] ?? 0) / totalBuckets)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {kinds.length > 0 && (
        <section aria-label="Wrong values by kind" className="kinds">
          <h3 className="subsection-title">Wrong values by kind</h3>
          <p className="small muted">Each kind has a different fix: value or mapping, sign, scale (off by a power of ten), period (another period's value).</p>
          <table className="data-table compact">
            <tbody>
              {kinds.map(([k, n]) => (
                <tr key={k}>
                  <th scope="row">{k}</th>
                  <td className="num">{formatNumber(n)}</td>
                  <td className="bar-cell">
                    <span className="hbar" style={{ width: `${(n / maxKind) * 100}%` }} aria-hidden="true" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </article>
  );
}

const ENGINE_NAMES: Record<string, string> = {
  statements: "Statement rows placed on a line",
  units: "Statement units (thousands, millions)",
  recon: "Reconciliation matches (recorded, not yet learned from)",
};

/** What reviewers' decisions have recorded so far: the outcomes calibration learns from (DECISIONS D40). */
function LearningSection() {
  const o = useApi(() => api.outcomes(), []);
  const engines = Object.entries(o.data?.engines ?? {});
  return (
    <section aria-labelledby="learning-title">
      <h2 id="learning-title" className="section-title">
        What reviewers have taught it
      </h2>
      <p className="muted">
        Every approval, remap and match decision is written down as evidence about the rule that made the call. When the
        rules are re-measured, this evidence counts alongside the answer keys, so a rule earns or loses automatic
        acceptance from your own reviewers' decisions.
      </p>
      {o.error && <ErrorState error={o.error} onRetry={o.reload} />}
      {o.data && engines.length === 0 && (
        <EmptyState title="No reviewer decisions recorded yet">
          <p>Approve a spread or decide a match, and its evidence appears here.</p>
        </EmptyState>
      )}
      {engines.length > 0 && (
        <div className="grid-scroll">
          <table className="data-table learning-table">
            <thead>
              <tr>
                <th scope="col">Rule</th>
                <th scope="col">What it decides</th>
                <th scope="col" className="num">Right</th>
                <th scope="col" className="num">Wrong</th>
              </tr>
            </thead>
            <tbody>
              {engines.flatMap(([engine, e]) =>
                Object.entries(e.methods).map(([method, c]) => (
                  <tr key={`${engine}:${method}`}>
                    <td>{method}</td>
                    <td>{ENGINE_NAMES[engine] ?? engine}</td>
                    <td className="num">{c.right ?? 0}</td>
                    <td className="num">{c.wrong ? <span className="count-bad">{c.wrong}</span> : 0}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
      {o.data && <p className="muted small">Kept in {o.data.folder}.</p>}
    </section>
  );
}

export function EvaluationPage() {
  const ev = useApi(() => api.evaluation(), []);
  const [all, setAll] = useState(false);
  const reports = ev.data?.reports ?? [];
  return (
    <Layout>
      <div className="page page-eval">
        <header className="page-head">
          <p className="eyebrow">Results</p>
          <h1>Accuracy</h1>
          <p className="lede">
            How often each part is right, measured against answer keys: for SEC filings, the filings' own inline XBRL
            tags; for synthetic statements, the values they were generated from. Every rate comes with the range it likely
            falls in; a small sample gives a wide range.
          </p>
        </header>
        <LearningSection />
        <h2 className="section-title">Evaluation reports</h2>
        {ev.loading && !ev.data && <Loading label="Loading evaluation reports" />}
        {ev.error && <ErrorState error={ev.error} onRetry={ev.reload} />}
        {ev.data && ev.data.reports.length === 0 && (
          <EmptyState title="No evaluation reports yet">
            <p>
              Run <code>.venv/Scripts/python scripts/run_eval.py</code>; reports are saved in <code>eval/reports/</code>.
            </p>
          </EmptyState>
        )}
        {(all ? reports : reports.slice(0, SHOWN_FIRST)).map((r) => <ReportView key={r.file} r={r} />)}
        {!all && reports.length > SHOWN_FIRST && (
          <button type="button" className="btn" onClick={() => setAll(true)}>
            Show {reports.length - SHOWN_FIRST} older reports
          </button>
        )}
      </div>
    </Layout>
  );
}
