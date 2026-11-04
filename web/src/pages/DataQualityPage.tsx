// Data-quality gate: check records before another system loads them. Runs, the records held back and why,
// and a person's decisions (release, reject, correct), each recorded with a reason.

import { useMemo, useState } from "react";
import { errorText, finops, type GateDataset, type GateRecord, type GateRun } from "../api/finops";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { formatDateTime } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { useApi } from "../lib/useApi";
import { AuditList, NameReminder } from "./finopsShared";

const DECISION_TEXT: Record<string, string> = {
  accepted: "accepted",
  review: "held for review",
  rejected: "rejected",
  duplicate: "duplicate row (loaded once)",
};

function DecisionPill({ d }: { d: string }) {
  const cls = d === "rejected" ? "pill pill-bad" : d === "review" ? "pill pill-warn" : d === "accepted" ? "pill pill-ok" : "pill";
  return <span className={cls}>{DECISION_TEXT[d] ?? d}</span>;
}

function Counts({ c }: { c: GateRun["counts"] }) {
  if (!c) return null;
  return (
    <span className="num">
      {c.accepted} accepted · {c.review} for review · {c.rejected} rejected · {c.duplicate} duplicate
    </span>
  );
}

export function DataQualityListPage({ view }: { view: "list" | "new" }) {
  const runs = useApi(() => finops.dqRuns(), []);
  const datasets = useApi(() => finops.dqDatasets(), []);
  const [dataset, setDataset] = useState("vendors.yaml");
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const spec: GateDataset | undefined = (datasets.data ?? []).find((d) => d.file === dataset);

  async function go(fn: () => Promise<number>) {
    setBusy(true);
    setErr(null);
    try {
      navigate(`/data-quality/runs/${await fn()}`);
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <div className="page-title-row">
        <h1>{view === "new" ? "Check an export" : "Data quality"}</h1>
        {view === "list" && <Link to="/data-quality/new" className="btn btn-primary">Check an export</Link>}
      </div>
      <p className="lede">
        Check records before another system loads them. Each source system's columns are mapped into one record; definite
        errors are rejected, suspicious records are held for a person, and only accepted records are exported for loading.
        Nothing is merged, guessed or written back to the source.
      </p>
      <NameReminder />
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      {view === "new" && <section className="fo-panel" aria-label="Check an export">
        <form
          className="fo-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void go(async () => (await finops.dqUpload(dataset, files)).run);
          }}
        >
          <label>
            Type of export{" "}
            <select
              value={dataset}
              onChange={(e) => {
                setDataset(e.target.value);
                setFiles({});
              }}
            >
              {(datasets.data ?? []).map((d) => (
                <option key={d.file} value={d.file} disabled={!!d.error}>
                  {d.name || d.file}
                  {d.error ? " (invalid configuration)" : ""}
                </option>
              ))}
            </select>
          </label>
          {spec &&
            Object.entries(spec.sources).map(([sid, label]) => (
              <label key={sid}>
                {label} (.csv or .xlsx){" "}
                <input type="file" accept=".csv,.xlsx" onChange={(e) => setFiles({ ...files, [`source_${sid}`]: e.target.files?.[0] ?? null })} />
              </label>
            ))}
          {spec?.references.map((r) => (
            <label key={r}>
              Accepted {r} file (to check references){" "}
              <input type="file" accept=".csv,.xlsx" onChange={(e) => setFiles({ ...files, [`reference_${r}`]: e.target.files?.[0] ?? null })} />
            </label>
          ))}
          {spec?.change_control && (
            <label>
              Last accepted export (optional: to hold changed bank details and tax ids){" "}
              <input type="file" accept=".csv,.xlsx" onChange={(e) => setFiles({ ...files, previous: e.target.files?.[0] ?? null })} />
            </label>
          )}
          <div className="fo-row">
            <button className="btn btn-primary" type="submit" disabled={busy || !Object.keys(files).some((k) => k.startsWith("source_") && files[k])}>
              Check
            </button>
            <button className="btn" type="button" disabled={busy} onClick={() => void go(async () => (await finops.dqSample()).vendors)}>
              Try sample data
            </button>
            <span className="muted small">Sample: synthetic vendor exports from two systems, then purchase orders checked against them.</span>
          </div>
        </form>
      </section>}
      {view === "list" && runs.loading && <Loading />}
      {view === "list" && runs.error && <ErrorState error={runs.error} onRetry={runs.reload} />}
      {view === "list" && runs.data && runs.data.length === 0 && (
        <EmptyState title="No exports checked yet">
          <Link to="/data-quality/new">Check an export or try the sample data.</Link>
        </EmptyState>
      )}
      {view === "list" && runs.data && runs.data.length > 0 && (
        <table className="data-table fo-table">
          <thead>
            <tr>
              <th>Check</th>
              <th>Type</th>
              <th>Files</th>
              <th>Result</th>
              <th>By</th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link to={`/data-quality/runs/${r.id}`}>Run {r.id}</Link>
                  <div className="muted small">{formatDateTime(r.started_at)}</div>
                </td>
                <td>{r.dataset_id.replace(/_/g, " ")}</td>
                <td className="small">{r.inputs.inputs.map((i) => i.name).join(", ")}</td>
                <td>{r.status === "succeeded" ? <Counts c={r.counts} /> : <span className="pill pill-bad">{r.status}: {r.error}</span>}</td>
                <td className="small">{r.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  );
}

function RecordCard({ rec, run, columns, onDone }: { rec: GateRecord; run: GateRun; columns: string[]; onDone: (id: number) => void }) {
  const [note, setNote] = useState("");
  const [field, setField] = useState(rec.issues.find((i) => i.field)?.field ?? columns[0] ?? "");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function act(action: string) {
    setBusy(true);
    setErr(null);
    try {
      const r = await finops.dqDecide(run.id, rec.id, action, note, action === "correct" ? field : undefined, action === "correct" ? value : undefined);
      onDone(r.run);
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }

  const held = rec.decision === "review" || rec.decision === "rejected";
  return (
    <article className={`fo-exc ${rec.decision === "rejected" ? "fo-exc-blocker" : "fo-exc-warning"}`} aria-label={`Record ${rec.id}`}>
      <header>
        <DecisionPill d={rec.decision} />{" "}
        <strong>{rec.canonical[columns[0] ?? ""] || "(no key)"}</strong> {rec.canonical["name"] ?? ""}
        <span className="muted small">
          {" "}
          · {rec.source_label}, {rec.file}
          {rec.sheet ? `!${rec.sheet}` : ""} row {rec.row}
          {rec.decided_by !== "rules" ? ` · decided by ${rec.decided_by}` : ""}
        </span>
      </header>
      <ul className="fo-issues">
        {rec.issues.map((i, k) => (
          <li key={k}>
            <code className="small">{i.code}</code> <span className={i.severity === "reject" ? "text-bad" : ""}>{i.message}</span>
          </li>
        ))}
      </ul>
      <details>
        <summary>Values and what the gate changed</summary>
        <table className="data-table small">
          <tbody>
            {columns.map((c) => (
              <tr key={c}>
                <th scope="row">{c}</th>
                <td>{rec.canonical[c]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rec.changes.length > 0 && (
          <ul className="small">
            {rec.changes.map((c, k) => (
              <li key={k}>
                {c.field}: “{c.before}” → “{c.after}” <span className="muted">({c.step})</span>
              </li>
            ))}
          </ul>
        )}
      </details>
      {held && run.latest && (
        <div className="fo-stack">
          {err && <InlineMessage kind="error">{err}</InlineMessage>}
          <label>
            Reason (required: what you checked){" "}
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. called the vendor on the number in the contract" />
          </label>
          <div className="fo-row">
            {rec.decision === "review" && (
              <>
                <button className="btn btn-primary" disabled={busy} onClick={() => void act("release")}>
                  Release (accept)
                </button>
                <button className="btn" disabled={busy} onClick={() => void act("reject")}>
                  Reject
                </button>
              </>
            )}
            <label>
              Correct{" "}
              <select value={field} onChange={(e) => setField(e.target.value)}>
                {columns.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="new value" aria-label="New value" />
            <button className="btn" disabled={busy} onClick={() => void act("correct")}>
              Save correction
            </button>
          </div>
          <p className="muted small">A correction is checked again by the same rules. Whoever corrects a record cannot also release it.</p>
        </div>
      )}
    </article>
  );
}

export function DataQualityRunPage({ runId }: { runId: number }) {
  const run = useApi((signal) => finops.dqRun(runId, signal), [runId]);
  const [filter, setFilter] = useState<"held" | "review" | "rejected" | "all">("held");
  const events = useApi(() => (run.data ? finops.dqEvents(run.data.dataset_id) : Promise.resolve([])), [run.data?.dataset_id]);
  const records = useMemo(() => {
    const all = run.data?.result?.records ?? [];
    if (filter === "all") return all;
    if (filter === "held") return all.filter((r) => r.decision === "review" || r.decision === "rejected");
    return all.filter((r) => r.decision === filter);
  }, [run.data, filter]);

  if (run.loading) return <Layout><Loading /></Layout>;
  if (run.error) return <Layout><ErrorState error={run.error} onRetry={run.reload} /></Layout>;
  if (!run.data) return <Layout><Loading /></Layout>;
  const r = run.data;
  const res = r.result;
  return (
    <Layout>
      <p className="small">
        <Link to="/data-quality">Data quality</Link> / run {r.id}
      </p>
      <h1>{r.dataset_id.replace(/_/g, " ")}: run {r.id}</h1>
      <p>
        <Counts c={r.counts} />
      </p>
      <p className="muted small">
        Files: {r.inputs.inputs.map((i) => `${i.name} (${i.source})`).join(", ")}
        {Object.keys(r.inputs.references).length > 0 && ` · checked against ${Object.values(r.inputs.references).map((x) => x.name).join(", ")}`}
        {r.inputs.previous && ` · last accepted export ${r.inputs.previous.name}`} · configuration {r.config_version}
      </p>
      {!r.latest && <InlineMessage kind="info">A newer run of this dataset exists; decisions are made on the latest run.</InlineMessage>}
      {res?.warnings.map((w, i) => <InlineMessage key={i} kind="info">{w}</InlineMessage>)}
      <div className="fo-row">
        <a className="btn btn-primary" href={`/api/finops/dq/runs/${r.id}/export/accepted.csv`}>
          Download accepted records (for loading)
        </a>
        <a className="btn" href={`/api/finops/dq/runs/${r.id}/export/quarantine.csv`}>
          Download quarantine report
        </a>
      </div>
      {res && (res.carried_forward.length > 0 || res.withheld.length > 0 || res.missing_from_source.length > 0) && (
        <section className="fo-panel">
          <h2>Last accepted versions</h2>
          <p className="small">
            {res.carried_forward.length} held record(s) are exported in their last accepted version, so work continues on data already checked.
            {res.withheld.length > 0 && ` Not carried forward because the new version blocks or deactivates them: ${res.withheld.join(", ")}.`}
            {res.missing_from_source.length > 0 && ` In the last accepted export but in no source file now: ${res.missing_from_source.join(", ")}.`}
          </p>
        </section>
      )}
      <div className="fo-row" role="group" aria-label="Show">
        {(["held", "review", "rejected", "all"] as const).map((f) => (
          <button key={f} className={`btn btn-small ${filter === f ? "btn-primary" : ""}`} onClick={() => setFilter(f)} aria-pressed={filter === f}>
            {f === "held" ? "All held" : f === "review" ? "For review" : f === "rejected" ? "Rejected" : "Everything"}
          </button>
        ))}
      </div>
      {records.length === 0 && <EmptyState title="Nothing here">No records match this view.</EmptyState>}
      {res && records.slice(0, 200).map((rec) => (
        <RecordCard key={rec.id} rec={rec} run={r} columns={res.columns} onDone={(id) => navigate(`/data-quality/runs/${id}`)} />
      ))}
      {records.length > 200 && <p className="muted">Showing the first 200 of {records.length}; download the quarantine report for all.</p>}
      <section className="fo-panel">
        <h2>Audit trail</h2>
        {events.data && <AuditList events={events.data} />}
      </section>
    </Layout>
  );
}
