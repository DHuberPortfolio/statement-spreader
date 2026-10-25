"""Measuring the data-quality gate against synthetic exports with known answers (see synthetic.py).

What is counted, per row of each source file:
- a fault caught: the row needed attention (expected review, rejected or duplicate) and did not go through as an
  ordinary accepted record. A fault missed is the opposite: a bad record that would have been loaded.
- a false quarantine: a valid row (clean, or a legitimate oddity) sent to review or rejected.
- the reason: of the faults caught, how many carry the reason code(s) the generator injected.
- exact decision: the decision is the one expected (a definite error rejected, not merely reviewed).

Also measured: crashes on hostile files (a crash is any error other than a clean refusal), and stability: the same
inputs with their rows shuffled must give the same decision for every record.
"""

from __future__ import annotations

import csv
import io
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from finops.core.config import load_config
from finops.core.evaluation import Rate, rate_table, write_report

from .config import DatasetSpec
from .engine import GateInputError, GateResult, SourceInput, accepted_rows, gate
from .synthetic import generate


def score(result: GateResult, truth: list[dict[str, Any]], file_of: dict[str, str]) -> dict[str, Any]:
    by_pos = {(r.source, r.row): r for r in result.records}
    tally: Counter[str] = Counter()
    cases: dict[str, Counter[str]] = defaultdict(Counter)
    misses: list[dict[str, Any]] = []
    for t in truth:
        rec = by_pos.get((t["source"], t["row"]))
        if rec is None:
            tally["not_found"] += 1
            misses.append({**t, "got": "no record"})
            continue
        codes = {i.code for i in rec.issues}
        expect, got = t["expect"], rec.decision
        valid = expect == "accepted"
        c = cases[t["case"]]
        c["n"] += 1
        if valid:
            tally["valid"] += 1
            if t["case"] != "clean":
                tally["legit"] += 1
            if got != "accepted":
                tally["false_quarantine"] += 1
                if t["case"] != "clean":
                    tally["legit_quarantined"] += 1
                c["wrong"] += 1
                misses.append({**t, "got": got, "codes": sorted(codes)})
            else:
                c["right"] += 1
            continue
        tally["faults"] += 1
        caught = got == expect if expect == "duplicate" else got in ("review", "rejected")
        if not caught:
            tally["missed"] += 1
            c["wrong"] += 1
            misses.append({**t, "got": got, "codes": sorted(codes)})
            continue
        tally["caught"] += 1
        if set(t["codes"]) <= codes:
            tally["reason_right"] += 1
        else:
            misses.append({**t, "got": got, "codes": sorted(codes), "note": "caught, other reason"})
        if got == expect:
            tally["exact"] += 1
            c["right"] += 1
        else:
            tally["caught_other_severity"] += 1
            c["other_severity"] += 1
            misses.append({**t, "got": got, "codes": sorted(codes), "note": "caught, other severity"})
    quarantined = sum(1 for r in result.records if r.decision in ("review", "rejected"))
    return {
        "rates": {
            "faults_caught": Rate(tally["caught"], tally["faults"]),
            "faults_missed": Rate(tally["missed"], tally["faults"]),
            "reason_right": Rate(tally["reason_right"], tally["caught"]),
            "exact_decision_of_faults": Rate(tally["exact"], tally["faults"]),
            "false_quarantine": Rate(tally["false_quarantine"], tally["valid"]),
            "legit_oddities_quarantined": Rate(tally["legit_quarantined"], tally["legit"]),
            "quarantine_precision": Rate(quarantined - tally["false_quarantine"], quarantined),
        },
        "counts": dict(tally), "decisions": result.counts(),
        "cases": {k: dict(v) for k, v in sorted(cases.items())},
        "misses": misses[:200], "files": file_of,
    }


def _shuffle_csv(data: bytes, seed: int) -> bytes:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    head, body = rows[0], rows[1:]
    random.Random(seed).shuffle(body)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows([head] + body)
    return buf.getvalue().encode()


