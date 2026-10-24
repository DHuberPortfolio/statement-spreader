"""Print a document's spread, checks and review items in the terminal (a debugging aid)."""

from __future__ import annotations

import sys

from spreader.ingest import read_path
from spreader.pipeline import spread_document
from spreader.profile import load_profile


def main() -> None:
    path = sys.argv[1]
    profile = load_profile()
    doc = read_path(path)
    spread, timings = spread_document(doc, profile)
    print(f"{doc.filename}: {len(doc.tables)} tables, timings {timings}")
    for skey, res in spread.statements.items():
        t = res.table
        print(f"\n== {skey} (table {t.table_index}, score {t.detection_score:.1f}) scale x{t.scale.multiplier:,} "
              f"[{t.scale.evidence}] shares x{t.share_scale.multiplier if t.share_scale else '-'}")
        print("   periods:", [p.key for p in t.periods], [p.assumed for p in t.periods if p.assumed])
        maps = {m.row_index: m for m in res.mappings}
        for r in t.rows:
            m = maps.get(r.index)
            vals = " | ".join(f"{(v.raw)}" for v in r.values.values())
            tag = f"{m.canonical or '-'} {m.method.value} {m.confidence:.2f}" if m else ""
            print(f"   [{r.role.value[:3]}] {r.label[:55]:55s} {r.unit.value[:5]:5s} {vals[:40]:40s} -> {tag}")
    print("\n== checks")
    for c in spread.checks:
        if c.status.value != "pass":
            print(f"   {c.status.value:7s} {c.id} {c.period}: {c.explanation}")
    print(f"   passed: {sum(c.status.value == 'pass' for c in spread.checks)} of {len(spread.checks)}")
    print("\n== review")
    for it in spread.review:
        print(f"   {it.severity.value:7s} {it.kind.value:16s} {it.message[:160]}")
    print("\n== ratios (latest period)")
    latest = spread.ratios[0].period if spread.ratios else None
    for r in spread.ratios:
        if r.period == latest:
            print(f"   {r.label:30s} {r.value if r.value is None else round(r.value, 4)} {r.reason or ''}")


if __name__ == "__main__":
    main()
