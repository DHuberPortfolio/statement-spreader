import { useEffect, useRef, useState, type DragEvent } from "react";
import { api, ApiError, uploadDocument } from "../api/client";
import type { DocumentRow, RunSummary } from "../api/types";
import { Glyph } from "../components/Markers";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { formatBytes, formatDateTime } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { flash } from "../lib/store";
import { useApi } from "../lib/useApi";

const ACCEPT = ".htm,.html,.xhtml,.pdf,.xlsx,.xlsm";

type UploadPhase =
  | { phase: "idle" }
  | { phase: "uploading"; name: string; fraction: number; index: number; total: number }
  | { phase: "processing"; name: string; index: number; total: number };

function UploadZone({ onUploaded }: { onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [state, setState] = useState<UploadPhase>({ phase: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ name: string; runId: number; status: string }[]>([]);

  async function handle(files: File[]) {
    if (!files.length) return;
    setError(null);
    setDone([]);
    const results: { name: string; runId: number; status: string }[] = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i]!;
      setState({ phase: "uploading", name: f.name, fraction: 0, index: i, total: files.length });
      try {
        const payload = await uploadDocument(f, (fraction) => {
          setState(
            fraction >= 1
              ? { phase: "processing", name: f.name, index: i, total: files.length }
              : { phase: "uploading", name: f.name, fraction, index: i, total: files.length },
          );
        });
        results.push({ name: f.name, runId: payload.run.id, status: payload.run.status });
        if (files.length === 1) {
          setState({ phase: "idle" });
          if (payload.run.status === "failed") {
            flash({ kind: "error", text: `${f.name} was stored, but processing failed: ${payload.run.error ?? "unknown error"}` });
          }
          navigate(`/runs/${payload.run.id}`);
          return;
        }
      } catch (e) {
        setError(`${f.name}: ${e instanceof Error ? e.message : String(e)}`);
        if (e instanceof ApiError && e.offline) break;
      }
    }
    setState({ phase: "idle" });
    setDone(results);
    onUploaded();
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (state.phase !== "idle") return;
    void handle([...e.dataTransfer.files]);
  };

  const busy = state.phase !== "idle";
  return (
    <section className="upload" aria-labelledby="upload-title">
      <div
        className={`dropzone ${drag ? "is-drag" : ""} ${busy ? "is-busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <h2 id="upload-title" className="dropzone-title">
          Add a statement package
        </h2>
        {state.phase === "idle" && (
          <>
            <p>
              Drop a file here, or{" "}
              <button type="button" className="btn btn-primary" onClick={() => input.current?.click()}>
                <Glyph name="upload" /> Choose a file
              </button>
            </p>
            <p className="muted small">SEC 10-K or 10-Q saved as HTML (.htm), a PDF of the statements, or an Excel workbook. Up to the server's size limit.</p>
          </>
        )}
        {state.phase === "uploading" && (
          <div className="progress-block" role="status" aria-live="polite">
            <p>
              Uploading <strong>{state.name}</strong>
              {state.total > 1 && ` (${state.index + 1} of ${state.total})`}
            </p>
            <progress max={1} value={state.fraction} aria-label="Upload progress" />
            <span className="num small">{Math.round(state.fraction * 100)}%</span>
          </div>
        )}
        {state.phase === "processing" && (
          <div className="progress-block" role="status" aria-live="polite">
            <p>
              Reading <strong>{state.name}</strong>: finding the statements, mapping rows, running the checks…
            </p>
            <progress aria-label="Processing" />
          </div>
        )}
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            const files = [...(e.target.files ?? [])];
            e.target.value = "";
            void handle(files);
          }}
        />
      </div>
      {error && (
        <InlineMessage kind="error" onDismiss={() => setError(null)}>
          {error}
        </InlineMessage>
      )}
      {done.length > 0 && (
        <InlineMessage kind="success" onDismiss={() => setDone([])}>
          Processed {done.length} file{done.length === 1 ? "" : "s"}:{" "}
          {done.map((d, i) => (
            <span key={d.runId}>
              {i > 0 && ", "}
              <Link to={`/runs/${d.runId}`}>{d.name}</Link>
              {d.status === "failed" && " (failed)"}
            </span>
          ))}
        </InlineMessage>
      )}
    </section>
  );
}

/** /api/documents has no review counts, so each run's summary is fetched (two at a time). */
function useRunSummaries(docs: DocumentRow[] | null): Record<number, RunSummary | "error"> {
  const [summaries, setSummaries] = useState<Record<number, RunSummary | "error">>({});
  useEffect(() => {
    if (!docs) return;
    const ctrl = new AbortController();
    const ids = docs.map((d) => d.run_id).filter((id): id is number => typeof id === "number");
    let next = 0;
    const worker = async () => {
      while (next < ids.length && !ctrl.signal.aborted) {
        const id = ids[next++]!;
        try {
          const p = await api.run(id, ctrl.signal);
          if (p.summary) setSummaries((s) => ({ ...s, [id]: p.summary! }));
        } catch {
          if (!ctrl.signal.aborted) setSummaries((s) => ({ ...s, [id]: "error" }));
        }
      }
    };
    void Promise.all([worker(), worker()]);
    return () => ctrl.abort();
  }, [docs]);
  return summaries;
}

function RunStatus({ doc }: { doc: DocumentRow }) {
  if (!doc.run_id) return <span className="muted">no run</span>;
  const cls = doc.run_status === "failed" ? "pill pill-bad" : doc.run_status === "running" ? "pill pill-warn" : "pill";
  return (
    <span className={cls}>
      #{doc.run_id} {doc.run_status}
    </span>
  );
}

export function DocumentsPage() {
  const docs = useApi(() => api.documents(), []);
  const summaries = useRunSummaries(docs.data);

  return (
    <div className="page page-documents">
      <header className="page-head">
        <h1>Documents</h1>
        <p className="lede">
          Each document is spread into the standard template. Every value keeps a trail to the printed cell it came from;
          checks and a review queue show what needs a person.
        </p>
      </header>

      <UploadZone onUploaded={docs.reload} />

      <section aria-labelledby="doc-list-title" className="doc-list">
        <h2 id="doc-list-title" className="section-title">
          Spread documents
        </h2>
        {docs.loading && !docs.data && <Loading label="Loading documents" />}
        {docs.error && <ErrorState error={docs.error} onRetry={docs.reload} />}
        {docs.data && docs.data.length === 0 && (
          <EmptyState title="No documents yet">
            <p>Upload the financial statements of one company to start. Good first files:</p>
            <ul className="plain-list">
              <li>
                An <strong>SEC 10-K or 10-Q</strong> saved from EDGAR as <code>.htm</code>: the statements are read from its tables.
              </li>
              <li>
                A <strong>PDF</strong> with the income statement, balance sheet and cash flow statement as text (not a scan).
              </li>
              <li>
                An <strong>Excel workbook</strong> with the statements laid out as on paper.
              </li>
            </ul>
            <p className="muted small">The same file uploaded twice is recognised and opens its existing run.</p>
          </EmptyState>
        )}
        {docs.data && docs.data.length > 0 && (
          <div className="grid-scroll">
            <table className="data-table doc-table">
              <thead>
                <tr>
                  <th scope="col">Document</th>
                  <th scope="col">Uploaded</th>
                  <th scope="col">Run</th>
                  <th scope="col">Approval</th>
                  <th scope="col" className="num">
                    Open blockers
                  </th>
                  <th scope="col" className="num">
                    Open warnings
                  </th>
                </tr>
              </thead>
              <tbody>
                {docs.data.map((d) => {
                  const s = d.run_id ? summaries[d.run_id] : undefined;
                  return (
                    <tr key={d.id}>
                      <th scope="row">
                        {d.run_id ? <Link to={`/runs/${d.run_id}`}>{d.label || d.filename}</Link> : d.label || d.filename}
                        <span className="muted small doc-meta">
                          {d.format.toUpperCase()} · {formatBytes(d.size)}
                        </span>
                      </th>
                      <td className="nowrap">{formatDateTime(d.uploaded_at)}</td>
                      <td>
                        <RunStatus doc={d} />
                      </td>
                      <td>{d.approved ? <span className="stamp stamp-small">Approved</span> : <span className="muted">Not approved</span>}</td>
                      <td className="num">
                        {s === undefined ? (
                          d.run_status === "succeeded" ? <span className="muted" aria-label="loading">…</span> : <span className="muted">–</span>
                        ) : s === "error" ? (
                          <span className="muted">?</span>
                        ) : s.open_blockers > 0 ? (
                          <span className="count-bad">{s.open_blockers}</span>
                        ) : (
                          <span className="count-ok">0</span>
                        )}
                      </td>
                      <td className="num">{s && s !== "error" ? s.open_warnings : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