def _rows_csv(rows: list[dict[str, str]], columns: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def hostile_inputs(portal: bytes) -> list[tuple[str, str, bytes]]:
    """Files a gate meets in practice: each must be gated or refused with a reason, never crash."""
    header = portal.split(b"\n", 1)[0]
    body = portal.split(b"\n", 1)[1]
    return [
        ("empty file", "a.csv", b""),
        ("header only", "a.csv", header + b"\n"),
        ("missing a mapped column", "a.csv", header.replace(b"Supplier Name,", b"") + b"\n" + body),
        ("duplicate header", "a.csv", header + b",EIN\n" + body),
        ("binary garbage", "a.csv", bytes(range(256)) * 40),
        ("not a workbook", "a.xlsx", b"PK\x03\x04 not really a zip"),
        ("windows-1252 text", "a.csv", portal.decode("utf-8").encode("cp1252", errors="replace")),
        ("byte-order mark", "a.csv", b"\xef\xbb\xbf" + portal),
        ("ragged rows", "a.csv", header + b"\nV999,Short\n" + b"V998," + b"x," * 30 + b"\n"),
        ("huge cell", "a.csv", header + b"\n" + b"V997," + b"A" * 200_000 + b"\n"),
        ("unsupported type", "a.pdf", b"%PDF-1.4"),
        ("quotes and newlines", "a.csv", header + b'\n"V996","Line one\nLine two",,,,,,A,US,a@b.co,30,01/02/2024\n'),
    ]


def baseline_without_gate(vspec: DatasetSpec, pspec: DatasetSpec, s: Any, previous_csv: bytes) -> dict[str, Any]:
    """Today's path, for comparison: the exports renamed into the invoice engine's master format and loaded as they
    are. What happens: does the load work at all, and what goes in unnoticed."""
    from finops.core.tabular import read_table
    from finops.invoice.master import BankFingerprinter, load_master

    out: dict[str, Any] = {}
    vendor_rows: list[dict[str, str]] = []
    for sid, name, data in (("portal", "portal.csv", s.portal_csv), ("erp", "erp.xlsx", s.erp_xlsx)):
        cols = vspec.sources[sid].columns
        _, rows = read_table(name, data)
        vendor_rows += [{f: r.values.get(c, "") for f, c in cols.items()} for r in rows]
    _, po_rows = read_table("po.csv", s.po_csv)
    pcols = pspec.sources["erp"].columns
    pos = [{f: r.values.get(c, "") for f, c in pcols.items()} for r in po_rows]
    ids = Counter(v["vendor_id"] for v in vendor_rows if v["vendor_id"])
    out["vendor_ids_overwritten_silently"] = sum(n - 1 for n in ids.values() if n > 1)
    out["po_lines_with_unknown_vendor"] = sum(1 for p in pos if p["vendor_id"] not in ids)
    _, prev = read_table("previous.csv", previous_csv)
    prev_bank = {r.values["vendor_id"]: (r.values.get("bank_account", ""), r.values.get("routing_number", "")) for r in prev}
    out["bank_changes_loaded_unreviewed"] = sum(1 for v in vendor_rows if v["vendor_id"] in prev_bank
                                                and (v["bank_account"], v["routing_number"]) != prev_bank[v["vendor_id"]])
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "vendors.csv").write_bytes(_rows_csv(vendor_rows, list(vspec.fields)))
        (d / "purchase_orders.csv").write_bytes(_rows_csv(pos, list(pspec.fields)))
        (d / "receipts.csv").write_text("receipt_id,po_number,line_no,quantity_received,received_date,status\n")
        try:
            m = load_master(d, {"vendors": "vendors.csv", "purchase_orders": "purchase_orders.csv", "receipts": "receipts.csv"},
                            BankFingerprinter(b"k" * 32))
            out["load"] = f"loaded: {len(m.vendors)} vendors from {len(vendor_rows)} rows, {len(m.pos)} purchase orders"
        except Exception as exc:  # noqa: BLE001 - what the status quo does with this data is the measurement
            out["load"] = f"failed: {type(exc).__name__}: {str(exc)[:160]}"
    return out


