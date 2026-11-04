// Accuracy for the people who rely on the numbers: what was tested, what slipped through, what was caught.
// The raw reports and every statistic live in the technical area (TechnicalPage).

import { api } from "../api/client";
import type { EvalBatch, EvalGroup, Rate, WideResult, WideSummary } from "../api/types";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { formatNumber } from "../lib/format";
import { Link } from "../lib/router";
import { useApi } from "../lib/useApi";

const count = (x: number | null | undefined) => formatNumber(x ?? 0);
const pct = (x: number | null | undefined, d = 1) => (x == null ? "" : formatNumber(x * 100, { decimals: d, suffix: "%", parens: false }));

function useSummary() {
  return useApi(() => api.evaluationSummary(), []);
}

function Figure({ value, label, tone }: { value: string; label: string; tone?: "bad" | "ok" }) {
  return (
    <div className="acc-figure">
      <span className={`num acc-figure-value ${tone ? `acc-${tone}` : ""}`}>{value}</span>
      <span className="small muted">{label}</span>
    </div>
  );
}

function SlippedThrough({ rate }: { rate: Rate | undefined }) {
  if (!rate || rate.rate == null) return null;
  return (
    <p className="acc-headline">
      <span className={`num acc-big ${rate.n ? "acc-bad" : "acc-ok"}`}>
        {count(rate.n)} of {count(rate.d)}
      </span>
      <span>
        numbers that went through with no one looking were wrong ({pct(rate.rate)}).
        <span className="small muted block">Could be as high as {pct(rate.high)}: this is a sample.</span>
      </span>
    </p>
  );
}

function GroupCard({ g }: { g: EvalGroup }) {
  const b: EvalBatch | undefined = g.holdout ?? g.dev;
  if (!b) return null;
  const buckets = b.buckets ?? {};
  const caught = b.rates.catch_rate;
  return (
    <article className="acc-card" aria-label={g.title}>
      <h2>{g.title}</h2>
      <p className="small muted">{count(b.documents)} filings.</p>
      <SlippedThrough rate={b.rates.silent_error_rate} />
      <div className="acc-figures">
        <Figure value={pct(b.rates.accuracy?.rate, 0)} label="of all numbers came out right" />
        <Figure value={caught ? `${count(caught.n)} of ${count(caught.d)}` : ""} label="wrong numbers were caught for review" />
        <Figure value={count(b.rates.review_rate?.n)} label="numbers sent to a person" />
        <Figure value={count(buckets.missing_silent)} label="numbers left blank with no flag" tone={buckets.missing_silent ? "bad" : "ok"} />
      </div>
    </article>
  );
}

function WideRow({ name, s }: { name: string; s: WideSummary }) {
  return (
    <tr>
      <th scope="row">{name}</th>
      <td className="num">{count(s.filings)}</td>
      <td className="num">{pct(s.right, 0)}</td>
      <td className="num">{count(s.silent_wrong[0])} of {count(s.silent_wrong[1])}</td>
      <td className="num">{count(s.blank_unflagged[0])}</td>
    </tr>
  );
}

