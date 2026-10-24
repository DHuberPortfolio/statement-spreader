import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Period, ProfileLine, StatementKey } from "../api/types";
import { StatusMarker } from "../components/Markers";
import { cleanEvidence, formatDate, formatLineValue, unitName } from "../lib/format";
import { durationLabel, groupPeriodsByEnd, periodKeyLabel, valueKey } from "../lib/periods";
import { SEVERITY, STATEMENT_ORDER, STATEMENT_TITLE, VALUE_STATUS } from "../lib/status";
import { useWorkspace } from "./context";
import { lineStyle } from "./model";

export const UNITS = [1, 1_000, 1_000_000, 1_000_000_000] as const;

export function UnitSelector({ value, onChange, idPrefix = "unit" }: { value: number; onChange: (u: number) => void; idPrefix?: string }) {
  return (
    <fieldset className="segmented" aria-label="Display unit">
      <legend className="segmented-legend">Show in</legend>
      {UNITS.map((u) => (
        <label key={u} className={value === u ? "is-on" : ""}>
          <input
            type="radio"
            name={`${idPrefix}-select`}
            value={u}
            checked={value === u}
            onChange={() => onChange(u)}
          />
          <span>{unitName(u)}</span>
        </label>
      ))}
    </fieldset>
  );
}

function PeriodHeader({ p }: { p: Period }) {
  const assumed = p.assumed.length > 0;
  const title = [`Printed header: "${p.label}"`, ...p.notes, ...p.assumed.map((a) => `Assumed: ${a}`)].join("\n");
  return (
    <span title={title} className="col-head">
      <span className="col-date">{formatDate(p.end)}</span>
      <span className="col-dur">
        {durationLabel(p)}
        {assumed && (
          <span className="col-assumed">
            {" "}
            <StatusMarker status="assumed" />
            <span className="sr-only">(period assumed: {p.assumed.join(" ")})</span>
          </span>
        )}
      </span>
    </span>
  );
}

