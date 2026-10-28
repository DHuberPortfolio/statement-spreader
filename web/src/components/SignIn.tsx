import { useEffect, useState, type ReactNode } from "react";
import { authState, devSignIn, loadMe, loadSetup, onAuthChange, type AuthSetup } from "../lib/auth";

/** Shows the app only to a signed-in user; otherwise the organisation's sign-in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [st, setSt] = useState(authState());
  useEffect(() => {
    const off = onAuthChange(setSt);
    void loadMe();
    return off;
  }, []);
  if (!st.checked) return <p className="signin-wait">Checking sign-in…</p>;
  if (!st.me) return <SignIn />;
  return <>{children}</>;
}

function SignIn() {
  const [setup, setSetup] = useState<AuthSetup | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => {
    loadSetup().then(setSetup, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  return (
    <main className="signin" id="main">
      <h1>Finance Operations</h1>
      {setup?.mode === "oidc" && (
        <>
          <p>Sign in with your organisation account ({setup.organization}).</p>
          <a className="btn btn-primary" href="/api/auth/login">
            Sign in
          </a>
        </>
      )}
      {setup?.mode === "development" && (
        <>
          <p className="dev-warning" role="note">
            {setup.warning}
          </p>
          <p>Choose a test user. Each has only its role&apos;s permissions, and approvals need a second person.</p>
          <ul className="signin-users">
            {(setup.dev_users ?? []).map((u) => (
              <li key={u.username}>
                <button
                  type="button"
                  className="btn"
                  disabled={!!busy}
                  onClick={async () => {
                    setBusy(u.username);
                    setError("");
                    try {
                      await devSignIn(u.username);
                    } catch (e) {
                      setError(e instanceof Error ? e.message : String(e));
                    } finally {
                      setBusy("");
                    }
                  }}
                >
                  {busy === u.username ? "Signing in…" : u.name}
                </button>{" "}
                <span className="muted small">{u.roles.join(", ")}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {error && (
        <p className="signin-error" role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