def score_independent(folder: Path, vspec: DatasetSpec, pspec: DatasetSpec) -> dict[str, Any]:
    """A test set written by someone who did not see the gate's code: portal.csv, erp.xlsx, previous.csv, po.csv,
    truth.json, and optionally vendors_reference.csv (else the gate's own accepted vendors are the reference)."""
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    src = {"portal.csv": "portal", "erp.xlsx": "erp", "po.csv": "erp"}
    vt = [{**t, "source": src[t["file"]], "codes": []} for t in truth if t["file"] != "po.csv"]
    pt = [{**t, "source": "erp", "codes": []} for t in truth if t["file"] == "po.csv"]
    v = gate(vspec, [SourceInput("portal", "portal.csv", (folder / "portal.csv").read_bytes()),
                     SourceInput("erp", "erp.xlsx", (folder / "erp.xlsx").read_bytes())],
             previous=("previous.csv", (folder / "previous.csv").read_bytes()))
    ref = folder / "vendors_reference.csv"
    reference = ref.read_bytes() if ref.exists() else _rows_csv(accepted_rows(v), v.columns)
    p = gate(pspec, [SourceInput("erp", "po.csv", (folder / "po.csv").read_bytes())], references={"vendors": ("vendors.csv", reference)})
    return {"vendors": score(v, vt, {}), "purchase_orders": score(p, pt, {}),
            "reference": "the set's vendors_reference.csv" if ref.exists() else "the vendors this gate run accepted"}


def run_report(name: str, root: Path, seeds: dict[str, int]) -> list[str]:
    vspec, vver = load_config(DatasetSpec, root / "config" / "finops" / "dq" / "vendors.yaml")
    pspec, pver = load_config(DatasetSpec, root / "config" / "finops" / "dq" / "purchase_orders.yaml")
    report: dict[str, Any] = {"name": name, "vendors_config": vver, "po_config": pver, "sets": {}}
    lines = [f"# Data-quality gate evaluation: {name}", "",
             "Synthetic vendor-master and purchase-order exports with injected faults and legitimate oddities, each row "
             "labelled with the decision it should get (finops.dq.synthetic). Two source systems with different "
             "schemas feed one canonical vendor record; purchase orders are checked against the accepted vendors.", ""]
    for split, seed in seeds.items():
        s = generate(seed)
        inputs = [SourceInput("portal", "portal.csv", s.portal_csv), SourceInput("erp", "erp.xlsx", s.erp_xlsx)]
        v = gate(vspec, inputs, previous=("previous.csv", s.previous_csv), config_version=vver)
        accepted = _rows_csv(accepted_rows(v), v.columns)
        p = gate(pspec, [SourceInput("erp", "po.csv", s.po_csv)], references={"vendors": ("vendors.csv", accepted)},
                 config_version=pver)
        vs, ps = score(v, s.vendor_truth, {}), score(p, s.po_truth, {})
        # stability: the portal rows shuffled, the same decision for every record (ids are row-content hashes)
        v2 = gate(vspec, [SourceInput("portal", "portal.csv", _shuffle_csv(s.portal_csv, seed)), inputs[1]],
                  previous=("previous.csv", s.previous_csv), config_version=vver)
        before = {r.id: r.decision for r in v.records}
        after = {r.id: r.decision for r in v2.records}
        unstable = sorted(k for k in before if before.get(k) != after.get(k))
        base = baseline_without_gate(vspec, pspec, s, s.previous_csv)
        report["sets"][split] = {"seed": seed, "vendors": vs, "purchase_orders": ps, "unstable_records": unstable,
                                 "carried_forward": len(v.carried_forward), "missing_from_source": len(v.missing_from_source),
                                 "baseline_without_gate": base}
        lines += [f"## {split} (seed {seed})", "",
                  f"Vendors: {len(v.records)} rows ({v.counts()}); purchase-order lines: {len(p.records)} ({p.counts()}). "
                  f"Shuffled rerun: {len(unstable)} record(s) changed decision.", "",
                  "Without the gate (the same exports renamed into the invoice engine's master format and loaded as they "
                  f"are): the master load {base['load']}; {base['vendor_ids_overwritten_silently']} vendor row(s) would "
                  f"silently replace another with the same id, {base['po_lines_with_unknown_vendor']} PO line(s) name an "
                  f"unknown vendor, {base['bank_changes_loaded_unreviewed']} bank-detail change(s) would load unreviewed.", ""]
        _blocks(lines, (("Vendors", vs), ("Purchase-order lines", ps)))
    for folder in sorted((root / "eval" / "dq").glob("independent-*")) if (root / "eval" / "dq").exists() else []:
        ind = score_independent(folder, vspec, pspec)
        report["sets"][folder.name] = ind
        lines += [f"## {folder.name} (written by someone who did not see the gate's code)", "",
                  f"Purchase orders checked against {ind['reference']}. Reason codes are not scored here: the set's "
                  "labels give decisions only.", ""]
        _blocks(lines, (("Vendors", ind["vendors"]), ("Purchase-order lines", ind["purchase_orders"])), reasons=False)
    _hostile(report, lines, vspec, vver, seeds)
    from finops.evalsets import DQ_SEEDS

    datasets: list[str | dict[str, Any]] = [f"dq-{sp}" if DQ_SEEDS.get(sp) == sd else
                                            {"name": f"dq-seed-{sd}", "version": None, "note": "generated, unregistered seed"}
                                            for sp, sd in seeds.items()]
    datasets += [f"dq-{f.name}" for f in sorted((root / "eval" / "dq").glob("independent-*"))] if (root / "eval" / "dq").exists() else []
    write_report(name, report, lines, datasets=datasets, config={"vendors": vver, "purchase_orders": pver})
    return lines


