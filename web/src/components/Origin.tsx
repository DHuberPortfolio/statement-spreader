import type { DocumentRow } from "../api/types";

/** What to call a document: the company and filing when the cover page says, else its file name. */
export function documentTitle(doc: DocumentRow | null | undefined): string {
  if (!doc) return "Document";
  if (doc.label) return doc.label;
  if (doc.company_name) return `${doc.company_name}${doc.filing ? `, ${doc.filing}` : ""}`;
  return doc.filename;
}

export function OriginChip({ doc }: { doc: DocumentRow | null | undefined }) {
  if (doc?.origin === "generated") {
    return (
      <span className="chip chip-generated" title="A made-up company's statements, written to show the platform working. Not a real company.">
        Generated to prove concept
      </span>
    );
  }
  if (doc?.origin === "sec") {
    return (
      <span className="chip chip-sec" title="A real filing from the SEC's public EDGAR database. The name comes from its cover page.">
        Real SEC filing
      </span>
    );
  }
  return null;
}
