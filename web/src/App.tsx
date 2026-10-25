import { useEffect } from "react";
import { Layout } from "./components/Layout";
import { BaselinePage } from "./pages/BaselinePage";
import { DataQualityListPage, DataQualityRunPage } from "./pages/DataQualityPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { InvoiceDetailPage, InvoiceListPage } from "./pages/InvoicesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReconListPage, ReconRunPage } from "./pages/ReconPage";
import { RoiPage } from "./pages/RoiPage";
import { RunWorkspace } from "./pages/RunWorkspace";
import { SheetScanPage, SpreadsheetsPage } from "./pages/SpreadsheetsPage";
import { Link, match, useLocation } from "./lib/router";

const TITLES: [RegExp, string][] = [
  [/^\/runs\//, "Run"],
  [/^\/statements/, "Statements"],
  [/^\/roi/, "Time saved"],
  [/^\/sessions\//, "Baseline session"],
  [/^\/evaluation/, "Accuracy"],
  [/^\/recon/, "Reconciliation"],
  [/^\/invoices/, "Invoices"],
  [/^\/data-quality/, "Data quality"],
  [/^\/spreadsheets/, "Spreadsheets"],
];

export function App() {
  const { path } = useLocation();

  useEffect(() => {
    const t = TITLES.find(([re]) => re.test(path))?.[1] ?? "Overview";
    document.title = `${t} · Finance Operations`;
  }, [path]);

  const run = match(/^\/runs\/(\d+)\/?$/, path);
  if (run) return <RunWorkspace key={run[0]} runId={Number(run[0])} />;
  const baseline = match(/^\/sessions\/(\d+)\/baseline\/?$/, path);
  if (baseline) return <BaselinePage sessionId={Number(baseline[0])} />;
  if (path === "/roi" || path === "/roi/") return <RoiPage />;
  if (path === "/evaluation" || path === "/evaluation/") return <EvaluationPage />;
  const reconRun = match(/^\/recon\/runs\/(\d+)\/?$/, path);
  if (reconRun) return <ReconRunPage key={reconRun[0]} runId={Number(reconRun[0])} />;
  if (path === "/recon" || path === "/recon/") return <ReconListPage />;
  const invoice = match(/^\/invoices\/([0-9a-f]{64})\/?$/, path);
  if (invoice) return <InvoiceDetailPage key={invoice[0]} docId={invoice[0] ?? ""} />;
  if (path === "/invoices" || path === "/invoices/") return <InvoiceListPage />;
  const gateRun = match(/^\/data-quality\/runs\/(\d+)\/?$/, path);
  if (gateRun) return <DataQualityRunPage key={gateRun[0]} runId={Number(gateRun[0])} />;
  if (path === "/data-quality" || path === "/data-quality/") return <DataQualityListPage />;
  const sheetScan = match(/^\/spreadsheets\/scans\/(\d+)\/?$/, path);
  if (sheetScan) return <SheetScanPage key={sheetScan[0]} scanId={Number(sheetScan[0])} />;
  if (path === "/spreadsheets" || path === "/spreadsheets/") return <SpreadsheetsPage />;
  if (path === "/statements" || path === "/statements/")
    return (
      <Layout>
        <DocumentsPage />
      </Layout>
    );
  if (path === "/" || path === "/index.html")
    return (
      <Layout>
        <OverviewPage />
      </Layout>
    );
  return (
    <Layout>
      <div className="state state-empty">
        <h1>Page not found</h1>
        <p>
          <Link to="/">Back to the overview</Link>
        </p>
      </div>
    </Layout>
  );
}
