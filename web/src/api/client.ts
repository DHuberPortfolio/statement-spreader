// A small fetch wrapper. Every request carries the reviewer's name in X-Actor (the backend
// records it in the audit log). Errors come back as {"error": "..."} (reviewer actions) or
// {"detail": "..."} (FastAPI's HTTPException); both are turned into an ApiError with that message.

import { getActor } from "../lib/actor";
import type {
  AuditEvent,
  DocumentRow,
  EvalReport,
  Profile,
  RoiReport,
  RunPayload,
  SourceTable,
  StatementKey,
  WorkSession,
} from "./types";

export class ApiError extends Error {
  status: number;
  /** true when the server could not be reached at all (stopped, network down) */
  offline: boolean;
  constructor(message: string, status: number, offline = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.offline = offline;
  }
}

async function messageFrom(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  if (text) {
    try {
      const body: unknown = JSON.parse(text);
      if (body && typeof body === "object") {
        const b = body as { error?: unknown; detail?: unknown };
        if (typeof b.error === "string") return b.error;
        if (typeof b.detail === "string") return b.detail;
        if (Array.isArray(b.detail)) {
          // FastAPI validation errors: [{loc, msg, type}]
          return b.detail
            .map((d: unknown) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
            .join("; ");
        }
      }
    } catch {
      /* not JSON */
    }
    // The Vite dev proxy answers 502/504 with a plain text or HTML page when the backend is down.
    if (res.status >= 502 && res.status <= 504) return "The spreading service is not responding.";
    return text.length < 200 ? text : `Request failed (${res.status})`;
  }
  return `Request failed (${res.status} ${res.statusText})`;
}

export async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Actor", getActor());
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("Cannot reach the spreading service. Is the backend running on port 8765?", 0, true);
  }
  if (!res.ok) {
    const text = await res.clone().text().catch(() => "");
    // A gateway error, or the Vite dev proxy's empty 500 when nothing listens on the backend port.
    const offline = (res.status >= 502 && res.status <= 504) || (res.status === 500 && text.trim() === "");
    if (offline) throw new ApiError("Cannot reach the spreading service. Is the backend running on port 8765?", res.status, true);
    throw new ApiError(await messageFrom(res), res.status, false);
  }
  return res;
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await request(path, signal ? { signal } : {});
  return (await res.json()) as T;
}

export async function sendJson<T>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  const res = await request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await res.json()) as T;
}

// ---- endpoints ----

export const api = {
  health: () => getJson<{ ok: boolean; version: string; profile: string; model: string }>("/api/health"),
  profile: () => getJson<Profile>("/api/profile"),
  documents: () => getJson<DocumentRow[]>("/api/documents"),
  run: (id: number, signal?: AbortSignal) => getJson<RunPayload>(`/api/runs/${id}`, signal),
  rerun: (docId: string) => sendJson<RunPayload>(`/api/documents/${docId}/runs`, "POST", {}),
  act: (runId: number, action: Record<string, unknown>) => sendJson<RunPayload>(`/api/runs/${runId}/actions`, "POST", action),
  events: (runId: number) => getJson<AuditEvent[]>(`/api/runs/${runId}/events`),
  source: (runId: number, statement: StatementKey) => getJson<SourceTable>(`/api/runs/${runId}/source/${statement}`),
  roi: () => getJson<RoiReport>("/api/roi"),
  setAssumptions: (values: Record<string, number>) => sendJson<RoiReport>("/api/roi/assumptions", "PUT", values),
  sessions: () => getJson<WorkSession[]>("/api/sessions"),
  startSession: (body: { mode: "baseline" | "assisted"; document_id: string; run_id?: number | null }) =>
    sendJson<{ id: number }>("/api/sessions", "POST", body),
  heartbeat: (sid: number, activeSeconds: number) =>
    sendJson<{ active_seconds: number }>(`/api/sessions/${sid}/heartbeat`, "POST", { active_seconds: activeSeconds }),
  endSession: (sid: number, body: Record<string, unknown>) => sendJson<WorkSession>(`/api/sessions/${sid}/end`, "POST", body),
  evaluation: () => getJson<{ reports: EvalReport[] }>("/api/evaluation"),
};

/** Upload with progress (fetch has no upload progress, so this uses XMLHttpRequest). */
export function uploadDocument(file: File, onProgress: (fraction: number) => void): Promise<RunPayload> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents");
    xhr.setRequestHeader("X-Actor", getActor());
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError("Cannot reach the spreading service. Is the backend running?", 0, true));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* not JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        resolve(body as RunPayload);
        return;
      }
      const b = (body ?? {}) as { error?: unknown; detail?: unknown };
      const offline = (xhr.status >= 502 && xhr.status <= 504) || (xhr.status === 500 && !xhr.responseText.trim());
      if (offline) {
        reject(new ApiError("Cannot reach the spreading service. Is the backend running on port 8765?", xhr.status, true));
        return;
      }
      const msg =
        typeof b.error === "string"
          ? b.error
          : typeof b.detail === "string"
            ? b.detail
            : xhr.status >= 502 && xhr.status <= 504
              ? "The spreading service is not responding."
              : `Upload failed (${xhr.status})`;
      reject(new ApiError(msg, xhr.status, false));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

/** Download an export with the X-Actor header (so the audit log names the reviewer). */
export async function downloadExport(runId: number, fmt: "xlsx" | "csv" | "json"): Promise<void> {
  const res = await request(`/api/runs/${runId}/export.${fmt}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `spread-run${runId}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
