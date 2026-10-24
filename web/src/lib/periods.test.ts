import { describe, expect, it } from "vitest";
import type { Period, SpreadValue } from "../api/types";
import { durationLabel, findValue, groupPeriodsByEnd, orderedPeriods, periodKeyLabel } from "./periods";

const p = (key: string, months: number | null): Period => ({
  key,
  end: key.split("/")[0]!,
  months,
  label: key,
  assumed: [],
  notes: [],
});

describe("groupPeriodsByEnd", () => {
  it("groups by end date, newest first, durations before the instant", () => {
    const periods = [
      p("2023-09-30/12M", 12),
      p("2025-09-27/I", null),
      p("2024-09-28/12M", 12),
      p("2025-09-27/12M", 12),
      p("2024-09-28/I", null),
    ];
    const groups = groupPeriodsByEnd(periods);
    expect(groups.map((g) => g.end)).toEqual(["2025-09-27", "2024-09-28", "2023-09-30"]);
    expect(groups[0]!.periods.map((x) => x.key)).toEqual(["2025-09-27/12M", "2025-09-27/I"]);
    expect(orderedPeriods(periods).map((x) => x.key)).toEqual([
      "2025-09-27/12M",
      "2025-09-27/I",
      "2024-09-28/12M",
      "2024-09-28/I",
      "2023-09-30/12M",
    ]);
  });

  it("orders a quarter and year-to-date by length within one end date", () => {
    const groups = groupPeriodsByEnd([p("2025-06-30/3M", 3), p("2025-06-30/6M", 6)]);
    expect(groups[0]!.periods.map((x) => x.key)).toEqual(["2025-06-30/6M", "2025-06-30/3M"]);
  });

  it("ignores duplicate keys and handles an empty list", () => {
    expect(groupPeriodsByEnd([p("2025-12-31/I", null), p("2025-12-31/I", null)])[0]!.periods).toHaveLength(1);
    expect(groupPeriodsByEnd([])).toEqual([]);
  });
});

describe("period labels", () => {
  it("describes durations and instants", () => {
    expect(durationLabel({ months: 12 })).toBe("12 months");
    expect(durationLabel({ months: 3 })).toBe("3 months");
    expect(durationLabel({ months: null })).toBe("At date");
    expect(periodKeyLabel("2025-09-27/I")).toBe("27 Sep 2025, at date");
    expect(periodKeyLabel("2025-09-27/12M")).toBe("27 Sep 2025, 12 months");
  });
});

describe("findValue", () => {
  const v = (line: string, period: string): SpreadValue => ({
    line,
    period,
    value: "1",
    status: "extracted",
    confidence: 1,
    source_rows: [],
    refs: [],
    steps: [],
    flags: [],
  });
  const index = new Map([
    ["cash@2025-12-31/I", v("cash", "2025-12-31/I")],
    ["revenue@2025-12-31/12M", v("revenue", "2025-12-31/12M")],
  ]);

  it("finds a value directly", () => {
    expect(findValue(index, "revenue", "2025-12-31/12M")?.line).toBe("revenue");
  });

  it("falls back from a flow period to the balance-sheet instant of the same end date", () => {
    expect(findValue(index, "cash", "2025-12-31/12M")?.period).toBe("2025-12-31/I");
    expect(findValue(index, "cash", "2024-12-31/12M")).toBeUndefined();
  });
});
