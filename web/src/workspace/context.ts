import { createContext, useContext } from "react";
import type { RunPayload, StatementKey } from "../api/types";
import type { WorkspaceModel } from "./model";

export type WorkspaceTab = "spread" | "source" | "checks" | "ratios" | "audit";

export interface WorkspaceApi {
  model: WorkspaceModel;
  runId: number;
  unit: number;
  setUnit: (u: number) => void;
  /** POST an action; returns the new payload or throws ApiError with the server's message */
  act: (action: Record<string, unknown>) => Promise<RunPayload>;
  selectCell: (key: string | null, opts?: { focusEvidence?: boolean }) => void;
  selectedCell: string | null;
  gotoTab: (tab: WorkspaceTab) => void;
  gotoSource: (statement: StatementKey, rows: number[]) => void;
}

export const WorkspaceContext = createContext<WorkspaceApi | null>(null);

export function useWorkspace(): WorkspaceApi {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace outside the run workspace");
  return ctx;
}
