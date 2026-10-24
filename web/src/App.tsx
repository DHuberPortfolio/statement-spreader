import { useEffect } from "react";
import { Layout } from "./components/Layout";
import { BaselinePage } from "./pages/BaselinePage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { RoiPage } from "./pages/RoiPage";
import { RunWorkspace } from "./pages/RunWorkspace";
import { Link, match, useLocation } from "./lib/router";

const TITLES: [RegExp, string][] = [
  [/^\/runs\//, "Run"],
  [/^\/roi/, "ROI"],
  [/^\/sessions\//, "Baseline session"],
  [/^\/evaluation/, "Evaluation"],
];

export function App() {
  const { path } = useLocation();

  useEffect(() => {
    const t = TITLES.find(([re]) => re.test(path))?.[1] ?? "Documents";
    document.title = `${t} · Statement Spreader`;
  }, [path]);

  const run = match(/^\/runs\/(\d+)\/?$/, path);
  if (run) return <RunWorkspace key={run[0]} runId={Number(run[0])} />;
  const baseline = match(/^\/sessions\/(\d+)\/baseline\/?$/, path);
  if (baseline) return <BaselinePage sessionId={Number(baseline[0])} />;
  if (path === "/roi" || path === "/roi/") return <RoiPage />;
  if (path === "/evaluation" || path === "/evaluation/") return <EvaluationPage />;
  if (path === "/" || path === "/index.html")
    return (
      <Layout>
        <DocumentsPage />
      </Layout>
    );
  return (
    <Layout>
      <div className="state state-empty">
        <h1>Page not found</h1>
        <p>
          <Link to="/">Back to the documents</Link>
        </p>
      </div>
    </Layout>
  );
}
