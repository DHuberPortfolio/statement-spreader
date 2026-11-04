import { describe, expect, it } from "vitest";
import type { DocumentRow } from "../api/types";
import { pageOfDocuments } from "./docList";

const doc = (name: string): DocumentRow => ({ id: name, filename: `${name}.htm`, company_name: name, filing: "10-K fiscal 2025" }) as unknown as DocumentRow;
const many = Array.from({ length: 60 }, (_, i) => doc(`Company ${i}`));

describe("pageOfDocuments", () => {
  it("shows one page at a time", () => {
    const p = pageOfDocuments(many, "", 2);
    expect(p.rows).toHaveLength(25);
    expect(p.rows[0]!.company_name).toBe("Company 25");
    expect(p.pages).toBe(3);
  });

  it("finds a company by part of its name, in any case", () => {
    const p = pageOfDocuments([doc("Southern Company"), doc("Yum! Brands, Inc.")], "  yum ", 1);
    expect(p.rows.map((d) => d.company_name)).toEqual(["Yum! Brands, Inc."]);
    expect(p.matches).toBe(1);
  });

  it("falls back to the last page when a search leaves fewer", () => {
    expect(pageOfDocuments(many, "Company 59", 3).page).toBe(1);
  });

  it("says when nothing matches", () => {
    expect(pageOfDocuments(many, "no such company", 1)).toMatchObject({ rows: [], matches: 0, pages: 1 });
  });
});
