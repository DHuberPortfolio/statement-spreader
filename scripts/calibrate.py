"""Refit each method's confidence from labelled outcomes (finops.core.policy) and write config/calibration/<engine>.json.

    .venv/Scripts/python scripts/calibrate.py statements           # SEC dev split, one outcome per mapped row
    .venv/Scripts/python scripts/calibrate.py statements --model http://127.0.0.1:8088   # also the model tier
    .venv/Scripts/python scripts/calibrate.py recon                # 30 generated sets no evaluation uses
    .venv/Scripts/python scripts/calibrate.py statements --outcomes reviewer-decisions.jsonl   # add labelled outcomes

Outcomes come from answer keys today and can come from reviewer decisions later (`--outcomes`, one JSON object per
line: {"method": ..., "right": true, "source": ...}). The file records exactly what it was fitted on: the datasets and
their versions, the commit, the profile, the outcome count per source. Calibrating on the dev split and measuring on
it is what D5 did by hand; the holdout split is never used to fit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from finops.core import policy
from finops.core.evaluation import provenance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Statement mapping paths whose result is not a value placed on a line: they never auto-accept anything.
NOT_PLACEMENTS = {"none", "structure.cross_line_subtotal", "structure.ignored_section"}


def statements(model_url: str | None) -> tuple[list[tuple[str, bool, str]], dict]:
    from run_eval import sec_docs

    from spreader.evaluation.score import score
    from spreader.evaluation.truth import AnswerKey
    from spreader.ingest import read_document
    from spreader.pipeline import spread_document
    from spreader.profile import load_profile

    profile = load_profile()
    model = None
    if model_url:
        from spreader.llm.local import LocalModelMapper

        model = LocalModelMapper(model_url, model_name="qwen3-4b-instruct-2507-q4km")
    outcomes = []
    docs = sec_docs("dev")
    for t, raw, key_path in docs:
        spread, _ = spread_document(read_document(raw.name, raw.read_bytes()), profile, model=model)
        rows: dict[str, list] = {}
        for c in score(spread, AnswerKey.load(key_path)).cells:
            if c.found and c.mapping_ok is not None and c.row and c.line_pred is not None and c.rule not in NOT_PLACEMENTS:
                r = rows.setdefault(c.row, [c.rule, True])
                r[1] = r[1] and bool(c.mapping_ok)
        outcomes += [(rule, ok, "sec-dev answer keys") for rule, ok in rows.values()]
        print(f"{t:6s} {len(rows):4d} mapped rows judged")
    meta = {"profile": f"{profile.id} {profile.version}+{profile.content_hash}", "documents": len(docs),
            "model": model_url or "not used (the model tier is calibrated only when --model is given)"}
    return outcomes, {"datasets": ["sec-dev"], **meta}


def recon() -> tuple[list[tuple[str, bool, str]], dict]:
    from finops.core.config import load_config
    from finops.evalsets import RECON_CALIBRATION_KINDS, RECON_CALIBRATION_SEEDS, RECON_SCALE
    from finops.recon.config import ReconProfile
    from finops.recon.engine import reconcile
    from finops.recon.evaluate import _members
    from finops.recon.model import MatchStatus
    from finops.recon.synthetic import generate

    profile, version = load_config(ReconProfile, ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml")
    # Calibrate exactly what each rule settles on its own when run as configured (its AUTO matches): a rule's proposals
    # are a different path (a sum without a reference is proposed by design, D18), and mixing them in would rate the
    # automatic path by the proposals' precision. A pairing is right for automation only if it is a true pairing
    # that needs no person (the generator's "expect": "auto"). A rule that never settles anything has no outcomes,
    # so it stays uncalibrated and is proposed.
    outcomes = []
    for seed in RECON_CALIBRATION_SEEDS:
        for kind, (share, messy) in RECON_CALIBRATION_KINDS.items():
            bank, ledger, truth = generate(seed, RECON_SCALE, round_share=share, messy=messy)
            index = {}
            for t in truth["groups"]:
                index[_members(t["left"], t["right"])] = t
                for alt in t["alternatives"]:
                    index[_members(t["left"], alt)] = t
            result = reconcile("bank.csv", bank, "ledger.csv", ledger, profile, version, calibrated=False)
            for g in result.groups:
                if g.status is not MatchStatus.AUTO:
                    continue
                t = index.get(_members(g.left, g.right))
                outcomes.append((g.rule, t is not None and t["expect"] == "auto", f"recon-calibration {kind}"))
    return outcomes, {"datasets": ["recon-calibration"], "profile": f"{profile.id} {version}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=["statements", "recon"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--outcomes", action="append", default=[], help="extra labelled outcomes (JSONL)")
    ap.add_argument("--outcomes-dir", default=None,
                    help="also fit on reviewer decisions recorded in this folder (finops.core.outcomes; 'default' is "
                         "FINOPS_OUTCOMES_DIR or var/outcomes). Reconciliation outcomes are not fitted on (one-sided, D40)")
    ap.add_argument("--out", default=None, help="directory (default config/calibration)")
    args = ap.parse_args()
    if args.engine == "statements":
        outcomes, meta = statements(args.model)
        kw = {"unit": "a mapped statement row (all its periods right)", "person_methods": ["memory"],
              "derived_methods": ["structure.total_of_children"], "never_auto": ["model"]}
    else:
        outcomes, meta = recon()
        kw = {"unit": "a match a rule produced (right: a true pairing that needs no person)"}
    for extra in args.outcomes:
        outcomes += policy.read_outcomes(Path(extra))
    reviewer = 0
    if args.outcomes_dir and args.engine == "statements":
        from finops.core import outcomes as decisions

        folder = None if args.outcomes_dir == "default" else Path(args.outcomes_dir)
        recorded = decisions.as_calibration_outcomes(decisions.read("statements", folder))
        reviewer = len(recorded)
        outcomes += recorded
        meta["reviewer_outcomes"] = {"folder": str(folder or decisions.directory()), "count": reviewer}
    prov = provenance(meta.pop("datasets"), {})
    fitted = {**prov, **meta, "outcomes": len(outcomes), "extra_outcome_files": args.outcomes,
              "fitted_by": "scripts/calibrate.py"}
    cal = policy.fit(args.engine, outcomes=outcomes, fitted=fitted, **kw)
    path = policy.save(cal, Path(args.out) if args.out else None)
    for m, s in cal.methods.items():
        print(f"{m:40s} {s.right:5d} of {s.total:<5d} {s.rate:7.1%}  at least {s.low:6.1%}  {s.sources}")
    if args.outcomes_dir:
        print(f"Reviewer outcomes used: {reviewer}")
    print(f"Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
