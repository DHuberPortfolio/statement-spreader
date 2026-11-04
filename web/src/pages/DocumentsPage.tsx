import { documentTitle, OriginChip } from "../components/Origin";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { api, ApiError, uploadDocument } from "../api/client";
import type { DocumentRow, RunSummary } from "../api/types";
import { Glyph } from "../components/Markers";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { pageOfDocuments, DOCS_PER_PAGE, type DocFilter } from "../lib/docList";
import { formatBytes, formatDateTime } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { flash } from "../lib/store";
import { useApi } from "../lib/useApi";

const ACCEPT = ".htm,.html,.xhtml,.pdf,.xlsx,.xlsm";

type UploadPhase =
  | { phase: "idle" }
  | { phase: "uploading"; name: string; fraction: number; index: number; total: number }
  | { phase: "processing"; name: string; index: number; total: number };

function CompanyField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const companies = useApi(() => api.companies(), []);
  return (
    <div className="company-field">
      <label htmlFor="company-input">Company</label>
      <input
        id="company-input"
        type="text"
        list="company-options"
        value={value}
        maxLength={100}
        placeholder="e.g. Acme Corp or the borrower's ID"
        onChange={(e) => onChange(e.target.value)}
        aria-describedby="company-hint"
      />
      <datalist id="company-options">
        {(companies.data ?? []).map((c) => (
          <option key={c.company_id} value={c.company_id}>
            {`${c.documents} document${c.documents === 1 ? "" : "s"}, ${c.approved_spreads} approved`}
          </option>
        ))}
      </datalist>
      <p id="company-hint" className="muted small">
        Optional, but worth it: last year's approved spread for the same company is used to check this one. SEC filings
        are recognised by their CIK without it.
      </p>
    </div>
  );
}

