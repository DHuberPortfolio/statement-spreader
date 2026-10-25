"""Operational check: every engine's real workflow, end to end through the API, in a throwaway data folder.

    .venv/Scripts/python scripts/smoke_check.py

Statements (upload with a company, review, approve, export, a second year compared with the first, set a company
after upload), reconciliation (sample run, accept and reject, resolve an exception, export), invoices (sample inbox,
detail, resolve, export), data-quality gate (sample, release a held record, export), spreadsheet scanner (sample,
confirm a finding, export), ROI, evaluation, the reviewer-outcomes feed and the web pages. Each step prints PASS or
FAIL with the reason; the exit code is the number of failures. Nothing outside the temporary folder is touched.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(tempfile.mkdtemp(prefix="smoke-"))
os.environ["SPREADER_DATA"] = str(DATA)
os.environ["FINOPS_OUTCOMES_DIR"] = str(DATA / "outcomes")
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from spreader import api  # noqa: E402

H = {"X-Actor": "Smoke Reviewer"}
client = TestClient(api.app)
results: list[tuple[str, bool, str, float]] = []


def step(name: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    def wrap(fn: Callable[[], str]) -> Callable[[], str]:
        t = time.perf_counter()
        try:
            note = fn() or ""
            results.append((name, True, note, time.perf_counter() - t))
        except Exception as exc:  # noqa: BLE001 - every failure is reported, the run continues
            results.append((name, False, f"{type(exc).__name__}: {exc}"[:300], time.perf_counter() - t))
        return fn
    return wrap


def ok(r: Any, what: str) -> Any:
    if r.status_code >= 400:
        raise AssertionError(f"{what}: HTTP {r.status_code} {r.text[:200]}")
    return r.json() if "json" in r.headers.get("content-type", "") else r


def check(cond: bool, why: str) -> None:
    if not cond:
        raise AssertionError(why)


state: dict[str, Any] = {}
SYN = ROOT / "eval" / "synthetic"


@step("health and profile")
def _health() -> str:
    h = ok(client.get("/api/health"), "health")
    p = ok(client.get("/api/profile"), "profile")
    check(h["ok"] and p["statements"], "health or profile empty")
    return f"version {h['version']}, profile {h['profile']}"


@step("statements: upload with a company, read, approve, export")
def _statements() -> str:
    f = SYN / "s7-001-clean" / "statement.html"
    run = ok(client.post("/api/documents", files={"file": (f.name, f.read_bytes())}, data={"company_id": "Smoke Co"},
                         headers=H), "upload")
    check(run["run"]["status"] == "succeeded", f"run {run['run']['status']}")
    rid = run["run"]["id"]
    blockers = [i for i in run["spread"]["review"] if i["severity"] == "blocker" and not i["resolved"]]
    check(not blockers, f"{len(blockers)} blockers on a clean synthetic statement")
    for stmt in run["spread"]["statements"]:
        ok(client.get(f"/api/runs/{rid}/source/{stmt}"), f"source {stmt}")
    after = ok(client.post(f"/api/runs/{rid}/actions", json={"type": "approve"}, headers=H), "approve")
    check(after["run"]["state"]["approved"]["by"] == "Smoke Reviewer", "approval not recorded")
    for fmt in ("xlsx", "csv", "json"):
        r = client.get(f"/api/runs/{rid}/export.{fmt}")
        check(r.status_code == 200 and len(r.content) > 100, f"export {fmt} HTTP {r.status_code}")
    ok(client.get(f"/api/runs/{rid}/events"), "events")
    state["doc"] = run["run"]["document_id"]
    return f"run {rid}: {len(run['spread']['values'])} values, approved, 3 exports"


@step("statements: the next document of the company is compared with the approved one")
def _company() -> str:
    f = SYN / "s7-002-clean" / "statement.html"
    run = ok(client.post("/api/documents", files={"file": (f.name, f.read_bytes())}, headers=H), "upload")
    moved = ok(client.post(f"/api/documents/{run['run']['document_id']}/company", json={"company_id": "Smoke Co"},
                           headers=H), "set company")
    check(moved["run"]["id"] != run["run"]["id"], "setting the company did not re-run the document")
    companies = ok(client.get("/api/companies"), "companies")
    smoke = next(c for c in companies if c["company_id"] == "Smoke Co")
    check(smoke["documents"] == 2 and smoke["approved_spreads"] == 1, f"companies: {smoke}")
    refused = client.post(f"/api/documents/{state['doc']}/company", json={"company_id": "Other"}, headers=H)
    check(refused.status_code == 400, "an approved document's company could be changed")
    return "company set after upload re-ran it; approved document kept its company"


@step("statements: documents list and summaries")
def _docs() -> str:
    docs = ok(client.get("/api/documents"), "documents")
    check(len(docs) == 2 and all(d["summary"] for d in docs), "missing documents or summaries")
    return f"{len(docs)} documents"


@step("reconciliation: sample run, accept, reject, resolve, export")
def _recon() -> str:
    profiles = ok(client.get("/api/finops/recon/profiles"), "profiles")
    wid = ok(client.post("/api/finops/recon/workspaces", json={"name": "Smoke", "profile": profiles[0]["file"]},
                         headers=H), "workspace")["id"]
    run = ok(client.post(f"/api/finops/recon/workspaces/{wid}/sample", json={}, headers=H), "sample run")
    rid = run["run"]["id"]
    groups = run["result"]["groups"]
    proposed = [g for g in groups if g["status"] == "proposed"]
    auto = sum(1 for g in groups if g["status"] == "auto_matched")
    check(proposed, "no proposals to decide")
    zero = next((g for g in proposed if float(g["difference"]) == 0), proposed[0])
    run = ok(client.post(f"/api/finops/recon/runs/{rid}/accept", json={"group_id": zero["id"], "note": "smoke: checked"},
                         headers=H), "accept")
    rid = run["run"]["id"]
    nxt = next((g for g in run["result"]["groups"] if g["status"] == "proposed"), None)
    if nxt:
        run = ok(client.post(f"/api/finops/recon/runs/{rid}/reject", json={"group_id": nxt["id"], "note": "smoke: no"},
                             headers=H), "reject")
        rid = run["run"]["id"]
    exc = next((e for e in run["result"]["exceptions"] if e["status"] == "open"), None)
    if exc:
        ok(client.post(f"/api/finops/recon/runs/{rid}/resolve", json={"exception_id": exc["id"], "action": "explained",
                                                                      "note": "smoke: explained"}, headers=H), "resolve")
    r = client.get(f"/api/finops/recon/runs/{rid}/export.csv")
    check(r.status_code == 200, f"export HTTP {r.status_code}")
    ok(client.get(f"/api/finops/recon/workspaces/{wid}/events"), "events")
    return f"{auto} automatic matches, {len(proposed)} proposals; accept, reject{', resolve' if exc else ''}, export"


@step("invoices: sample inbox, detail, resolve, export")
def _invoices() -> str:
    ok(client.post("/api/finops/invoices/sample", json={}, headers=H), "sample")
    rows = ok(client.get("/api/finops/invoices"), "list")
    check(rows, "no invoices")
    eligible = sum(1 for i in rows if i["eligibility"] == "eligible_for_approval")
    blocked = next(i for i in rows if i["open"])
    d = ok(client.get(f"/api/finops/invoices/{blocked['doc_id']}"), "detail")
    exc = next(e for e in d["outcome"]["exceptions"] if e["status"] == "open")
    action = "confirmed_not_duplicate" if "DUPLICATE" in exc["code"] else "explained"
    r = client.post(f"/api/finops/invoices/{blocked['doc_id']}/resolve",
                    json={"exception_id": exc["id"], "action": action, "note": "smoke: checked with the vendor"}, headers=H)
    check(r.status_code in (200, 400), f"resolve HTTP {r.status_code}")
    r2 = client.get("/api/finops/invoices/export.csv")
    check(r2.status_code == 200, "export")
    return f"{len(rows)} invoices, {eligible} eligible; resolve {'accepted' if r.status_code == 200 else 'refused by a control: ' + r.json().get('detail', '')[:80]}"


@step("data-quality gate: sample, release a held record, export")
def _dq() -> str:
    ok(client.post("/api/finops/dq/sample", json={}, headers=H), "sample")
    runs = ok(client.get("/api/finops/dq/runs"), "runs")
    run = ok(client.get(f"/api/finops/dq/runs/{runs[0]['id']}"), "run")
    records = run["result"]["records"]
    held = next((r for r in records if r["decision"] == "review"), None)
    check(held is not None or not runs[0]["counts"]["review"], "held records counted but none found")
    note = "no held record"
    if held:
        ok(client.post(f"/api/finops/dq/runs/{runs[0]['id']}/decide",
                       json={"record_id": held["id"], "action": "release", "note": "smoke: checked the source"},
                       headers=H), "release")
        note = f"released {held['id']}"
    for kind in ("accepted", "quarantine"):
        r = client.get(f"/api/finops/dq/runs/{runs[0]['id']}/export/{kind}.csv")
        check(r.status_code == 200, f"export {kind} HTTP {r.status_code}")
    return f"{len(runs)} runs, counts {runs[0]['counts']}; {note}"


@step("spreadsheet scanner: sample, confirm a finding, export")
def _sheets() -> str:
    ok(client.post("/api/finops/sheets/sample", json={}, headers=H), "sample")
    scans = ok(client.get("/api/finops/sheets/scans"), "scans")
    scan = ok(client.get(f"/api/finops/sheets/scans/{scans[0]['id']}"), "scan")
    findings = scan["result"]["findings"]
    if findings:
        ok(client.post(f"/api/finops/sheets/scans/{scans[0]['id']}/review",
                       json={"finding_id": findings[0]["id"], "action": "confirm", "note": "smoke: seen in the workbook"},
                       headers=H), "review")
    r = client.get(f"/api/finops/sheets/scans/{scans[0]['id']}/export.csv")
    check(r.status_code == 200, "export")
    return f"{len(scans)} scans, {len(findings)} findings in the first"


@step("ROI and evaluation pages' data")
def _roi() -> str:
    roi = ok(client.get("/api/finops/roi"), "finops roi")
    ok(client.get("/api/roi"), "statement roi")
    ev = ok(client.get("/api/evaluation"), "evaluation")
    return f"{len(ev['reports'])} evaluation reports; ROI engines {sorted(roi.get('engines', {}))}"


@step("reviewer outcomes were recorded for calibration")
def _outcomes() -> str:
    s = ok(client.get("/api/outcomes"), "outcomes")
    engines = s["engines"]
    check("statements" in engines and "units" in engines and "recon" in engines, f"engines recorded: {sorted(engines)}")
    check(Path(s["folder"]).resolve() == (DATA / "outcomes").resolve(), "outcomes went to the wrong folder")
    return ", ".join(f"{k} {v['outcomes']}" for k, v in sorted(engines.items()))


@step("web pages are served")
def _web() -> str:
    if not (ROOT / "web" / "dist" / "index.html").exists():
        return "web/dist not built: skipped (cd web && npm run build)"
    for path in ("/", "/statements", "/recon", "/invoices", "/data-quality", "/spreadsheets", "/roi", "/evaluation"):
        r = client.get(path)
        check(r.status_code == 200 and "<div id=\"root\"" in r.text, f"{path} HTTP {r.status_code}")
    return "8 routes"


@step("command line: spread, gate, scan")
def _cli() -> str:
    import subprocess

    exe = Path(sys.executable).parent / "spreader"
    out = DATA / "cli"
    runs = [
        [str(exe), "spread", str(SYN / "s7-001-clean" / "statement.pdf"), "--out", str(out / "spread.xlsx")],
        [str(exe), "gate", "--dataset", str(ROOT / "config" / "finops" / "dq" / "vendors.yaml"),
         "--source", f"portal={ROOT / 'eval' / 'dq' / 'independent-1' / 'portal.csv'}",
         "--source", f"erp={ROOT / 'eval' / 'dq' / 'independent-1' / 'erp.xlsx'}", "--out", str(out / "gate")],
        [str(exe), "scan", str(ROOT / "eval" / "sheets" / "independent-1" / "accruals_rec.xlsx"), "--out", str(out / "scan")],
    ]
    out.mkdir(parents=True, exist_ok=True)
    for cmd in runs:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        check(r.returncode == 0, f"{cmd[1]} exited {r.returncode}: {(r.stderr or r.stdout)[-200:]}")
    check((out / "spread.xlsx").stat().st_size > 1000, "no spread written")
    return "3 commands ran and wrote their outputs"


def main() -> int:
    width = max(len(n) for n, *_ in results)
    for name, passed, note, secs in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:{width}s}  {secs:5.1f}s  {note}")
    failed = sum(1 for _, p, *_ in results if not p)
    print(f"\n{len(results) - failed} of {len(results)} passed. Data folder: {DATA}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
