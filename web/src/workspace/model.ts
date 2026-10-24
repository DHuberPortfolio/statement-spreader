// Derived, read-only views of one run's payload that the workspace screens share.

import type {
  LineInfo,
  Period,
  Profile,
  ProfileLine,
  ReviewItem,
  RunPayload,
  Severity,
  Spread,
  SpreadValue,
  StatementKey,
} from "../api/types";
import { orderedPeriods, valueKey } from "../lib/periods";
import { STATEMENT_ORDER } from "../lib/status";

export interface WorkspaceModel {
  payload: RunPayload;
  spread: Spread;
  profile: Profile;
  index: Map<string, SpreadValue>;
  items: Map<string, ReviewItem>;
  periodsByKey: Map<string, Period>;
  statementPeriods: Record<StatementKey, Period[]>;
  statementLines: Record<StatementKey, ProfileLine[]>;
  lineInfo: (line: string) => LineInfo;
  flagSeverity: (v: SpreadValue) => Severity | null;
  relatedItems: (line: string, period: string) => ReviewItem[];
  defaultUnit: number;
  approved: boolean;
}

const SEV_RANK: Record<Severity, number> = { blocker: 3, warning: 2, info: 1 };

export function worstSeverity(items: (ReviewItem | undefined)[]): Severity | null {
  let best: Severity | null = null;
  for (const it of items) {
    if (!it || it.resolved) continue;
    if (!best || SEV_RANK[it.severity] > SEV_RANK[best]) best = it.severity;
  }
  return best;
}

/** Does a review item listing `itemPeriod` concern the value at `valuePeriod`? (mirrors review.attach_flags) */
export function periodMatches(itemPeriod: string, valuePeriod: string): boolean {
  if (itemPeriod === valuePeriod) return true;
  return itemPeriod.endsWith("M") && valuePeriod === `${itemPeriod.split("/")[0]}/I`;
}

function powerOfTenAtMost(n: number): number {
  for (const u of [1_000_000_000, 1_000_000, 1_000, 1]) if (n >= u) return u;
  return 1;
}

export function buildModel(payload: RunPayload, profile: Profile): WorkspaceModel | null {
  const spread = payload.spread;
  if (!spread) return null;
  const index = new Map<string, SpreadValue>();
  for (const v of spread.values) index.set(valueKey(v.line, v.period), v);
  const items = new Map(spread.review.map((i) => [i.id, i]));
  const periodsByKey = new Map(spread.periods.map((p) => [p.key, p]));

  const lineStatement = new Map<string, StatementKey>();
  const statementLines = {} as Record<StatementKey, ProfileLine[]>;
  for (const s of STATEMENT_ORDER) {
    statementLines[s] = profile.statements[s]?.lines ?? [];
    for (const l of statementLines[s]) lineStatement.set(l.id, s);
  }

  const statementPeriods = {} as Record<StatementKey, Period[]>;
  for (const s of STATEMENT_ORDER) {
    const keys = new Set<string>((spread.statements[s]?.table.periods ?? []).map((p) => p.key));
    for (const v of spread.values) if (lineStatement.get(v.line) === s) keys.add(v.period);
    const periods = [...keys].map((k) => periodsByKey.get(k) ?? spread.statements[s]?.table.periods.find((p) => p.key === k)).filter(
      (p): p is Period => !!p,
    );
    statementPeriods[s] = orderedPeriods(periods);
  }

  const profileLines = new Map<string, ProfileLine>();
  for (const s of STATEMENT_ORDER) for (const l of statementLines[s]) profileLines.set(l.id, l);

  const lineInfo = (line: string): LineInfo => {
    const fromPayload = payload.lines?.[line];
    if (fromPayload) return fromPayload;
    const p = profileLines.get(line);
    return {
      label: p?.label ?? line,
      kind: p?.kind ?? "",
      critical: p?.critical ?? false,
      statement: lineStatement.get(line) ?? "income_statement",
    };
  };

  const flagSeverity = (v: SpreadValue) => worstSeverity(v.flags.map((f) => items.get(f)));

  const relatedItems = (line: string, period: string): ReviewItem[] => {
    const v = index.get(valueKey(line, period));
    const ids = new Set(v?.flags ?? []);
    const out: ReviewItem[] = [];
    for (const it of spread.review) {
      if (ids.has(it.id) || (it.lines.includes(line) && it.periods.some((p) => periodMatches(p, period)))) out.push(it);
    }
    return out.sort((a, b) => Number(a.resolved) - Number(b.resolved) || SEV_RANK[b.severity] - SEV_RANK[a.severity]);
  };

  const scales = Object.values(spread.statements).map((r) => r?.table.scale.multiplier ?? 1);
  const defaultUnit = powerOfTenAtMost(Math.max(1, ...scales));

  return {
    payload,
    spread,
    profile,
    index,
    items,
    periodsByKey,
    statementPeriods,
    statementLines,
    lineInfo,
    flagSeverity,
    relatedItems,
    defaultUnit,
    approved: !!payload.run.state.approved,
  };
}

const TOTAL_IDS = new Set(["cfo", "cfi", "cff", "net_change_cash", "net_income_parent"]);
const GRAND_IDS = new Set(["net_income", "total_assets", "total_liabilities_equity", "cash_end"]);

/** Presentation only: which lines get a statement-style rule above (totals) or a double rule below. */
export function lineStyle(line: ProfileLine): "grand" | "total" | "detail" {
  if (GRAND_IDS.has(line.id)) return "grand";
  if (line.id.startsWith("total_") || line.kind === "result" || TOTAL_IDS.has(line.id)) return "total";
  return "detail";
}
