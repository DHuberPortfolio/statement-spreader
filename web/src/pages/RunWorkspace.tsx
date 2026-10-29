import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api, ApiError, downloadExport } from "../api/client";
import type { RunPayload, StatementKey } from "../api/types";
import { Layout } from "../components/Layout";
import { StatusLegend, TickMark } from "../components/Markers";
import { ErrorState, InlineMessage, Loading } from "../components/States";
import { readStored, writeStored } from "../lib/actor";
import { formatDateTime } from "../lib/format";
import { Link, navigate, setQuery, useLocation } from "../lib/router";
import { flash, getSession, setSession, updateSession, useProfile, useSession } from "../lib/store";
import { useCountActiveTime } from "../lib/timer";
import { useApi } from "../lib/useApi";
import { WorkspaceContext, type WorkspaceApi, type WorkspaceTab } from "../workspace/context";
import { EvidencePanel } from "../workspace/Evidence";
import { buildModel, type WorkspaceModel } from "../workspace/model";
import { ReviewQueue } from "../workspace/ReviewQueue";
import { SourceView } from "../workspace/SourceView";
import { SpreadGrid, UnitSelector } from "../workspace/SpreadGrid";
import { AuditTab, ChecksTab, RatiosTab } from "../workspace/Tabs";

const TABS: { id: WorkspaceTab; label: string }[] = [
  { id: "spread", label: "Spread" },
  { id: "source", label: "Source" },
  { id: "checks", label: "Checks" },
  { id: "ratios", label: "Ratios" },
  { id: "audit", label: "Audit log" },
];

