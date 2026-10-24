// Active-time measurement for timed work sessions (ROI).
//
// A second counts as active only while the tab is visible AND the person moved the mouse, typed,
// scrolled or touched in the last 60 seconds. Active seconds are sent as a heartbeat every 15
// seconds, and only while those same conditions hold; the server caps each heartbeat at 30 s.
// Leaving a tab open, or walking away, therefore does not inflate a session.

import { useEffect, useSyncExternalStore } from "react";
import { ApiError, api } from "../api/client";
import { flash, getSession, setSession, updateSession } from "./store";

export const IDLE_AFTER_MS = 60_000;
export const HEARTBEAT_EVERY_MS = 15_000;
const MAX_PER_HEARTBEAT = 30;

interface TimerState {
  pending: number; // active seconds not yet acknowledged by the server
  counting: boolean; // a page that counts is open
  active: boolean; // visible and recently used right now
}

let state: TimerState = { pending: 0, counting: false, active: false };
const subs = new Set<() => void>();
function set(patch: Partial<TimerState>) {
  state = { ...state, ...patch };
  subs.forEach((s) => s());
}
export const useTimer = () =>
  useSyncExternalStore(
    (fn) => {
      subs.add(fn);
      return () => {
        subs.delete(fn);
      };
    },
    () => state,
  );

/** Pure rule, exported for tests: does this moment count as active time? */
export function isActive(visible: boolean, lastInteraction: number, now: number): boolean {
  return visible && now - lastInteraction <= IDLE_AFTER_MS;
}

let sending = false;
async function send(seconds: number): Promise<void> {
  const s = getSession();
  if (!s || seconds <= 0 || sending) return;
  sending = true;
  const amount = Math.min(MAX_PER_HEARTBEAT, Math.round(seconds * 10) / 10);
  try {
    const res = await api.heartbeat(s.id, amount);
    set({ pending: Math.max(0, state.pending - amount) });
    updateSession({ activeSeconds: res.active_seconds });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 409 || e.status === 404)) {
      setSession(null);
      set({ pending: 0 });
      flash({ kind: "info", text: "The timed session had already ended, so timing stopped." });
    }
    // offline: keep the seconds and try again with the next heartbeat
  } finally {
    sending = false;
  }
}

/** Send every remaining active second (before ending a session). */
export async function flushTimer(): Promise<void> {
  for (let i = 0; i < 20 && state.pending > 0.05 && getSession(); i++) {
    const before = state.pending;
    await send(state.pending);
    if (state.pending >= before) break; // failed: stop trying
  }
}

/** Count active time while the calling page is mounted and `enabled` is true. */
export function useCountActiveTime(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    let last = Date.now();
    let prevTick = Date.now();
    const touch = () => {
      last = Date.now();
    };
    const events = ["mousemove", "mousedown", "keydown", "wheel", "touchstart", "pointerdown"] as const;
    events.forEach((ev) => window.addEventListener(ev, touch, { passive: true }));
    window.addEventListener("scroll", touch, { passive: true, capture: true });
    set({ counting: true });

    const tick = window.setInterval(() => {
      const now = Date.now();
      const elapsed = Math.min(2, (now - prevTick) / 1000); // timers throttled in the background never add more than 2 s
      prevTick = now;
      const active = isActive(document.visibilityState === "visible", last, now);
      if (active) set({ pending: state.pending + elapsed, active });
      else if (state.active) set({ active: false });
    }, 1000);

    const beat = window.setInterval(() => {
      if (isActive(document.visibilityState === "visible", last, Date.now()) && state.pending > 0) {
        void send(state.pending);
      }
    }, HEARTBEAT_EVERY_MS);

    return () => {
      events.forEach((ev) => window.removeEventListener(ev, touch));
      window.removeEventListener("scroll", touch, { capture: true });
      window.clearInterval(tick);
      window.clearInterval(beat);
      set({ counting: false, active: false });
      // Send what was counted on this page now rather than losing it.
      if (state.pending > 0) void send(state.pending);
    };
  }, [enabled]);
}

export function resetTimer(): void {
  set({ pending: 0, active: false });
}
