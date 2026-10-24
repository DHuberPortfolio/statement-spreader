// Checks, Ratios and Audit log tabs.

import { Fragment, useState } from "react";
import { api } from "../api/client";
import type { AuditEvent, CheckResult, CheckStatus, RatioResult } from "../api/types";
import { SeverityMark, TickLegend, TickMark } from "../components/Markers";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { formatAmountPrecise, formatDateTime, formatRatio, unitName } from "../lib/format";
import { findValue, orderedPeriods, periodKeyLabel, valueKey } from "../lib/periods";
import { STATEMENT_ORDER, STATEMENT_TITLE } from "../lib/status";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "./context";
import { UnitSelector } from "./SpreadGrid";

// ---------- Checks ----------

type CheckFilter = "all" | CheckStatus;

function CheckLines({ check }: { check: CheckResult }) {
  const { model, selectCell } = useWorkspace();
  return (
    <span className="q-links">
      {check.lines.map((l) => {
        const v = findValue(model.index, l, check.period);
        const key = v ? valueKey(v.line, v.period) : valueKey(l, check.period);
        return (
          <button key={l} type="button" className="chip chip-link" onClick={() => selectCell(key, { focusEvidence: true })} disabled={!v}>
            {model.lineInfo(l).label}
          </button>
        );
      })}
    </span>
  );
}

