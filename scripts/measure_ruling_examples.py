"""Do earlier rulings shown in the prompt make the model place lines better? (DECISIONS D55)

    llama-server -m Qwen3-4B-Instruct-2507-Q4_K_M.gguf -ngl 99 -c 8192 --host 127.0.0.1 --port 8088
    .venv/Scripts/python scripts/measure_ruling_examples.py --out eval/reports/ruling-examples-<date>.json

A simulation of the learning period on the SEC dev split, judged by its answer keys:

1. The model is asked where each row belongs, without examples, on every filing (the shadow role, D52). Only rows
   the key can judge are used: rows the rules placed whose cells the key ties to a line.
2. The filings are split in two by ticker order. On the teaching half, every row the model got wrong becomes a
   senior's ruling with the key's line, as a senior would rule on a disagreement.
3. On the other half, rows for which a similar ruled label exists are asked again with those rulings in the prompt;
   the rest keep their first answer. The two results are compared row by row.

The rulings are simulated from the answer keys, not made by people, and the filings are public SEC filings, not a
lender's documents: this measures the mechanism, not a production result.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


class _Store:
    """The two queries spreader.teaching.RulingExamples makes, on an in-memory table of simulated rulings."""

    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE disagreements (id INTEGER PRIMARY KEY, statement TEXT, label TEXT, section TEXT, "
                        "status TEXT, document_id TEXT, correct_line TEXT, analyst_line TEXT, ruled_at TEXT)")

    def query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()


def main() -> int:
    from run_eval import sec_docs

    from spreader.evaluation.score import _equivalent, score
    from spreader.evaluation.stats import wilson
    from spreader.evaluation.truth import AnswerKey
    from spreader.ingest import read_document
    from spreader.llm import local as local_mod
    from spreader.mapping import _unit_ok
    from spreader.pipeline import spread_document
    from spreader.profile import load_profile
    from spreader.teaching import RulingExamples

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8088")
    ap.add_argument("--model-name", default="Qwen3-4B-Instruct-2507-Q4_K_M")
    ap.add_argument("--cache", default=str(ROOT / "var" / "experiments" / "ruling-examples-cache.sqlite3"))
    ap.add_argument("--out")
    ap.add_argument("--similarity", choices=["token_set", "token_sort"], help="override spreader.teaching.SIMILARITY")
    args = ap.parse_args()
    if args.similarity:
        import spreader.teaching as teaching

        teaching.SIMILARITY = args.similarity

    import httpx

    for _ in range(120):  # the server loads the model first
        try:
            if httpx.get(f"{args.url}/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise SystemExit(f"no model server at {args.url}")
    local_mod.CACHE = Path(args.cache)  # a rerun asks nothing it has asked before
    mapper = local_mod.LocalModelMapper(args.url, model_name=args.model_name)
    profile = load_profile()
    docs = sec_docs("dev")
    t0 = time.perf_counter()
    cases: list[dict[str, Any]] = []
    contexts: dict[tuple[str, str], tuple[Any, Any, list[Any]]] = {}
    for ticker, raw, key_path in docs:
        spread, _ = spread_document(read_document(raw.name, raw.read_bytes()), profile)
        truth: dict[str, str] = {}
        for c in score(spread, AnswerKey.load(key_path)).cells:
            if c.found and c.row and c.line_truth:
                truth.setdefault(c.row, c.line_truth)
        for rowkey, line in truth.items():
            skey, idx = rowkey.rsplit(":", 1)
            res = spread.statements[skey]
            row = next(r for r in res.table.rows if r.index == int(idx))
            lines = [ln for ln in profile.statements[res.table.statement].lines if _unit_ok(ln, row)]
            answer = mapper.ask(res.table, row, lines)
            cases.append({"ticker": ticker, "doc": spread.doc_id, "row": rowkey, "statement": skey, "label": row.label,
                          "section": row.section.split(" > ")[-1] if row.section else "", "truth": line,
                          "before": answer})
            contexts[(ticker, rowkey)] = (res.table, row, lines)
        print(f"{ticker:6s} {len(truth):4d} judged rows", flush=True)

    def right(answer: str | None, truth: str) -> bool:
        return answer is not None and (answer == truth or _equivalent(answer, truth))

    tickers = [t for t, _, _ in docs]
    teach = set(tickers[0::2])
    store = _Store()
    for c in cases:
        if c["ticker"] in teach and not right(c["before"], c["truth"]):
            store.db.execute("INSERT INTO disagreements(statement, label, section, status, document_id, correct_line, "
                             "analyst_line, ruled_at) VALUES (?,?,?,?,?,?,?,?)",
                             (c["statement"], c["label"], c["section"], "ruled", c["doc"], c["truth"], c["truth"],
                              "2026-10-29T00:00:00+00:00"))
    rulings = store.query("SELECT COUNT(*) AS n FROM disagreements")[0]["n"]
    mapper.examples = RulingExamples(store)
    test = [c for c in cases if c["ticker"] not in teach]
    shown = 0
    for c in test:
        table, row, lines = contexts[(c["ticker"], c["row"])]
        ex = mapper.examples.for_row(c["statement"], c["label"], c["doc"], {ln.id for ln in lines})
        c["examples"] = len(ex)
        if ex:
            shown += 1
            c["after"] = mapper.ask(table, row, lines)
        else:
            c["after"] = c["before"]

    n = len(test)
    before = sum(right(c["before"], c["truth"]) for c in test)
    after = sum(right(c["after"], c["truth"]) for c in test)
    with_ex = [c for c in test if c["examples"]]
    fixed = sum(not right(c["before"], c["truth"]) and right(c["after"], c["truth"]) for c in with_ex)
    broken = sum(right(c["before"], c["truth"]) and not right(c["after"], c["truth"]) for c in with_ex)
    report = {
        "measured_at": time.strftime("%Y-%m-%d"), "model": args.model_name, "split": "sec dev",
        "similarity": args.similarity or "token_set",
        "documents": {"teaching": len(teach), "testing": len(tickers) - len(teach)},
        "simulated_rulings": rulings, "test_rows": n, "rows_shown_examples": shown,
        "right_before": before, "right_after": after,
        "rate_before": before / n, "rate_after": after / n,
        "interval_before": wilson(before, n), "interval_after": wilson(after, n),
        "fixed": fixed, "broken": broken, "model_errors": mapper.errors, "seconds": time.perf_counter() - t0,
        "rows_with_examples": {"n": len(with_ex), "right_before": sum(right(c["before"], c["truth"]) for c in with_ex),
                               "right_after": sum(right(c["after"], c["truth"]) for c in with_ex)},
        "cases": test,
    }
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    if args.out:
        Path(args.out).write_bytes(json.dumps(report, indent=2).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
