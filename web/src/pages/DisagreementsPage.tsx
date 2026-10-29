import { useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import type { Disagreement, DisagreementList } from "../api/types";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { can } from "../lib/auth";
import { formatDateTime } from "../lib/format";
import { Link } from "../lib/router";
import { useApi } from "../lib/useApi";

// The model's learning period (DECISIONS D53, D54): where the model's hidden opinion differed from what an analyst
// approved, a senior decides which was right and why. The two answers are shown as A and B, without saying whose is
// whose, until the senior has ruled: a ruling that knows the source can lean towards or against the model.

const STATEMENTS: Record<string, string> = {
  income_statement: "Income statement",
  balance_sheet: "Balance sheet",
  cash_flow: "Cash flow",
};

const VERDICT: Record<string, string> = {
  analyst: "The analyst was right",
  model: "The model was right",
  neither: "Neither was right",
};

function RuleForm({ item, list, onRuled }: { item: Disagreement; list: DisagreementList; onRuled: (d: Disagreement) => void }) {
  const [choice, setChoice] = useState<"a" | "b" | "neither" | "">("");
  const [line, setLine] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = `rule-${item.id}`;
  const others = (list.lines[item.statement] ?? []).filter((l) => !item.answers.some((a) => a.line === l.id));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!choice) return setError("Choose A, B or neither.");
    if (choice === "neither" && !line) return setError("Choose the line it belongs on.");
    if (!reason) return setError("Choose why.");
    if (note.trim().length < 3) return setError("Write a note saying why: the model learns from it.");
    setBusy(true);
    setError(null);
    try {
      onRuled(await api.rule(item.id, { choice, reason, note: note.trim(), ...(choice === "neither" ? { correct_line: line } : {}) }));
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="resolve-form" onSubmit={submit} aria-labelledby={`${id}-label`}>
      <fieldset className="rule-choices">
        <legend id={`${id}-label`}>Where does this line belong?</legend>
        {item.answers.map((a) => (
          <label key={a.key} className="rule-choice">
            <input type="radio" name={`${id}-choice`} value={a.key} checked={choice === a.key} onChange={() => setChoice(a.key)} />
            <span>
              <strong>Answer {a.key.toUpperCase()}</strong>: {a.label}
              {a.who && <span className="muted small"> ({a.who === "analyst" ? "the analyst's" : "the model's"})</span>}
            </span>
          </label>
        ))}
        <label className="rule-choice">
          <input type="radio" name={`${id}-choice`} value="neither" checked={choice === "neither"} onChange={() => setChoice("neither")} />
          <span>
            <strong>Neither</strong>: it belongs on
          </span>
          <select
            aria-label="The correct line"
            value={line}
            disabled={choice !== "neither"}
            onChange={(e) => setLine(e.target.value)}
          >
            <option value="">choose a line</option>
            {!item.answers.some((a) => a.line === "none") && <option value="none">left off the spread</option>}
            {others.map((l) => (
              <option key={l.id} value={l.id}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      </fieldset>
      <label htmlFor={`${id}-reason`}>
        Why <span className="req">(required)</span>
      </label>
      <select id={`${id}-reason`} value={reason} onChange={(e) => setReason(e.target.value)}>
        <option value="">choose a reason</option>
        {Object.entries(list.reasons).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
      <label htmlFor={`${id}-note`}>
        Note <span className="req">(required)</span>
      </label>
      <textarea
        id={`${id}-note`}
        rows={2}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="What makes it right, in a sentence the next analyst could learn from"
      />
      <div className="form-row">
        <button type="submit" className="btn btn-primary btn-small" disabled={busy}>
          {busy ? "Saving…" : "Rule"}
        </button>
      </div>
      {error && <InlineMessage kind="error">{error}</InlineMessage>}
    </form>
  );
}

function Item({ item, list, onRuled }: { item: Disagreement; list: DisagreementList; onRuled: (d: Disagreement) => void }) {
  const rulable = item.status !== "ruled";
  return (
    <article className="disagreement" aria-labelledby={`dis-${item.id}`}>
      <header>
        <h3 id={`dis-${item.id}`}>
          “{item.label}”
        </h3>
        <p className="small muted">
          {STATEMENTS[item.statement] ?? item.statement}
          {item.section && <> · under “{item.section}”</>} · {item.document ?? "document"} ·{" "}
          {/* while ruling blind, no link to the run: its page shows the approved placement, so whose answer is whose */}
          {list.blind && rulable ? <>run #{item.run_id}</> : <Link to={`/runs/${item.run_id}`}>run #{item.run_id}</Link>} ·
          approved {formatDateTime(item.approved_at)}
          {item.approved_by && <> by {item.approved_by}</>}
        </p>
        {item.status === "open" && <p className="small">Rule by {formatDateTime(item.due_at)}, or the analyst's answer stands.</p>}
        {item.status === "analyst_stands" && (
          <p className="small">
            <span className="chip chip-muted">Analyst's answer stands</span> No ruling by the deadline. A ruling now still
            replaces it.
          </p>
        )}
      </header>
      {rulable ? (
        <RuleForm item={item} list={list} onRuled={onRuled} />
      ) : (
        <div className="small">
          <p>
            <strong>{VERDICT[item.verdict ?? ""] ?? item.verdict}</strong>: {item.correct_label}.{" "}
            {item.answers.map((a) => (
              <span key={a.key} className="muted">
                {a.who === "analyst" ? "Analyst" : "Model"}: {a.label}.{" "}
              </span>
            ))}
          </p>
          <p className="muted">
            {list.reasons[item.reason ?? ""] ?? item.reason}. “{item.note}” · {item.ruled_by}, {formatDateTime(item.ruled_at ?? "")}
          </p>
        </div>
      )}
    </article>
  );
}

export function DisagreementsPage() {
  const allowed = can("adjudicate");
  // without the senior role nothing is asked of the server (it would refuse it anyway)
  const state = useApi((signal) => (allowed ? api.disagreements(signal) : Promise.resolve(null)), [allowed]);
  const [showRuled, setShowRuled] = useState(false);
  if (!allowed)
    return (
      <Layout>
        <EmptyState title="For senior reviewers">
          <p>Ruling on the model's disagreements needs the senior role.</p>
        </EmptyState>
      </Layout>
    );
  const list = state.data;
  const onRuled = (d: Disagreement) => {
    if (list) state.setData({ ...list, items: list.items.map((i) => (i.id === d.id ? d : i)) });
  };
  const rulable = list?.items.filter((i) => i.status !== "ruled") ?? [];
  const ruled = list?.items.filter((i) => i.status === "ruled") ?? [];
  return (
    <Layout>
      <header className="page-head">
        <h1>Model disagreements</h1>
        <p className="lede">
          During its learning period the model gives a hidden opinion on every line. Where it would have placed a line
          differently from what an analyst approved, decide which was right and why. The model learns from your ruling.
          {list?.blind && " You see the two answers as A and B; whose is whose shows once you have ruled."}
          {list && ` Without a ruling in ${list.review_days} days, the analyst's answer stands.`}
        </p>
      </header>
      {state.loading && !list && <Loading label="Loading disagreements" />}
      {state.error && <ErrorState error={state.error} onRetry={state.reload} />}
      {list && (
        <>
          <h2 className="section-title">
            To rule on <span className="muted">({rulable.length})</span>
          </h2>
          {rulable.length === 0 ? (
            <EmptyState title="Nothing to rule on">
              <p>Disagreements appear here when an analyst approves a spread the model saw differently.</p>
            </EmptyState>
          ) : (
            rulable.map((i) => <Item key={i.id} item={i} list={list} onRuled={onRuled} />)
          )}
          {ruled.length > 0 && (
            <>
              <h2 className="section-title">
                Ruled <span className="muted">({ruled.length})</span>{" "}
                <button type="button" className="btn btn-small btn-quiet" onClick={() => setShowRuled(!showRuled)}>
                  {showRuled ? "Hide" : "Show"}
                </button>
              </h2>
              {showRuled && ruled.map((i) => <Item key={i.id} item={i} list={list} onRuled={onRuled} />)}
            </>
          )}
        </>
      )}
    </Layout>
  );
}