export function ChecksTab() {
  const { model, unit, setUnit } = useWorkspace();
  const [filter, setFilter] = useState<CheckFilter>("all");
  const defs = new Map(model.profile.checks.map((c) => [c.id, c]));
  const checks = model.spread.checks.filter((c) => filter === "all" || c.status === filter);
  const counts = { pass: 0, fail: 0, skipped: 0 } as Record<CheckStatus, number>;
  for (const c of model.spread.checks) counts[c.status]++;
  const periodOrder = new Map(orderedPeriods(model.spread.periods).map((p, i) => [p.key, i]));

  return (
    <div className="tab-body">
      <div className="toolbar">
        <fieldset className="segmented" aria-label="Show checks">
          <legend className="segmented-legend">Show</legend>
          {(["all", "fail", "pass", "skipped"] as CheckFilter[]).map((f) => (
            <label key={f} className={filter === f ? "is-on" : ""}>
              <input type="radio" name="check-filter" checked={filter === f} onChange={() => setFilter(f)} />
              <span>
                {f === "all" ? `All ${model.spread.checks.length}` : `${f === "fail" ? "Failed" : f === "pass" ? "Passed" : "Skipped"} ${counts[f]}`}
              </span>
            </label>
          ))}
        </fieldset>
        <UnitSelector value={unit} onChange={setUnit} idPrefix="checks-unit" />
      </div>
      <details className="legend-box">
        <summary>Tick marks</summary>
        <TickLegend />
      </details>
      {STATEMENT_ORDER.map((s) => {
        const rows = checks
          .filter((c) => (defs.get(c.id)?.statement ?? "") === s)
          .sort((a, b) => {
            const da = [...defs.keys()].indexOf(a.id);
            const db = [...defs.keys()].indexOf(b.id);
            return da - db || (periodOrder.get(a.period) ?? 0) - (periodOrder.get(b.period) ?? 0);
          });
        if (!rows.length) return null;
        return (
          <section key={s} className="stmt" aria-labelledby={`chk-${s}`}>
            <div className="stmt-head">
              <h3 id={`chk-${s}`}>{STATEMENT_TITLE[s]}</h3>
              <span className="muted small">amounts in {unitName(unit)}</span>
            </div>
            <div className="grid-scroll">
              <table className="data-table checks-table">
                <thead>
                  <tr>
                    <th scope="col">
                      <span className="sr-only">Result</span>
                    </th>
                    <th scope="col">Check</th>
                    <th scope="col">Period</th>
                    <th scope="col" className="num">
                      Left
                    </th>
                    <th scope="col" className="num">
                      Right
                    </th>
                    <th scope="col" className="num">
                      Difference
                    </th>
                    <th scope="col" className="num">
                      Allowed
                    </th>
                    <th scope="col">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => {
                    const def = defs.get(c.id);
                    return (
                      <tr key={`${c.id}@${c.period}`} className={`check-${c.status}`}>
                        <td className="tick-cell">
                          <TickMark status={c.status} />
                        </td>
                        <th scope="row" className="check-title">
                          {c.title}
                          {def && def.severity !== "blocker" && c.status === "fail" && (
                            <span className="sev-inline">
                              <SeverityMark severity={def.severity} withLabel />
                            </span>
                          )}
                          <div className="check-formula small muted">
                            <code>{def ? `${def.lhs} = ${def.rhs}` : c.id}</code>
                          </div>
                          <CheckLines check={c} />
                        </th>
                        <td className="nowrap small">{periodKeyLabel(c.period, model.spread.periods)}</td>
                        <td className="num">{formatAmountPrecise(c.lhs, unit)}</td>
                        <td className="num">{formatAmountPrecise(c.rhs, unit)}</td>
                        <td className={`num ${c.status === "fail" ? "text-bad strong" : ""}`}>{formatAmountPrecise(c.difference, unit)}</td>
                        <td className="num muted">{c.tolerance != null ? `±${formatAmountPrecise(c.tolerance, unit, 3)}` : ""}</td>
                        <td className="small explain">
                          {c.explanation || (c.status === "pass" ? "Agrees." : "")}
                          {def?.note && <div className="muted">{def.note}</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
      {checks.length === 0 && <EmptyState title="No checks match this filter" />}
    </div>
  );
}

// ---------- Ratios ----------

export function RatiosTab() {
  const { model, unit, setUnit } = useWorkspace();
  const [open, setOpen] = useState<string | null>(null);
  const byId = new Map<string, RatioResult[]>();
  for (const r of model.spread.ratios) {
    const list = byId.get(r.id);
    if (list) list.push(r);
    else byId.set(r.id, [r]);
  }
  const periodKeys = [...new Set(model.spread.ratios.map((r) => r.period))];
  const periods = orderedPeriods(model.spread.periods.filter((p) => periodKeys.includes(p.key)));
  const defs = new Map(model.profile.ratios.map((r) => [r.id, r]));
  const ids = [...byId.keys()].sort((a, b) => [...defs.keys()].indexOf(a) - [...defs.keys()].indexOf(b));

  if (!ids.length) return <EmptyState title="No ratios were computed for this run" />;
  return (
    <div className="tab-body">
      <div className="toolbar">
        <p className="small muted">Ratios are computed from the spread as it stands, corrections included. Money ratios follow the unit selector.</p>
        <UnitSelector value={unit} onChange={setUnit} idPrefix="ratio-unit" />
      </div>
      <div className="grid-scroll">
        <table className="data-table ratios-table">
          <thead>
            <tr>
              <th scope="col">Ratio</th>
              {periods.map((p) => (
                <th key={p.key} scope="col" className="num">
                  {periodKeyLabel(p.key, model.spread.periods)}
                </th>
              ))}
              <th scope="col">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {ids.map((id) => {
              const results = byId.get(id)!;
              const first = results[0]!;
              const isOpen = open === id;
              return (
                <Fragment key={id}>
                  <tr>
                    <th scope="row">
                      {first.label}
                      <span className="ratio-format small muted"> · {first.format}</span>
                    </th>
                    {periods.map((p) => {
                      const r = results.find((x) => x.period === p.key);
                      if (!r) return <td key={p.key} className="num muted" />;
                      if (r.value == null)
                        return (
                          <td key={p.key} className="num nc" title={r.reason ?? "Not computable"}>
                            <span aria-hidden="true">n/c</span>
                            <span className="sr-only">{r.reason ?? "Not computable"}</span>
                          </td>
                        );
                      return (
                        <td key={p.key} className="num">
                          {formatRatio(r.value, r.format, unit)}
                        </td>
                      );
                    })}
                    <td>
                      <button type="button" className="btn btn-small btn-quiet" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : id)}>
                        {isOpen ? "Hide" : "Formula"}
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="ratio-detail">
                      <td colSpan={periods.length + 2}>
                        <p>
                          <code>{first.formula}</code>
                        </p>
                        {(first.note || defs.get(id)?.note) && <p className="small">{first.note || defs.get(id)?.note}</p>}
                        <ul className="plain-list small">
                          {results.map((r) => (
                            <li key={r.period}>
                              <strong>{periodKeyLabel(r.period, model.spread.periods)}:</strong>{" "}
                              {r.value == null ? <span className="text-warn">{r.reason ?? "not computable"}</span> : formatRatio(r.value, r.format, unit)}
                              {Object.keys(r.inputs).length > 0 && (
                                <span className="muted">
                                  {" "}
                                  (inputs:{" "}
                                  {Object.entries(r.inputs)
                                    .map(([k, val]) => `${model.lineInfo(k).label} ${val == null ? "missing" : formatAmountPrecise(val, unit)}`)
                                    .join("; ")}
                                  )
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted">n/c: not computable; hover or open the formula for the reason.</p>
    </div>
  );
}

// ---------- Audit log ----------

function describe(e: AuditEvent): string {
  const p = e.payload as Record<string, unknown>;
  switch (e.kind) {
    case "run":
      return p.status === "failed"
        ? `Run failed: ${String(p.error ?? "")}`
        : `Run finished: ${String(p.values ?? "?")} values, ${String(p.review_items ?? "?")} review items${p.parent ? `, from run #${String(p.parent)}` : ""}`;
    case "correct_value":
      return `Corrected ${String(p.line)} for ${String(p.period)} to ${String(p.value)}: ${String(p.reason ?? "")}`;
    case "resolve_item":
      return `Resolved ${String(p.item)}: ${String(p.note ?? "")}`;
    case "remap_row":
      return `Placed row “${String(p.label)}” on ${String(p.line)} (${String(p.statement)})`;
    case "exclude_row":
      return `Excluded row “${String(p.label)}” (${String(p.statement)})`;
    case "approve":
      return "Approved the spread";
    case "reopen":
      return "Reopened the spread";
    case "export":
      return `Exported ${String(p.format)}${p.approved ? " (approved)" : " (not approved)"}`;
    case "session_start":
      return `Started timed ${String(p.mode)} session #${String(p.session)}`;
    case "session_end":
      return `Ended timed session #${String(p.session)}`;
    default:
      return e.kind;
  }
}

export function AuditTab() {
  const { runId } = useWorkspace();
  const ev = useApi(() => api.events(runId), [runId]);
  if (ev.loading && !ev.data) return <Loading label="Loading the audit log" />;
  if (ev.error) return <ErrorState error={ev.error} onRetry={ev.reload} />;
  const events = ev.data ?? [];
  return (
    <div className="tab-body">
      <div className="toolbar">
        <p className="small muted">Every change to this run, newest last. Names come from the Reviewer field; there is no sign-in.</p>
        <button type="button" className="btn btn-small" onClick={ev.reload}>
          Refresh
        </button>
      </div>
      {events.length === 0 ? (
        <EmptyState title="No events for this run" />
      ) : (
        <div className="grid-scroll">
          <table className="data-table audit-table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Who</th>
                <th scope="col">What</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td className="nowrap num">{formatDateTime(e.at)}</td>
                  <td>{e.actor}</td>
                  <td>
                    <span className="chip">{e.kind.replace(/_/g, " ")}</span>
                  </td>
                  <td>
                    {describe(e)}
                    <details className="raw">
                      <summary className="small muted">payload</summary>
                      <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