function CompanyCell({ doc, onSaved }: { doc: DocumentRow; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(doc.company_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!editing) {
    return (
      <span className="company-cell">
        {doc.company_id ? <span>{doc.company_id}</span> : <span className="muted">not set</span>}
        {!doc.approved && (
          <button type="button" className="btn btn-quiet btn-small" onClick={() => setEditing(true)}>
            {doc.company_id ? "Change" : "Set"}
          </button>
        )}
      </span>
    );
  }
  return (
    <form
      className="form-inline"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api.setCompany(doc.id, draft);
          setEditing(false);
          onSaved();
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <input type="text" value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Company" list="company-options" />
      <button type="submit" className="btn btn-primary btn-small" disabled={busy || !draft.trim()}>
        {busy ? "Re-running…" : "Save"}
      </button>
      <button type="button" className="btn btn-small" onClick={() => setEditing(false)}>
        Cancel
      </button>
      {error && <span className="text-bad small">{error}</span>}
    </form>
  );
}

function UploadZone({ onUploaded }: { onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [company, setCompany] = useState("");
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
        const payload = await uploadDocument(
          f,
          (fraction) => {
            setState(
              fraction >= 1
                ? { phase: "processing", name: f.name, index: i, total: files.length }
                : { phase: "uploading", name: f.name, fraction, index: i, total: files.length },
            );
          },
          company,
        );
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
      <CompanyField value={company} onChange={setCompany} />
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
          Add financial statements
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

/** /api/documents has no review counts, so each visible run's summary is fetched (two at a time) and kept. */
function useRunSummaries(docs: DocumentRow[] | null): Record<number, RunSummary | "error"> {
  const [summaries, setSummaries] = useState<Record<number, RunSummary | "error">>({});
  const fetched = useRef(new Set<number>());
  useEffect(() => {
    if (!docs) return;
    const ctrl = new AbortController();
    const ids = docs.map((d) => d.run_id).filter((id): id is number => typeof id === "number" && !fetched.current.has(id));
    let next = 0;
    const worker = async () => {
      while (next < ids.length && !ctrl.signal.aborted) {
        const id = ids[next++]!;
        try {
          const p = await api.run(id, ctrl.signal);
          fetched.current.add(id);
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
  if (!doc.run_id) return <span className="muted">Not read yet</span>;
  const cls = doc.run_status === "failed" ? "pill pill-bad" : doc.run_status === "running" ? "pill pill-warn" : "pill";
  const word = doc.run_status === "failed" ? "Could not read" : doc.run_status === "running" ? "Reading" : "Read";
  return <span className={cls}>{word}</span>;
}

export function DocumentsPage({ view }: { view: "list" | "add" }) {
  const docs = useApi(() => api.documents(), []);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<DocFilter>("all");
  const shown = useMemo(() => pageOfDocuments(docs.data ?? [], query, page, DOCS_PER_PAGE, filter), [docs.data, query, page, filter]);
  const completed = docs.data?.filter((d) => d.approved).length ?? 0;
  const summaries = useRunSummaries(docs.data ? shown.rows : null);

  return (
    <div className="page page-documents">
      <header className="page-head">
        <p className="eyebrow">Daily work</p>
        <div className="page-title-row">
          <h1>{view === "add" ? "Add statements" : "Statements"}</h1>
          {view === "list" && (
            <Link to="/statements/add" className="btn btn-primary">
              Add statements
            </Link>
          )}
        </div>
        <p className="lede">
          {view === "add"
            ? "Upload a company's financial statements and they are spread into the standard template."
            : "Every value links back to the printed cell it came from; anything the checks doubt goes to the review queue for a person."}
        </p>
      </header>

      {view === "add" && <UploadZone onUploaded={() => navigate("/statements")} />}

      {view === "list" && <section aria-labelledby="doc-list-title" className="doc-list">
        <h2 id="doc-list-title" className="section-title">
          Spread documents
        </h2>
        {docs.data && docs.data.some((d) => d.origin === "generated") && docs.data.some((d) => d.origin === "sec") && (
          <p className="muted small doc-origin-note">
            {docs.data.filter((d) => d.origin === "sec").length} real SEC filings and{" "}
            {docs.data.filter((d) => d.origin === "generated").length} documents generated to prove concept.
          </p>
        )}
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
          <div className="doc-find">
            <div className="segmented" role="group" aria-label="Show">
              {([["all", `All (${docs.data.length})`], ["in_review", `In review (${docs.data.length - completed})`], ["completed", `Completed (${completed})`]] as [DocFilter, string][]).map(([key, text]) => (
                <button
                  key={key}
                  type="button"
                  className={filter === key ? "is-on" : ""}
                  aria-pressed={filter === key}
                  onClick={() => {
                    setFilter(key);
                    setPage(1);
                  }}
                >
                  {text}
                </button>
              ))}
            </div>
            <input
              type="search"
              aria-label="Find a company or filing"
              placeholder="Find a company or filing"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
            />
            <span className="muted small" aria-live="polite">
              {shown.matches === docs.data.length ? `${shown.matches} documents` : `${shown.matches} of ${docs.data.length} documents`}
            </span>
          </div>
        )}
        {docs.data && docs.data.length > 0 && shown.matches === 0 && <p className="muted">No company or filing matches that.</p>}
        {docs.data && shown.matches > 0 && (
          <div className="grid-scroll">
            <table className="data-table doc-table">
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col">Uploaded</th>
                  <th scope="col">Status</th>
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
                {shown.rows.map((d) => {
                  const s = d.run_id ? summaries[d.run_id] : undefined;
                  return (
                    <tr key={d.id}>
                      <th scope="row">
                        {d.run_id ? <Link to={`/runs/${d.run_id}`}>{documentTitle(d)}</Link> : documentTitle(d)}
                        <span className="muted small doc-meta">
                          <OriginChip doc={d} /> {d.format.toUpperCase()} · {formatBytes(d.size)}
                        </span>
                        {!d.company_name && <CompanyCell doc={d} onSaved={docs.reload} />}
                      </th>
                      <td className="nowrap">{formatDateTime(d.uploaded_at)}</td>
                      <td>
                        <RunStatus doc={d} />
                      </td>
                      <td>
                        {d.approved ? <span className="stamp stamp-small">Approved</span> : <span className="muted">Not approved</span>}
                        {(d.corrected_after_review ?? 0) > 0 && " "}
                        {(d.corrected_after_review ?? 0) > 0 && (
                          <span className="chip chip-bad" title="A senior ruled lines of this approved spread wrong; reopen it to fix them">
                            Corrected after review
                          </span>
                        )}
                      </td>
                      <td className="num">
                        {s === undefined ? (
                          d.run_status === "succeeded" ? <span className="muted" aria-label="loading">…</span> : <span className="muted">–</span>
                        ) : s === "error" ? (
                          <span className="muted">?</span>
                        ) : s.open_blockers > 0 ? (
                          <Link className="count-bad" to={`/runs/${d.run_id}?issues=blocker`}>
                            {s.open_blockers}
                          </Link>
                        ) : (
                          <span className="count-ok">0</span>
                        )}
                      </td>
                      <td className="num">
                        {s && s !== "error" ? s.open_warnings > 0 ? <Link to={`/runs/${d.run_id}?issues=warning`}>{s.open_warnings}</Link> : 0 : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {shown.pages > 1 && (
          <nav className="doc-pager" aria-label="Pages of documents">
            <button type="button" className="btn" disabled={shown.page <= 1} onClick={() => setPage(shown.page - 1)}>
              Previous
            </button>
            <span className="muted small">
              Page {shown.page} of {shown.pages}
            </span>
            <button type="button" className="btn" disabled={shown.page >= shown.pages} onClick={() => setPage(shown.page + 1)}>
              Next
            </button>
          </nav>
        )}
      </section>}
    </div>
  );
}
