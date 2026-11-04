import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { api } from "../api/client";
import type { Explanation, FixMode, ReviewItem, Severity, SourceRow, SourceTable, StatementKey, SuggestedFix } from "../api/types";
import { SeverityMark } from "../components/Markers";
import { InlineMessage } from "../components/States";
import { formatAmount, formatDate, formatExact, formatLineValue, toFullUnits, unitName } from "../lib/format";
import { findValue } from "../lib/periods";
import { setQuery } from "../lib/router";
import { STATEMENT_TITLE } from "../lib/status";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "./context";
import { rowHasValues, SheetContext } from "./SheetContext";

const UNITS = [1, 1_000, 1_000_000, 1_000_000_000];

const MODE_LABEL: Record<FixMode, string> = {
  move: "Move a row",
  exclude: "Leave a row off",
  value: "Change a value",
  accept: "Accept as it is",
};

const STRENGTH_LABEL: Record<SuggestedFix["strength"], string> = {
  strong: "The numbers show this",
  possible: "Possible",
  manual: "Your call",
};

function periodLabel(key: string): string {
  const [end, kind] = key.split("/");
  const d = end ? formatDate(end) : key;
  return kind && kind !== "I" ? `${d} (${kind.replace("M", " months")})` : d;
}

export function closeIssues() {
  setQuery({ issues: null, issue: null }, { push: true });
}

