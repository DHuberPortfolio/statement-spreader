// Spreadsheet risk scanner: upload a workbook (and optionally its earlier version), see definite errors, likely
// risks and low-confidence anomalies with the cell, the formula and what depends on it, and record a review.
// The workbook is only read; fixes are made in Excel.

import { useMemo, useState } from "react";
import { errorText, finops, type SheetCounts, type SheetFinding, type SheetScan } from "../api/finops";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { formatDateTime } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { useApi } from "../lib/useApi";
import { AuditList, NameReminder } from "./finopsShared";

const SEVERITY_TEXT: Record<string, string> = { error: "error", risk: "risk", anomaly: "anomaly" };

function SeverityPill({ s }: { s: string }) {
  const cls = s === "error" ? "pill pill-bad" : s === "risk" ? "pill pill-warn" : "pill";
  return <span className={cls}>{SEVERITY_TEXT[s] ?? s}</span>;
}

function Counts({ c }: { c: SheetCounts | null }) {
  if (!c) return null;
  return (
    <span className="num">
      {c.error} errors · {c.risk} risks · {c.anomaly} anomalies
      {c.material_changes ? ` · ${c.material_changes} material changes` : ""}
    </span>
  );
}

export function SpreadsheetsPage() {
  const scans = useApi(() => finops.sheetScans(), []);
  const [wb, setWb] = useState<File | null>(null);
  const [prev, setPrev] = useState<File | null>(null);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go(fn: () => Promise<number>) {
    setBusy(true);
    setErr(null);
    try {
      navigate(`/spreadsheets/scans/${await fn()}`);
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <h1>Spreadsheets</h1>
      <p className="lede">
        Scan a workbook for broken references, formulas that differ from their neighbours, typed numbers over formulas, totals
        that miss or double-count rows, and links to other files. Give an earlier version too to see which formulas changed in
        meaning. The workbook is only read, never changed or calculated.
      </p>
      <NameReminder />
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      <section className="fo-panel" aria-labelledby="new-scan">
        <h2 id="new-scan">Scan a workbook</h2>
        <form
          className="fo-stack"
          onSubmit={(e) => {
            e.preventDefault();
            if (wb) void go(async () => (await finops.sheetUpload(wb, prev, model)).scan);
          }}
        >
          <label>
            Workbook (.xlsx or .xlsm){" "}
            <input type="file" accept=".xlsx,.xlsm" onChange={(e) => setWb(e.target.files?.[0] ?? null)} />
          </label>
          <label>
            Earlier version (optional){" "}
            <input type="file" accept=".xlsx,.xlsm" onChange={(e) => setPrev(e.target.files?.[0] ?? null)} />
          </label>
          <label>
            Model name (optional: reviews carry to later versions of the same model){" "}
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. FY26 budget" />
          </label>
          <div className="fo-row">
            <button className="btn btn-primary" type="submit" disabled={busy || !wb}>
              Scan
            </button>
            <button className="btn" type="button" disabled={busy} onClick={() => void go(async () => (await finops.sheetSample()).scans[0] ?? 0)}>
              Try a sample workbook
            </button>
            <span className="muted small">Sample: a synthetic budget with planted problems, and an edited copy of another compared with its original.</span>
          </div>
        </form>
      </section>
      {scans.loading && <Loading />}
      {scans.error && <ErrorState error={scans.error} onRetry={scans.reload} />}
      {scans.data && scans.data.length === 0 && <EmptyState title="No scans yet">Upload a workbook above or try the sample.</EmptyState>}
      {scans.data && scans.data.length > 0 && (
        <table className="data-table fo-table">
          <thead>
            <tr>
              <th>Scan</th>
              <th>Workbook</th>
              <th>Model</th>
              <th>Result</th>
              <th>By</th>
            </tr>
          </thead>
          <tbody>
            {scans.data.map((s) => (
              <tr key={s.id}>
                <td>
                  <Link to={`/spreadsheets/scans/${s.id}`}>Scan {s.id}</Link>
                  <div className="muted small">{formatDateTime(s.at)}</div>
                </td>
                <td className="small">
                  {s.name}
                  {s.previous_name ? ` (compared with ${s.previous_name})` : ""}
                </td>
                <td className="small">{s.model}</td>
                <td>{s.status === "succeeded" ? <Counts c={s.counts} /> : <span className="pill pill-bad">{s.status}: {s.error}</span>}</td>
                <td className="small">{s.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  );
}

function FindingCard({ f, scan, onDone }: { f: SheetFinding; scan: SheetScan; onDone: (s: SheetScan) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function act(action: string) {
    setBusy(true);
    setErr(null);
    try {
      onDone(await finops.sheetReview(scan.id, f.id, action, note));
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }

  const where = f.sheet ? `${f.sheet}!${f.cell ?? ""}` : (f.cell ?? "");
  const label = [f.row_label, f.column_label].filter(Boolean).join(" · ");
  return (
    <article className={`fo-exc ${f.severity === "error" ? "fo-exc-blocker" : "fo-exc-warning"}`} aria-label={`${f.kind} at ${where}`}>
      <header>
        <SeverityPill s={f.severity} /> <strong>{where}</strong> {label && <span className="muted small">{label}</span>}{" "}
        <code className="small">{f.kind}</code>
        {f.review && (
          <span className="muted small">
            {" "}
            · {f.review.action === "dismiss" ? "dismissed" : "confirmed"} by {f.review.actor}: {f.review.note}
          </span>
        )}
      </header>
      <p>{f.detail}</p>
      <details>
        <summary>Formula, neighbours and dependencies</summary>
        <table className="data-table small">
          <tbody>
            {f.formula && (
              <tr>
                <th scope="row">Formula</th>
                <td><code>{f.formula}</code></td>
              </tr>
            )}
            {f.value != null && (
              <tr>
                <th scope="row">{f.formula ? "Saved value" : "Value"}</th>
                <td>{f.value}</td>
              </tr>
            )}
            {f.expected && (
              <tr>
                <th scope="row">Its neighbours would give</th>
                <td><code>{f.expected}</code></td>
              </tr>
            )}
            {f.group.length > 0 && (
              <tr>
                <th scope="row">Same problem in</th>
                <td>{f.group.join(", ")}</td>
              </tr>
            )}
            {f.cells.length > 0 && (
              <tr>
                <th scope="row">Cells involved</th>
                <td>{f.cells.join(", ")}</td>
              </tr>
            )}
            {f.precedents.length > 0 && (
              <tr>
                <th scope="row">Reads</th>
                <td>{f.precedents.join(", ")}</td>
              </tr>
            )}
            <tr>
              <th scope="row">Depends on it</th>
              <td>
                {f.dependents} formula(s) directly, {f.downstream} in all
                {f.feeds.length > 0 && `; flows into ${f.feeds.join(", ")}`}
              </td>
            </tr>
          </tbody>
        </table>
      </details>
      <div className="fo-stack">
        {err && <InlineMessage kind="error">{err}</InlineMessage>}
        <label>
          Reason (required: what you checked){" "}
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. agreed with the model owner: contracted price" />
        </label>
        <div className="fo-row">
          <button className="btn btn-primary" disabled={busy} onClick={() => void act("confirm")}>
            Confirm: needs fixing
          </button>
          {f.severity !== "error" && (
            <button className="btn" disabled={busy} onClick={() => void act("dismiss")}>
              Dismiss: deliberate
            </button>
          )}
        </div>
        {f.severity === "error" && <p className="muted small">A definite error cannot be dismissed: fix it in the workbook and scan again.</p>}
      </div>
    </article>
  );
}

export function SheetScanPage({ scanId }: { scanId: number }) {
  const scan = useApi((signal) => finops.sheetScan(scanId, signal), [scanId]);
  const [override, setOverride] = useState<SheetScan | null>(null);
  const [filter, setFilter] = useState<"open" | "error" | "risk" | "anomaly" | "all">("open");
  const s = override ?? scan.data;
  const events = useApi(() => (s ? finops.sheetEvents(s.model) : Promise.resolve([])), [s?.model, s?.result?.findings.map((f) => f.review?.at).join()]);
  const findings = useMemo(() => {
    const all = s?.result?.findings ?? [];
    if (filter === "all") return all;
    if (filter === "open") return all.filter((f) => f.severity !== "anomaly" && f.review?.action !== "dismiss");
    return all.filter((f) => f.severity === filter);
  }, [s, filter]);

  if (scan.loading && !s) return <Layout><Loading /></Layout>;
  if (scan.error) return <Layout><ErrorState error={scan.error} onRetry={scan.reload} /></Layout>;
  if (!s) return <Layout><Loading /></Layout>;
  const res = s.result;
  const material = (res?.changes ?? []).filter((c) => c.material);
  const summary = res?.change_summary as { typed_values_changed?: number; sheets?: Record<string, Record<string, number>> } | undefined;
  return (
    <Layout>
      <p className="small">
        <Link to="/spreadsheets">Spreadsheets</Link> / scan {s.id}
      </p>
      <h1>{s.name}</h1>
      <p>
        <Counts c={s.counts} />
        {s.open && <span className="muted"> · open: {s.open.error} errors, {s.open.risk} risks</span>}
      </p>
      <p className="muted small">
        Model “{s.model}” · {res?.sheets.length ?? 0} sheets, {s.counts?.formulas ?? 0} formulas · scanner {s.engine_version}, settings{" "}
        {s.config_version} · the file was read, not changed (sha256 {res?.sha256.slice(0, 12)}…)
      </p>
      {s.status !== "succeeded" && <InlineMessage kind="error">{s.error}</InlineMessage>}
      {res?.notes.map((n, i) => <InlineMessage key={i} kind="info">{n}</InlineMessage>)}
      <div className="fo-row">
        <a className="btn" href={`/api/finops/sheets/scans/${s.id}/export.csv`}>
          Download findings (CSV)
        </a>
      </div>
      {res?.previous && (
        <section className="fo-panel" aria-labelledby="changes">
          <h2 id="changes">Changes since {res.previous}</h2>
          <p className="small">
            {material.length} material change(s). Not material: {summary?.typed_values_changed ?? 0} typed values changed
            {summary?.sheets &&
              Object.entries(summary.sheets)
                .filter(([, v]) => v.rows_added || v.rows_removed || v.columns_added || v.columns_removed)
                .map(([k, v]) => `; ${k}: ${v.rows_added} rows added, ${v.rows_removed} removed, ${v.columns_added} columns added`)
                .join("")}
            . Formulas that only moved because rows were inserted are not listed.
          </p>
          {material.length > 0 && (
            <table className="data-table small">
              <thead>
                <tr>
                  <th>Change</th>
                  <th>Where</th>
                  <th>Before</th>
                  <th>Now</th>
                </tr>
              </thead>
              <tbody>
                {material.map((c, i) => (
                  <tr key={i}>
                    <td><code>{c.kind}</code></td>
                    <td>
                      {c.sheet}
                      {c.cell ? `!${c.cell}` : ""} <span className="muted">{c.row_label} {c.column_label}</span>
                    </td>
                    <td><code>{c.before ?? ""}</code></td>
                    <td><code>{c.after ?? ""}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
      <div className="fo-row" role="group" aria-label="Show">
        {(["open", "error", "risk", "anomaly", "all"] as const).map((f) => (
          <button key={f} className={`btn btn-small ${filter === f ? "btn-primary" : ""}`} onClick={() => setFilter(f)} aria-pressed={filter === f}>
            {f === "open" ? "Open errors and risks" : f === "error" ? "Errors" : f === "risk" ? "Risks" : f === "anomaly" ? "Anomalies" : "Everything"}
          </button>
        ))}
      </div>
      {findings.length === 0 && <EmptyState title="Nothing here">No findings match this view.</EmptyState>}
      {findings.slice(0, 200).map((f) => (
        <FindingCard key={f.id} f={f} scan={s} onDone={setOverride} />
      ))}
      {findings.length > 200 && <p className="muted">Showing the first 200 of {findings.length}; download the CSV for all.</p>}
      <section className="fo-panel">
        <h2>Audit trail</h2>
        {events.data && <AuditList events={events.data} />}
      </section>
    </Layout>
  );
}
