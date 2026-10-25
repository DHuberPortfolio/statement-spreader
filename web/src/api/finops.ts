// Types and calls for the reconciliation and invoice engines (/api/finops/...).
// Amounts arrive as decimal strings, exactly as the backend computed them.

import { getActor } from "../lib/actor";
import { ApiError, getJson, request, sendJson } from "./client";

export type Severity = "blocker" | "warning" | "info";

export interface ExceptionItem {
  id: string;
  engine: string;
  code: string;
  severity: Severity;
  title: string;
  detail: string;
  subjects: string[];
  evidence: Record<string, unknown>;
  suggested_action: string;
  status: "open" | "resolved";
  resolution: { action: string; note: string; actor: string; at: string } | null;
}

export interface Check {
  name: string;
  status: "pass" | "fail" | "skipped";
  detail: string;
}

export interface Txn {
  id: string;
  source: string;
  file: string;
  row: number;
  date: string;
  amount: string;
  currency: string;
  reference: string;
  description: string;
  counterparty: string;
}

export interface MatchGroup {
  id: string;
  left: string[];
  right: string[];
  rule: string;
  status: "auto_matched" | "accepted" | "proposed";
  decided_by: string;
  note: string;
  difference: string;
  date_gap_days: number;
  explanation: string[];
}

export interface ReconResult {
  profile_id: string;
  left_name: string;
  right_name: string;
  left_label: string;
  right_label: string;
  period_end: string | null;
  records: Record<string, Txn>;
  groups: MatchGroup[];
  exceptions: ExceptionItem[];
  totals: { currencies: Record<string, { difference: string; in_matches: string; in_proposals: string; open_items: string }> };
  checks: Check[];
}

export interface ReconRun {
  run: { id: number; workspace_id: number; status: string; is_latest: boolean; left_name: string; right_name: string; started_at: string; error: string | null };
  workspace: { id: number; name: string; profile: string };
  result: ReconResult | null;
  reused?: boolean;
}

export interface Workspace {
  id: number;
  name: string;
  profile: string;
  created_at: string;
  created_by: string;
  latest_run: number | null;
}

export interface AuditEvent {
  id: number;
  at: string;
  actor: string;
  kind: string;
  payload: Record<string, unknown>;
}

export interface FieldValue {
  value: unknown;
  origin: "extracted" | "normalized" | "computed" | "inferred" | "human";
  evidence: { page: number | null; text: string; pointer: string | null } | null;
  original: unknown;
  corrected_by: string | null;
  note: string;
}

export interface InvoiceLine {
  index: number;
  item_code: FieldValue | null;
  description: FieldValue;
  quantity: FieldValue | null;
  unit_price: FieldValue | null;
  amount: FieldValue | null;
}

export interface LineMatch {
  invoice_line: number;
  po_line: number | null;
  method: string;
  ordered: string | null;
  received: string | null;
  previously_invoiced: string | null;
  invoiced: string | null;
  po_price: string | null;
  invoice_price: string | null;
  receipts: string[];
  receipt_required: boolean;
  notes: string[];
}

export interface Outcome {
  invoice: { doc_id: string; file: string; format: string; pages: number; fields: Record<string, FieldValue>; lines: InvoiceLine[]; extraction_notes: string[] };
  vendor_id: string | null;
  po_number: string | null;
  extraction: string;
  validation: string;
  matching: string;
  eligibility: "eligible_for_approval" | "needs_review" | "blocked";
  authorization: string;
  touchless: boolean;
  exceptions: ExceptionItem[];
  line_matches: LineMatch[];
  checks: Check[];
}

export interface InvoiceDetail {
  document: { doc_id: string; name: string; uploaded_by: string; uploaded_at: string };
  outcome: Outcome | null;
  processed_at: string | null;
  rejected: boolean;
}

export interface InvoiceRow {
  doc_id: string;
  name: string;
  uploaded_by: string;
  uploaded_at: string;
  vendor: string | null;
  vendor_id: string | null;
  invoice_number: string | null;
  total: string | null;
  currency: string | null;
  eligibility: string | null;
  touchless: boolean | null;
  open: string[];
}

async function upload<T>(path: string, files: Record<string, File | null>): Promise<T> {
  const form = new FormData();
  for (const [k, f] of Object.entries(files)) if (f) form.append(k, f);
  const res = await request(path, { method: "POST", body: form });
  return (await res.json()) as T;
}

