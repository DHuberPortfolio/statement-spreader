import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { api } from "../api/client";
import type { SourceRow, SourceTable, StatementKey } from "../api/types";
import { ErrorState, InlineMessage, Loading } from "../components/States";
import { cleanEvidence, formatDate, unitName } from "../lib/format";
import { durationLabel } from "../lib/periods";
import { MAP_METHOD, STATEMENT_ORDER, STATEMENT_TITLE } from "../lib/status";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "./context";

function hasValues(r: SourceRow): boolean {
  return Object.values(r.values).some((v) => v.displayed !== null);
}

function isUnmapped(r: SourceRow): boolean {
  return !r.header && hasValues(r) && (!r.mapping || (!r.mapping.canonical && !r.mapping.excluded));
}

function MappingChip({ row, statement }: { row: SourceRow; statement: StatementKey }) {
  const { model } = useWorkspace();
  const m = row.mapping;
  if (row.header && !hasValues(row)) return <span className="muted small">header</span>;
  if (!m || (!m.canonical && !m.excluded)) {
    return <span className="chip chip-bad">Not placed</span>;
  }
  if (m.excluded) {
    return (
      <span className="chip chip-muted" title={m.reason}>
        Excluded
      </span>
    );
  }
  const label = model.lineInfo(m.canonical!).label;
  const conf = Math.round(m.confidence * 100);
  return (
    <details className="map-chip">
      <summary className={`chip ${conf < 90 ? "chip-warn" : ""}`}>
        <span>{label}</span>
        <span className="num">{conf}%</span>
        <span className="map-method">{MAP_METHOD[m.method] ?? m.method}</span>
      </summary>
      <div className="map-detail small">
        <p>{m.reason || "No reason recorded."}</p>
        {m.candidates.length > 0 && (
          <p className="muted">
            Other candidates:{" "}
            {m.candidates
              .filter(([c]) => c !== m.canonical)
              .slice(0, 4)
              .map(([c, s]) => `${model.lineInfo(c).label} (${Math.round(s * 100)}%)`)
              .join(", ") || "none"}
          </p>
        )}
        <p className="muted">Statement: {STATEMENT_TITLE[statement]}</p>
      </div>
    </details>
  );
}

function RemapControl({ row, statement, onDone }: { row: SourceRow; statement: StatementKey; onDone: () => void }) {
  const { model, act } = useWorkspace();
  const [target, setTarget] = useState(row.mapping?.canonical ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lines = model.statementLines[statement];
  const id = `remap-${statement}-${row.index}`;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!target) {
      setError("Choose a template line, or “Exclude”.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (target === "__exclude__") await act({ type: "exclude_row", statement, row: row.index });
      else await act({ type: "remap_row", statement, row: row.index, line: target });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };
  return (
    <form className="remap-form" onSubmit={submit}>
      <label htmlFor={id} className="small">
        Place “{row.label}” on
      </label>
      <div className="form-inline">
        <select id={id} value={target} onChange={(e) => setTarget(e.target.value)} disabled={busy}>
          <option value="">Choose a line…</option>
          {lines.map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
          <option value="__exclude__">Exclude: leave this row out of the spread</option>
        </select>
        <button type="submit" className="btn btn-small btn-primary" disabled={busy}>
          {busy ? "Re-running…" : "Apply"}
        </button>
        <button type="button" className="btn btn-small btn-quiet" onClick={onDone} disabled={busy}>
          Cancel
        </button>
      </div>
      <p className="small muted">
        Creates a new run, and is remembered: this label{row.section ? ` under “${row.section.split(" > ").pop()}”` : ""} maps the same
        way in future documents. Your corrections and resolutions carry over.
      </p>
      {error && <InlineMessage kind="error">{error}</InlineMessage>}
    </form>
  );
}

export function SourceView({ statement, highlight }: { statement: StatementKey; highlight: number[] }) {
  const { runId, model, gotoSource } = useWorkspace();
  const src = useApi(() => api.source(runId, statement), [runId, statement]);
  const [remapRow, setRemapRow] = useState<number | null>(null);
  const [onlyUnmapped, setOnlyUnmapped] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const available = STATEMENT_ORDER.filter((s) => model.spread.statements[s]);

  useEffect(() => {
    if (!src.data || !highlight.length) return;
    const el = scroller.current?.querySelector<HTMLElement>(`tr[data-row="${highlight[0]}"]`);
    el?.scrollIntoView({ block: "center" });
    el?.focus({ preventScroll: true });
  }, [src.data, highlight]);

  return (
    <div className="source-view">
      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Statement">
          {STATEMENT_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              className={s === statement ? "is-on" : ""}
              aria-pressed={s === statement}
              disabled={!available.includes(s)}
              onClick={() => gotoSource(s, [])}
            >
              {STATEMENT_TITLE[s]}
            </button>
          ))}
        </div>
        <label className="check-label">
          <input type="checkbox" checked={onlyUnmapped} onChange={(e) => setOnlyUnmapped(e.target.checked)} /> Only rows not placed
        </label>
      </div>
      {!model.spread.statements[statement] && <p className="stmt-missing">This statement was not found in the document.</p>}
      {src.loading && !src.data && <Loading label="Loading the statement as read" />}
      {src.error && model.spread.statements[statement] && <ErrorState error={src.error} onRetry={src.reload} />}
      {src.data && <SourceTableView data={src.data} statement={statement} highlight={highlight} remapRow={remapRow} setRemapRow={setRemapRow} onlyUnmapped={onlyUnmapped} scroller={scroller} />}
    </div>
  );
}

