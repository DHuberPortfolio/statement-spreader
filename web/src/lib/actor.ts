// The reviewer's name, kept in localStorage and sent as X-Actor on every request.
// Storage can be unavailable (private windows, blocked site data), so every access is guarded.

const KEY = "spreader.actor";
const listeners = new Set<(name: string) => void>();

export function getActor(): string {
  try {
    return localStorage.getItem(KEY)?.trim() || "local-user";
  } catch {
    return "local-user";
  }
}

export function setActor(name: string): void {
  const clean = name.replace(/[^\w .@-]/g, "").trim().slice(0, 60);
  try {
    if (clean) localStorage.setItem(KEY, clean);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the name lasts for this page only */
  }
  listeners.forEach((fn) => fn(clean || "local-user"));
}

export function onActorChange(fn: (name: string) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: unknown): void {
  try {
    if (value === undefined || value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}