export interface RoiNumber {
  value: number | null;
  label: string;
  unit: string;
  explanation: string;
  low: number | null;
  high: number | null;
  n: number | null;
}

export interface FinopsRoi {
  engines: Record<string, Record<string, RoiNumber | string>>;
  assumptions: Record<string, RoiNumber>;
  warnings: string[];
}

// -- data-quality gate --------------------------------------------------------------------------

export interface GateIssue {
  code: string;
  severity: "reject" | "review" | "info";
  field: string | null;
  message: string;
  related: string[];
}

export interface GateRecord {
  id: string;
  source: string;
  source_label: string;
  file: string;
  row: number;
  sheet: string | null;
  original: Record<string, string>;
  canonical: Record<string, string>;
  changes: { field: string; before: string; after: string; step: string }[];
  issues: GateIssue[];
  decision: "accepted" | "review" | "rejected" | "duplicate";
  decided_by: string;
  duplicate_of: string | null;
}

export interface GateCounts {
  accepted: number;
  review: number;
  rejected: number;
  duplicate: number;
}

export interface GateInputs {
  inputs: { source: string; name: string }[];
  references: Record<string, { name: string }>;
  previous: { name: string } | null;
}

export interface GateRun {
  id: number;
  dataset_file: string;
  dataset_id: string;
  config_version: string;
  status: string;
  error: string | null;
  started_at: string;
  actor: string;
  latest: boolean;
  counts: GateCounts | null;
  inputs: GateInputs;
  result: {
    columns: string[];
    records: GateRecord[];
    carried_forward: Record<string, string>[];
    missing_from_source: string[];
    withheld: string[];
    warnings: string[];
  } | null;
  decisions: { id: number; record_id: string; kind: string; actor: string; at: string; note: string }[];
}

export interface GateRunRow {
  id: number;
  dataset_file: string;
  dataset_id: string;
  status: string;
  error: string | null;
  started_at: string;
  actor: string;
  counts: GateCounts | null;
  inputs: GateInputs;
}

export interface GateDataset {
  file: string;
  id: string;
  name: string;
  sources: Record<string, string>;
  references: string[];
  change_control: boolean;
  error?: string;
}

export interface SheetFinding {
  id: string;
  key: string;
  kind: string;
  severity: "error" | "risk" | "anomaly";
  title: string;
  detail: string;
  sheet: string | null;
  cell: string | null;
  cells: string[];
  group: string[];
  formula: string | null;
  value: string | null;
  expected: string | null;
  row_label: string;
  column_label: string;
  precedents: string[];
  dependents: number;
  downstream: number;
  feeds: string[];
  review: { action: string; note: string; actor: string; at: string; scan_id: number } | null;
}

export interface SheetChange {
  kind: string;
  material: boolean;
  sheet: string;
  cell: string | null;
  before_cell: string | null;
  before: string | null;
  after: string | null;
  row_label: string;
  column_label: string;
  detail: string;
}

export interface SheetCounts {
  error: number;
  risk: number;
  anomaly: number;
  material_changes: number;
  formulas: number;
}

export interface SheetScanRow {
  id: number;
  model: string;
  name: string;
  previous_name: string | null;
  status: string;
  error: string | null;
  at: string;
  actor: string;
  counts: SheetCounts | null;
}

export interface SheetScan extends SheetScanRow {
  config_version: string;
  engine_version: string;
  open?: { error: number; risk: number };
  result: {
    workbook: string;
    sha256: string;
    previous: string | null;
    sheets: { name: string; state: string; cells: number; formulas: number }[];
    findings: SheetFinding[];
    changes: SheetChange[];
    change_summary: Record<string, unknown>;
    notes: string[];
  } | null;
}

