// Who is signed in. The server decides (a session cookie it issued, DECISIONS D43); the browser only asks.
// A 401 from any request means the session ended: the app goes back to the sign-in screen.

export type Me = {
  actor: string;
  name: string;
  roles: string[];
  permissions: string[];
  mode: "development" | "oidc";
  organization: string;
  verified: boolean;
};

export type AuthSetup = {
  mode: "development" | "oidc";
  organization: string;
  warning?: string;
  dev_users?: { username: string; name: string; roles: string[] }[];
};

type State = { me: Me | null; checked: boolean };
let state: State = { me: null, checked: false };
const listeners = new Set<(s: State) => void>();

function set(next: State): void {
  state = next;
  listeners.forEach((fn) => fn(state));
}

export function authState(): State {
  return state;
}

export function onAuthChange(fn: (s: State) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function can(permission: string): boolean {
  return !!state.me?.permissions.includes(permission);
}

/** Called by the request wrapper when the server answers 401. */
export function sessionEnded(): void {
  if (state.me || !state.checked) set({ me: null, checked: true });
}

export async function loadMe(): Promise<Me | null> {
  try {
    const res = await fetch("/api/auth/me", { credentials: "same-origin" });
    const me = res.ok ? ((await res.json()) as Me) : null;
    set({ me, checked: true });
    return me;
  } catch {
    set({ me: null, checked: true });
    return null;
  }
}

export async function loadSetup(): Promise<AuthSetup> {
  const res = await fetch("/api/auth/config", { credentials: "same-origin" });
  if (!res.ok) throw new Error(`Sign-in is not available (${res.status})`);
  return (await res.json()) as AuthSetup;
}

export async function devSignIn(username: string): Promise<void> {
  const res = await fetch("/api/auth/dev-login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!res.ok) throw new Error(`Sign-in refused (${res.status})`);
  await loadMe();
}

export async function signOut(): Promise<void> {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }).catch(() => undefined);
  set({ me: null, checked: true });
}
