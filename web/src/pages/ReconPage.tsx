// Reconciliation: workspaces (one per account and period), runs, and the exception queue.

import { useMemo, useState } from "react";
import { errorText, finops, needsName, type MatchGroup, type ReconRun, type Txn } from "../api/finops";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { formatDateTime } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { useApi } from "../lib/useApi";
import { AuditList, Checks, ExceptionCard, NameReminder, StatusPill, money } from "./finopsShared";

const RESOLUTIONS = ["explained", "journal_entry_posted", "corrected_in_source", "timing_will_clear", "write_off_approved", "not_an_issue"];

export function ReconListPage() {
  const ws = useApi(() => finops.workspaces(), []);
  const profiles = useApi(() => finops.profiles(), []);
  const [name, setName] = useState("Operating account, March 2026");
  const [profile, setProfile] = useState("bank-vs-gl.yaml");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [files, setFiles] = useState<Record<number, { left: File | null; right: File | null }>>({});

  async function act(key: string, fn: () => Promise<ReconRun | { id: number }>) {
    setBusy(key);
    setErr(null);
    try {
      const r = await fn();
      if ("run" in r) navigate(`/recon/runs/${r.run.id}`);
      else ws.reload();
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Layout>
      <h1>Reconciliation</h1>
      <p className="lede">
        Match two sources (a bank statement and the cash ledger), see what does not match and why, and settle each
        exception with a recorded decision. Rules settle only what is unambiguous; everything else is proposed to a person.
      </p>
      <NameReminder />
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      <section className="fo-panel" aria-labelledby="new-ws">
        <h2 id="new-ws">New reconciliation</h2>
        <form
          className="fo-row"
          onSubmit={(e) => {
            e.preventDefault();
            void act("create", () => finops.createWorkspace(name, profile));
          }}
        >
          <label>
            Name <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Profile{" "}
            <select value={profile} onChange={(e) => setProfile(e.target.value)}>
              {(profiles.data ?? []).map((p) => (
                <option key={p.file} value={p.file} disabled={!!p.error}>
                  {p.name || p.file}
                  {p.error ? " (invalid)" : ""}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" type="submit" disabled={busy !== null}>
            Create
          </button>
        </form>
      </section>
      {ws.loading && <Loading />}
      {ws.error && <ErrorState error={ws.error} onRetry={ws.reload} />}
      {ws.data && ws.data.length === 0 && <EmptyState title="No reconciliations yet">Create one above, then upload two files or try the sample data.</EmptyState>}
      {ws.data && ws.data.length > 0 && (
        <table className="data-table fo-table">
          <thead>
            <tr>
              <th>Reconciliation</th>
              <th>Profile</th>
              <th>Latest run</th>
              <th>Run with files</th>
            </tr>
          </thead>
          <tbody>
            {ws.data.map((w) => (
              <tr key={w.id}>
                <td>
                  <strong>{w.name}</strong>
                  <div className="muted small">
                    by {w.created_by}, {formatDateTime(w.created_at)}
                  </div>
                </td>
                <td className="small">{w.profile}</td>
                <td>{w.latest_run ? <Link to={`/recon/runs/${w.latest_run}`}>Run {w.latest_run}</Link> : <span className="muted">none</span>}</td>
                <td>
                  <div className="fo-row">
                    <label className="small">
                      Left (bank){" "}
                      <input type="file" accept=".csv,.xlsx" onChange={(e) => setFiles({ ...files, [w.id]: { left: e.target.files?.[0] ?? null, right: files[w.id]?.right ?? null } })} />
                    </label>
                    <label className="small">
                      Right (ledger){" "}
                      <input type="file" accept=".csv,.xlsx" onChange={(e) => setFiles({ ...files, [w.id]: { left: files[w.id]?.left ?? null, right: e.target.files?.[0] ?? null } })} />
                    </label>
                    <button
                      className="btn btn-small"
                      type="button"
                      disabled={busy !== null || (!w.latest_run && !(files[w.id]?.left && files[w.id]?.right))}
                      onClick={() => void act(`run${w.id}`, () => finops.runFiles(w.id, files[w.id]?.left ?? null, files[w.id]?.right ?? null))}
                    >
                      {busy === `run${w.id}` ? "Running…" : "Run"}
                    </button>
                    <button className="btn btn-small btn-quiet" type="button" disabled={busy !== null} onClick={() => void act(`s${w.id}`, () => finops.runSample(w.id))}>
                      {busy === `s${w.id}` ? "Running…" : "Try sample data"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  );
}

function RecordLine({ t }: { t: Txn | undefined }) {
  if (!t) return null;
  return (
    <div className="fo-rec">
      <code className="small">{t.id}</code> <span className="num">{money(t.amount)}</span> {t.currency} · {t.date} ·{" "}
      <span>{t.description || t.reference}</span>{" "}
      <span className="muted small">
        ({t.file} row {t.row})
      </span>
    </div>
  );
}

type Tab = "exceptions" | "matches" | "unmatched" | "audit";

export function ReconRunPage({ runId }: { runId: number }) {
  const st = useApi((s) => finops.run(runId, s), [runId]);
  const [tab, setTab] = useState<Tab>("exceptions");
  const [showResolved, setShowResolved] = useState(false);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [note, setNote] = useState("");
  const events = useApi(() => (st.data ? finops.reconEvents(st.data.workspace.id) : Promise.resolve([])), [st.data?.workspace.id, st.data?.run.id]);

  const res = st.data?.result ?? null;
  const groupOf = useMemo(() => {
    const m = new Map<string, MatchGroup>();
    res?.groups.forEach((g) => [...g.left, ...g.right].forEach((id) => m.set(id, g)));
    return m;
  }, [res]);

  if (st.loading && !st.data) return <Layout><Loading /></Layout>;
  if (st.error) return <Layout><ErrorState error={st.error} onRetry={st.reload} /></Layout>;
  if (!st.data || !res) return <Layout><EmptyState title="This run has no result">{st.data?.run.error ?? ""}</EmptyState></Layout>;
  const data = st.data;

  async function decide(fn: () => Promise<ReconRun>) {
    setErr(null);
    try {
      const r = await fn();
      navigate(`/recon/runs/${r.run.id}`);
    } catch (x) {
      setErr(errorText(x));
      throw x;
    }
  }

  const open = res.exceptions.filter((e) => e.status === "open");
  const shown = res.exceptions.filter((e) => (showResolved || e.status === "open") && (!code || e.code === code));
  const codes = [...new Set(res.exceptions.map((e) => e.code))].sort();
  const count = (s: string) => res.groups.filter((g) => g.status === s).length;
  const unmatched = (side: string) => Object.values(res.records).filter((t) => t.source === side && !groupOf.has(t.id));

  return (
    <Layout wide>
      <p className="small">
        <Link to="/recon">Reconciliation</Link> / {data.workspace.name}
      </p>
      <h1>
        {data.workspace.name} <span className="muted">run {data.run.id}</span>
      </h1>
      {!data.run.is_latest && (
        <InlineMessage kind="info">
          This is an older run. Decisions can only be made on the latest run of this reconciliation.
        </InlineMessage>
      )}
      <NameReminder />
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      <div className="fo-summary">
        <div><span className="fo-big">{count("auto_matched")}</span> matched by rules</div>
        <div><span className="fo-big">{count("accepted")}</span> accepted by a person</div>
        <div><span className="fo-big">{count("proposed")}</span> proposed</div>
        <div><span className="fo-big">{unmatched(res.left_name).length + unmatched(res.right_name).length}</span> unmatched records</div>
        <div><span className="fo-big">{open.length}</span> open exceptions ({open.filter((e) => e.severity === "blocker").length} blockers)</div>
      </div>
      <p className="small muted">
        {res.left_label}: {data.run.left_name} · {res.right_label}: {data.run.right_name} · period end {res.period_end ?? "unknown"} ·{" "}
        <a href={`/api/finops/recon/runs/${data.run.id}/export.csv`}>Export CSV</a>
      </p>
      {Object.entries(res.totals.currencies).map(([cur, t]) => (
        <p key={cur} className="small">
          <strong>{cur}</strong>: {res.left_label} minus {res.right_label} = {money(t.difference)}; inside matches {money(t.in_matches)}, inside
          proposals {money(t.in_proposals)}, open items {money(t.open_items)}.
        </p>
      ))}
      <details className="fo-panel">
        <summary>Completeness checks ({res.checks.filter((c) => c.status === "pass").length} of {res.checks.length} pass)</summary>
        <Checks checks={res.checks} />
      </details>
      <div className="fo-tabs" role="tablist">
        {(["exceptions", "matches", "unmatched", "audit"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`btn btn-small ${tab === t ? "btn-primary" : ""}`} onClick={() => setTab(t)}>
            {t === "exceptions" ? `Exceptions (${open.length} open)` : t === "matches" ? `Matches (${res.groups.length})` : t === "unmatched" ? "Unmatched records" : "Audit log"}
          </button>
        ))}
      </div>

      {tab === "exceptions" && (
        <section>
          <div className="fo-row">
            <label>
              Reason{" "}
              <select value={code} onChange={(e) => setCode(e.target.value)}>
                <option value="">all</option>
                {codes.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} /> show resolved
            </label>
          </div>
          {shown.length === 0 && <p className="muted">Nothing here.</p>}
          {shown.map((e) => {
            const ids = [
              ...(typeof e.evidence.group === "string" ? [e.evidence.group] : []),
              ...(Array.isArray(e.evidence.proposed_groups) ? (e.evidence.proposed_groups as string[]) : []),
            ];
            const props = res.groups.filter((x) => ids.includes(x.id) && x.status === "proposed");
            return (
              <ExceptionCard key={e.id} e={e} actions={RESOLUTIONS} onResolve={(a, n) => decide(() => finops.resolveRecon(data.run.id, e.id, a, n))}>
                {e.subjects.map((s) => (
                  <RecordLine key={s} t={res.records[s]} />
                ))}
                {data.run.is_latest &&
                  props.map((g) => (
                    <div key={g.id} className="fo-row small">
                      Proposed: {[...g.left, ...g.right].join(" + ")} (difference {money(g.difference)})
                      <GroupActions runId={data.run.id} g={g} decide={decide} />
                    </div>
                  ))}
              </ExceptionCard>
            );
          })}
        </section>
      )}

      {tab === "matches" && (
        <table className="data-table fo-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>{res.left_label}</th>
              <th>{res.right_label}</th>
              <th className="num">Difference</th>
              <th>Why</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {res.groups.map((g) => (
              <tr key={g.id}>
                <td>
                  <StatusPill s={g.status} />
                  <div className="muted small">{g.rule.replace(/_/g, " ")}</div>
                </td>
                <td>{g.left.map((id) => <RecordLine key={id} t={res.records[id]} />)}</td>
                <td>{g.right.map((id) => <RecordLine key={id} t={res.records[id]} />)}</td>
                <td className="num">{money(g.difference)}</td>
                <td className="small">{g.explanation.join(" ")}</td>
                <td>{data.run.is_latest && <GroupActions runId={data.run.id} g={g} decide={decide} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "unmatched" && (
        <section>
          <p className="small">Tick records on both sides to match them by hand. A manual match always needs a note saying what links them.</p>
          <div className="fo-cols">
            {[res.left_name, res.right_name].map((side) => (
              <div key={side}>
                <h3>{side === res.left_name ? res.left_label : res.right_label}</h3>
                {unmatched(side).map((t) => (
                  <label key={t.id} className="fo-pick">
                    <input
                      type="checkbox"
                      checked={sel.has(t.id)}
                      onChange={(e) => {
                        const n = new Set(sel);
                        if (e.target.checked) n.add(t.id);
                        else n.delete(t.id);
                        setSel(n);
                      }}
                    />
                    <RecordLine t={t} />
                  </label>
                ))}
              </div>
            ))}
          </div>
          <form
            className="fo-row"
            onSubmit={(e) => {
              e.preventDefault();
              const ids = [...sel];
              void decide(() =>
                finops.manual(
                  data.run.id,
                  ids.filter((i) => res.records[i]?.source === res.left_name),
                  ids.filter((i) => res.records[i]?.source === res.right_name),
                  note,
                ),
              ).then(() => setSel(new Set())).catch(() => undefined);
            }}
          >
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required): what links these records" className="fo-grow" />
            <button className="btn" type="submit" disabled={sel.size < 2 || needsName() || !data.run.is_latest}>
              Match {sel.size} selected
            </button>
          </form>
        </section>
      )}

      {tab === "audit" && (events.data ? <AuditList events={events.data} /> : <Loading />)}
    </Layout>
  );
}

function GroupActions({ runId, g, decide }: { runId: number; g: MatchGroup; decide: (fn: () => Promise<ReconRun>) => Promise<void> }) {
  const [note, setNote] = useState("");
  const needsNote = g.status !== "proposed" || Number(g.difference) !== 0;
  return (
    <div className="fo-row fo-actions">
      {needsNote && (
        <input className="fo-small-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder={needsNote ? "Note" : "Note (optional)"} aria-label="Note" />
      )}
      {g.status === "proposed" && (
        <button className="btn btn-small btn-primary" type="button" disabled={needsName()} onClick={() => void decide(() => finops.accept(runId, g.id, note)).catch(() => undefined)}>
          Accept
        </button>
      )}
      <button className="btn btn-small" type="button" disabled={needsName()} onClick={() => void decide(() => finops.reject(runId, g.id, note)).catch(() => undefined)}>
        {g.status === "proposed" ? "Reject" : "Undo match"}
      </button>
    </div>
  );
}
