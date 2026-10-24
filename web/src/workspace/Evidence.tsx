import { useEffect, useRef, useState, type FormEvent, type MutableRefObject } from "react";
import { ApiError } from "../api/client";
import type { ProvenanceStep, ReviewItem, SourceRef, SpreadValue } from "../api/types";
import { SeverityMark, StatusMarker } from "../components/Markers";
import { InlineMessage } from "../components/States";
import { formatExact, formatLineValue, formatPerShare, toFullUnits, unitName } from "../lib/format";
import { periodKeyLabel } from "../lib/periods";
import { REVIEW_KIND, STATEMENT_TITLE, STEP_KIND, VALUE_STATUS } from "../lib/status";
import { getSession, updateSession } from "../lib/store";
import { useWorkspace } from "./context";
import { UNITS } from "./SpreadGrid";

// ---- source location and PDF page ----

function refLocation(ref: SourceRef): string {
  if (ref.format === "pdf") return `Page ${ref.page ?? "?"}, table ${ref.table + 1}, row ${ref.row + 1}`;
  if (ref.format === "xlsx") return `${ref.sheet ? `Sheet “${ref.sheet}”` : "Sheet"}, cell ${ref.cell ?? "?"}`;
  return `Table ${ref.table + 1}, row ${ref.row + 1}`;
}

const PDF_RENDER_SCALE = 1.5; // the server renders page PNGs at scale 1.5

export function PdfHighlight({ docId, page, bbox }: { docId: string; page: number; bbox: [number, number, number, number] | null }) {
  const box = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const src = `/api/documents/${docId}/pages/${page}.png`;
  const [x0, top, x1, bottom] = (bbox ?? [0, 0, 0, 0]).map((n) => n * PDF_RENDER_SCALE) as [number, number, number, number];
  const pad = 3;
  const onLoad = () => {
    const el = box.current;
    if (!el || !bbox) return;
    // Centre the highlighted cell in the viewer.
    el.scrollTo({ left: Math.max(0, x0 - el.clientWidth / 2 + (x1 - x0) / 2), top: Math.max(0, top - el.clientHeight / 2) });
  };
  if (failed) return <p className="muted small">The page image could not be loaded.</p>;
  return (
    <figure className="pdf-figure">
      <div className="pdf-viewer" ref={box} tabIndex={0} aria-label={`Page ${page} of the PDF, the cell is highlighted`}>
        <div className="pdf-canvas">
          <img src={src} alt={`Page ${page} of the source PDF`} onLoad={onLoad} onError={() => setFailed(true)} />
          {bbox && (
            <span
              className="pdf-box"
              style={{ left: x0 - pad, top: top - pad, width: x1 - x0 + pad * 2, height: bottom - top + pad * 2 }}
              aria-hidden="true"
            />
          )}
        </div>
      </div>
      <figcaption className="small muted">
        Page {page}.{" "}
        <a href={src} target="_blank" rel="noreferrer">
          Open the full page
        </a>
      </figcaption>
    </figure>
  );
}

function PrintedRef({ sref: ref }: { sref: SourceRef }) {
  return (
    <div className="printed-ref">
      <code className="printed" title="Exactly as printed in the source">
        {ref.text || "(blank)"}
      </code>
      <span className="small muted">{refLocation(ref)}</span>
      {ref.xpath && (
        <span className="xpath small" title={ref.xpath}>
          {ref.xpath}
        </span>
      )}
      {ref.format === "pdf" && ref.page != null && <PdfHighlight docId={ref.doc_id} page={ref.page} bbox={ref.bbox} />}
    </div>
  );
}

// ---- provenance trail ----

