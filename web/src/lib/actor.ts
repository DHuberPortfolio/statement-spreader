// The signed-in user's name as the audit log records it (lib/auth.ts holds the session).
// "local-user" means nobody is signed in: actions that need a person stay disabled.
import { authState, onAuthChange } from "./auth";

export function getActor(): string {
  return authState().me?.actor ?? "local-user";
}

export function onActorChange(fn: (name: string) => void): () => void {
  return onAuthChange((s) => fn(s.me?.actor ?? "local-user"));
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
