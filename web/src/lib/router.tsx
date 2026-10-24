// A tiny history-API router: the app has five screens, which does not justify a routing library.
// FastAPI serves index.html for every non-API path, so deep links work after a reload.

import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from "react";

type Listener = () => void;
const listeners = new Set<Listener>();

export interface Location {
  path: string;
  query: URLSearchParams;
}

function current(): Location {
  return { path: window.location.pathname, query: new URLSearchParams(window.location.search) };
}

export function navigate(to: string, opts: { replace?: boolean } = {}): void {
  if (to === window.location.pathname + window.location.search) return;
  if (opts.replace) window.history.replaceState(null, "", to);
  else window.history.pushState(null, "", to);
  listeners.forEach((l) => l());
}

/** Change query parameters without adding a history entry for each small change. */
export function setQuery(updates: Record<string, string | null>, opts: { push?: boolean } = {}): void {
  const q = new URLSearchParams(window.location.search);
  for (const [k, v] of Object.entries(updates)) {
    if (v === null || v === "") q.delete(k);
    else q.set(k, v);
  }
  const s = q.toString();
  navigate(window.location.pathname + (s ? `?${s}` : ""), { replace: !opts.push });
}

export function useLocation(): Location {
  const [loc, setLoc] = useState<Location>(current);
  useEffect(() => {
    const update = () => setLoc(current());
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return loc;
}

export function Link({
  to,
  children,
  ...rest
}: { to: string; children: ReactNode } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    rest.onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(to);
    window.scrollTo(0, 0);
  };
  return (
    <a href={to} {...rest} onClick={onClick}>
      {children}
    </a>
  );
}

export function match(pattern: RegExp, path: string): string[] | null {
  const m = pattern.exec(path);
  return m ? m.slice(1) : null;
}