export function ProvenanceTrail({ v, kind }: { v: SpreadValue; kind: string }) {
  const reads = v.steps.filter((s) => s.kind === "read");
  const paired = reads.length > 0 && reads.length === v.refs.length;
  let readIndex = 0;
  const nodes: { kind: string; step?: ProvenanceStep; ref?: SourceRef; refs?: SourceRef[] }[] = [];
  if (!paired && v.refs.length > 0) nodes.push({ kind: "printed", refs: v.refs });
  for (const s of v.steps) {
    if (paired && s.kind === "read") nodes.push({ kind: "read", step: s, ref: v.refs[readIndex++]! });
    else nodes.push({ kind: s.kind, step: s });
  }
  return (
    <section className="ev-section" aria-labelledby="trail-title">
      <h3 id="trail-title">Provenance trail</h3>
      <p className="small muted">From the printed text, through each step, to the value in the spread.</p>
      <ol className="trail">
        {nodes.map((n, i) => (
          <li key={i} className={`trail-node trail-${n.kind}`}>
            <span className="trail-kind">{n.kind === "printed" ? (v.status === "calculated" ? "Inputs" : "Printed") : STEP_KIND[n.kind] ?? n.kind}</span>
            <div className="trail-body">
              {n.ref && <PrintedRef sref={n.ref} />}
              {n.refs?.map((r, j) => <PrintedRef key={j} sref={r} />)}
              {n.step && <p>{n.step.detail}</p>}
            </div>
          </li>
        ))}
        {nodes.length === 0 && (
          <li className="trail-node">
            <span className="trail-kind">—</span>
            <div className="trail-body">
              <p className="muted">No steps were recorded for this value.</p>
            </div>
          </li>
        )}
        <li className="trail-node trail-result">
          <span className="trail-kind">Spread</span>
          <div className="trail-body">
            <span className="num strong">{kind === "per_share" ? formatPerShare(v.value) : formatExact(v.value)}</span>{" "}
            <StatusMarker status={v.status} withLabel />
          </div>
        </li>
      </ol>
    </section>
  );
}

// ---- review items ----

export function ResolveForm({ item, onDone, compact = false }: { item: ReviewItem; onDone?: () => void; compact?: boolean }) {
  const { act, model } = useWorkspace();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const needsConfirm = item.kind === "assumed_scale";
  const id = `resolve-${item.id.replace(/[^\w-]/g, "_")}`;
  if (model.approved) return <p className="small muted">The spread is approved. Reopen it to resolve items.</p>;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!note.trim()) {
      setError("Write a note saying why this item is resolved.");
      return;
    }
    if (needsConfirm && !/confirm/i.test(note)) {
      setError("An assumed unit is resolved only by confirming it: include the word “confirm” (for example “Confirm: the filing is in millions”).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await act({ type: "resolve_item", item: item.id, note: note.trim() });
      setNote("");
      onDone?.();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className={`resolve-form ${compact ? "is-compact" : ""}`} onSubmit={submit}>
      <label htmlFor={id}>
        Resolution note <span className="req">(required)</span>
      </label>
      <textarea
        id={id}
        rows={2}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={needsConfirm ? "Confirm: the statements are in thousands (stated on page 3)" : "Why this is acceptable or what was done"}
        aria-describedby={needsConfirm ? `${id}-hint` : undefined}
      />
      {needsConfirm && (
        <p id={`${id}-hint`} className="small muted">
          The unit was assumed. Resolving it means you confirm it: the note must contain “confirm”.
        </p>
      )}
      <div className="form-row">
        <button type="submit" className="btn btn-small" disabled={busy}>
          {busy ? "Resolving…" : "Resolve"}
        </button>
        {onDone && (
          <button type="button" className="btn btn-small btn-quiet" onClick={onDone}>
            Cancel
          </button>
        )}
      </div>
      {error && <InlineMessage kind="error">{error}</InlineMessage>}
    </form>
  );
}

