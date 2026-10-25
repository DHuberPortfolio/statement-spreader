// Invoice intake: the inbox, and one invoice with its fields, lines, PO match, exceptions and audit trail.

import { useState } from "react";
import { errorText, finops, needsName, type FieldValue, type InvoiceDetail } from "../api/finops";
import { Layout } from "../components/Layout";
import { EmptyState, ErrorState, InlineMessage, Loading } from "../components/States";
import { formatDateTime, humanizeCode } from "../lib/format";
import { Link, navigate } from "../lib/router";
import { useApi } from "../lib/useApi";
import { AuditList, Checks, ExceptionCard, NameReminder, StatusPill, money } from "./finopsShared";

const BANK = new Set(["BANK_DETAILS_CHANGED", "BANK_DETAILS_UNVERIFIED"]);
const GENERAL = ["explained", "corrected_by_vendor", "accept_variance", "confirmed_not_duplicate", "rejected"];
const FIELDS: [string, string][] = [
  ["vendor_name", "Vendor (as printed)"], ["vendor_id", "Vendor id"], ["vendor_tax_id", "Vendor tax id"], ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date"], ["due_date", "Due date"], ["po_number", "PO number"], ["terms", "Terms"], ["currency", "Currency"],
  ["subtotal", "Subtotal"], ["tax", "Tax"], ["tax_rate", "Tax rate"], ["freight", "Freight"], ["discount", "Discount"], ["total", "Total"],
  ["bank_account", "Bank account (masked)"],
];
const CORRECTABLE = new Set(["vendor_name", "invoice_number", "invoice_date", "due_date", "po_number", "currency", "subtotal", "tax", "freight", "discount", "total", "terms"]);

function actionsFor(code: string): string[] {
  if (BANK.has(code)) return ["verified_independently", "rejected"];
  if (code === "EXACT_DUPLICATE") return ["rejected", "confirmed_not_duplicate"];
  return GENERAL;
}

