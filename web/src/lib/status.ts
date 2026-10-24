import type { CheckStatus, MapMethod, ReviewKind, Severity, ValueStatus } from "../api/types";

export interface StatusMeta {
  label: string;
  short: string;
  description: string;
}

export const VALUE_STATUS: Record<ValueStatus, StatusMeta> = {
  extracted: {
    label: "Extracted",
    short: "read",
    description: "Read from one printed cell; only the declared unit (e.g. millions) was applied.",
  },
  normalized: {
    label: "Normalized",
    short: "adjusted",
    description: "Read from the source, then transformed: rows summed or the sign flipped to the template's convention.",
  },
  calculated: {
    label: "Calculated",
    short: "calc",
    description: "Not printed. Computed from other spread values by a profile formula.",
  },
  ai_mapped: {
    label: "AI-mapped",
    short: "AI",
    description: "Printed in the source, but a language model chose which template line it belongs to.",
  },
  human: {
    label: "Reviewer",
    short: "human",
    description: "Set or corrected by a reviewer, with a recorded reason.",
  },
  assumed: {
    label: "Assumed",
    short: "assumed",
    description: "Depends on something the system had to assume (for example a missing unit statement or period end).",
  },
  missing: {
    label: "Missing",
    short: "missing",
    description: "Not found in the source.",
  },
};

export const VALUE_STATUS_ORDER: ValueStatus[] = [
  "extracted",
  "normalized",
  "calculated",
  "ai_mapped",
  "human",
  "assumed",
  "missing",
];

export const SEVERITY: Record<Severity, { label: string; plural: string; description: string }> = {
  blocker: { label: "Blocker", plural: "Blockers", description: "Must be resolved before the spread can be approved." },
  warning: { label: "Warning", plural: "Warnings", description: "Should be looked at; does not stop approval." },
  info: { label: "Info", plural: "Notes", description: "For information; nothing is wrong." },
};

export const SEVERITY_ORDER: Severity[] = ["blocker", "warning", "info"];

export const REVIEW_KIND: Record<ReviewKind, string> = {
  unmapped_row: "Row not placed",
  low_confidence: "Low-confidence mapping",
  failed_check: "Check failed",
  footing: "Total does not foot",
  assumed_scale: "Unit assumed",
  assumed_period: "Period assumed",
  missing_statement: "Statement missing",
  conflict: "Conflicting rows",
  suspicious: "Looks suspicious",
  unreadable: "Unreadable",
};

export const CHECK_STATUS: Record<CheckStatus, { label: string; description: string }> = {
  pass: { label: "Pass", description: "Ticked and footed: both sides agree within the allowed rounding." },
  fail: { label: "Fail", description: "The two sides differ by more than the allowed rounding." },
  skipped: { label: "Skipped", description: "Not tested: an input was missing or one side was calculated from the other." },
};

export const MAP_METHOD: Record<MapMethod, string> = {
  alias: "alias",
  memory: "reviewer memory",
  fuzzy: "close spelling",
  structure: "position",
  model: "AI model",
  human: "reviewer",
  none: "none",
};

export const STEP_KIND: Record<string, string> = {
  read: "Read",
  scale: "Scale",
  sum: "Sum",
  sign: "Sign",
  map: "Map",
  calculate: "Calculate",
  correct: "Correct",
};

export const STATEMENT_TITLE: Record<string, string> = {
  income_statement: "Income statement",
  balance_sheet: "Balance sheet",
  cash_flow: "Cash flow statement",
};

export const STATEMENT_ORDER = ["income_statement", "balance_sheet", "cash_flow"] as const;
