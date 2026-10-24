// Small glyphs: value status markers, auditors' tick marks and severity marks.
// Each carries an accessible label, and each differs by shape as well as colour.

import type { CheckStatus, Severity, ValueStatus } from "../api/types";
import { CHECK_STATUS, SEVERITY, VALUE_STATUS, VALUE_STATUS_ORDER } from "../lib/status";

const STATUS_SHAPES: Record<ValueStatus, JSX.Element> = {
  // read straight from a printed cell: a small solid dot (the quiet default)
  extracted: <circle cx="5" cy="5" r="2.4" />,
  // read, then transformed: a ring
  normalized: <circle cx="5" cy="5" r="2.9" fill="none" strokeWidth="1.4" />,
  // calculated by formula: an open triangle (a delta)
  calculated: <path d="M5 1.6 L8.6 8.2 H1.4 Z" fill="none" strokeWidth="1.3" strokeLinejoin="round" />,
  // a model chose the line: a solid diamond
  ai_mapped: <path d="M5 0.8 L9.2 5 L5 9.2 L0.8 5 Z" />,
  // a reviewer set it: a solid square
  human: <rect x="1.6" y="1.6" width="6.8" height="6.8" />,
  // rests on an assumption: a solid triangle
  assumed: <path d="M5 1.2 L9 8.6 H1 Z" />,
  // not found: a dashed ring
  missing: <circle cx="5" cy="5" r="3" fill="none" strokeWidth="1.2" strokeDasharray="1.6 1.4" />,
};

export function StatusMarker({
  status,
  withLabel = false,
  decorative = false,
}: {
  status: ValueStatus;
  withLabel?: boolean;
  /** the label is already written next to it (legends) */
  decorative?: boolean;
}) {
  const meta = VALUE_STATUS[status];
  if (decorative) {
    return (
      <span className={`status-marker st-${status}`} aria-hidden="true">
        <svg viewBox="0 0 10 10" width="10" height="10" focusable="false">
          {STATUS_SHAPES[status]}
        </svg>
      </span>
    );
  }
  return (
    <span className={`status-marker st-${status}`} title={`${meta.label}: ${meta.description}`}>
      <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true" focusable="false">
        {STATUS_SHAPES[status]}
      </svg>
      {withLabel ? <span className="status-marker-label">{meta.label}</span> : <span className="sr-only">{meta.label}</span>}
    </span>
  );
}

export function StatusLegend({ compact = false }: { compact?: boolean }) {
  return (
    <ul className={`legend ${compact ? "legend-compact" : ""}`} aria-label="Value status legend">
      {VALUE_STATUS_ORDER.filter((s) => s !== "missing").map((s) => (
        <li key={s} title={VALUE_STATUS[s].description}>
          <StatusMarker status={s} decorative />
          <span>{VALUE_STATUS[s].label}</span>
        </li>
      ))}
      <li title="Has an open review item: blocker (red corner) or warning (amber corner)">
        <span className="legend-flag sev-blocker" aria-hidden="true" />
        <span className="legend-flag sev-warning" aria-hidden="true" />
        <span>Flagged</span>
      </li>
      <li title="A wrong value on this line changes a credit decision">
        <span className="legend-critical" aria-hidden="true" />
        <span>Critical line</span>
      </li>
    </ul>
  );
}

// Auditors' tick marks: a footed tick (checked and footed), a cross (does not agree), a dash (not tested).
const TICKS: Record<CheckStatus, JSX.Element> = {
  pass: (
    <>
      <path d="M2.2 7.4 L5.4 10.4 L11.8 2.8" fill="none" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2.2 13 H11.8" fill="none" strokeWidth="1.3" strokeLinecap="round" />
    </>
  ),
  fail: <path d="M3 3 L11 11 M11 3 L3 11" fill="none" strokeWidth="1.8" strokeLinecap="round" />,
  skipped: <path d="M3.5 7 H10.5" fill="none" strokeWidth="1.6" strokeLinecap="round" />,
};

export function TickMark({ status }: { status: CheckStatus }) {
  const meta = CHECK_STATUS[status];
  return (
    <span className={`tick tick-${status}`} title={`${meta.label}: ${meta.description}`}>
      <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true" focusable="false">
        {TICKS[status]}
      </svg>
      <span className="sr-only">{meta.label}</span>
    </span>
  );
}

export function TickLegend() {
  return (
    <ul className="legend" aria-label="Tick mark legend">
      {(["pass", "fail", "skipped"] as CheckStatus[]).map((s) => (
        <li key={s}>
          <span aria-hidden="true">
            <TickMark status={s} />
          </span>
          <span>
            <strong>{CHECK_STATUS[s].label}</strong> {CHECK_STATUS[s].description}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function SeverityMark({ severity, withLabel = false }: { severity: Severity; withLabel?: boolean }) {
  const shape =
    severity === "blocker" ? (
      <path d="M4 1 H10 L13 4 V10 L10 13 H4 L1 10 V4 Z" />
    ) : severity === "warning" ? (
      <path d="M7 1.2 L13 12.4 H1 Z" />
    ) : (
      <circle cx="7" cy="7" r="5.4" />
    );
  return (
    <span className={`sev-mark sev-${severity}`} title={SEVERITY[severity].description}>
      <svg viewBox="0 0 14 14" width="12" height="12" aria-hidden="true" focusable="false">
        {shape}
      </svg>
      {withLabel ? <span>{SEVERITY[severity].label}</span> : <span className="sr-only">{SEVERITY[severity].label}</span>}
    </span>
  );
}

export function Glyph({ name }: { name: "upload" | "back" | "external" | "close" | "chevron" }) {
  const paths: Record<typeof name, JSX.Element> = {
    upload: <path d="M8 11 V2 M4.5 5.5 L8 2 L11.5 5.5 M2.5 11 V14 H13.5 V11" fill="none" strokeWidth="1.5" />,
    back: <path d="M10 3 L5 8 L10 13" fill="none" strokeWidth="1.5" />,
    external: <path d="M9 2 H14 V7 M14 2 L7 9 M12 10 V14 H2 V4 H6" fill="none" strokeWidth="1.4" />,
    close: <path d="M3.5 3.5 L12.5 12.5 M12.5 3.5 L3.5 12.5" fill="none" strokeWidth="1.5" />,
    chevron: <path d="M5 6.5 L8 9.5 L11 6.5" fill="none" strokeWidth="1.5" />,
  };
  return (
    <svg className="glyph" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false" stroke="currentColor">
      {paths[name]}
    </svg>
  );
}
