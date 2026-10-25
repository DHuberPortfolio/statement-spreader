"""Scoring the scanner against workbooks whose problems are known.

Rules, fixed before the independent set was scored:
- A claim is one anchor cell reported at severity error or risk (several findings on one cell are one claim;
  anomalies are not claims). A claim is right when its cell, or a cell in its `group` or (for a loop) its cycle,
  is a planted problem's cell or group cell. Precision = right claims / claims; recall = problems found / problems.
- The kind is scored separately (kind agreement): a found problem whose finding names the planted kind, or a kind
  the truth lists in `also_ok`.
- Version changes: a material change reported at a labelled cell with the labelled kind (or a sheet change for the
  labelled sheet) is right; any other material change is a false alarm.
- Status quo baseline: what a simple "flag every typed number next to a formula and every formula that differs
  from the one to its left" check reports on the same workbooks, the noisy kind of tool the mandate warns about.
- Every workbook is hashed before and after scanning, to show the scanner never changed one.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any

from openpyxl.utils.cell import range_boundaries

from finops.core.evaluation import Rate, prf, rate_table, write_report
from finops.core.fingerprint import sha256_bytes

from .config import ScanSpec
from .diff import compare
from .scan import scan_workbook
from .workbook import WorkbookError, load

CLAIMED = ("error", "risk")


def _norm(sheet: str | None, cell: str | None) -> str:
    return f"{(sheet or '').strip(chr(39)).lower()}!{(cell or '').replace('$', '').upper()}"


def _cycle_cells(items: list[str]) -> set[str]:
    out = set()
    for x in items:
        if "!" in x:
            s, c = x.rsplit("!", 1)
            out.add(_norm(s, c))
    return out


def score_book(findings: list[Any], faults: list[dict[str, Any]]) -> dict[str, Any]:
    claims: dict[str, dict[str, Any]] = {}
    for f in findings:
        if f.severity not in CLAIMED:
            continue
        anchor = _norm(f.sheet, f.cell) if f.cell else _norm(f.sheet, "")
        c = claims.setdefault(anchor, {"cells": set(), "kinds": set(), "ids": []})
        c["cells"].add(anchor)
        c["cells"].update(_norm(f.sheet, g) for g in f.group)
        if f.kind == "CIRCULAR_REFERENCE":
            c["cells"].update(_cycle_cells(f.cells))
        c["kinds"].add(f.kind)
        c["ids"].append(f.id)
    truth = []
    for t in faults:
        cells = {_norm(t.get("sheet"), t.get("cell"))} | {_norm(t.get("sheet"), g) for g in t.get("group", [])}
        cells |= _cycle_cells(t.get("cycle", []))
        truth.append((t, cells))
    found, kind_ok, missed = 0, 0, []
    used: set[str] = set()
    for t, cells in truth:
        hits = [a for a, c in claims.items() if c["cells"] & cells]
        if hits:
            found += 1
            used.update(hits)
            kinds = set().union(*(claims[a]["kinds"] for a in hits))
            also = t.get("also_ok") or []
            ok = {t["kind"], *(also if isinstance(also, list) else [also])}
            if kinds & ok:
                kind_ok += 1
        else:
            missed.append({k: t.get(k) for k in ("sheet", "cell", "kind", "note")})
    false = [{"cell": a, "kinds": sorted(c["kinds"]), "ids": c["ids"]} for a, c in claims.items() if a not in used]
    return {"faults": len(truth), "found": found, "kind_agrees": kind_ok, "claims": len(claims),
            "right_claims": len(claims) - len(false), "missed": missed, "false_alarms": false}


def _in_legit(anchor: str, legit: list[dict[str, Any]]) -> str | None:
    sheet, cell = anchor.split("!", 1)
    for item in legit:
        if (item.get("sheet") or "").lower() != sheet:
            continue
        ref = str(item.get("cell") or "")
        try:
            c1, r1, c2, r2 = range_boundaries(ref.replace("$", ""))
        except (ValueError, TypeError):
            continue
        from openpyxl.utils.cell import column_index_from_string, coordinate_from_string
        try:
            col, row = coordinate_from_string(cell)
        except ValueError:
            continue
        cc = column_index_from_string(col)
        if (c1 or 1) <= cc <= (c2 or 16384) and (r1 or 1) <= row <= (r2 or 1_048_576):
            return str(item.get("what", ""))
    return None


def baseline(wb: Any) -> int:
    """Claims a naive checker makes: every typed number with a formula beside it, every formula unlike its left one."""
    n = 0
    for sh in wb.sheets.values():
        for (r, c), cell in sh.cells.items():
            left, right = sh.get(r, c - 1), sh.get(r, c + 1)
            typed_by_formula = cell.kind == "number" and any(x is not None and x.kind == "formula" for x in (left, right))
            unlike_left = cell.kind == "formula" and left is not None and left.kind == "formula" and left.sig != cell.sig
            n += typed_by_formula or unlike_left
    return n


def score_pair(before: bytes, after: bytes, names: tuple[str, str], truth: list[dict[str, Any]]) -> dict[str, Any]:
    comp = compare(load(names[0], before), load(names[1], after))
    material = [c for c in comp.changes if c.material]
    right, found, missed = set(), 0, []
    for t in truth:
        hit = None
        for i, c in enumerate(material):
            same_sheet = c.sheet.lower() == (t.get("sheet") or "").strip("'").lower()
            if t["kind"] in ("SHEET_ADDED", "SHEET_REMOVED"):
                ok = same_sheet and c.kind == t["kind"]
            else:
                ok = same_sheet and (c.cell or "").upper() == (t.get("cell") or "").upper() and c.kind == t["kind"]
            if ok:
                hit = i
                break
        if hit is None:
            missed.append(t)
        else:
            found += 1
            right.add(hit)
    false = [c.model_dump(include={"kind", "sheet", "cell", "detail"}) for i, c in enumerate(material) if i not in right]
    return {"changes": len(truth), "found": found, "reported": len(material), "right": len(right), "missed": missed,
            "false_alarms": false, "not_material_reported": sum(1 for c in comp.changes if not c.material),
            "summary": comp.summary}


def _scan_bytes(name: str, data: bytes, spec: ScanSpec) -> tuple[list[Any], Any, float]:
    before = sha256_bytes(data)
    t0 = time.perf_counter()
    wb = load(name, data, spec)
    findings, _ = scan_workbook(wb, spec)
    dt = time.perf_counter() - t0
    if sha256_bytes(data) != before:
        raise AssertionError(f"{name} changed while scanning")
    return findings, wb, dt


def score_set(books: list[tuple[str, bytes, list[dict[str, Any]], list[dict[str, Any]]]],
              pairs: list[tuple[str, bytes, str, bytes, list[dict[str, Any]]]], spec: ScanSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"books": {}, "pairs": {}}
    tot = {"faults": 0, "found": 0, "kind": 0, "claims": 0, "right": 0, "baseline": 0, "legit": 0, "legit_flagged": 0,
           "anomalies": 0}
    seconds = 0.0
    by_kind: dict[str, list[int]] = {}
    for name, data, faults, legit in books:
        findings, wb, dt = _scan_bytes(name, data, spec)
        s = score_book(findings, faults)
        s["legit_flagged"] = [dict(fa, legit=_in_legit(fa["cell"], legit)) for fa in s["false_alarms"] if _in_legit(fa["cell"], legit)]
        s["anomalies"] = sum(1 for f in findings if f.severity == "anomaly")
        s["baseline_claims"] = baseline(wb)
        s["seconds"] = round(dt, 3)
        out["books"][name] = s
        tot["faults"] += s["faults"]
        tot["found"] += s["found"]
        tot["kind"] += s["kind_agrees"]
        tot["claims"] += s["claims"]
        tot["right"] += s["right_claims"]
        tot["baseline"] += s["baseline_claims"]
        tot["legit"] += len(legit)
        tot["legit_flagged"] += len(s["legit_flagged"])
        tot["anomalies"] += s["anomalies"]
        seconds += dt
        missed = {(m["sheet"], m["cell"]) for m in s["missed"]}
        for t in faults:
            tally = by_kind.setdefault(t["kind"], [0, 0])
            tally[1] += 1
            tally[0] += (t.get("sheet"), t.get("cell")) not in missed
    ch = {"changes": 0, "found": 0, "reported": 0, "right": 0}
    for name, before, name2, after, truth in pairs:
        p = score_pair(before, after, (name, name2), truth)
        out["pairs"][f"{name} -> {name2}"] = p
        for k in ch:
            ch[k] += p[k]
    out["counts"] = {**tot, "seconds": round(seconds, 2), **{f"pair_{k}": v for k, v in ch.items()}}
    pr = prf(tot["right"], tot["claims"] - tot["right"], tot["faults"] - tot["found"])
    # Recall counts planted problems found (one finding can cover two problems, so not right claims).
    out["rates"] = {"precision": pr["precision"], "recall": Rate(tot["found"], tot["faults"]), "kind_agreement": Rate(tot["kind"], tot["found"]),
                    "change_precision": Rate(ch["right"], ch["reported"]), "change_recall": Rate(ch["found"], ch["changes"])}
    out["by_kind"] = {k: {"found": v[0], "planted": v[1]} for k, v in sorted(by_kind.items())}
    return out


def synthetic_set(seed: int) -> tuple[list[Any], list[Any]]:
    from .synthetic import generate

    books, pairs = generate(seed)
    return ([(b.name, b.data, b.faults, b.legit) for b in books],
            [(p.before.name, p.before.data, p.after.name, p.after.data, p.changes) for p in pairs])


def folder_set(folder: Path) -> tuple[list[Any], list[Any]]:
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    books = [(n, (folder / n).read_bytes(), t.get("faults", []), t.get("legit", [])) for n, t in truth["workbooks"].items()]
    pairs = [(d["before"], (folder / d["before"]).read_bytes(), d["after"], (folder / d["after"]).read_bytes(), d["changes"])
             for d in truth.get("diffs", [])]
    return books, pairs


def hostile_inputs() -> list[tuple[str, bytes, str]]:
    """Files a scanner meets in practice; each must be refused with a message or scanned, never crash."""
    from openpyxl import Workbook

    def xlsx(build: Any) -> bytes:
        wb = Workbook()
        build(wb)
        b = io.BytesIO()
        wb.save(b)
        return b.getvalue()

    def rezip(data: bytes, edit: Any) -> bytes:
        src = zipfile.ZipFile(io.BytesIO(data))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for i in src.infolist():
                body = src.read(i.filename)
                body = edit(i.filename, body)
                if body is not None:
                    z.writestr(i.filename, body)
        return out.getvalue()

    plain = xlsx(lambda wb: wb.active.append([1, 2, "=A1+B1"]))
    entity = rezip(plain, lambda n, b: re.sub(rb"^(<\?xml[^>]*\?>)?", rb"<!DOCTYPE x [<!ENTITY a \"aaaa\">]>", b, count=1)
                   if n == "xl/worksheets/sheet1.xml" else b)
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/worksheets/sheet1.xml", b"<a>" + b" " * (450 * 1024 * 1024) + b"</a>")
    return [
        ("empty.xlsx", b"", "refused"),
        ("old-format.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 504, "refused"),
        ("not-a-workbook.xlsx", b"PK\x03\x04 this is not a zip", "refused"),
        ("a-text-file.xlsx", b"Name,Amount\nA,1\n", "refused"),
        ("zip-not-excel.xlsx", _zip({"readme.txt": "hello"}), "refused"),
        ("binary.xlsb", _zip({"[Content_Types].xml": "<Types/>", "xl/workbook.bin": "x"}), "refused"),
        ("entities.xlsx", entity, "refused"),
        ("expands-to-450MB.xlsx", bomb.getvalue(), "refused"),
        ("truncated.xlsx", plain[: len(plain) // 2], "refused"),
        ("formula-only.xlsx", plain, "scanned"),
        ("odd-formulas.xlsx", xlsx(lambda wb: [wb.active.append(r) for r in (["=SUM(", "=1+", "=A1:A3 B2:C2", "=Tbl[Col]"],
                                                                            ["=LET(x,1,x+A1)", "=A1#", "=@A1", "=-(-A2)"])]),
         "scanned"),
        ("empty-workbook.xlsx", xlsx(lambda wb: None), "scanned"),
    ]


def _zip(files: dict[str, str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return b.getvalue()


def hostile(spec: ScanSpec) -> list[dict[str, Any]]:
    rows = []
    for name, data, expect in hostile_inputs():
        try:
            findings, _, _ = _scan_bytes(name, data, spec)
            got, msg = "scanned", f"{len(findings)} finding(s)"
        except WorkbookError as exc:
            got, msg = "refused", str(exc)
        except Exception as exc:  # noqa: BLE001 - the point is to record any crash
            got, msg = "crashed", f"{type(exc).__name__}: {exc}"
        rows.append({"file": name, "expected": expect, "result": got, "message": msg[:200]})
    return rows


def run_report(name: str, seeds: list[int], folders: list[Path], spec: ScanSpec | None = None) -> Path:
    spec = spec or ScanSpec()
    report: dict[str, Any] = {"engine": "sheets", "sets": {}}
    for seed in seeds:
        report["sets"][f"synthetic-{seed}"] = score_set(*synthetic_set(seed), spec)
    for f in folders:
        report["sets"][f.name] = score_set(*folder_set(f), spec)
    report["hostile"] = hostile(spec)
    # Stability: the same bytes give the same findings.
    b, _ = synthetic_set(seeds[0] if seeds else 1)
    a1 = [f.model_dump() for f in _scan_bytes(b[0][0], b[0][1], spec)[0]]
    a2 = [f.model_dump() for f in _scan_bytes(b[0][0], b[0][1], spec)[0]]
    report["stable"] = a1 == a2
    lines = [f"# Spreadsheet risk scanner: {name}", "",
             "Claims are anchor cells reported as error or risk; anomalies are listed but not counted. Every workbook was "
             "hashed before and after scanning and none changed.", ""]
    for set_name, s in report["sets"].items():
        c = s["counts"]
        lines += [f"## {set_name}", "", *rate_table([("Precision (claims that are planted problems)", s["rates"]["precision"]),
                                                    ("Recall (planted problems found)", s["rates"]["recall"]),
                                                    ("Kind agreement (found problems named right)", s["rates"]["kind_agreement"]),
                                                    ("Version changes: precision", s["rates"]["change_precision"]),
                                                    ("Version changes: recall", s["rates"]["change_recall"])]), "",
                  f"Workbooks {len(s['books'])}, planted problems {c['faults']}, claims {c['claims']}, anomalies {c['anomalies']}, "
                  f"legitimate exceptions listed {c['legit']} (flagged: {c['legit_flagged']}). Naive checker on the same files: "
                  f"{c['baseline']} claims. Scan time {c['seconds']} s.", ""]
        for bn, bs in s["books"].items():
            for m in bs["missed"]:
                lines.append(f"- missed in {bn}: {m['kind']} at {m['sheet']}!{m['cell']} ({m.get('note') or ''})")
            for fa in bs["false_alarms"]:
                lines.append(f"- false alarm in {bn}: {fa['cell']} {', '.join(fa['kinds'])}")
        for pn, ps in s["pairs"].items():
            for m in ps["missed"]:
                lines.append(f"- change missed in {pn}: {m['kind']} at {m.get('sheet')}!{m.get('cell')}")
            for fa in ps["false_alarms"]:
                lines.append(f"- change false alarm in {pn}: {fa['kind']} {fa['sheet']}!{fa.get('cell')}")
        lines.append("")
    lines += ["## Hostile files", "", "| File | Expected | Result | Message |", "|---|---|---|---|"]
    lines += [f"| {h['file']} | {h['expected']} | {h['result']} | {h['message']} |" for h in report["hostile"]]
    lines += ["", f"Same findings on a second scan of the same bytes: {report['stable']}."]
    from finops.core.fingerprint import content_hash
    from finops.evalsets import SHEETS_SEEDS

    datasets: list[str | dict[str, Any]] = [f"sheets-synthetic-{s}" if s in SHEETS_SEEDS else
                                            {"name": f"sheets-seed-{s}", "version": None, "note": "generated, unregistered seed"} for s in seeds]
    datasets += [f"sheets-{f.name}" if f.parent.name == "sheets" else {"name": str(f), "version": None} for f in folders]
    return write_report(name, report, lines, datasets=datasets, config={"scan_spec": content_hash(spec.model_dump())})
