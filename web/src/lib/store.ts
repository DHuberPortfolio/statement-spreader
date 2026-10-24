// Small shared stores (useSyncExternalStore): a flash message that survives a navigation, the
// profile (loaded once), and the active timed work session.

import { useSyncExternalStore } from "react";
import { api } from "../api/client";
import type { Profile } from "../api/types";
import { readStored, writeStored } from "./actor";

function createStore<T>(initial: T) {
  let state = initial;
  const subs = new Set<() => void>();
  return {
    get: () => state,
    set: (next: T) => {
      state = next;
      subs.forEach((s) => s());
    },
    subscribe: (fn: () => void) => {
      subs.add(fn);
      return () => {
        subs.delete(fn);
      };
    },
  };
}

// ---- flash ----

export interface Flash {
  kind: "success" | "info" | "error";
  text: string;
}
const flashStore = createStore<Flash | null>(null);
export const flash = (f: Flash | null) => flashStore.set(f);
export const useFlash = () => useSyncExternalStore(flashStore.subscribe, flashStore.get);

// ---- profile ----

interface ProfileState {
  profile: Profile | null;
  error: Error | null;
}
const profileStore = createStore<ProfileState>({ profile: null, error: null });
let profileLoading: Promise<void> | null = null;

export function loadProfile(force = false): Promise<void> {
  if (profileLoading && !force) return profileLoading;
  profileLoading = api
    .profile()
    .then((p) => profileStore.set({ profile: p, error: null }))
    .catch((e: unknown) => {
      profileLoading = null;
      profileStore.set({ profile: null, error: e instanceof Error ? e : new Error(String(e)) });
    });
  return profileLoading;
}

export function useProfile(): ProfileState {
  const s = useSyncExternalStore(profileStore.subscribe, profileStore.get);
  if (!s.profile && !s.error && !profileLoading) void loadProfile();
  return s;
}

// ---- timed work session ----

export interface ActiveSession {
  id: number;
  mode: "baseline" | "assisted";
  documentId: string;
  runId: number | null;
  filename: string;
  startedAt: string;
  /** active seconds the server has acknowledged */
  activeSeconds: number;
  corrections: number;
}

const SESSION_KEY = "spreader.session";
const sessionStore = createStore<ActiveSession | null>(readStored<ActiveSession | null>(SESSION_KEY, null));

export function setSession(s: ActiveSession | null): void {
  writeStored(SESSION_KEY, s);
  sessionStore.set(s);
}

export function updateSession(patch: Partial<ActiveSession>): void {
  const cur = sessionStore.get();
  if (cur) setSession({ ...cur, ...patch });
}

export const getSession = () => sessionStore.get();
export const useSession = () => useSyncExternalStore(sessionStore.subscribe, sessionStore.get);
