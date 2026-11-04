import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { authState, can, onAuthChange, signOut } from "../lib/auth";
import { formatDuration } from "../lib/format";
import { NAV, breadcrumbs, findPage, normalPath, type IconName, type NavItem } from "../lib/nav";
import { Link, navigate, useLocation } from "../lib/router";
import { endActiveSession } from "../lib/session";
import { flash, useFlash, useSession } from "../lib/store";
import { useTimer } from "../lib/timer";
import { useSimulated } from "../lib/simulated";
import { InlineMessage } from "./States";

function UserBadge() {
  const [me, setMe] = useState(authState().me);
  useEffect(() => onAuthChange((st) => setMe(st.me)), []);
  if (!me) return null;
  return (
    <div className="user-badge">
      {!me.verified && (
        <span className="dev-auth" title="Development sign-in: identities are not verified. Not for real data or approvals.">
          Development sign-in
        </span>
      )}
      <span className="user-name">
        <strong>{me.name}</strong> <span className="muted small">{me.roles.join(", ") || "no role"}</span>
      </span>
      <button type="button" className="btn btn-small btn-quiet" onClick={() => void signOut()}>
        Sign out
      </button>
    </div>
  );
}

function SessionBanner() {
  const s = useSession();
  const t = useTimer();
  const [ending, setEnding] = useState(false);
  if (!s || !can("roi")) return null;
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

const ICON_PATHS: Record<IconName, string> = {
  home: "M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4.5h-5V17H4a1 1 0 0 1-1-1z",
  statement: "M5 3h7l3 3v11H5zM12 3v3h3M7.5 9.5h5M7.5 12.5h5M7.5 15h3",
  match: "M4 6h8m0 0-2.5-2.5M12 6l-2.5 2.5M16 14H8m0 0 2.5-2.5M8 14l2.5 2.5",
  invoice: "M5 3h10v14l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3zM7.5 7h5M7.5 10h5M7.5 13h3",
  shield: "M10 3 4.5 5v4.5c0 3.5 2.4 6.2 5.5 7.5 3.1-1.3 5.5-4 5.5-7.5V5zM7.5 10l1.8 1.8L12.8 8.3",
  grid: "M3.5 4h13v12h-13zM3.5 8h13M3.5 12h13M8 4v12M12.5 4v12",
  clock: "M10 3.5a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM10 6.5V10l2.5 1.5",
  target: "M10 3.5a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM10 7a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM10 9.6a.4.4 0 1 1 0 .8.4.4 0 0 1 0-.8z",
  wrench: "M15.7 5.2a3.8 3.8 0 0 1-5 4.7l-5 5a1.4 1.4 0 0 1-2-2l5-5a3.8 3.8 0 0 1 4.7-5l-2.2 2.2.6 1.7 1.7.6z",
  menu: "M3.5 5.5h13M3.5 10h13M3.5 14.5h13",
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg viewBox="0 0 20 20" width={size} height={size} aria-hidden="true" className="icon">
      <path d={ICON_PATHS[name]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Which drop-downs a person opened or closed: each page draws its own Layout, so this outlives one page.
const toggled = new Map<string, boolean>();
let sidebarScroll = 0;

function NavSection({ item, path }: { item: NavItem; path: string }) {
  const [, redraw] = useState(0);
  const here = findPage(path);
  const active = here?.item === item;
  const children = (item.children ?? []).filter((c) => !c.needs || can(c.needs));
  const open = toggled.get(item.label) ?? active;
  const hasMenu = children.length > 0;
  return (
    <li>
      <div className="nav-row">
        <Link
          to={item.to}
          aria-current={active && !hasMenu ? "page" : undefined}
          className={active ? "is-current" : ""}
          onClick={() => toggled.delete(item.label)}
        >
          <Icon name={item.icon} />
          <span className="nav-text">
            <span className="nav-label">{item.label}</span>
            <span className="nav-hint">{item.hint}</span>
          </span>
        </Link>
        {hasMenu && (
          <button
            type="button"
            className={`nav-caret ${open ? "is-open" : ""}`}
            aria-expanded={open}
            aria-label={`${open ? "Hide" : "Show"} ${item.label} pages`}
            onClick={() => {
              toggled.set(item.label, !open);
              redraw((n) => n + 1);
            }}
          >
            <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
              <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>
      {hasMenu && open && (
        <ul className="nav-sub">
          {children.map((c) => {
            const current = here?.child?.to === c.to;
            return (
              <li key={c.to}>
                <Link to={c.to} aria-current={current ? "page" : undefined} className={current ? "is-sub-current" : ""}>
                  {c.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}

function Breadcrumbs({ path }: { path: string }) {
  const crumbs = breadcrumbs(path);
  if (crumbs.length === 0) return null;
  return (
    <nav className="breadcrumbs small" aria-label="You are here">
      {crumbs.map((c, i) => (
        <span key={c.to}>
          {i > 0 && <span className="muted" aria-hidden="true"> / </span>}
          {i < crumbs.length - 1 ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function Layout({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [loc.path]);
  const path = normalPath(loc.path);
  const side = useRef<HTMLElement>(null);
  // The menu stays where it was when a click opens another page.
  useLayoutEffect(() => {
    if (side.current) side.current.scrollTop = sidebarScroll;
  }, []);
  return (
    <div className={`app ${open ? "nav-open" : ""}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar" aria-label="Sections" ref={side} onScroll={(e) => (sidebarScroll = e.currentTarget.scrollTop)}>
        <div className="sidebar-head">
          <a
            className="brand"
            href="/"
            onClick={(e) => {
              e.preventDefault();
              navigate("/");
            }}
          >
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 16 16" width="16" height="16">
                <path d="M2.5 8.2 L6 11.5 L13.5 3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </span>
            <span className="brand-text">
              Finance Operations
              <small>Checked automation</small>
            </span>
          </a>
          <button type="button" className="nav-toggle" aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>
            <Icon name="menu" />
            <span className="sr-only">Menu</span>
          </button>
        </div>
        <nav id="main-nav" aria-label="Main">
          {NAV.map((g) => (
            <div className="nav-group" key={g.group || "home"}>
              {g.group && <p className="nav-group-title">{g.group}</p>}
              <ul>
                {g.items.filter((n) => !n.needs || can(n.needs)).map((n) => (
                  <NavSection key={n.to} item={n} path={path} />
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <p className="sidebar-foot">Nothing is approved, paid or released without a named person.</p>
      </aside>
      <div className="workarea">
        <header className="topbar">
          <span className="topbar-note">Local prototype · public and synthetic data only</span>
          <UserBadge />
        </header>
        <SimulatedBanner />
        <SessionBanner />
        <FlashArea />
        <main id="main" className={wide ? "main main-wide" : "main"} tabIndex={-1}>
          <Breadcrumbs path={path} />
          {children}
        </main>
      </div>
    </div>
  );
}

/** A workspace of made-up work says so on every page: its time and money figures are not measurements (D69). */
function SimulatedBanner() {
  if (!useSimulated()) return null;
  return (
    <p className="sim-banner" role="note">
      <strong>Simulated workspace.</strong> The completed work is made up: demo analysts on fictional companies, so no time, cost or accuracy figure from it is a measurement. Filings marked Real SEC filing are real and have not been worked on.
    </p>
  );
}
