// Number formatting for a financial spread.
//
// Values arrive from the backend as decimal strings (Python Decimal), sometimes in exponent form
// ("1E+6"). They are formatted with exact decimal arithmetic (BigInt), never through a float, so a
// 16-digit amount shown in units is never off by a rounding artefact. Negative numbers are shown in
// parentheses, the way a printed statement and Excel's #,##0;(#,##0) format show them.

export interface Dec {
  neg: boolean;
  digits: string; // the significand as an integer, no sign, no leading zeros ("0" for zero)
  exp: number; // value = digits x 10^exp
}

const DEC_RE = /^\s*([+-])?(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?\s*$/;

export function parseDec(input: string | number | null | undefined): Dec | null {
  if (input === null || input === undefined) return null;
  const s = typeof input === "number" ? (Number.isFinite(input) ? String(input) : "") : input;
  const m = DEC_RE.exec(s);
  if (!m) return null;
  const intPart = m[2] ?? "";
  const frac = m[3] ?? "";
  if (!intPart && !frac) return null;
  const digits = (intPart + frac).replace(/^0+/, "") || "0";
  const exp = -frac.length + (m[4] ? parseInt(m[4], 10) : 0);
  return { neg: m[1] === "-" && digits !== "0", digits, exp };
}

export function isZero(d: Dec): boolean {
  return d.digits === "0";
}

/** Number of digits after the decimal point the value really has (trailing zeros ignored). */
export function fractionDigits(d: Dec): number {
  if (d.exp >= 0 || isZero(d)) return 0;
  const trailingZeros = d.digits.length - d.digits.replace(/0+$/, "").length;
  return Math.max(0, -d.exp - trailingZeros);
}

/**
 * Round d / 10^shift to `decimals` places (half away from zero) and return the absolute value as a
 * plain digit string with a decimal point, e.g. "45,754" or "1.90".
 */
function roundAbs(d: Dec, shift: number, decimals: number): { text: string; zero: boolean } {
  const s = d.exp - shift + decimals;
  let n = BigInt(d.digits);
  if (s >= 0) {
    n = n * 10n ** BigInt(s);
  } else {
    const div = 10n ** BigInt(-s);
    const q = n / div;
    const r = n % div;
    n = r * 2n >= div ? q + 1n : q;
  }
  let str = n.toString().padStart(decimals + 1, "0");
  const intStr = decimals > 0 ? str.slice(0, str.length - decimals) : str;
  const fracStr = decimals > 0 ? str.slice(str.length - decimals) : "";
  str = groupThousands(intStr) + (decimals > 0 ? "." + fracStr : "");
  return { text: str, zero: n === 0n };
}

export function groupThousands(intDigits: string): string {
  return intDigits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export interface FormatOptions {
  /** divide by 10^shift before display: 0 units, 3 thousands, 6 millions, 9 billions; -2 shows a ratio as a percent */
  shift?: number;
  decimals?: number;
  /** negatives in parentheses (default) or with a leading minus sign */
  parens?: boolean;
  suffix?: string;
}

/** Format a decimal string. Returns "" for null or unparseable input. */
export function formatDecimal(value: string | number | null | undefined, opts: FormatOptions = {}): string {
  const d = parseDec(value);
  if (!d) return "";
  const shift = opts.shift ?? 0;
  const decimals = Math.max(0, opts.decimals ?? 0);
  const { text } = roundAbs(d, shift, decimals);
  const suffix = opts.suffix ?? "";
  if (!d.neg) return text + suffix;
  // A negative that rounds to zero still shows as (0): the sign is information.
  return opts.parens === false ? `−${text}${suffix}` : `(${text}${suffix})`;
}

export type DisplayUnit = 1 | 1_000 | 1_000_000 | 1_000_000_000;

export function unitShift(unit: number): number {
  const shift = Math.round(Math.log10(unit));
  if (10 ** shift !== unit) throw new Error(`Display unit must be a power of ten, got ${unit}`);
  return shift;
}

export function unitName(unit: number): string {
  switch (unit) {
    case 1:
      return "units";
    case 1_000:
      return "thousands";
    case 1_000_000:
      return "millions";
    case 1_000_000_000:
      return "billions";
    default:
      return `x${groupThousands(String(unit))}`;
  }
}

/** A money or share amount in the chosen display unit, whole numbers, negatives in parentheses. */
export function formatAmount(value: string | null | undefined, unit: number = 1): string {
  return formatDecimal(value, { shift: unitShift(unit), decimals: 0 });
}

/**
 * An amount in the display unit with as many decimals as it needs (up to maxDecimals), so a check
 * difference of 400,000 shown in millions reads 0.4 rather than a misleading 0.
 */
export function formatAmountPrecise(value: string | null | undefined, unit: number = 1, maxDecimals = 2): string {
  const d = parseDec(value ?? null);
  if (!d) return "";
  const shift = unitShift(unit);
  const decimals = Math.min(maxDecimals, fractionDigits({ ...d, exp: d.exp - shift }));
  return formatDecimal(value, { shift, decimals });
}

/** The exact amount in units with grouping, e.g. 45,754,000,000 (for the evidence panel). */
export function formatExact(value: string | null | undefined): string {
  const d = parseDec(value ?? null);
  if (!d) return "";
  return formatDecimal(value, { decimals: fractionDigits(d) });
}

/** Earnings per share: at least 2 decimals, up to 4 when the source has them. */
export function formatPerShare(value: string | null | undefined): string {
  const d = parseDec(value ?? null);
  if (!d) return "";
  return formatDecimal(value, { decimals: Math.min(4, Math.max(2, fractionDigits(d))) });
}

/** Format a value of a spread line according to its kind (per-share lines are never scaled). */
export function formatLineValue(value: string | null | undefined, kind: string, unit: number): string {
  if (kind === "per_share") return formatPerShare(value);
  return formatAmount(value, unit);
}

export function formatRatio(value: string | null | undefined, format: string, unit: number = 1): string {
  switch (format) {
    case "percent":
      return formatDecimal(value, { shift: -2, decimals: 1, suffix: "%" });
    case "times":
      return formatDecimal(value, { decimals: 2, suffix: "×" });
    case "days":
      return formatDecimal(value, { decimals: 1, suffix: " d" });
    case "money":
      return formatAmount(value, unit);
    default:
      return formatDecimal(value, { decimals: 2 });
  }
}

// ---- reading what a person types ----

/**
 * Read a number as an analyst types it: "1,234", "(1,234)", "-1234.5", "$ 1,234", "1 234".
 * Returns a canonical decimal string ("-1234.5") or null when it is not a number.
 */
export function parseUserNumber(input: string): string | null {
  let s = input.trim().replace(/[$€£\s,]/g, "").replace(/−/g, "-");
  if (!s) return null;
  let neg = false;
  if (/^\(.*\)$/.test(s)) {
    neg = true;
    s = s.slice(1, -1);
  }
  if (s.startsWith("-")) {
    neg = !neg;
    s = s.slice(1);
  } else if (s.startsWith("+")) {
    s = s.slice(1);
  }
  if (!/^(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  const d = parseDec(s);
  if (!d) return null;
  return decToString({ ...d, neg: neg && !isZero(d) });
}

/** Multiply a typed number by the unit it was typed in, exactly: ("1,234.5", 1e6) -> "1234500000". */
export function toFullUnits(input: string, unit: number): string | null {
  const canon = parseUserNumber(input);
  if (canon === null) return null;
  const d = parseDec(canon);
  if (!d) return null;
  return decToString({ ...d, exp: d.exp + unitShift(unit) });
}

/** Plain decimal string with no exponent and no grouping. */
export function decToString(d: Dec): string {
  let out: string;
  if (d.exp >= 0) {
    out = d.digits === "0" ? "0" : d.digits + "0".repeat(d.exp);
  } else {
    const padded = d.digits.padStart(-d.exp + 1, "0");
    const intPart = padded.slice(0, padded.length + d.exp);
    const frac = padded.slice(padded.length + d.exp).replace(/0+$/, "");
    out = frac ? `${intPart}.${frac}` : intPart;
  }
  return d.neg && out !== "0" ? "-" + out : out;
}

// ---- plain JS numbers (ROI report) ----

export function formatNumber(
  n: number | null | undefined,
  opts: { decimals?: number; prefix?: string; suffix?: string; parens?: boolean } = {},
): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "";
  const decimals = opts.decimals ?? 0;
  const abs = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  const body = `${opts.prefix ?? ""}${abs}${opts.suffix ?? ""}`;
  const isNeg = n < 0 && Number(abs.replace(/,/g, "")) !== 0;
  if (!isNeg) return body;
  return opts.parens === false ? `−${body}` : `(${body})`;
}

export function formatShare(n: number | null | undefined, decimals = 1): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "";
  return formatNumber(n * 100, { decimals, suffix: "%" });
}

/** A unit statement as found ("(In millions") without its stray brackets: "In millions". */
export function cleanEvidence(e: string): string {
  return e.replace(/^[\s(]+|[\s),.;:]+$/g, "");
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2025-09-27" -> "27 Sep 2025" (parsed by hand: no time-zone shift). */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[parseInt(m[2]!, 10) - 1] ?? m[2];
  return `${parseInt(m[3]!, 10)} ${month} ${m[1]}`;
}

/** ISO timestamp -> local "27 Sep 2025, 14:39". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `${date}, ${time}`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}