function RelatedItems({ items }: { items: ReviewItem[] }) {
  const [openForm, setOpenForm] = useState<string | null>(null);
  if (!items.length) return null;
  const open = items.filter((i) => !i.resolved);
  const resolved = items.filter((i) => i.resolved);
  return (
    <section className="ev-section" aria-labelledby="ev-items-title">
      <h3 id="ev-items-title">
        Review items on this value <span className="count">{open.length} open</span>
      </h3>
      <ul className="ev-items">
        {open.map((it) => (
          <li key={it.id} className={`ev-item sev-row-${it.severity}`}>
            <div className="q-head">
              <SeverityMark severity={it.severity} withLabel />
              <span className="q-kind">{REVIEW_KIND[it.kind] ?? it.kind}</span>
            </div>
            <p>{it.message}</p>
            {openForm === it.id ? (
              <ResolveForm item={it} onDone={() => setOpenForm(null)} />
            ) : (
              <button type="button" className="btn btn-small" onClick={() => setOpenForm(it.id)} aria-expanded={false}>
                Resolve with a note…
              </button>
            )}
          </li>
        ))}
      </ul>
      {resolved.length > 0 && (
        <details className="resolved">
          <summary>Resolved ({resolved.length})</summary>
          <ul className="ev-items">
            {resolved.map((it) => (
              <li key={it.id} className="ev-item is-resolved">
                <div className="q-head">
                  <SeverityMark severity={it.severity} withLabel />
                  <span className="q-kind">{REVIEW_KIND[it.kind] ?? it.kind}</span>
                </div>
                <p>{it.message}</p>
                <p className="small">
                  <strong>Resolved:</strong> {it.resolution}
                </p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

// ---- correction ----

function CorrectionForm({ line, period, kind, current }: { line: string; period: string; kind: string; current: SpreadValue | undefined }) {
  const { act, unit, model } = useWorkspace();
  const perShare = kind === "per_share";
  const [entryUnit, setEntryUnit] = useState(perShare ? 1 : unit);
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setText("");
    setReason("");
    setError(null);
    setOk(null);
  }, [line, period]);
  useEffect(() => setEntryUnit(perShare ? 1 : unit), [unit, perShare]);

  if (model.approved) {
    return (
      <section className="ev-section">
        <h3>Correct this value</h3>
        <p className="small muted">The spread is approved and locked. Reopen it to change values.</p>
      </section>
    );
  }
  const full = text.trim() ? toFullUnits(text, entryUnit) : null;
  const invalid = text.trim() !== "" && full === null;
  const fid = `corr-${line}`;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setOk(null);
    if (full === null) {
      setError(text.trim() ? "That is not a number. Use digits, with commas or parentheses if you like: (1,234.5)." : "Enter the correct value.");
      return;
    }
    if (!reason.trim()) {
      setError("A correction needs a reason (for example: “Printed on page 4 as 1,234; the row was mis-read”).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await act({ type: "correct_value", line, period, value: full, reason: reason.trim() });
      const s = getSession();
      if (s && s.mode === "assisted" && s.documentId === model.spread.doc_id) updateSession({ corrections: s.corrections + 1 });
      setOk(`Saved: ${formatExact(full)}. Checks, ratios and the review queue were recalculated.`);
      setText("");
      setReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ev-section" aria-labelledby={`${fid}-title`}>
      <h3 id={`${fid}-title`}>{current?.value != null ? "Correct this value" : "Enter this value by hand"}</h3>
      <form className="correction-form" onSubmit={submit} noValidate>
        <div className="form-grid">
          <label htmlFor={`${fid}-value`}>New value</label>
          <div className="form-inline">
            <input
              id={`${fid}-value`}
              type="text"
              inputMode="decimal"
              className="num-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-invalid={invalid}
              aria-describedby={`${fid}-preview`}
              placeholder={current?.value != null ? formatLineValue(current.value, kind, entryUnit) : "0"}
              autoComplete="off"
            />
            {!perShare && (
              <select aria-label="Unit the new value is typed in" value={entryUnit} onChange={(e) => setEntryUnit(Number(e.target.value))}>
                {UNITS.map((u) => (
                  <option key={u} value={u}>
                    in {unitName(u)}
                  </option>
                ))}
              </select>
            )}
          </div>
          <span />
          <output id={`${fid}-preview`} className={`small ${invalid ? "text-bad" : "muted"}`}>
            {invalid ? "Not a number yet" : full !== null ? `= ${formatExact(full)} ${perShare ? "per share" : "in units"}` : "Negative: (1,234) or -1234"}
          </output>
          <label htmlFor={`${fid}-reason`}>
            Reason <span className="req">(required)</span>
          </label>
          <textarea id={`${fid}-reason`} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What the source shows and why the value was wrong" />
        </div>
        <div className="form-row">
          <button type="submit" className="btn btn-primary btn-small" disabled={busy}>
            {busy ? "Saving…" : "Save correction"}
          </button>
        </div>
        {error && <InlineMessage kind="error">{error}</InlineMessage>}
        {ok && <InlineMessage kind="success">{ok}</InlineMessage>}
      </form>
    </section>
  );
}

// ---- panel ----

export function EvidencePanel({
  cellKey,
  onBack,
  focusTick = 0,
  focusConsumed,
}: {
  cellKey: string;
  onBack: () => void;
  focusTick?: number;
  focusConsumed?: MutableRefObject<number>;
}) {
  const { model, unit, gotoSource } = useWorkspace();
  const at = cellKey.indexOf("@");
  const line = cellKey.slice(0, at);
  const period = cellKey.slice(at + 1);
  const v = model.index.get(cellKey);
  const info = model.lineInfo(line);
  const related = model.relatedItems(line, period);
  const heading = useRef<HTMLHeadingElement>(null);
  const stmtResult = model.spread.statements[info.statement];
  const status = v ? VALUE_STATUS[v.status] : null;

  // A focus request (from the review queue or a check link) is honoured once, after rendering.
  useEffect(() => {
    if (focusConsumed && focusTick > focusConsumed.current) {
      focusConsumed.current = focusTick;
      heading.current?.focus({ preventScroll: true });
      heading.current?.scrollIntoView({ block: "nearest" });
    }
  }, [focusTick, cellKey, focusConsumed]);

  return (
    <section className="evidence" aria-labelledby="ev-title">
      <div className="panel-bar">
        <button type="button" className="btn btn-small btn-quiet" onClick={onBack}>
          ← Review queue
        </button>
      </div>
      <header className="ev-head">
        <p className="eyebrow">
          {STATEMENT_TITLE[info.statement]} · {periodKeyLabel(period, model.spread.periods)}
        </p>
        <h2 id="ev-title" ref={heading} tabIndex={-1}>
          {info.label}
          {info.critical && <span className="badge" title="A wrong value on this line changes a credit decision">critical</span>}
        </h2>
      </header>

      {v && v.value != null ? (
        <div className={`ev-value ${v.flags.length ? `flag-${model.flagSeverity(v) ?? ""}` : ""}`}>
          <span className="ev-big num">{formatLineValue(v.value, info.kind, unit)}</span>
          <span className="muted small">{info.kind === "per_share" ? "per share" : unitName(unit)}</span>
          <span className="ev-exact num small">
            = {info.kind === "per_share" ? formatPerShare(v.value) : formatExact(v.value)} {info.kind === "per_share" ? "" : "in units"}
          </span>
        </div>
      ) : (
        <div className="ev-value ev-none">
          <p>
            <strong>No value</strong> for this line and period.{" "}
            {stmtResult
              ? "No row of the statement was placed on this line. If the document prints it, remap that row in the Source view, or enter the value by hand below."
              : "The statement was not found in the document."}
          </p>
        </div>
      )}

      {v && status && (
        <dl className="ev-facts">
          <dt>Status</dt>
          <dd>
            <StatusMarker status={v.status} withLabel /> <span className="small muted">{status.description}</span>
          </dd>
          <dt>Confidence</dt>
          <dd>
            <span className="num">{Math.round(v.confidence * 100)}%</span>
            <span className="meter" aria-hidden="true">
              <span style={{ width: `${Math.round(v.confidence * 100)}%` }} />
            </span>
          </dd>
          {v.source_rows.length > 0 && stmtResult && (
            <>
              <dt>Source rows</dt>
              <dd>
                {v.source_rows.map((r) => `row ${r + 1}`).join(", ")}{" "}
                <button type="button" className="btn btn-small" onClick={() => gotoSource(info.statement, v.source_rows)}>
                  Show in source
                </button>
              </dd>
            </>
          )}
        </dl>
      )}

      <RelatedItems items={related} />
      {v && <ProvenanceTrail v={v} kind={info.kind} />}
      <CorrectionForm line={line} period={period} kind={info.kind} current={v} />
    </section>
  );
}
