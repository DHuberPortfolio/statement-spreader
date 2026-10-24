// Shapes of the JSON the FastAPI backend returns (src/spreader/api.py, roi_api.py, contracts.py).
// Decimals arrive as strings ("45754000000", "-1.5"), never as JSON numbers.

export type DecimalString = string;

export type StatementKey = "income_statement" | "balance_sheet" | "cash_flow";

export type ValueStatus =
  | "extracted"
  | "normalized"
  | "calculated"
  | "ai_mapped"
  | "human"
  | "assumed"
  | "missing";

export type Severity = "blocker" | "warning" | "info";
export type CheckStatus = "pass" | "fail" | "skipped";

export type ReviewKind =
  | "unmapped_row"
  | "low_confidence"
  | "failed_check"
  | "footing"
  | "assumed_scale"
  | "assumed_period"
  | "missing_statement"
  | "conflict"
  | "suspicious"
  | "unreadable";

export interface SourceRef {
  doc_id: string;
  format: "html" | "pdf" | "xlsx";
  table: number;
  row: number;
  page: number | null;
  bbox: [number, number, number, number] | null;
  sheet: string | null;
  cell: string | null;
  xpath: string | null;
  text: string;
}

export interface Period {
  key: string;
  end: string;
  months: number | null;
  label: string;
  assumed: string[];
  notes: string[];
}

export interface Scale {
  multiplier: number;
  evidence: string;
  assumed: boolean;
}

export interface ProvenanceStep {
  kind: string; // read | scale | sign | sum | map | calculate | correct
  detail: string;
}

export interface SpreadValue {
  line: string;
  period: string;
  value: DecimalString | null;
  status: ValueStatus;
  confidence: number;
  source_rows: number[];
  refs: SourceRef[];
  steps: ProvenanceStep[];
  flags: string[];
}

export interface CheckResult {
  id: string;
  title: string;
  period: string;
  status: CheckStatus;
  lhs: DecimalString | null;
  rhs: DecimalString | null;
  difference: DecimalString | null;
  tolerance: DecimalString | null;
  lines: string[];
  explanation: string;
}

export interface ReviewItem {
  id: string;
  kind: ReviewKind;
  severity: Severity;
  statement: StatementKey | null;
  message: string;
  lines: string[];
  rows: number[];
  periods: string[];
  resolved: boolean;
  resolution: string | null;
}

export interface RatioResult {
  id: string;
  label: string;
  period: string;
  value: DecimalString | null;
  format: "percent" | "times" | "days" | "money" | string;
  formula: string;
  inputs: Record<string, DecimalString | null>;
  reason: string | null;
  note: string;
}

export type MapMethod = "alias" | "memory" | "fuzzy" | "structure" | "model" | "human" | "none";

export interface RowMapping {
  row_index: number;
  canonical: string | null;
  method: MapMethod;
  confidence: number;
  excluded: boolean;
  candidates: [string, number][];
  reason: string;
}

export interface StatementTable {
  doc_id: string;
  table_index: number;
  statement: StatementKey;
  title: string;
  periods: Period[];
  scale: Scale;
  share_scale: Scale | null;
  detection_score: number;
  warnings: string[];
  // rows are large; the source endpoint is used for them instead
}

export interface StatementResult {
  table: StatementTable;
  mappings: RowMapping[];
}

export interface Spread {
  doc_id: string;
  profile_id: string;
  profile_version: string;
  statements: Partial<Record<StatementKey, StatementResult>>;
  periods: Period[];
  values: SpreadValue[];
  checks: CheckResult[];
  ratios: RatioResult[];
  review: ReviewItem[];
  warnings: string[];
}

export interface RunState {
  approved?: { by: string; at: string };
  overrides?: Record<string, { value: string; reason: string; actor: string; at: string; previous: string | null }>;
  resolved?: Record<string, string>;
}

export interface Run {
  id: number;
  document_id: string;
  idempotency_key: string;
  profile_id: string;
  profile_version: string;
  engine_version: string;
  memory_version: number;
  model: string;
  status: "running" | "succeeded" | "failed";
  error: string | null;
  started_at: string;
  finished_at: string | null;
  timings: Record<string, number>;
  state: RunState;
  parent_run: number | null;
}

