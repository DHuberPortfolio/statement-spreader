import { useEffect, useState } from "react";
import { api } from "../api/client";

let asked: Promise<string | null> | null = null;

/** What this workspace simulates, or null for a real one. It is marked in the data, so it cannot be lost by accident (D69). */
export function useSimulated(): string | null {
  const [simulated, setSimulated] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    asked ??= api.health().then((h) => h.simulated ?? null).catch(() => null);
    void asked.then((s) => {
      if (live) setSimulated(s);
    });
    return () => {
      live = false;
    };
  }, []);
  return simulated;
}
