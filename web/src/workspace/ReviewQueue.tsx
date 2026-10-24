import { useRef, useState, type KeyboardEvent } from "react";
import type { ReviewItem } from "../api/types";
import { SeverityMark } from "../components/Markers";
import { formatDate } from "../lib/format";
import { findValue, valueKey } from "../lib/periods";
import { REVIEW_KIND, SEVERITY, SEVERITY_ORDER, STATEMENT_TITLE } from "../lib/status";
import { useWorkspace } from "./context";
import { ResolveForm } from "./Evidence";

const MAX_LINKS = 8;

function shortPeriod(key: string): string {
  const [end, kind] = key.split("/");
  const d = end ? formatDate(end) : key;
  return kind === "I" ? d : `${d} (${kind?.replace("M", " mo")})`;
}

function ItemLinks({ item }: { item: ReviewItem }) {
  const { model, selectCell, gotoSource } = useWorkspace();
  const links: { key: string; label: string }[] = [];
  for (const line of item.lines) {
    for (const p of item.periods) {
      const v = findValue(model.index, line, p);
      const key = v ? valueKey(v.line, v.period) : valueKey(line, p);
      if (!links.some((l) => l.key === key)) {
        links.push({ key, label: `${model.lineInfo(line).label} · ${shortPeriod(v?.period ?? p)}` });
      }
    }
  }
  const shown = links.slice(0, MAX_LINKS);
  return (
    <div className="q-links">
      {shown.map((l) => (
        <button key={l.key} type="button" className="chip chip-link" onClick={() => selectCell(l.key, { focusEvidence: true })}>
          {l.label}
        </button>
      ))}
      {links.length > MAX_LINKS && <span className="small muted">+{links.length - MAX_LINKS} more</span>}
      {item.statement && item.rows.length > 0 && (
        <button type="button" className="chip chip-link chip-source" onClick={() => gotoSource(item.statement!, item.rows)}>
          {item.rows.length === 1 ? `Row ${item.rows[0]! + 1}` : `Rows ${item.rows.map((r) => r + 1).join(", ")}`} in the source
        </button>
      )}
    </div>
  );
}

function QueueItem({ item, index }: { item: ReviewItem; index: number }) {
  const [resolving, setResolving] = useState(false);
  return (
    <li className={`q-item sev-row-${item.severity}`} tabIndex={index === 0 ? 0 : -1} data-qi={index} aria-label={`${SEVERITY[item.severity].label}: ${REVIEW_KIND[item.kind] ?? item.kind}. ${item.message}`}>
      <div className="q-head">
        <SeverityMark severity={item.severity} />
        <span className="q-kind">{REVIEW_KIND[item.kind] ?? item.kind}</span>
        {item.statement && <span className="q-stmt">{STATEMENT_TITLE[item.statement]}</span>}
      </div>
      <p className="q-msg">{item.message}</p>
      <ItemLinks item={item} />
      {resolving ? (
        <ResolveForm item={item} onDone={() => setResolving(false)} compact />
      ) : (
        <button type="button" className="btn btn-small btn-quiet q-resolve" onClick={() => setResolving(true)}>
          Resolve with a note…
        </button>
      )}
    </li>
  );
}

export function ReviewQueue() {
  const { model } = useWorkspace();
  const list = useRef<HTMLDivElement>(null);
  const open = model.spread.review.filter((i) => !i.resolved);
  const resolved = model.spread.review.filter((i) => i.resolved);
  const blockers = open.filter((i) => i.severity === "blocker").length;

  // Arrow keys move between queue items (roving tabindex); Enter opens the first linked value.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (!target.classList.contains("q-item")) return;
    const items = [...(list.current?.querySelectorAll<HTMLElement>("li.q-item") ?? [])];
    const i = items.indexOf(target);
    let next = -1;
    if (e.key === "ArrowDown") next = Math.min(items.length - 1, i + 1);
    else if (e.key === "ArrowUp") next = Math.max(0, i - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else if (e.key === "Enter") {
      e.preventDefault();
      target.querySelector<HTMLButtonElement>(".chip-link")?.click();
      return;
    }
    if (next >= 0) {
      e.preventDefault();
      items.forEach((el, j) => (el.tabIndex = j === next ? 0 : -1));
      items[next]?.focus();
    }
  };

  let n = 0;
  return (
    <section className="queue" aria-labelledby="queue-title">
      <header className="queue-head">
        <h2 id="queue-title">Review queue</h2>
        <span className="small muted">
          {open.length} open{blockers > 0 && <>, {blockers} blocking approval</>}
        </span>
      </header>
      {open.length === 0 ? (
        <p className="queue-empty">
          Nothing open. {model.approved ? "The spread is approved." : "Every check that ran agrees and nothing needs a person: the spread can be approved."}
        </p>
      ) : (
        <p className="small muted queue-help">↑ ↓ move between items · Enter opens the value it concerns</p>
      )}
      <div ref={list} onKeyDown={onKeyDown}>
        {SEVERITY_ORDER.map((sev) => {
          const items = open.filter((i) => i.severity === sev);
          if (!items.length) return null;
          return (
            <div key={sev} className="q-group">
              <h3 className={`q-group-title sev-text-${sev}`}>
                <SeverityMark severity={sev} /> {SEVERITY[sev].plural} <span className="count">{items.length}</span>
              </h3>
              <ul className="q-list">
                {items.map((it) => (
                  <QueueItem key={it.id} item={it} index={n++} />
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {resolved.length > 0 && (
        <details className="resolved">
          <summary>Resolved ({resolved.length})</summary>
          <ul className="q-list">
            {resolved.map((it) => (
              <li key={it.id} className="q-item is-resolved">
                <div className="q-head">
                  <SeverityMark severity={it.severity} />
                  <span className="q-kind">{REVIEW_KIND[it.kind] ?? it.kind}</span>
                </div>
                <p className="q-msg">{it.message}</p>
                <p className="small">
                  <strong>Resolution:</strong> {it.resolution}
                </p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
