// The app's map: one list the sidebar, the breadcrumbs and the page titles all read.

export type IconName = "home" | "statement" | "match" | "invoice" | "shield" | "grid" | "clock" | "target" | "wrench" | "menu";

export interface NavChild {
  to: string;
  label: string;
  /** Pages under this entry that are not in the menu, such as one run */
  alsoFor?: RegExp;
  /** shown only to someone with this permission */
  needs?: string;
}

export interface NavItem {
  to: string;
  label: string;
  hint: string;
  icon: IconName;
  active: (path: string) => boolean;
  /** shown only to someone with this permission */
  needs?: string;
  children?: NavChild[];
}

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "",
    items: [{ to: "/", label: "Overview", hint: "What needs attention", icon: "home", active: (p) => p === "/" }],
  },
  {
    group: "Daily work",
    items: [
      {
        to: "/statements", label: "Statements", hint: "Spread financial statements", icon: "statement",
        active: (p) => p.startsWith("/statements") || p.startsWith("/runs"),
        children: [
          { to: "/statements", label: "All statements", alsoFor: /^\/runs\// },
          { to: "/statements/add", label: "Add statements" },
        ],
      },
      {
        to: "/recon", label: "Reconciliation", hint: "Bank against ledger", icon: "match", active: (p) => p.startsWith("/recon"),
        children: [
          { to: "/recon", label: "All reconciliations", alsoFor: /^\/recon\/runs\// },
          { to: "/recon/new", label: "New reconciliation" },
        ],
      },
      {
        to: "/invoices", label: "Invoices", hint: "Match to orders and receipts", icon: "invoice", active: (p) => p.startsWith("/invoices"),
        children: [
          { to: "/invoices", label: "Invoice queue", alsoFor: /^\/invoices\/[0-9a-f]{64}/ },
          { to: "/invoices/add", label: "Add invoices" },
        ],
      },
    ],
  },
  {
    group: "Data checks",
    items: [
      {
        to: "/data-quality", label: "Data quality", hint: "Vendor and order exports", icon: "shield", active: (p) => p.startsWith("/data-quality"),
        children: [
          { to: "/data-quality", label: "Checked exports", alsoFor: /^\/data-quality\/runs\// },
          { to: "/data-quality/new", label: "Check an export" },
        ],
      },
      {
        to: "/spreadsheets", label: "Spreadsheets", hint: "Formula risks in workbooks", icon: "grid", active: (p) => p.startsWith("/spreadsheets"),
        children: [
          { to: "/spreadsheets", label: "Scanned workbooks", alsoFor: /^\/spreadsheets\/scans\// },
          { to: "/spreadsheets/new", label: "Scan a workbook" },
        ],
      },
    ],
  },
  {
    group: "Results",
    items: [
      {
        to: "/evaluation", label: "Accuracy", hint: "How often it is right", icon: "target",
        active: (p) => p.startsWith("/evaluation") || p.startsWith("/disagreements"),
        children: [
          { to: "/evaluation", label: "Summary" },
          { to: "/evaluation/errors", label: "Types of error" },
          { to: "/evaluation/reviewers", label: "Reviewer decisions" },
          { to: "/disagreements", label: "AI second opinions", needs: "adjudicate" },
        ],
      },
      {
        to: "/roi", label: "Time saved", hint: "Hours, cash and costs", icon: "clock", needs: "roi",
        active: (p) => p.startsWith("/roi") || p.startsWith("/sessions"),
        children: [
          { to: "/roi", label: "Summary" },
          { to: "/roi/value", label: "Hours and cash" },
          { to: "/roi/costs", label: "Costs" },
          { to: "/roi/errors", label: "Errors avoided" },
          { to: "/roi/scenarios", label: "What-if scenarios" },
          { to: "/roi/areas", label: "Reconciliation and more" },
          { to: "/roi/assumptions", label: "Assumptions" },
          { to: "/roi/timing", label: "Time a document", alsoFor: /^\/sessions\// },
        ],
      },
    ],
  },
  {
    group: "Technical",
    items: [
      {
        to: "/technical", label: "For engineers", hint: "Raw reports and rule data", icon: "wrench", active: (p) => p.startsWith("/technical"),
        children: [
          { to: "/technical", label: "Test reports" },
          { to: "/technical/rules", label: "Rule track record" },
          { to: "/technical/processing", label: "Processing", needs: "roi" },
        ],
      },
    ],
  },
];

export function normalPath(path: string): string {
  return path.replace(/\/+$/, "") || "/";
}

/** The menu entry for a page: exact first, then the pages it stands for. */
export function findPage(rawPath: string): { group: string; item: NavItem; child: NavChild | null } | null {
  const path = normalPath(rawPath);
  for (const g of NAV) {
    for (const item of g.items) {
      if (!item.active(path)) continue;
      const kids = item.children ?? [];
      const child = kids.find((c) => c.to === path) ?? kids.find((c) => c.alsoFor?.test(path)) ?? null;
      return { group: g.group, item, child };
    }
  }
  return null;
}

/** The browser-tab title and the trail above a page. */
export function pageTitle(path: string): string {
  const p = findPage(path);
  return p?.child && p.child.to !== p.item.to ? `${p.child.label} · ${p.item.label}` : p?.item.label ?? "Overview";
}

export function breadcrumbs(rawPath: string): { to: string; label: string }[] {
  const p = findPage(rawPath);
  if (!p?.child || normalPath(rawPath) !== p.child.to || p.child.to === p.item.to) return [];
  return [{ to: p.item.to, label: p.item.label }, { to: p.child.to, label: p.child.label }];
}