function RunHeader({
  model,
  onPayload,
  onReload,
}: {
  model: WorkspaceModel;
  onPayload: (p: RunPayload) => void;
  onReload: () => void;
}) {
  const { payload } = model;
  const { run, document: doc, summary } = payload;
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "error" | "success" | "info"; text: string } | null>(null);
  const session = useSession();
  const approved = run.state.approved;
  const blockers = summary?.open_blockers ?? 0;
  const [profileVersion, profileHash] = run.profile_version.split("+");
  // Is this the document's latest run? (A remap or re-run creates a newer one.)
  const docs = useApi(() => api.documents(), [run.id]);
  const latestRunId = docs.data?.find((d) => d.id === run.document_id)?.run_id ?? null;

  const doAction = async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    setMessage(null);
    try {
      await fn();
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : String(e) });
      // The server refused (e.g. someone else approved meanwhile): show its current state.
      if (e instanceof ApiError && e.status === 400) onReload();
    } finally {
      setBusy(null);
    }
  };

  const rerun = () =>
    doAction("rerun", async () => {
      const p = await api.rerun(run.document_id);
      if (p.run.id === run.id) {
        setMessage({
          kind: "info",
          text: "Nothing has changed since this run (same document, profile, reviewer memory, model and engine), so this run was kept.",
        });
      } else {
        flash({ kind: "success", text: `Re-run finished: run #${p.run.id}.` });
        navigate(`/runs/${p.run.id}`);
      }
    });

  const approve = () =>
    doAction("approve", async () => {
      onPayload(await api.act(run.id, { type: "approve", expected_version: run.version }));
      setMessage({ kind: "success", text: "Approved. The spread is locked; reopen it to make changes." });
    });

  const reopen = () =>
    doAction("reopen", async () => {
      onPayload(await api.act(run.id, { type: "reopen", expected_version: run.version }));
      setMessage({ kind: "info", text: "Reopened. Approval was withdrawn." });
    });

  const exportAs = (fmt: "xlsx" | "csv" | "json") => doAction(`export-${fmt}`, () => downloadExport(run.id, fmt));

  const startTimed = () =>
    doAction("session", async () => {
      const res = await api.startSession({ mode: "assisted", document_id: run.document_id, run_id: run.id });
      setSession({
        id: res.id,
        mode: "assisted",
        documentId: run.document_id,
        runId: run.id,
        filename: doc?.filename ?? "document",
        startedAt: new Date().toISOString(),
        activeSeconds: 0,
        corrections: 0,
      });
    });

  return (
    <header className="run-header">
      <div className="run-title-row">
        <div className="run-title">
          <p className="eyebrow">
            <Link to="/statements">Statements</Link> / run #{run.id}
            {run.parent_run && (
              <>
                {" "}
                (from <Link to={`/runs/${run.parent_run}`}>#{run.parent_run}</Link>)
              </>
            )}
          </p>
          <h1>{doc?.label || doc?.filename || "Document"}</h1>
          <p className="run-meta small muted">
            Profile <span title={`content hash ${profileHash ?? ""}`}>{run.profile_id} {profileVersion}</span> · engine {run.engine_version} · mapping model{" "}
            {run.model} · reviewer memory v{run.memory_version} · finished {formatDateTime(run.finished_at)}
          </p>
        </div>
        <div className="run-actions">
          <button type="button" className="btn" onClick={rerun} disabled={!!busy}>
            {busy === "rerun" ? "Re-running…" : "Re-run"}
          </button>
          {approved ? (
            <button type="button" className="btn" onClick={reopen} disabled={!!busy}>
              {busy === "reopen" ? "Reopening…" : "Reopen"}
            </button>
          ) : (
            <span className="approve-wrap">
              <button
                type="button"
                className="btn btn-primary"
                onClick={approve}
                disabled={!!busy || blockers > 0 || run.status !== "succeeded"}
                aria-describedby="approve-reason"
              >
                {busy === "approve" ? "Approving…" : "Approve"}
              </button>
            </span>
          )}
          <span className="export-group" role="group" aria-label="Export the spread">
            <span className="export-label small muted">Export</span>
            {(["xlsx", "csv", "json"] as const).map((f) => (
              <a
                key={f}
                className="btn btn-small"
                href={`/api/runs/${run.id}/export.${f}`}
                onClick={(e) => {
                  e.preventDefault();
                  void exportAs(f);
                }}
                aria-disabled={busy === `export-${f}`}
              >
                {busy === `export-${f}` ? "…" : f}
              </a>
            ))}
          </span>
          {!session && (
            <button type="button" className="btn btn-small btn-quiet" onClick={startTimed} disabled={!!busy} title="Measure your active review time for the ROI report">
              Time my review
            </button>
          )}
        </div>
      </div>

      <div className="run-status-row">
        {approved ? (
          <span className="stamp" role="status">
            Approved · {approved.by} · {formatDateTime(approved.at)}
          </span>
        ) : (
          <span id="approve-reason" className={blockers > 0 ? "approve-reason is-blocked" : "approve-reason"}>
            {blockers > 0
              ? `Not approved: ${blockers} blocking item${blockers === 1 ? "" : "s"} open. Resolve or correct them first.`
              : "Not approved. No blockers are open."}
          </span>
        )}
        {summary && (
          <dl className="counts">
            <div>
              <dt>Values</dt>
              <dd className="num">{summary.values}</dd>
            </div>
            <div title="Values with no open review item">
              <dt>Auto-accepted</dt>
              <dd className="num">{summary.auto_accepted}</dd>
            </div>
            <div className={summary.open_blockers ? "is-bad" : ""}>
              <dt>Blockers</dt>
              <dd className="num">{summary.open_blockers}</dd>
            </div>
            <div className={summary.open_warnings ? "is-warn" : ""}>
              <dt>Warnings</dt>
              <dd className="num">{summary.open_warnings}</dd>
            </div>
            <div className="counts-checks">
              <dt>Checks</dt>
              <dd className="num">
                <span title="passed">
                  <TickMark status="pass" /> {summary.checks_passed}
                </span>
                <span title="failed">
                  <TickMark status="fail" /> {summary.checks_failed}
                </span>
                <span title="skipped">
                  <TickMark status="skipped" /> {summary.checks_skipped}
                </span>
              </dd>
            </div>
          </dl>
        )}
      </div>
      {(payload.corrected_after_review?.length ?? 0) > 0 && (
        <InlineMessage kind="error">
          <strong>Corrected after review.</strong> A senior reviewed this approved spread and ruled{" "}
          {payload.corrected_after_review!.length === 1 ? "one line" : `${payload.corrected_after_review!.length} lines`} wrong.
          Reopen the spread to fix {payload.corrected_after_review!.length === 1 ? "it" : "them"}:
          <ul className="plain-list">
            {payload.corrected_after_review!.map((c) => (
              <li key={c.id}>
                “{c.label}”: approved as {c.approved_label}, belongs {c.correct_line === "none" ? "off the spread" : `on ${c.correct_label}`}.{" "}
                <span className="muted small">
                  “{c.note}” · {c.ruled_by}, {formatDateTime(c.ruled_at)}
                </span>
              </li>
            ))}
          </ul>
        </InlineMessage>
      )}
      {latestRunId !== null && latestRunId !== run.id && (
        <InlineMessage kind="info">
          This is not the latest run of this document: <Link to={`/runs/${latestRunId}`}>run #{latestRunId}</Link> is newer. Review and
          approve the latest run.
        </InlineMessage>
      )}
      {message && (
        <InlineMessage kind={message.kind} onDismiss={() => setMessage(null)}>
          {message.text}
        </InlineMessage>
      )}
      {model.spread.warnings.length > 0 && (
        <InlineMessage kind="info">
          <ul className="plain-list">
            {model.spread.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </InlineMessage>
      )}
    </header>
  );
}

/** The display unit, remembered per document (defaults to the largest unit the statements print in). */
function useDisplayUnit(model: WorkspaceModel | null): [number, (u: number) => void] {
  const key = `spreader.unit.${model?.spread.doc_id ?? ""}`;
  const [unit, setUnitState] = useState<number | null>(() => readStored<number | null>(key, null));
  useEffect(() => setUnitState(readStored<number | null>(key, null)), [key]);
  const setUnit = useCallback(
    (u: number) => {
      setUnitState(u);
      writeStored(key, u);
    },
    [key],
  );
  return [unit ?? model?.defaultUnit ?? 1_000_000, setUnit];
}

function TabList({ tab, model }: { tab: WorkspaceTab; model: WorkspaceModel }) {
  const failed = model.spread.checks.filter((c) => c.status === "fail").length;
  const ref = useRef<HTMLDivElement>(null);
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.id === tab);
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    if (next >= 0) {
      e.preventDefault();
      setQuery({ tab: TABS[next]!.id === "spread" ? null : TABS[next]!.id });
      requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>(`#tab-${TABS[next]!.id}`)?.focus());
    }
  };
  return (
    <div className="tabs" role="tablist" aria-label="Run views" ref={ref} onKeyDown={onKeyDown}>
      {TABS.map((t) => (
        <button
          key={t.id}
          id={`tab-${t.id}`}
          type="button"
          role="tab"
          aria-selected={tab === t.id}
          aria-controls="tabpanel"
          tabIndex={tab === t.id ? 0 : -1}
          className={tab === t.id ? "is-on" : ""}
          onClick={() => setQuery({ tab: t.id === "spread" ? null : t.id }, { push: true })}
        >
          {t.label}
          {t.id === "checks" && failed > 0 && <span className="tab-count is-bad">{failed} failed</span>}
          {t.id === "spread" && (model.payload.summary?.open_blockers ?? 0) > 0 && (
            <span className="tab-count is-bad">{model.payload.summary?.open_blockers} blockers</span>
          )}
        </button>
      ))}
    </div>
  );
}

