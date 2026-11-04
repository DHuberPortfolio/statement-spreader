"""Does the ontology place rows where the filer says they belong? The false-mapping test (D67).

    .venv/Scripts/python scripts/eval_ontology.py --set eval/vocab --split dev --save vocab-dev

Each row of a real statement carries the filer's own tag. For a row the ontology placed, the tag says what the filer meant, and the
crosswalk in spreader.evaluation.ixbrl_truth says which template line that tag feeds. Agreement is a right placement; a different
line is a false mapping. A tag the crosswalk does not know decides nothing, and is counted as unjudged. The sealed half is refused
unless --open-seal is given, and each opening is logged.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spreader.evaluation.ixbrl_truth import crosswalk_for, read_facts  # noqa: E402
from spreader.evaluation.stats import wilson  # noqa: E402
from spreader.ingest import read_document  # noqa: E402
from spreader.pipeline import document_industries, spread_document  # noqa: E402
from spreader.profile import load_profile  # noqa: E402

PROFILE_FILES = {"us-bank": ROOT / "config/profiles/us-bank.yaml", "us-insurer": ROOT / "config/profiles/us-insurer.yaml", "us-commercial": None}
_NUMBERS: dict[str, Any] = {}


def tags_by_value(data: bytes) -> dict[tuple[str, str], set[str]]:
    """(cleaned printed label, number as shown) -> tags the filer gave that row."""
    from mine_labels import clean

    facts, _ = read_facts(data)
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    for f in facts:
        if f.row_label:
            out[(clean(f.row_label), str(abs(f.printed).normalize()))].add(f.concept)
    return out


def one(item: tuple[str, dict[str, Any], str]) -> dict[str, Any]:
    key, m, folder = item
    path = Path(folder) / "raw" / m["file"]
    out: dict[str, Any] = {"doc": key, "sector": m["sector"], "rows": [], "error": None, "industries": []}
    try:
        data = path.read_bytes()
        profile = load_profile(PROFILE_FILES[m["profile"]])
        cw = crosswalk_for(profile)
        spread, _ = spread_document(read_document(path.name, data), profile)
        out["industries"] = sorted(document_industries((r.table for r in spread.statements.values()), profile.id))
        tags = tags_by_value(data)
        for skey, res in spread.statements.items():
            rows = {r.index: r for r in res.table.rows}
            for mp in res.mappings:
                if not (mp.rule.startswith("ontology") and mp.rule != "ontology.part_exceeds_total"):
                    continue
                row = rows[mp.row_index]
                from mine_labels import clean

                seen: set[str] = set()
                for v in row.values.values():
                    if v.displayed is None:
                        continue
                    for mult in (1, 1000, 1000000):
                        seen |= tags.get((clean(row.label), str(abs(v.displayed * mult).normalize())), set())
                own = {ln.id for ln in next(s.lines for k, s in profile.statements.items() if k.value == str(skey))}
                lines = {cw[t] for t in seen if cw.get(t) in own}  # a tag can sit on two statements: only this one's lines judge
                if mp.rule == "ontology.disclosure":
                    verdict = "unjudged" if not lines else "false_disclosure"
                elif not lines:
                    verdict = "unjudged"
                else:
                    verdict = "right" if mp.canonical in lines else "false"
                out["rows"].append({"label": row.label_clean, "statement": str(skey), "concept": mp.concept, "line": mp.canonical, "rule": mp.rule,
                                    "tags": sorted(seen)[:4], "filer_lines": sorted(lines), "verdict": verdict})
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval/vocab")
    ap.add_argument("--split", default="dev", choices=["dev", "sealed"])
    ap.add_argument("--open-seal", action="store_true")
    ap.add_argument("--save", default="ontology")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    folder = (ROOT / a.set).resolve()
    if a.split == "sealed":
        if not a.open_seal:
            raise SystemExit("The sealed half is opened only with --open-seal, and the opening is logged.")
        with (folder / "seal-log.txt").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} opened: {a.save}\n")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    items = [(k, m, str(folder)) for k, m in manifest.items() if m.get("split") == a.split]
    with ProcessPoolExecutor(a.workers) as ex:
        docs = list(ex.map(one, items))
    rows = [r for d in docs for r in d["rows"]]
    verdicts = Counter(r["verdict"] for r in rows)
    judged = verdicts["right"] + verdicts["false"]
    low = wilson(verdicts["right"], judged)[0] if judged else None
    wrong = Counter((r["concept"], r["label"], r["line"], tuple(r["filer_lines"])) for r in rows if r["verdict"] in {"false", "false_disclosure"})
    detect: dict[str, Counter[str]] = defaultdict(Counter)
    for d in docs:
        detect[d["sector"]].update(d["industries"] or ["(none)"])
    report = {"set": a.set, "split": a.split, "filings": len(docs), "crashed": [d["doc"] for d in docs if d["error"]], "verdicts": dict(verdicts),
              "judged": judged, "right_low": low, "false_mappings": [{"concept": k[0], "label": k[1], "line": k[2], "filer_lines": list(k[3]), "n": n} for k, n in wrong.most_common()],
              "industry_detected": {k: dict(v) for k, v in sorted(detect.items())}, "rows": rows}
    out = ROOT / "eval" / "reports" / f"{a.save}.json"
    out.write_text(json.dumps(report, indent=0), encoding="utf-8")
    print(f"{len(docs)} filings, {len(report['crashed'])} crashed, {dict(verdicts)}; right {verdicts['right']} of {judged}, low {low}")
    print(json.dumps(report["industry_detected"]))
    for k, n in wrong.most_common(40):
        print(n, k)


if __name__ == "__main__":
    main()
