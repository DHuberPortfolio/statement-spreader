import { api } from "../api/client";
import { finops } from "../api/finops";
import { Icon } from "../components/Layout";
import { Link } from "../lib/router";
import { useApi } from "../lib/useApi";

type Tone = "ok" | "warn" | "bad" | "idle";

interface AreaCard {
  to: string;
  icon: Parameters<typeof Icon>[0]["name"];
  title: string;
  what: string;
  status: string;
  detail: string;
  tone: Tone;
  action: string;
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

/** The home page: one card per area, saying in plain words what is waiting for a person. */
export function OverviewPage() {
  const docs = useApi(() => api.documents(), []);
  const invoices = useApi(() => finops.invoices(), []);
  const workspaces = useApi(() => finops.workspaces(), []);
  const gate = useApi(() => finops.dqRuns(), []);
  const sheets = useApi(() => finops.sheetScans(), []);

  const cards: AreaCard[] = [];

  {
    const d = docs.data ?? [];
    const open = d.filter((x) => !x.approved);
    const blockers = open.reduce((n, x) => n + (x.summary?.blocker ?? 0), 0);
    cards.push({
      to: "/statements", icon: "statement", title: "Statements",
      what: "Financial statements spread into one standard template, every number traced to where it was printed.",
      status: docs.loading ? "Loading…" : d.length === 0 ? "Nothing uploaded yet" : `${plural(open.length, "spread")} waiting for approval`,
      detail: d.length === 0 ? "Upload a 10-K, a PDF or an Excel workbook to start." : `${plural(blockers, "blocking item")} to resolve; ${plural(d.length - open.length, "approved spread")}.`,
      tone: d.length === 0 ? "idle" : blockers > 0 ? "bad" : open.length > 0 ? "warn" : "ok",
      action: d.length === 0 ? "Upload statements" : "Review spreads",
    });
  }
  {
    const w = workspaces.data ?? [];
    cards.push({
      to: "/recon", icon: "match", title: "Reconciliation",
      what: "Bank lines ticked off against the ledger; only rules with measured precision match on their own.",
      status: workspaces.loading ? "Loading…" : w.length === 0 ? "No reconciliations yet" : plural(w.length, "reconciliation"),
      detail: w.length === 0 ? "Create one and load a bank file and a ledger export." : "Open one to see proposed matches and exceptions.",
      tone: w.length === 0 ? "idle" : "warn",
      action: w.length === 0 ? "Start a reconciliation" : "Open reconciliations",
    });
  }
  {
    const inv = invoices.data ?? [];
    const waiting = inv.filter((i) => i.open.length > 0).length;
    cards.push({
      to: "/invoices", icon: "invoice", title: "Invoices",
      what: "Invoices read, matched to purchase orders and receipts, and checked for duplicates and changed bank details.",
      status: invoices.loading ? "Loading…" : inv.length === 0 ? "No invoices yet" : `${plural(waiting, "invoice")} need a person`,
      detail: inv.length === 0 ? "Upload invoices or load the sample set." : `${plural(inv.length - waiting, "invoice")} cleared every check.`,
      tone: inv.length === 0 ? "idle" : waiting > 0 ? "warn" : "ok",
      action: inv.length === 0 ? "Add invoices" : "Work the queue",
    });
  }
  {
    const latest = (gate.data ?? [])[0];
    const review = latest?.counts?.review ?? 0;
    cards.push({
      to: "/data-quality", icon: "shield", title: "Data quality",
      what: "Vendor and purchase-order exports checked before another system loads them.",
      status: gate.loading ? "Loading…" : !latest ? "No exports checked yet" : `${plural(review, "record")} held for review`,
      detail: !latest ? "Check an export, or load the sample." : `Latest: ${latest.dataset_file}.`,
      tone: !latest ? "idle" : review > 0 ? "warn" : "ok",
      action: !latest ? "Check an export" : "See held records",
    });
  }
  {
    const latest = (sheets.data ?? [])[0];
    const serious = (latest?.counts?.error ?? 0) + (latest?.counts?.risk ?? 0);
    cards.push({
      to: "/spreadsheets", icon: "grid", title: "Spreadsheets",
      what: "Workbooks scanned for broken formulas, hard-coded numbers and risky changes between versions.",
      status: sheets.loading ? "Loading…" : !latest ? "No workbooks scanned yet" : `${plural(serious, "error or risk", "errors and risks")} in the latest scan`,
      detail: !latest ? "Scan a workbook, or load the samples." : `Latest: ${latest.name}.`,
      tone: !latest ? "idle" : (latest.counts?.error ?? 0) > 0 ? "bad" : serious > 0 ? "warn" : "ok",
      action: !latest ? "Scan a workbook" : "See findings",
    });
  }

  return (
    <>
      <header className="page-head">
        <p className="eyebrow">Overview</p>
        <h1>What needs a person today</h1>
        <p className="lede">
          The platform does the keying and ticking, checks its own work, and sends here only what it is unsure of.
          Each card says what is waiting; open it to work through the items.
        </p>
      </header>

      <div className="area-grid">
        {cards.map((c) => (
          <Link key={c.to} to={c.to} className={`area-card tone-${c.tone}`}>
            <span className="area-icon">
              <Icon name={c.icon} size={22} />
            </span>
            <span className="area-body">
              <span className="area-title">{c.title}</span>
              <span className="area-status">
                <span className="status-dot" aria-hidden="true" />
                {c.status}
              </span>
              <span className="area-detail">{c.detail}</span>
              <span className="area-what">{c.what}</span>
            </span>
            <span className="area-action">{c.action} →</span>
          </Link>
        ))}
      </div>

      <section className="how-it-works" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol className="steps">
          <li>
            <strong>Bring in the documents.</strong> Statements, bank and ledger exports, invoices, master data or
            workbooks.
          </li>
          <li>
            <strong>It reads and checks them.</strong> Every number is traced to its source; accounting identities and
            controls are run; each automatic decision uses a rule whose accuracy was measured.
          </li>
          <li>
            <strong>You decide what it is unsure of.</strong> Blocking items stop approval until a named person resolves
            them with a note. Your decisions are recorded, and they teach it which rules to trust.
          </li>
        </ol>
        <p className="muted small">
          Colours: <span className="tone-chip tone-bad">red</span> blocks approval,{" "}
          <span className="tone-chip tone-warn">amber</span> waits for a look, <span className="tone-chip tone-ok">green</span> is clear.
          See <Link to="/evaluation">Accuracy</Link> for how often each part is right.
        </p>
      </section>
    </>
  );
}
