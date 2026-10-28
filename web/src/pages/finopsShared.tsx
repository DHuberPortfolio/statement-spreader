// Pieces the reconciliation and invoice screens share: severity and status pills, the exception
// card with its resolve form, and the audit list.

import { useState } from "react";
import { errorText, needsName, type AuditEvent, type Check, type ExceptionItem } from "../api/finops";
import { InlineMessage } from "../components/States";
import { formatDateTime, formatExact } from "../lib/format";

export function SeverityPill({ s }: { s: string }) {
  const cls = s === "blocker" ? "pill pill-bad" : s === "warning" ? "pill pill-warn" : "pill";
  return <span className={cls}>{s}</span>;
}

const STATUS_TEXT: Record<string, string> = {
  auto_matched: "matched by rules",
  accepted: "accepted by a person",
  proposed: "proposed: needs a person",
  eligible_for_approval: "eligible for approval",
  needs_review: "needs review",
  blocked: "blocked",
  rejected: "rejected",
};

export function StatusPill({ s }: { s: string | null | undefined }) {
  if (!s) return null;
  const bad = s === "blocked" || s === "rejected";
  const warn = s === "proposed" || s === "needs_review";
  return <span className={`pill ${bad ? "pill-bad" : warn ? "pill-warn" : "pill-ok"}`}>{STATUS_TEXT[s] ?? s.replace(/_/g, " ")}</span>;
}

export function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul className="fo-checks">
      {checks.map((c, i) => (
        <li key={i} className={`fo-check fo-check-${c.status}`}>
          <span className="fo-check-mark" aria-hidden="true">{c.status === "pass" ? "✓" : c.status === "fail" ? "✗" : "–"}</span>
          <span>
            <strong>{c.name}</strong> <span className="muted">{c.detail}</span>
            <span className="sr-only"> ({c.status})</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function ExceptionCard({
  e,
  actions,
  onResolve,
  children,
}: {
  e: ExceptionItem;
  actions: string[];
  onResolve: (action: string, note: string) => Promise<void>;
  children?: React.ReactNode;
}) {
  const [action, setAction] = useState(actions[0] ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <article className={`fo-exc fo-exc-${e.severity} ${e.status === "resolved" ? "is-resolved" : ""}`} aria-label={e.title}>
      <header>
        <SeverityPill s={e.severity} /> <code className="fo-code">{e.code}</code> <strong>{e.title}</strong>
      </header>
      <p>{e.detail}</p>
      {children}
      {e.suggested_action && <p className="muted small">Suggested: {e.suggested_action}</p>}
      {e.status === "resolved" && e.resolution ? (
        <p className="small">
          Resolved by <strong>{e.resolution.actor}</strong> as <em>{e.resolution.action.replace(/_/g, " ")}</em>
          {e.resolution.note ? `: ${e.resolution.note}` : ""} ({formatDateTime(e.resolution.at)})
        </p>
      ) : (
        <form
          className="fo-resolve"
          onSubmit={async (ev) => {
            ev.preventDefault();
            setBusy(true);
            setErr(null);
            try {
              await onResolve(action, note);
            } catch (x) {
              setErr(errorText(x));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Resolution{" "}
            <select value={action} onChange={(ev) => setAction(ev.target.value)}>
              {actions.map((a) => (
                <option key={a} value={a}>
                  {a.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
          <label className="fo-note">
            Note{e.severity === "blocker" ? " (required)" : ""}{" "}
            <input value={note} onChange={(ev) => setNote(ev.target.value)} placeholder="What you checked and found" />
          </label>
          <button className="btn btn-small" type="submit" disabled={busy || needsName()} title={needsName() ? "Sign in first" : ""}>
            {busy ? "Saving…" : "Resolve"}
          </button>
          {err && <InlineMessage kind="error">{err}</InlineMessage>}
        </form>
      )}
    </article>
  );
}

export function AuditList({ events }: { events: AuditEvent[] }) {
  if (!events.length) return <p className="muted">No events yet.</p>;
  return (
    <ol className="fo-audit">
      {[...events].reverse().map((ev) => (
        <li key={ev.id}>
          <span className="muted small">{formatDateTime(ev.at)}</span> <strong>{ev.actor}</strong> {ev.kind.replace(/_/g, " ")}{" "}
          <code className="small">{JSON.stringify(ev.payload).slice(0, 220)}</code>
        </li>
      ))}
    </ol>
  );
}

export function NameReminder() {
  if (!needsName()) return null;
  return (
    <InlineMessage kind="info">
      Sign in to act: every decision is recorded under the signed-in user.
    </InlineMessage>
  );
}

/** An amount exactly as computed (decimal string), grouped, negatives in parentheses. */
export function money(v: unknown): string {
  return v == null || v === "" ? "" : formatExact(String(v));
}