def _blocks(lines: list[str], scored: tuple[tuple[str, dict[str, Any]], ...], reasons: bool = True) -> None:
    for label, sc in scored:
        rr = sc["rates"]
        rows = [("Faults caught (needed attention, did not go through)", rr["faults_caught"]),
                ("**Faults missed** (bad records that would have loaded)", rr["faults_missed"])]
        if reasons:
            rows.append(("Right reason, of faults caught", rr["reason_right"]))
        rows += [("Exact decision (errors rejected, suspicions reviewed), of faults", rr["exact_decision_of_faults"]),
                 ("**False quarantines** (valid records held)", rr["false_quarantine"]),
                 ("Legitimate oddities held", rr["legit_oddities_quarantined"]),
                 ("Quarantine precision (held records that needed it)", rr["quarantine_precision"])]
        lines += [f"**{label}**", ""] + rate_table(rows) + [""]
        wrong = [f"{k} ({c.get('wrong', 0)} of {c['n']})" for k, c in sc["cases"].items() if c.get("wrong")]
        if wrong:
            lines += ["Cases not decided as expected: " + ", ".join(wrong), ""]


def _hostile(report: dict[str, Any], lines: list[str], vspec: DatasetSpec, vver: str, seeds: dict[str, int]) -> None:
    crashes, handled = [], []
    for label, fname, data in hostile_inputs(generate(seeds[next(iter(seeds))]).portal_csv):
        try:
            gate(vspec, [SourceInput("portal", fname, data)], config_version=vver)
            handled.append((label, "gated"))
        except GateInputError as exc:
            handled.append((label, f"refused: {str(exc)[:90]}"))
        except Exception as exc:  # noqa: BLE001 - counting crashes is the point
            crashes.append((label, f"{type(exc).__name__}: {exc}"[:200]))
    report["hostile"] = {"crashes": crashes, "handled": handled}
    lines += ["## Hostile files", "", f"{len(crashes)} crash(es) in {len(crashes) + len(handled)} files.", ""]
    lines += [f"- {label}: {what}" for label, what in handled + crashes] + [""]
