// Baseline timing: the analyst keys the main lines by hand into a blank template while reading the
// statement as printed. The spread's own values are never shown here (that would bias the test).

import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Period, Profile, StatementKey } from "../api/types";
import { Layout } from "../components/Layout";
import { endActiveSession } from "../lib/session";
import { ErrorState, InlineMessage, Loading } from "../components/States";
import { readStored, writeStored } from "../lib/actor";
import { cleanEvidence, formatDate, formatDuration, formatExact, toFullUnits, unitName } from "../lib/format";
import { durationLabel, orderedPeriods } from "../lib/periods";
import { Link, navigate } from "../lib/router";
import { STATEMENT_ORDER, STATEMENT_TITLE } from "../lib/status";
import { useProfile, useSession } from "../lib/store";
import { useCountActiveTime, useTimer } from "../lib/timer";
import { useApi } from "../lib/useApi";
import { UNITS } from "../workspace/SpreadGrid";

function mainLines(profile: Profile, s: StatementKey) {
  return (profile.statements[s]?.lines ?? []).filter((l) => l.critical);
}

function PrintedStatement({ runId, statement }: { runId: number; statement: StatementKey }) {
  const src = useApi(() => api.source(runId, statement), [runId, statement]);
  if (src.loading && !src.data) return <Loading label="Loading the statement" />;
  if (src.error) return <ErrorState error={src.error} onRetry={src.reload} />;
  const d = src.data!;
  return (
    <div className="grid-scroll printed-statement">
      <table className="source-table">
        <caption className="small muted">
          {STATEMENT_TITLE[statement]} as printed ({d.scale.assumed || !d.scale.evidence ? `no unit statement: taken as ${unitName(d.scale.multiplier)}` : `“${cleanEvidence(d.scale.evidence)}”`})
        </caption>
        <thead>
          <tr>
            <th scope="col">Label</th>
            {d.periods.map((p) => (
              <th key={p.key} scope="col" className="num">
                <span className="col-date">{p.label}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.rows.map((r) => (
            <tr key={r.index} className={`src-${r.role} ${r.bold ? "is-bold" : ""}`}>
              <th scope="row" className="src-label">
                {r.label}
              </th>
              {d.periods.map((p) => (
                <td key={p.key} className="num printed-cell">
                  {r.values[p.key]?.raw ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BaselinePage({ sessionId }: { sessionId: number }) {
  const session = useSession();
  const timer = useTimer();
  const { profile } = useProfile();
  const mine = session && session.id === sessionId && session.mode === "baseline" ? session : null;
  const run = useApi((signal) => (mine?.runId ? api.run(mine.runId, signal) : Promise.reject(new Error("This session has no run."))), [mine?.runId]);
  const draftKey = `spreader.baseline.${sessionId}`;
  const [values, setValues] = useState<Record<string, string>>(() => readStored(draftKey, {}));
  const [units, setUnits] = useState<Partial<Record<StatementKey, number>>>(() => readStored(`${draftKey}.units`, {}));
  const [stmt, setStmt] = useState<StatementKey>("income_statement");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useCountActiveTime(!!mine);
  useEffect(() => writeStored(draftKey, values), [draftKey, values]);
  useEffect(() => writeStored(`${draftKey}.units`, units), [draftKey, units]);

  const spread = run.data?.spread;
  const periodsOf = useMemo(() => {
    const out = {} as Record<StatementKey, Period[]>;
    for (const s of STATEMENT_ORDER) out[s] = orderedPeriods(spread?.statements[s]?.table.periods ?? []);
    return out;
  }, [spread]);
  const unitOf = (s: StatementKey) => units[s] ?? spread?.statements[s]?.table.scale.multiplier ?? 1;

  if (!mine) {
    return (
      <Layout>
        <div className="state state-empty">
          <h1>Session #{sessionId} is not running here</h1>
          <p>It has ended, or it was started in another browser. Start a new baseline session from the ROI page.</p>
          <Link to="/roi/timing" className="btn">
            Go to ROI
          </Link>
        </div>
      </Layout>
    );
  }

  const entries = Object.entries(values).filter(([, v]) => v.trim() !== "");
  const finish = async () => {
    const out: Record<string, string> = {};
    for (const [k, raw] of entries) {
      const line = k.split("@")[0]!;
      const s = STATEMENT_ORDER.find((x) => profile?.statements[x]?.lines.some((l) => l.id === line)) ?? "income_statement";
      const kind = profile?.statements[s]?.lines.find((l) => l.id === line)?.kind;
      const full = toFullUnits(raw, kind === "per_share" ? 1 : unitOf(s));
      if (full === null) {
        setError(`“${raw}” for ${line} is not a number. Fix it or clear it before finishing.`);
        return;
      }
      out[k] = full;
    }
    setBusy(true);
    setError(null);
    await endActiveSession({ values: out, values_entered: entries.length });
    writeStored(draftKey, null);
    writeStored(`${draftKey}.units`, null);
    setBusy(false);
    navigate("/roi/timing");
  };

  return (
    <Layout wide>
      <div className="page page-baseline">
        <header className="page-head">
          <p className="eyebrow">
            <Link to="/roi/timing">Time a document</Link> / by-hand session
          </p>
          <h1>Spread {mine.filename} by hand</h1>
          <p className="lede">
            Key the main lines from the statement on the left, in the unit you read them in. The clock counts only while you work here:{" "}
            <strong className="num">{formatDuration(mine.activeSeconds + timer.pending)}</strong> active so far.
          </p>
        </header>
        {run.loading && !run.data && <Loading label="Loading the document" />}
        {run.error && <ErrorState error={run.error} onRetry={run.reload} />}
        {spread && profile && (
          <>
            <div className="toolbar">
              <div className="segmented" role="group" aria-label="Statement">
                {STATEMENT_ORDER.filter((s) => spread.statements[s]).map((s) => (
                  <button key={s} type="button" className={s === stmt ? "is-on" : ""} aria-pressed={s === stmt} onClick={() => setStmt(s)}>
                    {STATEMENT_TITLE[s]}
                  </button>
                ))}
              </div>
            </div>
            <div className="baseline-grid">
              <section aria-label="The statement as printed">
                <PrintedStatement runId={mine.runId!} statement={stmt} />
              </section>
              <section aria-labelledby="bl-form-title" className="baseline-form">
                <h2 id="bl-form-title" className="section-title">
                  Template: {STATEMENT_TITLE[stmt]}
                </h2>
                <label className="small">
                  I am keying in{" "}
                  <select value={unitOf(stmt)} onChange={(e) => setUnits((u) => ({ ...u, [stmt]: Number(e.target.value) }))}>
                    {UNITS.map((u) => (
                      <option key={u} value={u}>
                        {unitName(u)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid-scroll">
                  <table className="data-table baseline-table">
                    <thead>
                      <tr>
                        <th scope="col">Line</th>
                        {periodsOf[stmt].map((p) => (
                          <th key={p.key} scope="col" className="num">
                            <span className="col-date">{formatDate(p.end)}</span>
                            <span className="col-dur">{durationLabel(p)}</span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {mainLines(profile, stmt).map((l) => (
                        <tr key={l.id}>
                          <th scope="row">{l.label}</th>
                          {periodsOf[stmt].map((p) => {
                            const k = `${l.id}@${p.key}`;
                            const raw = values[k] ?? "";
                            const full = raw.trim() ? toFullUnits(raw, l.kind === "per_share" ? 1 : unitOf(stmt)) : null;
                            const bad = raw.trim() !== "" && full === null;
                            return (
                              <td key={p.key} className="num">
                                <input
                                  className={`num-input ${bad ? "is-bad" : ""}`}
                                  type="text"
                                  inputMode="decimal"
                                  aria-label={`${l.label}, ${formatDate(p.end)} ${durationLabel(p).toLowerCase()}`}
                                  aria-invalid={bad}
                                  title={full ? `= ${formatExact(full)}` : undefined}
                                  value={raw}
                                  onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
                                />
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small muted">
                  {entries.length} value{entries.length === 1 ? "" : "s"} keyed across all statements. Leave a cell empty if the line is not
                  printed. Negative numbers: (1,234) or -1234.
                </p>
                <div className="form-row">
                  <button type="button" className="btn btn-primary" onClick={finish} disabled={busy}>
                    {busy ? "Finishing…" : "Finish and compare"}
                  </button>
                </div>
                {error && <InlineMessage kind="error">{error}</InlineMessage>}
              </section>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
