import { useEffect, useState, type ReactNode } from "react";
import { getActor, onActorChange, setActor } from "../lib/actor";
import { formatDuration } from "../lib/format";
import { Link, navigate, useLocation } from "../lib/router";
import { endActiveSession } from "../lib/session";
import { flash, useFlash, useSession } from "../lib/store";
import { useTimer } from "../lib/timer";
import { InlineMessage } from "./States";

function ActorField() {
  const [name, setName] = useState(getActor());
  const [draft, setDraft] = useState(name === "local-user" ? "" : name);
  useEffect(() => onActorChange(setName), []);
  return (
    <form
      className="actor-field"
      onSubmit={(e) => {
        e.preventDefault();
        setActor(draft);
        (document.activeElement as HTMLElement | null)?.blur();
      }}
    >
      <label htmlFor="actor-input">Reviewer</label>
      <input
        id="actor-input"
        type="text"
        value={draft}
        placeholder="your name"
        maxLength={60}
        autoComplete="name"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => setActor(draft)}
        aria-describedby="actor-hint"
      />
      <span id="actor-hint" className="sr-only">
        Recorded in the audit log with every action. Currently {name}.
      </span>
    </form>
  );
}

function SessionBanner() {
  const s = useSession();
  const t = useTimer();
  const [ending, setEnding] = useState(false);
  if (!s) return null;
  const where = s.mode === "assisted" ? (s.runId ? `/runs/${s.runId}` : "/") : `/sessions/${s.id}/baseline`;
  return (
    <div className="session-banner" role="region" aria-label="Timed work session">
      <span className={`session-dot ${t.active ? "is-active" : ""}`} aria-hidden="true" />
      <span>
        <strong>Timing</strong> {s.mode === "assisted" ? "assisted review" : "by-hand baseline"} of{" "}
        <Link to={where}>{s.filename}</Link>
      </span>
      <span className="session-time num" aria-live="off">
        {formatDuration(s.activeSeconds + t.pending)} active
      </span>
      <span className="muted small">
        {t.counting ? (t.active ? "counting" : "paused: no activity in the last minute or tab hidden") : "paused: open the document to count time"}
      </span>
      {s.mode === "assisted" && (
        <button
          type="button"
          className="btn btn-small"
          disabled={ending}
          onClick={async () => {
            setEnding(true);
            await endActiveSession();
            setEnding(false);
          }}
        >
          {ending ? "Ending…" : "End session"}
        </button>
      )}
      {s.mode === "baseline" && <Link to={where} className="btn btn-small">Go to the form</Link>}
    </div>
  );
}

function FlashArea() {
  const f = useFlash();
  const loc = useLocation();
  const [shownAt, setShownAt] = useState(loc.path);
  useEffect(() => {
    if (f) setShownAt(loc.path);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f]);
  // Clear the flash once the person has moved on to a different screen.
  useEffect(() => {
    if (f && loc.path !== shownAt) flash(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc.path]);
  if (!f) return null;
  return (
    <div className="flash-area">
      <InlineMessage kind={f.kind} onDismiss={() => flash(null)}>
        {f.text}
      </InlineMessage>
    </div>
  );
}

export function Layout({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const loc = useLocation();
  const nav = [
    { to: "/", label: "Statements", active: loc.path === "/" || loc.path.startsWith("/runs") },
    { to: "/recon", label: "Reconciliation", active: loc.path.startsWith("/recon") },
    { to: "/invoices", label: "Invoices", active: loc.path.startsWith("/invoices") },
    { to: "/data-quality", label: "Data quality", active: loc.path.startsWith("/data-quality") },
    { to: "/spreadsheets", label: "Spreadsheets", active: loc.path.startsWith("/spreadsheets") },
    { to: "/roi", label: "ROI", active: loc.path.startsWith("/roi") || loc.path.startsWith("/sessions") },
    { to: "/evaluation", label: "Evaluation", active: loc.path.startsWith("/evaluation") },
  ];
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate("/");
          }}
        >
          <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true">
            <path d="M2.5 8.2 L6 11.5 L13.5 3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M2.5 14.2 H13.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          <span>Finance Operations</span>
        </a>
        <nav aria-label="Main">
          <ul>
            {nav.map((n) => (
              <li key={n.to}>
                <Link to={n.to} aria-current={n.active ? "page" : undefined} className={n.active ? "is-current" : ""}>
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <ActorField />
      </header>
      <SessionBanner />
      <FlashArea />
      <main id="main" className={wide ? "main main-wide" : "main"} tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