function StatementGrid({ statement, hideEmpty }: { statement: StatementKey; hideEmpty: boolean }) {
  const { model, unit, selectCell, selectedCell } = useWorkspace();
  const table = useRef<HTMLTableElement>(null);
  const periods = model.statementPeriods[statement];
  const allLines = model.statementLines[statement];
  const lines = hideEmpty
    ? allLines.filter((l) => periods.some((p) => model.index.get(valueKey(l.id, p.key))?.value != null))
    : allLines;
  const groups = groupPeriodsByEnd(periods);
  const twoRows = groups.some((g) => g.periods.length > 1);
  const res = model.spread.statements[statement];
  const [active, setActive] = useState<{ r: number; c: number }>({ r: 0, c: 0 });

  // When a cell is selected from elsewhere (review queue, checks), make it this table's active cell.
  useEffect(() => {
    if (!selectedCell) return;
    const [line, period] = splitKey(selectedCell);
    const r = lines.findIndex((l) => l.id === line);
    const c = periods.findIndex((p) => p.key === period);
    if (r >= 0 && c >= 0) {
      setActive({ r, c });
      const el = table.current?.querySelector<HTMLElement>(`td[data-r="${r}"][data-c="${c}"]`);
      el?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCell]);

  if (!res && periods.length === 0) {
    const missing = model.spread.review.find((i) => i.kind === "missing_statement" && i.statement === statement);
    return (
      <section className="stmt" aria-labelledby={`stmt-${statement}`}>
        <div className="stmt-head">
          <h3 id={`stmt-${statement}`}>{STATEMENT_TITLE[statement]}</h3>
        </div>
        <p className="stmt-missing">
          Not found in this document{missing ? `: ${missing.message}` : "."} None of its lines are in the spread.
        </p>
      </section>
    );
  }

  const focusCell = (r: number, c: number) => {
    const rr = Math.max(0, Math.min(lines.length - 1, r));
    const cc = Math.max(0, Math.min(periods.length - 1, c));
    setActive({ r: rr, c: cc });
    table.current?.querySelector<HTMLElement>(`td[data-r="${rr}"][data-c="${cc}"]`)?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTableElement>) => {
    const target = e.target as HTMLElement;
    if (target.tagName !== "TD") return;
    const { r, c } = active;
    const moves: Record<string, () => void> = {
      ArrowDown: () => focusCell(r + 1, c),
      ArrowUp: () => focusCell(r - 1, c),
      ArrowRight: () => focusCell(r, c + 1),
      ArrowLeft: () => focusCell(r, c - 1),
      Home: () => (e.ctrlKey ? focusCell(0, 0) : focusCell(r, 0)),
      End: () => (e.ctrlKey ? focusCell(lines.length - 1, periods.length - 1) : focusCell(r, periods.length - 1)),
      PageDown: () => focusCell(r + 10, c),
      PageUp: () => focusCell(r - 10, c),
      Enter: () => {
        const l = lines[r];
        const p = periods[c];
        if (l && p) selectCell(valueKey(l.id, p.key));
      },
    };
    moves[" "] = moves.Enter!;
    const fn = moves[e.key];
    if (fn) {
      e.preventDefault();
      fn();
    }
  };

  const scale = res?.table.scale;
  return (
    <section className="stmt" aria-labelledby={`stmt-${statement}`}>
      <div className="stmt-head">
        <h3 id={`stmt-${statement}`}>{STATEMENT_TITLE[statement]}</h3>
        {scale && (
          <span className="muted small">
            Printed {unitName(scale.multiplier)}
            {scale.evidence && !scale.assumed && <> (“{cleanEvidence(scale.evidence)}”)</>}
            {scale.assumed && (
              <span className="badge badge-warn" title={scale.evidence}>
                unit assumed
              </span>
            )}
            {" · "}shown in {unitName(unit)}
          </span>
        )}
      </div>
      <div className="grid-scroll">
        <table
          ref={table}
          className="spread-grid"
          role="grid"
          aria-labelledby={`stmt-${statement}`}
          aria-describedby="grid-help"
          onKeyDown={onKeyDown}
        >
          <thead>
            {twoRows ? (
              <>
                <tr>
                  <th scope="col" rowSpan={2} className="line-col">
                    Line
                  </th>
                  {groups.map((g) => (
                    <th key={g.end} scope="colgroup" colSpan={g.periods.length} className="group-head">
                      {formatDate(g.end)}
                    </th>
                  ))}
                </tr>
                <tr>
                  {periods.map((p) => (
                    <th key={p.key} scope="col" className="num">
                      <span title={p.label}>{durationLabel(p)}</span>
                    </th>
                  ))}
                </tr>
              </>
            ) : (
              <tr>
                <th scope="col" className="line-col">
                  Line
                </th>
                {periods.map((p) => (
                  <th key={p.key} scope="col" className="num">
                    <PeriodHeader p={p} />
                  </th>
                ))}
              </tr>
            )}
          </thead>
          <tbody>
            {lines.map((line, r) => (
              <GridRow key={line.id} line={line} r={r} periods={periods} active={active} setActive={setActive} />
            ))}
          </tbody>
        </table>
      </div>
      {lines.length === 0 && <p className="muted small">No lines with values.</p>}
    </section>
  );
}

function splitKey(key: string): [string, string] {
  const i = key.indexOf("@");
  return [key.slice(0, i), key.slice(i + 1)];
}

function GridRow({
  line,
  r,
  periods,
  active,
  setActive,
}: {
  line: ProfileLine;
  r: number;
  periods: Period[];
  active: { r: number; c: number };
  setActive: (a: { r: number; c: number }) => void;
}) {
  const { model, unit, selectCell, selectedCell } = useWorkspace();
  const style = lineStyle(line);
  return (
    <tr className={`row-${style} ${line.critical ? "row-critical" : ""}`}>
      <th scope="row" className="line-label">
        <span className="line-label-text">{line.label}</span>
        {line.critical && <span className="sr-only"> (critical line)</span>}
      </th>
      {periods.map((p, c) => {
        const key = valueKey(line.id, p.key);
        const v = model.index.get(key);
        const sev = v ? model.flagSeverity(v) : null;
        const selected = selectedCell === key;
        const isActive = active.r === r && active.c === c;
        const shown = v && v.value != null ? formatLineValue(v.value, line.kind, unit) : "";
        const label = [
          `${line.label}, ${periodKeyLabel(p.key, model.spread.periods)}:`,
          v && v.value != null ? shown : "no value",
          v ? `(${VALUE_STATUS[v.status].label}${v.confidence < 1 ? `, ${Math.round(v.confidence * 100)}% confidence` : ""})` : "",
          sev ? `flagged: ${v!.flags.length} open review item${v!.flags.length === 1 ? "" : "s"}, worst ${SEVERITY[sev].label.toLowerCase()}` : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <td
            key={p.key}
            role="gridcell"
            data-r={r}
            data-c={c}
            tabIndex={isActive ? 0 : -1}
            aria-selected={selected}
            aria-label={label}
            className={[
              "cell",
              v ? `cell-${v.status}` : "cell-empty",
              sev ? `flag-${sev}` : "",
              selected ? "is-selected" : "",
            ].join(" ")}
            onClick={() => {
              setActive({ r, c });
              selectCell(key);
            }}
            onFocus={() => {
              if (!isActive) setActive({ r, c });
            }}
          >
            {v && v.value != null ? (
              <>
                <StatusMarker status={v.status} />
                <span className="cell-num">{shown}</span>
              </>
            ) : v ? (
              <>
                <StatusMarker status={v.status} />
                <span className="cell-num muted">n/a</span>
              </>
            ) : (
              <span className="cell-blank" aria-hidden="true" />
            )}
            {sev && <span className={`flag-corner sev-${sev}`} aria-hidden="true" />}
          </td>
        );
      })}
    </tr>
  );
}

export function SpreadGrid({ hideEmpty }: { hideEmpty: boolean }) {
  return (
    <div className="spread">
      <p id="grid-help" className="sr-only">
        Use the arrow keys to move between values, Enter to open the evidence for a value, Tab to leave the table.
      </p>
      {STATEMENT_ORDER.map((s) => (
        <StatementGrid key={s} statement={s} hideEmpty={hideEmpty} />
      ))}
    </div>
  );
}
