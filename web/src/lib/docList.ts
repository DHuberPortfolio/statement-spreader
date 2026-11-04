import { documentTitle } from "../components/Origin";
import type { DocumentRow } from "../api/types";

export const DOCS_PER_PAGE = 25;

export interface DocPage {
  rows: DocumentRow[];
  matches: number;
  page: number;
  pages: number;
}

/** One page of the statements list, filtered by company or filing. A page past the end shows the last one. */
export function pageOfDocuments(docs: DocumentRow[], query: string, page: number, size = DOCS_PER_PAGE): DocPage {
  const q = query.trim().toLowerCase();
  const found = q ? docs.filter((d) => `${documentTitle(d)} ${d.filename}`.toLowerCase().includes(q)) : docs;
  const pages = Math.max(1, Math.ceil(found.length / size));
  const at = Math.min(Math.max(1, page), pages);
  return { rows: found.slice((at - 1) * size, at * size), matches: found.length, page: at, pages };
}
