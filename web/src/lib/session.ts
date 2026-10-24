// Ending a timed work session: send the last active seconds, then close it on the server.

import { api, ApiError } from "../api/client";
import { formatDuration } from "./format";
import { flash, getSession, setSession } from "./store";
import { flushTimer, resetTimer } from "./timer";

export async function endActiveSession(extra: Record<string, unknown> = {}): Promise<void> {
  const s = getSession();
  if (!s) return;
  await flushTimer();
  try {
    const res = await api.endSession(s.id, { corrections: s.corrections, ...extra });
    setSession(null);
    resetTimer();
    const checked =
      res.values_checked != null ? ` ${res.values_checked} keyed values compared with the spread, ${res.errors_found ?? 0} disagreed.` : "";
    flash({
      kind: "success",
      text: `Timed ${s.mode} session #${s.id} ended: ${formatDuration(res.active_seconds)} active.${checked}`,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      setSession(null);
      resetTimer();
    }
    flash({ kind: "error", text: `Could not end the session: ${e instanceof Error ? e.message : String(e)}` });
  }
}