function Workspace({
  model,
  onPayload,
  onReload,
}: {
  model: WorkspaceModel;
  onPayload: (p: RunPayload) => void;
  onReload: () => void;
}) {
  const loc = useLocation();
  const runId = model.payload.run.id;
  const tab = (loc.query.get("tab") as WorkspaceTab | null) ?? "spread";
  const selectedCell = loc.query.get("cell");
  const sourceStatement = (loc.query.get("stmt") as StatementKey | null) ?? "income_statement";
  const highlight = useMemo(
    () =>
      (loc.query.get("rows") ?? "")
        .split(",")
        .filter(Boolean)
        .map(Number)
        .filter((n) => Number.isFinite(n)),
    [loc.query],
  );
  const [unit, setUnit] = useDisplayUnit(model);
  const [side, setSide] = useState<"queue" | "evidence">(selectedCell ? "evidence" : "queue");
  const [hideEmpty, setHideEmpty] = useState<boolean>(() => readStored("spreader.hideEmpty", false));
  const sidePane = useRef<HTMLElement>(null);

  const act = useCallback(
    async (action: Record<string, unknown>) => {
      const p = await api.act(runId, action);
      if (p.run.id !== runId) {
        // remap/exclude create a new run: move to it and keep the reviewer where they were
        const s = getSession();
        if (s && s.documentId === p.run.document_id) updateSession({ runId: p.run.id });
        flash({
          kind: "success",
          text: `Mapping changed: new run #${p.run.id} (from #${runId}). Corrections and resolutions were carried over; the mapping is remembered for future documents.`,
        });
        const q = new URLSearchParams(window.location.search);
        navigate(`/runs/${p.run.id}?${q.toString()}`);
      } else {
        onPayload(p);
      }
      return p;
    },
    [runId, onPayload],
  );

  const selectCell = useCallback((key: string | null, opts: { focusEvidence?: boolean } = {}) => {
    const q = new URLSearchParams(window.location.search);
    const goingToSpread = q.get("tab") && q.get("tab") !== "spread";
    setQuery({ cell: key, tab: null }, { push: !!goingToSpread });
    if (key) {
      setSide("evidence");
      // On one-column layouts the evidence sits below the grid: bring it into view.
      if (window.matchMedia("(max-width: 1023px)").matches) setRevealTick((t) => t + 1);
      // From the review queue or a check, move focus to the evidence heading (after it renders).
      if (opts.focusEvidence) setFocusTick((t) => t + 1);
    }
  }, []);
  const [focusTick, setFocusTick] = useState(0);
  const focusConsumed = useRef(0);
  const [revealTick, setRevealTick] = useState(0);
  useEffect(() => {
    if (revealTick) sidePane.current?.scrollIntoView({ block: "start" });
  }, [revealTick]);

  const gotoSource = useCallback((statement: StatementKey, rows: number[]) => {
    setQuery({ tab: "source", stmt: statement, rows: rows.length ? rows.join(",") : null }, { push: true });
  }, []);

  const gotoTab = useCallback((t: WorkspaceTab) => setQuery({ tab: t === "spread" ? null : t }, { push: true }), []);

  const ctx: WorkspaceApi = { model, runId, unit, setUnit, act, selectCell, selectedCell, gotoTab, gotoSource };

  // Count active review time when an assisted session for this document is running.
  const session = useSession();
  useCountActiveTime(!!session && session.mode === "assisted" && session.documentId === model.spread.doc_id);

  return (
    <WorkspaceContext.Provider value={ctx}>
      <RunHeader model={model} onPayload={onPayload} onReload={onReload} />
      <TabList tab={tab} model={model} />
      <div id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="tabpanel">
        {tab === "spread" && (
          <div className="workspace-grid">
            <section className="grid-pane" aria-label="Spread">
              <div className="toolbar">
                <UnitSelector value={unit} onChange={setUnit} />
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={hideEmpty}
                    onChange={(e) => {
                      setHideEmpty(e.target.checked);
                      writeStored("spreader.hideEmpty", e.target.checked);
                    }}
                  />{" "}
                  Hide empty lines
                </label>
              </div>
              <StatusLegend />
              <SpreadGrid hideEmpty={hideEmpty} />
            </section>
            <aside className="side-pane" ref={sidePane} aria-label="Review and evidence">
              <div className="side-tabs" role="group" aria-label="Side panel">
                <button type="button" className={side === "queue" ? "is-on" : ""} aria-pressed={side === "queue"} onClick={() => setSide("queue")}>
                  Review queue <span className="tab-count">{model.spread.review.filter((i) => !i.resolved).length}</span>
                </button>
                <button
                  type="button"
                  className={side === "evidence" ? "is-on" : ""}
                  aria-pressed={side === "evidence"}
                  onClick={() => setSide("evidence")}
                  disabled={!selectedCell}
                  title={selectedCell ? undefined : "Select a value in the grid"}
                >
                  Evidence
                </button>
              </div>
              <div className="side-body">
                {side === "evidence" && selectedCell ? (
                  <EvidencePanel
                    cellKey={selectedCell}
                    onBack={() => setSide("queue")}
                    focusTick={focusTick}
                    focusConsumed={focusConsumed}
                  />
                ) : (
                  <ReviewQueue />
                )}
              </div>
            </aside>
          </div>
        )}
        {tab === "source" && <SourceView statement={sourceStatement} highlight={highlight} />}
        {tab === "checks" && <ChecksTab />}
        {tab === "ratios" && <RatiosTab />}
        {tab === "audit" && <AuditTab />}
      </div>
    </WorkspaceContext.Provider>
  );
}