function FixForm({
  item,
  ex,
  chosen,
  statement,
  source,
  row,
  setRow,
  mode,
  setMode,
  onApplied,
}: {
  item: ReviewItem;
  ex: Explanation;
  chosen: SuggestedFix | null;
  statement: StatementKey | null;
  source: SourceTable | null;
  row: number | null;
  setRow: (r: number) => void;
  mode: FixMode;
  setMode: (m: FixMode) => void;
  onApplied: (text: string) => void;
}) {
  const { act, model, unit } = useWorkspace();
  const [line, setLine] = useState<string>("");
  const [valueKey, setValueKey] = useState<string>(ex.values[0] ? `${ex.values[0].line}@${ex.values[0].period}` : "");
  const [text, setText] = useState("");
  const [entryUnit, setEntryUnit] = useState(unit);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!chosen) return;
    const f = chosen.fix;
    if (f.line) setLine(f.line);
    if (f.mode === "value" && f.line && f.period) {
      setValueKey(`${f.line}@${f.period}`);
      setText(f.value ?? "");
      setEntryUnit(1);
    }
    setReason(chosen.reason);
    setError(null);
  }, [chosen]);

  if (model.approved) return <p className="small muted">The spread is approved and locked. Reopen it to change anything.</p>;

  const lines = statement ? model.statementLines[statement] : [];
  const rows: SourceRow[] = source?.rows.filter(rowHasValues) ?? [];
  const selectedRow = rows.find((r) => r.index === row);
  const period = item.periods[0] ?? source?.periods[0]?.key;
  const amount = selectedRow && period && source ? selectedRow.values[period]?.displayed : null;
  const added = amount != null && source ? Number(amount) * source.scale.multiplier : null;
  const existing = line && period ? findValue(model.index, line, period)?.value : null;
  const [valLine, valPeriod] = valueKey.split("@");
  const full = text.trim() ? toFullUnits(text, entryUnit) : null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const why = reason.trim();
    if (!why) {
      setError("Say why: the next reviewer and the audit log read it.");
      return;
    }
    if (ex.needs_confirm_word && mode === "accept" && !/confirm/i.test(why)) {
      setError("An assumed unit is accepted only by confirming it: include the word “confirm”, as in “Confirm: in thousands, page 3”.");
      return;
    }
    let action: Record<string, unknown>;
    let done: string;
    if (mode === "move" || mode === "exclude") {
      if (row === null || !statement) return setError("Choose the row.");
      if (mode === "move" && !line) return setError("Choose the line it belongs on.");
      action =
        mode === "move"
          ? { type: "remap_row", statement, row, line, reason: why }
          : { type: "exclude_row", statement, row, reason: why };
      done = "Row moved. The checks and this list were recalculated.";
    } else if (mode === "value") {
      if (full === null) return setError(text.trim() ? "That is not a number." : "Enter the correct value.");
      action = { type: "correct_value", line: valLine, period: valPeriod, value: full, reason: why };
      done = "Value changed. The checks and this list were recalculated.";
    } else {
      action = { type: "resolve_item", item: item.id, note: why };
      done = "Accepted, with your reason on record.";
    }
    setBusy(true);
    try {
      await act(action);
      setReason("");
      setText("");
      onApplied(done);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="fix-form" onSubmit={submit} noValidate>
      <div className="fix-modes" role="group" aria-label="How to fix it">
        {ex.modes.map((m) => (
          <button key={m} type="button" className={mode === m ? "is-on" : ""} aria-pressed={mode === m} onClick={() => setMode(m)}>
            {MODE_LABEL[m]}
          </button>
        ))}
      </div>

      {(mode === "move" || mode === "exclude") &&
        (rows.length === 0 ? (
          <p className="small muted">This issue has no row to move. Use another fix, or open the document to find one.</p>
        ) : (
          <div className="fix-fields">
            <label>
              Row
              <select value={row ?? ""} onChange={(e) => setRow(Number(e.target.value))}>
                {rows.map((r) => (
                  <option key={r.index} value={r.index}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
            {mode === "move" && (
              <label>
                Belongs on
                <select value={line} onChange={(e) => setLine(e.target.value)}>
                  <option value="">Choose a line…</option>
                  {lines.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="small muted fix-note">
              {mode === "move" && line && added !== null
                ? `${model.lineInfo(line).label} is ${existing == null ? "blank" : formatAmount(existing, unit)} now and would be ${formatAmount(String(added + Number(existing ?? 0)), unit)} for ${periodLabel(period!)}. `
                : ""}
              {mode === "move" ? "The placement is remembered for this label in future documents." : "The row stays in the document but adds nothing to the spread."}
            </p>
          </div>
        ))}

      {mode === "value" && (
        <div className="fix-fields">
          <label>
            Value to change
            <select value={valueKey} onChange={(e) => setValueKey(e.target.value)}>
              {ex.values.map((v) => (
                <option key={`${v.line}@${v.period}`} value={`${v.line}@${v.period}`}>
                  {v.label}, {periodLabel(v.period)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Correct value
            <span className="form-inline">
              <input type="text" inputMode="decimal" className="num-input" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" />
              <select aria-label="Unit the value is typed in" value={entryUnit} onChange={(e) => setEntryUnit(Number(e.target.value))}>
                {UNITS.map((u) => (
                  <option key={u} value={u}>
                    in {unitName(u)}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <p className="small muted fix-note">{full !== null ? `= ${formatExact(full)}` : "Negative: (1,234) or -1234"}</p>
        </div>
      )}

      {mode === "accept" && <p className="small muted fix-note">Nothing changes in the spread. This records that a person looked and it is fine.</p>}

      <label className="fix-reason">
        {mode === "accept" ? "Why is it fine as it is?" : "Why did it need changing?"} <span className="req">(required)</span>
        <textarea
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={
            ex.needs_confirm_word && mode === "accept"
              ? "Confirm: the statements are in thousands (stated on page 3)"
              : mode === "accept"
                ? "What you compared, and what you found"
                : "What the document shows, and why the spread was wrong"
          }
        />
      </label>
      <div className="form-row">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Applying…" : mode === "accept" ? "Accept with this reason" : "Apply the fix"}
        </button>
      </div>
      {error && <InlineMessage kind="error">{error}</InlineMessage>}
    </form>
  );
}

function Detail({ item, ex, onApplied }: { item: ReviewItem; ex: Explanation; onApplied: (text: string) => void }) {
  const { model, unit, runId } = useWorkspace();
  const [chosen, setChosen] = useState<SuggestedFix | null>(null);
  const [mode, setMode] = useState<FixMode>(ex.modes[0] ?? "accept");
  const [row, setRow] = useState<number | null>(ex.rows[0]?.row ?? item.rows[0] ?? null);
  const statement = (chosen?.fix.statement ?? ex.rows[0]?.statement ?? item.statement) as StatementKey | null;
  const source = useApi(() => (statement ? api.source(runId, statement) : Promise.reject(new Error("none"))), [runId, statement]);
  const marked = useMemo(() => [...new Set([...ex.rows.map((r) => r.row), ...ex.values.flatMap((v) => v.rows), ...item.rows])], [ex, item]);
  const choose = (s: SuggestedFix) => {
    setChosen(s);
    setMode(s.fix.mode);
    if (s.fix.row !== undefined && s.fix.row !== null) setRow(s.fix.row);
  };
  const pick = (r: number) => {
    setRow(r);
    const v = ex.modes.find((m) => m === "move" || m === "exclude");
    if (v && mode !== "move" && mode !== "exclude") setMode(v);
  };
  const seeInDocument = (rows: number[]) => {
    if (!item.statement) return;
    setQuery({ issues: null, issue: null, tab: "source", stmt: item.statement, rows: rows.join(",") || null }, { push: true });
  };
  const blocker = item.severity === "blocker";
  return (
    <div className="issue-detail">
      <header>
        <p className={`issue-kicker sev-text-${item.severity}`}>
          <SeverityMark severity={item.severity} /> {blocker ? "Blocks approval" : "Warning"}
          {item.statement && <span className="muted"> · {STATEMENT_TITLE[item.statement]}</span>}
          {item.periods[0] && <span className="muted"> · {periodLabel(item.periods[0])}</span>}
        </p>
        <h3>{ex.title}</h3>
      </header>

      <section>
        <h4>What's wrong</h4>
        <p>{ex.what}</p>
        {ex.compare && (
          <dl className="issue-compare">
            <div>
              <dt>{ex.compare.left_label}</dt>
              <dd className="num">{formatAmount(ex.compare.left, unit)}</dd>
            </div>
            <div>
              <dt>{ex.compare.right_label}</dt>
              <dd className="num">{formatAmount(ex.compare.right, unit)}</dd>
            </div>
            <div className="is-gap">
              <dt>Gap</dt>
              <dd className="num">{formatAmount(ex.compare.gap, unit)}</dd>
            </div>
            <p className="small muted">In {unitName(unit)}.</p>
          </dl>
        )}
      </section>

      <section>
        <h4>{blocker ? "Why it blocks approval" : "Why it's flagged"}</h4>
        <p>{ex.why}</p>
      </section>

      {source.data && statement && (
        <section>
          <h4>Where it is in the statement</h4>
          <SheetContext source={source.data} marked={marked} picked={row} onPick={pick} />
          <p className="sheet-more">
            <button type="button" className="link-button small" onClick={() => seeInDocument(marked)}>
              Open the full statement
            </button>
          </p>
        </section>
      )}

      {ex.suggestions.length > 0 && (
        <section>
          <h4>Suggested fixes</h4>
          <ul className="issue-suggestions">
            {ex.suggestions.map((s) => (
              <li key={s.title} className={chosen === s ? "is-chosen" : ""}>
                <div>
                  <span className={`strength strength-${s.strength}`}>{STRENGTH_LABEL[s.strength]}</span>
                  <p className="s-title">{s.title}</p>
                  <p className="small muted">{s.detail}</p>
                </div>
                <button type="button" className="btn btn-small" onClick={() => choose(s)}>
                  Use this
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h4>Fix it</h4>
        <FixForm
          key={item.id}
          item={item}
          ex={ex}
          chosen={chosen}
          statement={statement}
          source={source.data}
          row={row}
          setRow={setRow}
          mode={mode}
          setMode={setMode}
          onApplied={(t) => {
            setChosen(null);
            onApplied(t);
          }}
        />
      </section>

      {ex.values.length > 0 && (
        <section>
          <h4>Values involved</h4>
          <table className="issue-values">
            <tbody>
              {ex.values.map((v) => (
                <tr key={`${v.line}@${v.period}`}>
                  <th scope="row">
                    {v.label}
                    {v.confirmed_by.length > 0 && <span className="small muted"> · confirmed by: {v.confirmed_by.join("; ")}</span>}
                  </th>
                  <td className="small muted">{periodLabel(v.period)}</td>
                  <td className="num">{v.value === null ? <span className="muted">blank</span> : formatLineValue(v.value, model.lineInfo(v.line).kind, unit)}</td>
                  <td>
                    {item.statement && v.rows.length > 0 && (
                      <button type="button" className="btn btn-quiet btn-small" onClick={() => seeInDocument(v.rows)}>
                        See in document
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <details className="issue-technical">
        <summary>Technical detail</summary>
        <p className="small muted">{item.message}</p>
      </details>
    </div>
  );
}

export function IssuesPanel({ filter, selected }: { filter: string; selected: string | null }) {
  const { model } = useWorkspace();
  const explanations = useMemo(() => model.payload.explanations ?? {}, [model]);
  const open = useMemo(() => model.spread.review.filter((i) => !i.resolved && explanations[i.id]), [model, explanations]);
  const counts = {
    blocker: open.filter((i) => i.severity === "blocker").length,
    warning: open.filter((i) => i.severity === "warning").length,
  };
  const sev: Severity = filter === "warning" ? "warning" : "blocker";
  const list = open.filter((i) => i.severity === sev);
  const item = list.find((i) => i.id === selected) ?? list[0] ?? null;
  const ex = item ? explanations[item.id] : undefined;
  const [note, setNote] = useState<string | null>(null);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    close.current?.focus();
  }, []);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") closeIssues();
  };

  return (
    <div className="issues-backdrop" onKeyDown={onKey} onMouseDown={(e) => e.target === e.currentTarget && closeIssues()}>
      <div className="issues-panel" role="dialog" aria-modal="true" aria-labelledby="issues-title">
        <header className="issues-head">
          <h2 id="issues-title">Issues to review</h2>
          <div className="fix-modes" role="group" aria-label="Show">
            {(["blocker", "warning"] as const).map((s) => (
              <button key={s} type="button" className={sev === s ? "is-on" : ""} aria-pressed={sev === s} onClick={() => setQuery({ issues: s, issue: null })}>
                {s === "blocker" ? "Blockers" : "Warnings"} <span className="count">{counts[s]}</span>
              </button>
            ))}
          </div>
          <button ref={close} type="button" className="btn btn-small issues-close" onClick={closeIssues}>
            Close
          </button>
        </header>
        {note && (
          <InlineMessage kind="success" onDismiss={() => setNote(null)}>
            {note}
          </InlineMessage>
        )}
        {list.length === 0 ? (
          <div className="issues-empty">
            <h3>{sev === "blocker" ? "No blockers left" : "No warnings left"}</h3>
            <p className="muted">
              {sev === "blocker" ? "Nothing is locking approval." : "Nothing is waiting for a look."}
              {sev === "blocker" && counts.warning > 0 && ` ${counts.warning} warning${counts.warning === 1 ? " is" : "s are"} still open.`}
            </p>
          </div>
        ) : (
          <div className="issues-body">
            <ol className="issues-list">
              {list.map((i) => (
                <li key={i.id}>
                  <button type="button" className={i.id === item?.id ? "is-on" : ""} aria-current={i.id === item?.id} onClick={() => setQuery({ issue: i.id })}>
                    <span className="il-title">{explanations[i.id]?.headline}</span>
                    <span className="il-meta small muted">
                      {i.statement ? STATEMENT_TITLE[i.statement] : "Whole document"}
                      {i.periods[0] ? ` · ${periodLabel(i.periods[0])}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
            {item && ex && <Detail key={item.id} item={item} ex={ex} onApplied={setNote} />}
          </div>
        )}
      </div>
    </div>
  );
}
