// ROI for the reconciliation and invoice engines: observed rates (synthetic), assumed minutes,
// estimated hours. Same labels as the statement engine's ROI above it on the page.

import { useState } from "react";
import { errorText, finops, type FinopsRoi, type RoiNumber } from "../api/finops";
import type { RoiLabel } from "../api/types";
import { ErrorState, InlineMessage, Loading } from "../components/States";
import { useApi } from "../lib/useApi";
import { LabelBadge } from "./RoiPage";

const NAMES: Record<string, string> = {
  false_match_rate: "Wrong matches made on its own",
  exceptions_per_record: "Items needing a person, per record",
  records_auto_settled: "Records settled automatically",
  touchless_rate: "Invoices cleared with no one touching them",
  false_touchless: "Invoices cleared that should not have been",
  hours_by_hand: "Hours by hand",
  hours_with_engine: "Hours with the platform",
  hours_released: "Hours released",
  cash_value: "Cash value",
  faults_caught: "Bad records stopped (of all bad records)",
  false_quarantine: "Valid records held anyway",
  review_hours_added: "Review hours added",
  bad_records_stopped: "Bad records stopped",
  bad_records_still_loaded: "Bad records still loaded",
  value_of_stopped_records: "Value of stopped records",
  precision: "Findings that are real problems",
  recall: "Planted problems found",
  triage_hours: "Hours to check the findings",
  real_problems_reported: "Real problems reported",
  value_of_problems_caught: "Value of problems caught",
};

const ENGINE_NAMES: Record<string, string> = { recon: "Reconciliation", invoice: "Invoices", dq: "Data quality", sheets: "Spreadsheets" };

function fmt(n: RoiNumber): string {
  if (n.value == null) return "not measured";
  const share = n.unit.startsWith("share");
  const v = share ? `${(n.value * 100).toFixed(1)}%` : n.unit.startsWith("$") ? `$${n.value.toFixed(0)}` : n.value.toFixed(n.value < 1 ? 3 : 1);
  const range = share && n.low != null && n.high != null ? ` (likely ${(n.low * 100).toFixed(1)}-${(n.high * 100).toFixed(1)}%)` : "";
  return `${v}${range}`;
}

export function FinopsRoiSection({ view }: { view: "results" | "assumptions" }) {
  const st = useApi(() => finops.roi(), []);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const r: FinopsRoi | null = st.data;
  return (
    <section className="roi-section" aria-labelledby="roi-finops">
      {view === "assumptions" && (
        <h2 id="roi-finops" className="section-title">
          Reconciliation, invoices and data checks
        </h2>
      )}
      {st.loading && <Loading />}
      {st.error && <ErrorState error={st.error} onRetry={st.reload} />}
      {r && (
        <>
          {view === "results" && r.warnings.map((w) => (
            <InlineMessage key={w} kind="info">
              {w}
            </InlineMessage>
          ))}
          {view === "results" && Object.entries(r.engines).map(([engine, nums]) => (
            <table key={engine} className="data-table fo-table">
              <caption>{ENGINE_NAMES[engine] ?? engine}</caption>
              <tbody>
                {Object.entries(nums)
                  .filter(([k]) => k !== "source")
                  .map(([k, v]) => {
                    const n = v as RoiNumber;
                    return (
                      <tr key={k}>
                        <th scope="row">{NAMES[k] ?? k}</th>
                        <td className="num">{fmt(n)}</td>
                        <td>
                          <LabelBadge label={n.label as RoiLabel} />
                        </td>
                        <td className="small muted">{n.explanation}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          ))}
          {view === "assumptions" && <form
            className="fo-panel"
            onSubmit={async (e) => {
              e.preventDefault();
              setErr(null);
              const values: Record<string, number> = {};
              for (const [k, v] of Object.entries(draft)) if (v.trim() !== "") values[k] = Number(v);
              try {
                st.setData(await finops.setRoiAssumptions(values));
                setDraft({});
              } catch (x) {
                setErr(errorText(x));
              }
            }}
          >
            <div className="fo-cols">
              {Object.entries(r.assumptions).map(([k, a]) => (
                <label key={k} className="small">
                  {k.replace(/_/g, " ")} <LabelBadge label={a.label as RoiLabel} />
                  <input inputMode="decimal" placeholder={String(a.value)} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
                  <span className="muted">{a.explanation}</span>
                </label>
              ))}
            </div>
            <button className="btn btn-primary" type="submit" disabled={Object.keys(draft).length === 0}>
              Save assumptions
            </button>
            {err && <InlineMessage kind="error">{err}</InlineMessage>}
          </form>}
        </>
      )}
    </section>
  );
}
