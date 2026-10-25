"""Rebuild the statement reviewers' outcomes from the audit log (finops.core.outcomes, DECISIONS D40).

    .venv/Scripts/python scripts/export_outcomes.py                      # var/spreader.sqlite3 -> var/outcomes-rebuilt/
    .venv/Scripts/python scripts/export_outcomes.py --db path --out folder
    .venv/Scripts/python scripts/export_outcomes.py --summary            # what the live folder holds

The live folder is written as decisions happen. This rebuilds the same outcomes from the store's append-only events
(every approval, remap and exclusion), into a separate folder so nothing live is overwritten: for a folder that was
lost, for backfilling decisions made before outcomes were recorded, or to check that the two agree.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finops.core import outcomes  # noqa: E402
from finops.core.outcomes import Outcome  # noqa: E402
from spreader.contracts import Spread  # noqa: E402
from spreader.learning import NOT_JUDGED, approval_outcomes  # noqa: E402
from spreader.profile import load_profile  # noqa: E402
from spreader.store import Store  # noqa: E402


def rebuild(store: Store) -> list[Outcome]:
    profile = load_profile()
    out: list[Outcome] = []
    for e in store.query("SELECT * FROM events WHERE kind IN ('approve', 'remap_row', 'exclude_row') ORDER BY id"):
        payload = json.loads(e["payload"])
        refs = {"run": e["run_id"], "document": e["document_id"]}
        if e["kind"] == "approve":
            run = store.query("SELECT spread, state FROM runs WHERE id=?", (e["run_id"],))[0]
            spread = Spread.model_validate_json(run["spread"])
            state = json.loads(run["state"] or "{}")
            out += approval_outcomes(spread, state, {**refs, "company": payload.get("company_id")}, e["actor"], e["at"],
                                     profile.line_statement)
        elif payload.get("previous_rule") and payload["previous_rule"] not in NOT_JUDGED \
                and payload.get("previous_line") != payload.get("line"):
            out.append(Outcome(engine="statements", method=payload["previous_rule"], right=False,
                               how="excluded" if not payload.get("line") else "remapped",
                               subject=f"{payload['statement'].replace('_', ' ')}: '{payload['label']}' -> "
                                       f"{payload.get('previous_line')}",
                               decided_by=e["actor"], decided_at=e["at"],
                               refs={**refs, "statement": payload["statement"], "row": payload["row"],
                                     "line": payload.get("previous_line"), "moved_to": payload.get("line")}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "var" / "spreader.sqlite3"))
    ap.add_argument("--out", default=str(ROOT / "var" / "outcomes-rebuilt"))
    ap.add_argument("--summary", action="store_true", help="print what the live outcomes folder holds and stop")
    args = ap.parse_args()
    if args.summary:
        print(json.dumps(outcomes.summary(), indent=1))
        return
    rows = rebuild(Store(Path(args.db)))
    for engine in ("statements", "units"):
        outcomes.write_lines(Path(args.out) / f"{engine}.jsonl", [o for o in rows if o.engine == engine])
    print(f"{len(rows)} outcomes rebuilt into {args.out}")


if __name__ == "__main__":
    main()
