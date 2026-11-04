import { useEffect, useRef } from "react";
import type { SourceRow, SourceTable } from "../api/types";
import { formatDate, unitName } from "../lib/format";
import { durationLabel } from "../lib/periods";
import { STATEMENT_TITLE } from "../lib/status";
import { useWorkspace } from "./context";

export function rowHasValues(r: SourceRow): boolean {
  return Object.values(r.values).some((v) => v.displayed !== null);
}

/** The printed statement beside a fix: the rows an issue concerns are marked, and any row can be picked. */
export function SheetContext({
  source,
  marked,
  picked,
  onPick,
}: {
  source: SourceTable;
  marked: number[];
  picked: number | null;
  onPick: (row: number) => void;
}) {
  const { model } = useWorkspace();
  const scroller = useRef<HTMLDivElement>(null);
  const target = picked ?? marked[0] ?? null;

  // Bring the row into the middle of this box without moving the panel around it.
  useEffect(() => {
    const box = scroller.current;
    const el = box?.querySelector<HTMLElement>(`tr[data-row="${target}"]`);
    if (box && el) box.scrollTop = el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2;
  }, [target, source]);

  return (
    <div className="sheet">
      <p className="small muted sheet-caption">
        <strong>{STATEMENT_TITLE[source.statement]}</strong>, as printed, in {unitName(source.scale.multiplier)}. Click a row to choose it.
      </p>
      <div className="sheet-scroll" ref={scroller}>
        <table className="sheet-table">
          <thead>
            <tr>
              <th scope="col">Printed row</th>
              {source.periods.map((p) => (
                <th key={p.key} scope="col" className="num">
                  {formatDate(p.end)}
                  <span className="sheet-dur">{durationLabel(p)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {source.rows.map((r) => {
              const pickable = rowHasValues(r);
              const placed = r.mapping?.canonical ? model.lineInfo(r.mapping.canonical).label : null;
              const cls = [
                r.bold || r.role === "total" ? "is-strong" : "",
                pickable && !placed && !r.mapping?.excluded ? "is-unplaced" : "",
                marked.includes(r.index) ? "is-marked" : "",
                picked === r.index ? "is-picked" : "",
                pickable ? "is-pickable" : "",
              ].join(" ");
              return (
                <tr
                  key={r.index}
                  data-row={r.index}
                  className={cls}
                  tabIndex={pickable ? 0 : undefined}
                  aria-selected={picked === r.index}
                  onClick={pickable ? () => onPick(r.index) : undefined}
                  onKeyDown={(e) => {
                    if (pickable && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      onPick(r.index);
                    }
                  }}
                >
                  <th scope="row">
                    {r.label}
                    {pickable && (
                      <span className="sheet-placed small">
                        {placed ? (
                          <span className="muted">On the spread as {placed}</span>
                        ) : r.mapping?.excluded ? (
                          <span className="muted">Left off the spread</span>
                        ) : (
                          <span className="sheet-unplaced">Not placed</span>
                        )}
                      </span>
                    )}
                  </th>
                  {source.periods.map((p) => (
                    <td key={p.key} className="num">
                      {r.values[p.key]?.raw ?? ""}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