export interface DocumentRow {
  id: string;
  filename: string;
  format: "html" | "pdf" | "xlsx";
  size: number;
  uploaded_at: string;
  label: string | null;
  run_id?: number | null;
  run_status?: Run["status"] | null;
  run_at?: string | null;
  approved?: boolean;
}

export interface LineInfo {
  label: string;
  kind: string;
  critical: boolean;
  statement: StatementKey;
}

export interface RunSummary {
  values: number;
  auto_accepted: number;
  open_blockers: number;
  open_warnings: number;
  checks_passed: number;
  checks_failed: number;
  checks_skipped: number;
}

export interface RunPayload {
  run: Run;
  spread: Spread | null;
  lines?: Record<string, LineInfo>;
  summary?: RunSummary;
  document: DocumentRow | null;
}

export interface ProfileLine {
  id: string;
  label: string;
  kind: string;
  critical: boolean;
}

export interface Profile {
  id: string;
  version: string;
  hash: string;
  title: string;
  statements: Partial<Record<StatementKey, { title: string; lines: ProfileLine[] }>>;
  checks: { id: string; statement: string; title: string; lhs: string; rhs: string; severity: Severity; note: string }[];
  ratios: { id: string; label: string; expr: string; format: string; note: string }[];
  derived: { line: string; expr: string }[];
}

export interface SourceCell {
  raw: string;
  displayed: DecimalString | null;
  ref: SourceRef | null;
  note: string | null;
}

export interface SourceRow {
  index: number;
  label: string;
  section: string;
  indent: number;
  bold: boolean;
  role: "header" | "detail" | "total";
  unit: "money" | "shares" | "per_share" | "percent";
  children: number[];
  values: Record<string, SourceCell>;
  mapping: RowMapping | null;
  header: boolean;
}

export interface SourceTable {
  statement: StatementKey;
  title: string;
  table_index: number;
  scale: Scale;
  share_scale: Scale | null;
  periods: Period[];
  rows: SourceRow[];
  warnings: string[];
}

export interface AuditEvent {
  id: number;
  run_id: number | null;
  document_id: string | null;
  at: string;
  actor: string;
  kind: string;
  payload: Record<string, unknown>;
}

// ---- ROI ----

export type RoiLabel = "observed" | "estimated" | "hypothetical" | "verified" | "assumption" | "default";

export interface RoiNumber {
  value: number | null;
  label: RoiLabel;
  unit: string;
  explanation: string;
  low: number | null;
  high: number | null;
  n: number | null;
}

export type MoneyBlock = {
  capacity_hours: number | null;
  capacity_value: number | null;
  cash_savings: number | null;
  net_monthly_cash: number | null;
  net_monthly_capacity: number | null;
  first_year_roi_cash: number | null;
  payback_months_cash: number | null;
};

export interface RoiReport {
  numbers: Record<string, RoiNumber>;
  scenarios: Partial<Record<"low" | "expected" | "high", MoneyBlock>>;
  sensitivity: { assumption: string; low: number; high: number }[];
  warnings: string[];
  sessions: { baseline: number; assisted: number };
}

export interface WorkSession {
  id: number;
  document_id: string;
  run_id: number | null;
  mode: "baseline" | "assisted";
  actor: string;
  started_at: string;
  ended_at: string | null;
  active_seconds: number;
  corrections: number | null;
  values_entered: number | null;
  errors_found: number | null;
  values_checked: number | null;
  note: string | null;
}

// ---- Evaluation ----

export interface Rate {
  n: number;
  d: number;
  rate: number | null;
  low: number | null;
  high: number | null;
}

export interface EvalReport {
  name: string;
  documents: number;
  crashed: number;
  profile: string;
  rates: Record<string, Rate>;
  cells: Record<string, { ok: number; total: number }> | null;
  error_kinds: Record<string, number> | null;
  buckets: Record<string, number> | null;
  seconds: number | null;
  file: string;
}
