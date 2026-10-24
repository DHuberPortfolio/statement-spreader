// Period columns: grouped by end date, newest first.

import type { Period, SpreadValue } from "../api/types";
import { formatDate } from "./format";

export interface PeriodGroup {
  end: string;
  periods: Period[];
}

/** Duration periods first (longest first), then the balance-sheet instant. */
function withinGroupOrder(a: Period, b: Period): number {
  const am = a.months ?? -1;
  const bm = b.months ?? -1;
  if (am !== bm) return bm - am;
  return a.key.localeCompare(b.key);
}

export function groupPeriodsByEnd(periods: Period[]): PeriodGroup[] {
  const groups = new Map<string, Period[]>();
  const seen = new Set<string>();
  for (const p of periods) {
    if (seen.has(p.key)) continue;
    seen.add(p.key);
    const list = groups.get(p.end);
    if (list) list.push(p);
    else groups.set(p.end, [p]);
  }
  return [...groups.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0))
    .map(([end, ps]) => ({ end, periods: [...ps].sort(withinGroupOrder) }));
}

/** Flattened column order after grouping. */
export function orderedPeriods(periods: Period[]): Period[] {
  return groupPeriodsByEnd(periods).flatMap((g) => g.periods);
}

export function durationLabel(p: Pick<Period, "months">): string {
  if (p.months === null || p.months === undefined) return "At date";
  if (p.months === 12) return "12 months";
  return `${p.months} months`;
}

/** Short human label for a period key alone, e.g. "2025-09-27/12M" -> "27 Sep 2025, 12 months". */
export function periodKeyLabel(key: string, periods?: Period[]): string {
  const p = periods?.find((x) => x.key === key);
  if (p) return `${formatDate(p.end)}, ${durationLabel(p).toLowerCase()}`;
  const [end, kind] = key.split("/");
  if (!end) return key;
  if (kind === "I") return `${formatDate(end)}, at date`;
  const m = /^(\d+)M$/.exec(kind ?? "");
  return m ? `${formatDate(end)}, ${m[1]} months` : `${formatDate(end)} (${kind ?? ""})`;
}

/**
 * Find the spread value a review item points at. A balance-sheet line inside a flow check is listed
 * with the flow period ("2025-12-31/12M"); its value sits on the instant of the same end date
 * ("2025-12-31/I"). This mirrors review.attach_flags on the server.
 */
export function findValue(
  index: Map<string, SpreadValue>,
  line: string,
  period: string,
): SpreadValue | undefined {
  const direct = index.get(`${line}@${period}`);
  if (direct) return direct;
  if (period.endsWith("M")) return index.get(`${line}@${period.split("/")[0]}/I`);
  return undefined;
}

export function valueKey(line: string, period: string): string {
  return `${line}@${period}`;
}