export const finops = {
  dqDatasets: () => getJson<GateDataset[]>("/api/finops/dq/datasets"),
  dqRuns: () => getJson<GateRunRow[]>("/api/finops/dq/runs"),
  dqRun: (id: number, signal?: AbortSignal) => getJson<GateRun>(`/api/finops/dq/runs/${id}`, signal),
  dqSample: () => sendJson<{ vendors: number; purchase_orders: number }>("/api/finops/dq/sample", "POST", {}),
  dqUpload: (dataset: string, files: Record<string, File | null>) => {
    const form = new FormData();
    form.append("dataset", dataset);
    for (const [k, f] of Object.entries(files)) if (f) form.append(k, f);
    return request("/api/finops/dq/runs", { method: "POST", body: form }).then((r) => r.json() as Promise<{ run: number }>);
  },
  dqDecide: (id: number, record_id: string, action: string, note: string, field?: string, value?: string) =>
    sendJson<{ run: number }>(`/api/finops/dq/runs/${id}/decide`, "POST", { record_id, action, note, field, value }),
  dqEvents: (dataset: string) => getJson<AuditEvent[]>(`/api/finops/dq/datasets/${dataset}/events`),
  sheetScans: () => getJson<SheetScanRow[]>("/api/finops/sheets/scans"),
  sheetScan: (id: number, signal?: AbortSignal) => getJson<SheetScan>(`/api/finops/sheets/scans/${id}`, signal),
  sheetSample: () => sendJson<{ scans: number[] }>("/api/finops/sheets/sample", "POST", {}),
  sheetUpload: (workbook: File, previous: File | null, model: string) => {
    const form = new FormData();
    form.append("workbook", workbook);
    if (previous) form.append("previous", previous);
    if (model.trim()) form.append("model", model.trim());
    return request("/api/finops/sheets/scans", { method: "POST", body: form }).then((r) => r.json() as Promise<{ scan: number }>);
  },
  sheetReview: (id: number, finding_id: string, action: string, note: string) =>
    sendJson<SheetScan>(`/api/finops/sheets/scans/${id}/review`, "POST", { finding_id, action, note }),
  sheetEvents: (model: string) => getJson<AuditEvent[]>(`/api/finops/sheets/models/${encodeURIComponent(model)}/events`),
  roi: () => getJson<FinopsRoi>("/api/finops/roi"),
  setRoiAssumptions: (values: Record<string, number>) => sendJson<FinopsRoi>("/api/finops/roi/assumptions", "PUT", values),
  workspaces: () => getJson<Workspace[]>("/api/finops/recon/workspaces"),
  profiles: () => getJson<{ file: string; id: string; name: string; error?: string }[]>("/api/finops/recon/profiles"),
  createWorkspace: (name: string, profile: string) => sendJson<{ id: number }>("/api/finops/recon/workspaces", "POST", { name, profile }),
  runFiles: (wid: number, left: File | null, right: File | null) => upload<ReconRun>(`/api/finops/recon/workspaces/${wid}/run`, { left, right }),
  runSample: (wid: number) => sendJson<ReconRun>(`/api/finops/recon/workspaces/${wid}/sample`, "POST", {}),
  run: (id: number, signal?: AbortSignal) => getJson<ReconRun>(`/api/finops/recon/runs/${id}`, signal),
  accept: (id: number, group_id: string, note: string) => sendJson<ReconRun>(`/api/finops/recon/runs/${id}/accept`, "POST", { group_id, note }),
  reject: (id: number, group_id: string, note: string) => sendJson<ReconRun>(`/api/finops/recon/runs/${id}/reject`, "POST", { group_id, note }),
  manual: (id: number, left: string[], right: string[], note: string) =>
    sendJson<ReconRun>(`/api/finops/recon/runs/${id}/manual`, "POST", { left, right, note }),
  resolveRecon: (id: number, exception_id: string, action: string, note: string) =>
    sendJson<ReconRun>(`/api/finops/recon/runs/${id}/resolve`, "POST", { exception_id, action, note }),
  reconEvents: (wid: number) => getJson<AuditEvent[]>(`/api/finops/recon/workspaces/${wid}/events`),
  invoices: () => getJson<InvoiceRow[]>("/api/finops/invoices"),
  uploadInvoice: (file: File) => upload<InvoiceDetail>("/api/finops/invoices", { file }),
  sampleInvoices: () => sendJson<{ submitted: number }>("/api/finops/invoices/sample", "POST", {}),
  invoice: (docId: string, signal?: AbortSignal) => getJson<InvoiceDetail>(`/api/finops/invoices/${docId}`, signal),
  correct: (docId: string, field: string, value: string, note: string) =>
    sendJson<InvoiceDetail>(`/api/finops/invoices/${docId}/correct`, "POST", { field, value, note }),
  resolveInvoice: (docId: string, exception_id: string, action: string, note: string) =>
    sendJson<InvoiceDetail>(`/api/finops/invoices/${docId}/resolve`, "POST", { exception_id, action, note }),
  invoiceEvents: (docId: string) => getJson<AuditEvent[]>(`/api/finops/invoices/${docId}/events`),
};

export function needsName(): boolean {
  return getActor() === "local-user";
}

export function errorText(e: unknown): string {
  return e instanceof ApiError || e instanceof Error ? e.message : String(e);
}
