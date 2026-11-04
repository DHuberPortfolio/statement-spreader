"""What real filings call things: each statement row's printed label beside the tag the filer gave that number.

    .venv/Scripts/python scripts/mine_labels.py --out eval/ontology/labels.json

Reads only the tuning half of the wide set (never the sealed half) and keeps rows of the primary statements. The result
is the evidence for config/ontology: which wordings exist, in which industries, and what the filer says they mean. The
tag is the filer's own statement of the concept, so it is also how scripts/eval_ontology.py checks a term for false
mappings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spreader.evaluation.ixbrl_truth import find_statements, read_facts  # noqa: E402


def clean(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", label.lower())).strip()


def rows_of(data: bytes) -> list[tuple[str, str, str]]:
    """(statement, cleaned label, tag) for each tagged row of the primary statements."""
    facts, _ = read_facts(data)
    seen: set[tuple[str, str, str]] = set()
    for skey, st in find_statements(facts).items():
        for f in st.facts:
            if f.row_label:
                seen.add((skey, clean(f.row_label), f"{f.prefix}:{f.concept}" if f.prefix != "us-gaap" else f.concept))
    return sorted(seen)


def one(item: tuple[str, dict[str, Any], Path]) -> tuple[str, list[tuple[str, str, str]]]:
    key, m, folder = item
    try:
        return m["sector"], rows_of((folder / "raw" / m["file"]).read_bytes())
    except Exception as exc:  # noqa: BLE001 - one unreadable filing must not stop the rest
        print(f"{key}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return m["sector"], []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/ontology/labels.json")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--set", default="eval/wide")
    a = ap.parse_args()
    folder = ROOT / a.set
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    items = [(k, m, folder) for k, m in manifest.items() if m.get("split") == "dev"]
    counts: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    with ProcessPoolExecutor(a.workers) as ex:
        for sector, rows in ex.map(one, items):
            for row in rows:
                counts[row][sector] += 1
    out = [{"statement": k[0], "label": k[1], "tag": k[2], "filings": sum(v.values()), "sectors": dict(v)}
           for k, v in sorted(counts.items(), key=lambda kv: -sum(kv[1].values()))]
    p = ROOT / a.out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"filings": len(items), "rows": out}, indent=0), encoding="utf-8")
    print(f"{len(items)} filings, {len(out)} label-and-tag pairs -> {p}")


if __name__ == "__main__":
    main()
