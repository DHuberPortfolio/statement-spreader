import { useEffect } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { BaselinePage } from "./pages/BaselinePage";
import { DataQualityListPage, DataQualityRunPage } from "./pages/DataQualityPage";
import { DisagreementsPage } from "./pages/DisagreementsPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ErrorTypesPage, EvaluationPage, ReviewersPage } from "./pages/EvaluationPage";
import { InvoiceDetailPage, InvoiceListPage } from "./pages/InvoicesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReconListPage, ReconRunPage } from "./pages/ReconPage";
import { RoiPage, TechnicalProcessingPage } from "./pages/RoiPage";
import { RunWorkspace } from "./pages/RunWorkspace";
import { SheetScanPage, SpreadsheetsPage } from "./pages/SpreadsheetsPage";
import { TechnicalReportsPage, TechnicalRulesPage } from "./pages/TechnicalPage";
import { normalPath, pageTitle } from "./lib/nav";
import { Link, match, useLocation } from "./lib/router";

export function App() {
  const { path } = useLocation();
  return (
    <ErrorBoundary key={path}>
      <Routes path={path} />
    </ErrorBoundary>
  );
}

const ROI_VIEWS = ["value", "costs", "errors", "scenarios", "areas", "assumptions", "timing"] as const;

function Routes({ path: rawPath }: { path: string }) {
  const path = normalPath(rawPath);

  useEffect(() => {
    document.title = `${pageTitle(path)} · Finance Operations`;
  }, [path]);

  const run = match(/^\/runs\/(\d+)\/?$/, path);
  if (run) return <RunWorkspace key={run[0]} runId={Number(run[0])} />;
  const baseline = match(/^\/sessions\/(\d+)\/baseline\/?$/, path);
  if (baseline) return <BaselinePage sessionId={Number(baseline[0])} />;
  if (path === "/roi") return <RoiPage view="summary" />;
  const roiView = ROI_VIEWS.find((v) => path === `/roi/${v}`);
  if (roiView) return <RoiPage view={roiView} />;
  if (path === "/evaluation") return <EvaluationPage />;
  if (path === "/evaluation/errors") return <ErrorTypesPage />;
  if (path === "/evaluation/reviewers") return <ReviewersPage />;
  if (path === "/disagreements") return <DisagreementsPage />;
  if (path === "/technical") return <TechnicalReportsPage />;
  if (path === "/technical/rules") return <TechnicalRulesPage />;
  if (path === "/technical/processing") return <TechnicalProcessingPage />;
  const reconRun = match(/^\/recon\/runs\/(\d+)\/?$/, path);
  if (reconRun) return <ReconRunPage key={reconRun[0]} runId={Number(reconRun[0])} />;
  if (path === "/recon") return <ReconListPage view="list" />;
  if (path === "/recon/new") return <ReconListPage view="new" />;
  const invoice = match(/^\/invoices\/([0-9a-f]{64})\/?$/, path);
  if (invoice) return <InvoiceDetailPage key={invoice[0]} docId={invoice[0] ?? ""} />;
  if (path === "/invoices") return <InvoiceListPage view="list" />;
  if (path === "/invoices/add") return <InvoiceListPage view="add" />;
  const gateRun = match(/^\/data-quality\/runs\/(\d+)\/?$/, path);
  if (gateRun) return <DataQualityRunPage key={gateRun[0]} runId={Number(gateRun[0])} />;
  if (path === "/data-quality") return <DataQualityListPage view="list" />;
  if (path === "/data-quality/new") return <DataQualityListPage view="new" />;
  const sheetScan = match(/^\/spreadsheets\/scans\/(\d+)\/?$/, path);
  if (sheetScan) return <SheetScanPage key={sheetScan[0]} scanId={Number(sheetScan[0])} />;
  if (path === "/spreadsheets") return <SpreadsheetsPage view="list" />;
  if (path === "/spreadsheets/new") return <SpreadsheetsPage view="new" />;
  if (path === "/statements" || path === "/statements/add")
    return (
      <Layout>
        <DocumentsPage view={path === "/statements" ? "list" : "add"} />
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
