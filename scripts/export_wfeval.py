"""Export engine outputs and answer keys for an independent second scorer: workflow-eval-harness (wfeval).

    .venv/Scripts/python scripts/export_wfeval.py            # writes eval/wfeval/<set>/{pred,key}.jsonl
    node <workflow-eval-harness>/bin/wfeval.js score --config eval/wfeval/invoice.config.json \
         --pred eval/wfeval/invoice-dev/pred.jsonl --key eval/wfeval/invoice-dev/key.jsonl

Why: this repository's own scorers were written alongside the engines. wfeval was written earlier, for other
workflows, and counts silent publishes and silent omissions its own way. If both agree, neither is likely to be
fooling us. The answer keys come from the generators, exactly as in scripts/run_eval.py.

One record per invoice (route = eligibility; codes = open exceptions above info) and one per reconciliation
unit (a true pairing, or a record with no counterpart; route = what happened to it; partners = the records an
automatic match tied it to).
"""

from __future__ import annotations

import json
from pathlib import Path

from finops.core.config import load_config
from finops.core.exceptions import ExceptionStatus, Severity
from finops.invoice.config import APPolicy
from finops.invoice.engine import history_entry, process
from finops.invoice.master import BankFingerprinter, load_master
from finops.invoice.matching import History
from finops.recon.config import ReconProfile
from finops.recon.engine import reconcile
from finops.recon.model import MatchStatus
from finops.recon.synthetic import generate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "wfeval"


def jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def invoices(name: str, folder: Path, policy_file: str) -> None:
    policy = load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / policy_file)[0]
    fp = BankFingerprinter(b"wfeval")
    master = load_master(folder / "master", policy.master_data.model_dump(), fp)
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    history, pred, key = History(), [], []
    for doc in truth["inbox"]:
        o = process(Path(doc["file"]).name, (folder / doc["file"]).read_bytes(), policy, master, history, fp)
        history.invoices.append(history_entry(o))
        codes = sorted({e.code for e in o.exceptions if e.status is ExceptionStatus.OPEN and e.severity is not Severity.INFO})
        pred.append({"id": doc["id"], "route": o.eligibility, "codes": codes})
        key.append({"id": doc["id"], "expected_route": "eligible_for_approval" if doc["expect"]["touchless"] else "needs_person",
                    "codes": sorted(doc["expect"]["codes"]), "trap": doc["kind"]})
    jsonl(OUT / name / "pred.jsonl", pred)
    jsonl(OUT / name / "key.jsonl", key)


def recon(name: str, seed: int, **opts: object) -> None:
    profile, version = load_config(ReconProfile, ROOT / "config" / "finops" / "recon" / "bank-vs-gl.yaml")
    bank, ledger, truth = generate(seed, 300, **opts)  # type: ignore[arg-type]
    res = reconcile("bank.csv", bank, "ledger.csv", ledger, profile, version)
    group_of = res.group_of()
    flagged = {s for e in res.exceptions for s in e.subjects}
    units = [(f"g{i}", t["left"] + t["right"], t["expect"], t["kind"], [t["left"] + a for a in t["alternatives"]])
             for i, t in enumerate(truth["groups"])]
    units += [(f"n:{n['id']}", [n["id"]], "alone", n["kind"], []) for n in truth["no_counterpart"]]
    pred, key = [], []
    for uid, members, expect, kind, alts in units:
        groups = {group_of[m].id: group_of[m] for m in members if m in group_of}
        auto = [g for g in groups.values() if g.status in (MatchStatus.AUTO, MatchStatus.ACCEPTED)]
        if auto:
            route, partners = "auto_matched", sorted({m for g in auto for m in g.left + g.right})
        elif groups or any(m in flagged for m in members):
            route, partners = "review", []
        else:
            route, partners = "nothing", []
        truth_partners = sorted(members) if expect != "alone" else []
        if auto and alts and sorted(partners) in [sorted(a) for a in alts]:
            truth_partners = sorted(partners)  # the key accepts either of two identical duplicate postings
        pred.append({"id": uid, "route": route, "partners": partners})
        key.append({"id": uid, "expected_route": "auto_matched" if expect == "auto" else "review",
                    "partners": truth_partners if expect == "auto" else [], "trap": kind})
    jsonl(OUT / name / "pred.jsonl", pred)
    jsonl(OUT / name / "key.jsonl", key)


def main() -> None:
    for name, folder, pol in (("invoice-dev", "dev", "default-ap.yaml"), ("invoice-holdout", "holdout", "default-ap.yaml"),
                              ("invoice-unseen-default", "unseen", "default-ap.yaml"),
                              ("invoice-messy-31", "messy-31", "example-all-known-wording.yaml"),
                              ("invoice-messy-32", "messy-32", "example-all-known-wording.yaml")):
        if (ROOT / "eval" / "invoice" / folder / "truth.json").exists():
            invoices(name, ROOT / "eval" / "invoice" / folder, pol)
    recon("recon-dev", 7)
    recon("recon-holdout", 11)
    recon("recon-stress", 13, round_share=0.4)
    recon("recon-messy-101", 101, round_share=0.2, messy=True)
    recon("recon-messy-103", 103, round_share=0.2, messy=True)
    print("written to", OUT)


if __name__ == "__main__":
    main()