function WideTable({ wide }: { wide: WideResult }) {
  const title = (k: string) => k.charAt(0).toUpperCase() + k.slice(1);
  return (
    <section aria-labelledby="wide-title">
      <h2 id="wide-title" className="section-title">Unseen test: real companies drawn at random</h2>
      <p className="small muted">
        Companies of every size and industry, drawn at random from the SEC's list and kept out of tuning. This set was opened more than once while a bug was fixed, so it is close to unseen, not perfectly unseen.
      </p>
      <div className="grid-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Group</th>
              <th scope="col" className="num">Filings</th>
              <th scope="col" className="num">Right</th>
              <th scope="col" className="num">Wrong with no flag</th>
              <th scope="col" className="num">Blank with no flag</th>
            </tr>
          </thead>
          <tbody>
            <WideRow name="All filings" s={wide.all} />
            {Object.entries(wide.by_sector).map(([k, s]) => <WideRow key={k} name={title(k)} s={s} />)}
            {Object.entries(wide.by_form).map(([k, s]) => <WideRow key={k} name={k} s={s} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function EvaluationPage() {
  const s = useSummary();
  const groups = s.data?.groups ?? [];
  return (
    <Layout>
      <div className="page page-eval">
        <header className="page-head">
          <p className="eyebrow">Results</p>
          <h1>Accuracy</h1>
          <p className="lede">
            Every number the platform spreads is compared with the answer in the company's own filing. The figure to watch is the wrong
            numbers no one was asked to look at.
          </p>
        </header>
        {s.loading && !s.data && <Loading label="Loading results" />}
        {s.error && <ErrorState error={s.error} onRetry={s.reload} />}
        {s.data && groups.length === 0 && (
          <EmptyState title="No test results yet">
            <p>Results appear here after the platform has been tested.</p>
          </EmptyState>
        )}
        {s.data?.wide && <WideTable wide={s.data.wide} />}
        <h2 className="section-title">Validation filings</h2>
        <p className="small muted">
          Kept apart from tuning, but failures found here have been studied and fixed, so these are a regression check, not an unseen test.
        </p>
        <div className="acc-grid">
          {groups.map((g) => <GroupCard key={g.key} g={g} />)}
        </div>
        <p className="small muted">
          Measured on public filings, not on your organisation's documents. A company with last year's spread on file gets more
          numbers confirmed.
        </p>
        <nav className="link-tiles" aria-label="More on accuracy">
          <Link to="/evaluation/errors" className="link-tile">
            <strong>Types of error</strong>
            <span className="small muted">What went wrong and where every number ended up.</span>
          </Link>
          <Link to="/evaluation/reviewers" className="link-tile">
            <strong>Reviewer decisions</strong>
            <span className="small muted">What your team's approvals and corrections have recorded.</span>
          </Link>
          <Link to="/technical" className="link-tile">
            <strong>Full test reports</strong>
            <span className="small muted">Every report and statistic, for engineers and data scientists.</span>
          </Link>
        </nav>
      </div>
    </Layout>
  );
}

const KIND_NAMES: Record<string, { label: string; explain: string }> = {
  value: { label: "Wrong amount or wrong line", explain: "The number does not match the filing, or sits on the wrong line." },
  sign: { label: "Wrong sign", explain: "Positive where the filing is negative, or the other way round." },
  scale: { label: "Wrong scale", explain: "Off by thousands or millions." },
  period: { label: "Wrong period", explain: "The number belongs to another year or quarter." },
};

const OUTCOMES: { key: string; label: string; tone: "ok" | "warn" | "bad" | "muted" }[] = [
  { key: "correct_auto", label: "Right, went straight through", tone: "ok" },
  { key: "correct_review", label: "Right, a person checks it", tone: "muted" },
  { key: "wrong_review", label: "Wrong, caught for review", tone: "warn" },
  { key: "wrong_auto", label: "Wrong, not flagged", tone: "bad" },
  { key: "missing_flagged", label: "Blank, flagged", tone: "warn" },
  { key: "missing_silent", label: "Blank, not flagged", tone: "bad" },
];

function ErrorCard({ g }: { g: EvalGroup }) {
  const b = g.holdout ?? g.dev;
  if (!b) return null;
  const total = OUTCOMES.reduce((n, o) => n + (b.buckets?.[o.key] ?? 0), 0);
  const kinds = Object.entries(b.error_kinds ?? {}).sort((x, y) => y[1] - x[1]);
  return (
    <article className="acc-card" aria-label={g.title}>
      <h2>{g.title}</h2>
      <h3 className="subsection-title">Where every number ended up</h3>
      <div className="bucket-bar" aria-hidden="true">
        {OUTCOMES.map((o) => {
          const n = b.buckets?.[o.key] ?? 0;
          return n ? <span key={o.key} className={`bucket-seg tone-${o.tone}`} style={{ width: `${(n / total) * 100}%` }} title={`${o.label}: ${n}`} /> : null;
        })}
      </div>
      <table className="data-table compact">
        <tbody>
          {OUTCOMES.map((o) => (
            <tr key={o.key}>
              <th scope="row">
                <span className={`swatch tone-${o.tone}`} aria-hidden="true" /> {o.label}
              </th>
              <td className="num">{count(b.buckets?.[o.key])}</td>
              <td className="num small muted">{total ? pct((b.buckets?.[o.key] ?? 0) / total) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {kinds.length > 0 && (
        <>
          <h3 className="subsection-title">What the wrong numbers were</h3>
          <table className="data-table compact">
            <tbody>
              {kinds.map(([k, n]) => (
                <tr key={k}>
                  <th scope="row">
                    {KIND_NAMES[k]?.label ?? k}
                    <span className="small muted block">{KIND_NAMES[k]?.explain}</span>
                  </th>
                  <td className="num">{count(n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </article>
  );
}

export function ErrorTypesPage() {
  const s = useSummary();
  return (
    <Layout>
      <div className="page page-eval">
        <header className="page-head">
          <p className="eyebrow">Accuracy</p>
          <h1>Types of error</h1>
          <p className="lede">Where every number on the validation filings ended up, and what kind of mistake the wrong ones were.</p>
        </header>
        {s.loading && !s.data && <Loading label="Loading results" />}
        {s.error && <ErrorState error={s.error} onRetry={s.reload} />}
        <div className="acc-grid">{(s.data?.groups ?? []).map((g) => <ErrorCard key={g.key} g={g} />)}</div>
      </div>
    </Layout>
  );
}

const AREA_NAMES: Record<string, string> = { statements: "Statement lines", units: "Statement units", recon: "Reconciliation matches" };

export function ReviewersPage() {
  const o = useApi(() => api.outcomes(), []);
  const engines = Object.entries(o.data?.engines ?? {});
  const tally = (m: Record<string, { right?: number; wrong?: number }>, k: "right" | "wrong") =>
    Object.values(m).reduce((n, c) => n + (c[k] ?? 0), 0);
  return (
    <Layout>
      <div className="page page-eval">
        <header className="page-head">
          <p className="eyebrow">Accuracy</p>
          <h1>Reviewer decisions</h1>
          <p className="lede">
            Every approval, correction and match decision is recorded. Those decisions decide which of the platform's answers can be
            trusted without a second look, so your team's judgement shapes it.
          </p>
        </header>
        {o.error && <ErrorState error={o.error} onRetry={o.reload} />}
        {o.data && engines.length === 0 && (
          <EmptyState title="No reviewer decisions recorded yet">
            <p>Approve a spread or decide a match, and it appears here.</p>
          </EmptyState>
        )}
        {engines.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Area</th>
                <th scope="col" className="num">Confirmed right</th>
                <th scope="col" className="num">Corrected</th>
              </tr>
            </thead>
            <tbody>
              {engines.map(([engine, e]) => (
                <tr key={engine}>
                  <th scope="row">{AREA_NAMES[engine] ?? engine}</th>
                  <td className="num">{count(tally(e.methods, "right"))}</td>
                  <td className="num">{count(tally(e.methods, "wrong"))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Layout>
  );
}
