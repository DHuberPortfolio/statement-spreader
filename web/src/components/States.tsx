import type { ReactNode } from "react";
import type { ApiError } from "../api/client";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorState({ error, onRetry, title }: { error: ApiError | Error; onRetry?: () => void; title?: string }) {
  const offline = "offline" in error && (error as ApiError).offline;
  return (
    <div className="state state-error" role="alert">
      <h2>{title ?? (offline ? "The spreading service is not reachable" : "Something went wrong")}</h2>
      <p>{error.message}</p>
      {offline && (
        <p className="muted small">
          Start it from the repository root:{" "}
          <code>.venv/Scripts/python -m uvicorn spreader.api:app --port 8765</code>
        </p>
      )}
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <h2>{title}</h2>
      {children}
    </div>
  );
}

/** A message shown inline after an action, e.g. the server refusing approval. */
export function InlineMessage({
  kind,
  children,
  onDismiss,
}: {
  kind: "error" | "success" | "info";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div className={`inline-msg inline-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <div className="inline-msg-body">{children}</div>
      {onDismiss && (
        <button type="button" className="btn-icon" onClick={onDismiss} aria-label="Dismiss message">
          ×
        </button>
      )}
    </div>
  );
}