export function InvoiceListPage() {
  const list = useApi(() => finops.invoices(), []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "document" in r) navigate(`/invoices/${(r as InvoiceDetail).document.doc_id}`);
      else list.reload();
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <h1>Invoices</h1>
      <p className="lede">
        Invoices are read, checked arithmetically, matched to purchase orders and goods receipts, and screened for duplicates and
        changed bank details. The best status an invoice can reach here is <em>eligible for approval</em>: approval and payment happen
        in your ERP, by authorised people.
      </p>
      <NameReminder />
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      <div className="fo-row fo-panel">
        <label>
          Upload an invoice (PDF with a text layer, or JSON){" "}
          <input type="file" accept=".pdf,.json" disabled={busy} onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void run(() => finops.uploadInvoice(file));
            }} />
        </label>
        <button className="btn btn-quiet" type="button" disabled={busy} onClick={() => void run(() => finops.sampleInvoices())}>
          {busy ? "Working…" : "Load the sample inbox (81 synthetic invoices)"}
        </button>
        <a className="small" href="/api/finops/invoices/export.csv">
          Export CSV
        </a>
      </div>
      {list.loading && <Loading />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.data && list.data.length === 0 && <EmptyState title="No invoices yet">Upload one, or load the sample inbox.</EmptyState>}
      {list.data && list.data.length > 0 && (
        <table className="data-table fo-table">
          <thead>
            <tr>
              <th>Invoice</th>
              <th>Vendor</th>
              <th className="num">Total</th>
              <th>Status</th>
              <th>Open exceptions</th>
            </tr>
          </thead>
          <tbody>
            {list.data.map((i) => (
              <tr key={i.doc_id}>
                <td>
                  <Link to={`/invoices/${i.doc_id}`}>{i.invoice_number ?? i.name}</Link>
                  <div className="muted small">{i.name}</div>
                </td>
                <td>
                  {i.vendor ?? <span className="muted">unread</span>}
                  {i.vendor_id && <div className="muted small">{i.vendor_id}</div>}
                </td>
                <td className="num">
                  {money(i.total)} {i.currency ?? ""}
                </td>
                <td>
                  <StatusPill s={i.eligibility} />
                  {i.touchless && <div className="small muted">touchless</div>}
                </td>
                <td>
                  <span className="reason-list">
                    {i.open.map((c) => (
                      <span key={c} className="reason-chip" title={c}>
                        {humanizeCode(c)}
                      </span>
                    ))}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Layout>
  );
}

function show(f: FieldValue | undefined): string {
  if (!f) return "";
  const v = f.value;
  return typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v) && v.includes(".") ? money(v) : String(v ?? "");
}

export function InvoiceDetailPage({ docId }: { docId: string }) {
  const st = useApi((s) => finops.invoice(docId, s), [docId]);
  const events = useApi(() => finops.invoiceEvents(docId), [docId, st.data?.processed_at]);
  const [edit, setEdit] = useState<{ field: string; value: string; note: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (st.loading && !st.data) return <Layout><Loading /></Layout>;
  if (st.error) return <Layout><ErrorState error={st.error} onRetry={st.reload} /></Layout>;
  const d = st.data;
  if (!d || !d.outcome) return <Layout><EmptyState title="Not processed" /></Layout>;
  const o = d.outcome;
  const f = o.invoice.fields;

  async function save(fn: () => Promise<InvoiceDetail>) {
    setErr(null);
    try {
      st.setData(await fn());
      setEdit(null);
    } catch (x) {
      setErr(errorText(x));
      throw x;
    }
  }

  return (
    <Layout wide>
      <p className="small">
        <Link to="/invoices">Invoices</Link> / {d.document.name}
      </p>
      <h1>
        {String(f.vendor_name?.value ?? "Unknown vendor")} <span className="muted">{String(f.invoice_number?.value ?? "")}</span>
      </h1>
      <NameReminder />
      {err && <InlineMessage kind="error">{err}</InlineMessage>}
      <div className="fo-summary">
        <div>Extraction: <strong>{o.extraction}</strong></div>
        <div>Arithmetic: <strong>{o.validation}</strong></div>
        <div>PO and receipts: <strong>{o.matching.replace(/_/g, " ")}</strong></div>
        <div>Policy: <StatusPill s={d.rejected ? "rejected" : o.eligibility} /></div>
        <div>Authorization: <strong>not authorized here</strong></div>
        <div>{o.touchless ? "Touchless" : "Needed a person"}</div>
      </div>
      <p className="small muted">
        Uploaded by {d.document.uploaded_by}, {formatDateTime(d.document.uploaded_at)} · processed {formatDateTime(d.processed_at)} · {o.invoice.format.toUpperCase()},{" "}
        {o.invoice.pages} page(s){o.po_number ? ` · PO ${o.po_number}` : ""}
      </p>

      <h2>Exceptions</h2>
      {o.exceptions.length === 0 && <p className="muted">None: every check passed.</p>}
      {o.exceptions.map((e) => (
        <ExceptionCard key={e.id} e={e} actions={actionsFor(e.code)} onResolve={(a, n) => save(() => finops.resolveInvoice(docId, e.id, a, n))}>
          {BANK.has(e.code) && (
            <p className="small">
              <strong>Verify through an independent channel</strong>: call the vendor on a number from the vendor master or the contract, never
              one from this invoice or its email. Someone other than the person who uploaded the invoice must record the verification. This
              system never changes vendor bank details.
            </p>
          )}
        </ExceptionCard>
      ))}

      <h2>Fields</h2>
      <table className="data-table fo-table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Origin</th>
            <th>Where it came from</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {FIELDS.filter(([k]) => f[k]).map(([k, label]) => {
            const fv = f[k]!;
            return (
            <tr key={k}>
              <td>{label}</td>
              <td>
                {edit?.field === k ? (
                  <form
                    className="fo-row"
                    onSubmit={(ev) => {
                      ev.preventDefault();
                      void save(() => finops.correct(docId, k, edit.value, edit.note)).catch(() => undefined);
                    }}
                  >
                    <input value={edit.value} onChange={(ev) => setEdit({ ...edit, value: ev.target.value })} aria-label={`New ${label}`} />
                    <input value={edit.note} onChange={(ev) => setEdit({ ...edit, note: ev.target.value })} placeholder="Where the value comes from" aria-label="Note" />
                    <button className="btn btn-small btn-primary" type="submit">Save</button>
                    <button className="btn btn-small" type="button" onClick={() => setEdit(null)}>Cancel</button>
                  </form>
                ) : (
                  <>
                    <strong>{show(fv)}</strong>
                    {fv.origin === "human" && (
                      <div className="small muted">
                        was {String(fv.original ?? "empty")}, corrected by {fv.corrected_by}: {fv.note}
                      </div>
                    )}
                  </>
                )}
              </td>
              <td className="small">{fv.origin}</td>
              <td className="small muted">
                {fv.evidence ? (fv.evidence.page ? `page ${fv.evidence.page}: "${fv.evidence.text}"` : fv.evidence.pointer ?? "") : fv.note}
              </td>
              <td>
                {CORRECTABLE.has(k) && !edit && (
                  <button className="btn btn-small btn-quiet" type="button" disabled={needsName()} onClick={() => setEdit({ field: k, value: String(fv.value ?? ""), note: "" })}>
                    Correct
                  </button>
                )}
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
      {o.invoice.extraction_notes.length > 0 && <InlineMessage kind="info">{o.invoice.extraction_notes.join(" ")}</InlineMessage>}

      <h2>Lines and purchase-order match</h2>
      <table className="data-table fo-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Item</th>
            <th className="num">Qty</th>
            <th className="num">Unit price</th>
            <th className="num">Amount</th>
            <th>PO line</th>
            <th className="num">Ordered / received / invoiced before</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {o.invoice.lines.map((ln) => {
            const m = o.line_matches.find((x) => x.invoice_line === ln.index);
            return (
              <tr key={ln.index}>
                <td>{ln.index}</td>
                <td>
                  {ln.item_code && <code className="small">{String(ln.item_code.value)} </code>}
                  {String(ln.description.value)}
                </td>
                <td className="num">{String(ln.quantity?.value ?? "")}</td>
                <td className="num">{money(ln.unit_price?.value as string)}</td>
                <td className="num">{money(ln.amount?.value as string)}</td>
                <td className="small">{m?.po_line ? `${m.po_line} (by ${m.method.replace("_", " ")})` : "none"}</td>
                <td className="num small">
                  {m?.ordered ?? ""} / {m?.receipt_required ? m?.received ?? "0" : "no receipt needed"} / {m?.previously_invoiced ?? ""}
                </td>
                <td className="small muted">{m?.notes.slice(1).join(" ")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <details className="fo-panel">
        <summary>Checks ({o.checks.filter((c) => c.status === "pass").length} of {o.checks.length} pass)</summary>
        <Checks checks={o.checks} />
      </details>
      <h2>Audit trail</h2>
      {events.data ? <AuditList events={events.data} /> : <Loading />}
    </Layout>
  );
}