export function RunWorkspace({ runId }: { runId: number }) {
  const run = useApi((signal) => api.run(runId, signal), [runId]);
  const { profile, error: profileError } = useProfile();
  const status = run.data?.run.status;

  // A run still processing: poll until it finishes.
  useEffect(() => {
    if (status !== "running") return;
    const t = window.setTimeout(run.reload, 2000);
    return () => window.clearTimeout(t);
  }, [status, run.reload, run.data]);

  const model = useMemo(() => (run.data && profile ? buildModel(run.data, profile) : null), [run.data, profile]);

  let body;
  if (run.error) {
    body = (
      <ErrorState
        error={run.error}
        onRetry={run.reload}
        title={run.error.status === 404 ? `There is no run #${runId}` : undefined}
      />
    );
  } else if (profileError) {
    body = <ErrorState error={profileError} title="The template profile could not be loaded" />;
  } else if (!run.data || !profile) {
    body = <Loading label={`Loading run #${runId}`} />;
  } else if (run.data.run.status === "running") {
    body = <Loading label={`Run #${runId} is still processing`} />;
  } else if (run.data.run.status === "failed" || !model) {
    body = <FailedRun payload={run.data} />;
  } else {
    body = <Workspace model={model} onPayload={run.setData} onReload={run.reload} />;
  }
  return <Layout wide>{body}</Layout>;
}

function FailedRun({ payload }: { payload: RunPayload }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="state state-error" role="alert">
      <p className="eyebrow">
        <Link to="/statements">Statements</Link> / run #{payload.run.id}
      </p>
      <h1>{payload.document?.filename ?? "Document"}</h1>
      <h2>This run did not produce a spread</h2>
      <p>{payload.run.error ?? "The run has no spread."}</p>
      <p className="muted small">Nothing partial was saved. A re-run starts from the stored file.</p>
      <button
        type="button"
        className="btn"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setErr(null);
          try {
            const p = await api.rerun(payload.run.document_id);
            navigate(`/runs/${p.run.id}`);
          } catch (e) {
            setErr(e instanceof ApiError ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Re-running…" : "Re-run"}
      </button>
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
    </div>
  );
}
