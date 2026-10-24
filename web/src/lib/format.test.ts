import { describe, expect, it } from "vitest";
import {
  decToString,
  cleanEvidence,
  formatAmount,
  formatAmountPrecise,
  formatDate,
  formatDecimal,
  formatExact,
  formatLineValue,
  formatNumber,
  formatPerShare,
  formatRatio,
  parseDec,
  parseUserNumber,
  toFullUnits,
  unitName,
} from "./format";

describe("formatAmount", () => {
  it("scales to the display unit and groups thousands", () => {
    expect(formatAmount("45754000000", 1_000_000)).toBe("45,754");
    expect(formatAmount("45754000000", 1_000)).toBe("45,754,000");
    expect(formatAmount("45754000000", 1)).toBe("45,754,000,000");
    expect(formatAmount("45754000000", 1_000_000_000)).toBe("46");
  });

  it("shows negatives in parentheses", () => {
    expect(formatAmount("-1234000000", 1_000_000)).toBe("(1,234)");
    expect(formatAmount("-7", 1)).toBe("(7)");
  });

  it("rounds half away from zero, symmetrically", () => {
    expect(formatAmount("1500000", 1_000_000)).toBe("2");
    expect(formatAmount("-1500000", 1_000_000)).toBe("(2)");
    expect(formatAmount("1499999", 1_000_000)).toBe("1");
  });

  it("keeps the sign of a small negative that rounds to zero, like Excel", () => {
    expect(formatAmount("-400000", 1_000_000)).toBe("(0)");
    expect(formatAmount("0", 1_000_000)).toBe("0");
    expect(formatAmount("-0", 1_000_000)).toBe("0");
  });

  it("returns an empty string for a missing value", () => {
    expect(formatAmount(null, 1_000_000)).toBe("");
    expect(formatAmount(undefined)).toBe("");
    expect(formatAmount("n/a")).toBe("");
  });

  it("reads Python Decimal exponent notation", () => {
    expect(formatAmount("1E+6", 1_000)).toBe("1,000");
    expect(formatAmount("4.5754E+10", 1_000_000)).toBe("45,754");
    expect(formatAmount("1000000.0", 1)).toBe("1,000,000");
  });

  it("is exact beyond float precision", () => {
    // 2^53 + 1 cannot be represented by a JS number
    expect(formatAmount("9007199254740993", 1)).toBe("9,007,199,254,740,993");
  });

  it("refuses a display unit that is not a power of ten", () => {
    expect(() => formatAmount("1", 1500)).toThrow();
  });
});

describe("per-share and ratio formats", () => {
  it("shows at least two decimals for EPS and never scales it", () => {
    expect(formatPerShare("6.08")).toBe("6.08");
    expect(formatPerShare("6")).toBe("6.00");
    expect(formatPerShare("-0.5")).toBe("(0.50)");
    expect(formatPerShare("1.23456")).toBe("1.2346");
    expect(formatLineValue("6.08", "per_share", 1_000_000)).toBe("6.08");
    expect(formatLineValue("6080000", "shares", 1_000_000)).toBe("6");
  });

  it("formats ratios by their declared format", () => {
    expect(formatRatio("0.018699135164998618813879858", "percent")).toBe("1.9%");
    expect(formatRatio("-0.042", "percent")).toBe("(4.2%)");
    expect(formatRatio("1.456", "times")).toBe("1.46×");
    expect(formatRatio("45.25", "days")).toBe("45.3 d");
    expect(formatRatio("-2500000000", "money", 1_000_000)).toBe("(2,500)");
    expect(formatRatio(null, "percent")).toBe("");
  });

  it("can show a minus sign instead of parentheses", () => {
    expect(formatDecimal("-12.5", { decimals: 1, parens: false })).toBe("−12.5");
  });

  it("keeps the decimals a check difference needs in a large unit", () => {
    expect(formatAmountPrecise("-400000", 1_000_000)).toBe("(0.4)");
    expect(formatAmountPrecise("1000000.0", 1_000_000)).toBe("1");
    expect(formatAmountPrecise("1234567", 1_000_000)).toBe("1.23");
    expect(formatAmountPrecise("13872000000", 1_000_000)).toBe("13,872");
  });

  it("shows the exact value with only the decimals it has", () => {
    expect(formatExact("45754000000")).toBe("45,754,000,000");
    expect(formatExact("-1.50")).toBe("(1.5)");
    expect(formatExact(null)).toBe("");
  });
});

describe("reading typed numbers", () => {
  it("accepts the ways an analyst types a number", () => {
    expect(parseUserNumber("1,234")).toBe("1234");
    expect(parseUserNumber("(1,234)")).toBe("-1234");
    expect(parseUserNumber("-1234.50")).toBe("-1234.5");
    expect(parseUserNumber("$ 1,234")).toBe("1234");
    expect(parseUserNumber("−5")).toBe("-5");
    expect(parseUserNumber(".5")).toBe("0.5");
  });

  it("rejects what is not a number", () => {
    expect(parseUserNumber("")).toBeNull();
    expect(parseUserNumber("abc")).toBeNull();
    expect(parseUserNumber("1.2.3")).toBeNull();
    expect(parseUserNumber("12e5")).toBeNull();
  });

  it("converts a number typed in millions to units exactly", () => {
    expect(toFullUnits("1,234.5", 1_000_000)).toBe("1234500000");
    expect(toFullUnits("(47,941)", 1_000_000)).toBe("-47941000000");
    expect(toFullUnits("0.1", 1_000)).toBe("100");
    expect(toFullUnits("12", 1)).toBe("12");
    expect(toFullUnits("x", 1_000)).toBeNull();
  });

  it("round-trips decimals without exponent notation", () => {
    const d = parseDec("1.5E-3");
    expect(d).not.toBeNull();
    expect(decToString(d!)).toBe("0.0015");
  });
});

describe("plain numbers and dates", () => {
  it("formats floats with parentheses for negatives", () => {
    expect(formatNumber(-570.00002, { decimals: 0, prefix: "$" })).toBe("($570)");
    expect(formatNumber(11400, { prefix: "$" })).toBe("$11,400");
    expect(formatNumber(-0.0001, { decimals: 2 })).toBe("0.00");
    expect(formatNumber(null)).toBe("");
  });

  it("formats ISO dates without a time-zone shift", () => {
    expect(formatDate("2025-09-27")).toBe("27 Sep 2025");
    expect(formatDate("2025-01-01")).toBe("1 Jan 2025");
  });

  it("names display units", () => {
    expect(unitName(1_000_000)).toBe("millions");
    expect(unitName(1)).toBe("units");
  });
});

describe("cleanEvidence", () => {
  it("strips the brackets a unit statement was found with", () => {
    expect(cleanEvidence("(In millions")).toBe("In millions");
    expect(cleanEvidence("(in thousands, except per share data)")).toBe("in thousands, except per share data");
    expect(cleanEvidence("In millions")).toBe("In millions");
  });
});