function SourceTableView({
  data,
  statement,
  highlight,
  remapRow,
  setRemapRow,
  onlyUnmapped,
  scroller,
}: {
  data: SourceTable;
  statement: StatementKey;
  highlight: number[];
  remapRow: number | null;
  setRemapRow: (r: number | null) => void;
  onlyUnmapped: boolean;
  scroller: RefObject<HTMLDivElement>;
}) {
  const { model } = useWorkspace();
  const unmapped = data.rows.filter(isUnmapped).length;
  const rows = onlyUnmapped ? data.rows.filter(isUnmapped) : data.rows;
  const minIndent = Math.min(...data.rows.map((r) => r.indent || 0));
  return (
    <section aria-labelledby="src-title" className="source-table-wrap">
      <header className="source-head">
        <h3 id="src-title">
          {STATEMENT_TITLE[statement]} <span className="muted small">as the pipeline read it (table {data.table_index + 1})</span>
        </h3>
        <p className="small">
          Unit: <strong>{unitName(data.scale.multiplier)}</strong>{" "}
          {data.scale.assumed ? (
            <span className="badge badge-warn">assumed: {data.scale.evidence}</span>
          ) : (
            <span className="muted">from “{cleanEvidence(data.scale.evidence)}”</span>
          )}
          {data.share_scale && (
            <>
              {" · "}shares in <strong>{unitName(data.share_scale.multiplier)}</strong>
            </>
          )}
          {" · "}
          {unmapped > 0 ? <span className="text-warn">{unmapped} value row{unmapped === 1 ? "" : "s"} not placed</span> : <span className="muted">every value row is placed or excluded</span>}
        </p>
        {data.warnings.length > 0 && (
          <ul className="warn-list small">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </header>
      <div className="grid-scroll" ref={scroller}>
        <table className="source-table">
          <thead>
            <tr>
              <th scope="col" className="num">
                Row
              </th>
              <th scope="col">Label as printed</th>
              {data.periods.map((p) => (
                <th key={p.key} scope="col" className="num" title={[`Printed header: “${p.label}”`, ...p.notes, ...p.assumed].join("\n")}>
                  <span className="col-date">{formatDate(p.end)}</span>
                  <span className="col-dur">
                    {durationLabel(p)}
                    {p.assumed.length > 0 && <span className="badge badge-warn">assumed</span>}
                  </span>
                </th>
              ))}
              <th scope="col">Placed on</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const hl = highlight.includes(r.index);
              const cls = [
                `src-${r.role}`,
                r.bold ? "is-bold" : "",
                isUnmapped(r) ? "is-unmapped" : "",
                r.mapping?.excluded ? "is-excluded" : "",
                hl ? "is-highlight" : "",
              ].join(" ");
              return (
                <tr key={r.index} data-row={r.index} className={cls} tabIndex={hl ? -1 : undefined}>
                  <td className="num muted">{r.index + 1}</td>
                  <th scope="row" className="src-label" style={{ paddingLeft: `${0.5 + Math.min(6, Math.max(0, (r.indent - minIndent) / 10))}rem` }}>
                    {r.label}
                    {r.role === "total" && <span className="sr-only"> (total of rows {r.children.map((c) => c + 1).join(", ")})</span>}
                    {r.role === "total" && (
                      <span className="role-tag" title={`Foots to rows ${r.children.map((c) => c + 1).join(", ")}`}>
                        total
                      </span>
                    )}
                  </th>
                  {data.periods.map((p) => {
                    const cell = r.values[p.key];
                    return (
                      <td key={p.key} className="num printed-cell" title={cell?.note ?? undefined}>
                        {cell ? cell.raw : ""}
                        {cell?.note && <span className="sr-only"> ({cell.note})</span>}
                      </td>
                    );
                  })}
                  <td className="map-cell">
                    <MappingChip row={r} statement={statement} />
                  </td>
                  <td className="act-cell">
                    {(hasValues(r) || r.mapping) && !model.approved && remapRow !== r.index && (
                      <button type="button" className="btn btn-small btn-quiet" onClick={() => setRemapRow(r.index)} aria-label={`Change where “${r.label}” is placed`}>
                        Change…
                      </button>
                    )}
                    {remapRow === r.index && <RemapControl row={r} statement={statement} onDone={() => setRemapRow(null)} />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {model.approved && <p className="small muted">The spread is approved. Reopen it to change mappings.</p>}
    </section>
  );
}
