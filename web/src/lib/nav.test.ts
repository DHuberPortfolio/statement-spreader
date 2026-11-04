import { describe, expect, it } from "vitest";
import { NAV, breadcrumbs, findPage, normalPath, pageTitle } from "./nav";

describe("the app's map", () => {
  it("finds the menu entry for sub-pages and for pages not in the menu", () => {
    expect(findPage("/roi/assumptions")?.child?.label).toBe("Assumptions");
    expect(findPage("/runs/17")?.child?.label).toBe("All statements");
    expect(findPage("/recon/runs/3/")?.child?.label).toBe("All reconciliations");
    expect(findPage("/sessions/4/baseline")?.child?.label).toBe("Time a document");
    expect(findPage("/disagreements")?.item.label).toBe("Accuracy");
  });

  it("gives sub-pages a trail and leaves section home pages without one", () => {
    expect(breadcrumbs("/roi/costs")).toEqual([
      { to: "/roi", label: "Time saved" },
      { to: "/roi/costs", label: "Costs" },
    ]);
    expect(breadcrumbs("/roi")).toEqual([]);
    expect(breadcrumbs("/runs/17")).toEqual([]);
  });

  it("names the tab after the page", () => {
    expect(pageTitle("/roi/costs")).toBe("Costs · Time saved");
    expect(pageTitle("/evaluation")).toBe("Accuracy");
    expect(pageTitle("/")).toBe("Overview");
  });

  it("lists every page once", () => {
    const seen = NAV.flatMap((g) => g.items.flatMap((i) => (i.children ?? []).map((c) => c.to)));
    expect(new Set(seen).size).toBe(seen.length);
  });

  it("ignores a trailing slash", () => {
    expect(normalPath("/roi/")).toBe("/roi");
    expect(normalPath("/")).toBe("/");
  });
});
