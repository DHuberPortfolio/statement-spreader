"""A simulated workspace: what the platform looks like after two weeks of analysts' work (D69). For display only.

    .venv/Scripts/python scripts/simulate_two_weeks.py var/two-weeks
    SPREADER_DATA=var/two-weeks .venv/Scripts/python -m uvicorn spreader.api:app --port 8767

Every company and document is made up. The work goes through the real services on a simulated clock, in a new data folder, so
each screen fills in as it would in use and the audit chain is valid. Review minutes are drawn at random, so nothing here measures
anything: the folder is marked simulated, and the app shows that on every page. The folder must not already exist.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Made-up names. None shares its first word with a company on the SEC's list (10,409 names, Nov 2026); private companies were not checked.
COMPANIES = [
    "Brindlewick Provisions", "Corvane Freightways", "Dunmarrow Timberworks", "Ellacott Marine Supply", "Fenwyth Agricultural",
    "Galloreen Packaging", "Harrowmere Tool & Die", "Ivelford Ceramics", "Jessamine Cold Storage", "Kestrelline Aviation Parts",
    "Lorrimer Vale Textiles", "Marrowby Building Products", "Nettlecombe Dairy", "Orrendale Pharmacy Group", "Pellward Electrical",
    "Quenby Hollow Foods", "Rushcombe Plastics", "Sallowfield Hardware", "Thistlemoor Printing", "Umberleigh Coachworks",
    "Varnholt Instruments", "Wexcombe Fabrication", "Yarrowdene Nurseries", "Zennor Ridge Quarries", "Aldermoor Fasteners",
    "Blythewood Bottling", "Cindervale Foundry", "Drovers Reach Logistics", "Eastmarch Paper Mills", "Foxglade Outfitters",
    "Greystoke Harbor Seafood", "Hazelbourne Medical Supply", "Inglenook Furniture Makers", "Juniper Ferry Beverages",
    "Kingsmere Roofing", "Larkhollow Pet Foods", "Merrowgate Engineering", "Northwick Glassworks", "Oakhanger Mills",
    "Penhallow Boatbuilders", "Quarrington Stoneworks", "Ravensthorpe Cutlery", "Swanmere Laundry Services", "Tamsin Bay Canning",
    "Underhay Bakeries", "Vellacott Seed Company", "Whitlowe Saddlery", "Yewtree Hospitality Supply",
]
PREPARERS = ["ana", "pat", "sam"]
REVIEWERS = ["rae", "sam"]
APPROVERS = ["ari", "rae"]
OPEN_AT_THE_END = 8  # the last documents are still in review, as on any working day
LAST_FISCAL_YEAR = 2025
NOTES = {
    "assumed_scale": "Confirmed the unit against the statement heading.",
    "failed_check": "Checked against the printed statement; the difference is in the source and is noted on the file.",
    "low_confidence": "Checked the row in the printed statement; the placement is right.",
    "unmapped": "Read the row; it does not belong on the template.",
}
NOTE = "Checked against the printed statement."


class Clock:
    def __init__(self, start: datetime = datetime(2000, 1, 1, tzinfo=UTC)) -> None:
        self.start = self.at = start

    def now(self) -> str:
        return self.at.isoformat(timespec="seconds")

    def set(self, at: datetime) -> None:
        self.at = max(self.at, at)  # the log only ever moves forward

    def restart(self) -> None:
        """Back to the start, for the next area of work: the areas run one after another but happen side by side."""
        self.at = self.start

    def step(self, rng: random.Random, low: int = 3, high: int = 25) -> None:
        self.at += timedelta(minutes=rng.randint(low, high))


def working_days(end: date, count: int = 10) -> list[date]:
    days: list[date] = []
    d = end
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def install(clock: Clock) -> None:
    """Every part of the app reads the time through one of two functions; both now read the simulated clock."""
    from finops.core import audit
    from spreader import store

    originals = (store.now, audit.now)
    for module in list(sys.modules.values()):
        if module and getattr(module, "now", None) in originals:
            module.now = clock.now  # type: ignore[attr-defined]


def _statement(index: int, name: str, seed: int) -> tuple[str, bytes, Any]:
    from spreader.evaluation import synthetic
    from spreader.evaluation.synthetic import build_key, make_case, render_html, render_xlsx

    choose = synthetic.choose_spec

    def recent(rng: random.Random, kind: str) -> Any:  # last year's accounts, as a desk would be spreading now
        spec = choose(rng, kind)
        spec.last_year = LAST_FISCAL_YEAR
        return spec

    synthetic.choose_spec = recent
    kind = "footing-error" if index % 11 == 5 else "no-unit-statement" if index % 7 == 3 else "clean"
    case = make_case(seed, index, kind)
    synthetic.choose_spec = choose
    case.spec.company = name
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if index % 5 == 4:
        return f"{slug}-financial-statements.xlsx", render_xlsx(case), build_key(case)
    return f"{slug}-financial-statements.html", render_html(case).encode(), build_key(case)


def _review(svc: Any, run_id: int, key: Any, reviewer: str, clock: Clock, rng: random.Random) -> int:
    """A reviewer's pass: put right what the key shows was misread, then close each item with a note."""
    view = svc.get(run_id)
    truth = {(t.line, t.period): t.value for t in key.spread}
    corrected = 0
    for v in view.spread.values:
        right = truth.get((v.line, v.period))
        if right is not None and v.value is not None and right != v.value and corrected < 3:
            clock.step(rng, 2, 9)
            svc.act(run_id, {"type": "correct_value", "line": v.line, "period": v.period, "value": str(right),
                             "reason": "Checked against the printed statement."}, reviewer)
            corrected += 1
    for _ in range(3):
        view = svc.get(run_id)
        resolved = view.run["state"].get("resolved", {})
        items = [i for i in view.spread.review if i.id not in resolved]
        if not items:
            break
        clock.step(rng, 1, 4)
        for item in items:
            try:
                svc.act(run_id, {"type": "resolve_item", "item": item.id, "note": NOTES.get(item.kind.value, NOTE)}, reviewer)
            except Exception:  # noqa: BLE001 - an item can close by itself once a correction lands
                continue
    return corrected


def _session(svc: Any, doc_id: str, run_id: int | None, mode: str, actor: str, clock: Clock, seconds: float, values: int = 0,
             ended: bool = False) -> None:
    with svc.store.tx() as c:
        c.execute("INSERT INTO work_sessions(document_id, run_id, mode, actor, started_at, ended_at, active_seconds, values_entered, background)"
                  " VALUES (?,?,?,?,?,?,?,?,?)", (doc_id, run_id, mode, actor, clock.now(), clock.now() if ended else None, seconds, values,
                                                  0 if mode == "baseline" else 1))


def statements(svc: Any, days: list[date], clock: Clock, rng: random.Random, seed: int) -> dict[str, int]:
    per_day = len(COMPANIES) / len(days)
    counts = {"approved": 0, "open": 0, "corrected": 0}
    for i, name in enumerate(COMPANIES):
        day = days[min(int(i / per_day), len(days) - 1)]
        slot = 9 * 60 + int((i % per_day) * 90)
        clock.set(datetime(day.year, day.month, day.day, 13, 0, tzinfo=UTC) + timedelta(minutes=slot - 9 * 60 + rng.randint(0, 20)))
        filename, data, key = _statement(i + 1, name, seed)
        preparer = PREPARERS[i % len(PREPARERS)]
        doc, view = svc.upload(filename, data, preparer, company_id=name, generated=True, display_name=name)
        run_id = view.run["id"]
        with svc.store.tx() as c:
            c.execute("UPDATE documents SET filing='Annual financial statements' WHERE id=?", (doc["id"],))
        if i >= len(COMPANIES) - OPEN_AT_THE_END:
            counts["open"] += 1
            if i % 2 == 0:  # some already picked up, some still waiting
                clock.step(rng, 5, 20)
                _session(svc, doc["id"], run_id, "assisted", preparer, clock, rng.uniform(240, 700))
            continue
        reviewer = REVIEWERS[i % len(REVIEWERS)]
        reviewer = "rae" if reviewer == preparer else reviewer
        clock.step(rng, 10, 40)
        _session(svc, doc["id"], run_id, "assisted", reviewer, clock, rng.uniform(480, 1560))
        counts["corrected"] += _review(svc, run_id, key, reviewer, clock, rng)
        clock.step(rng, 5, 30)
        approver = next(a for a in APPROVERS if a not in {preparer, reviewer})
        svc.act(run_id, {"type": "approve"}, approver, separation=(True, True))
        counts["approved"] += 1
        if i % 8 == 1:  # a few timed by hand, for the comparison on the Time saved page
            clock.step(rng, 1, 5)
            _session(svc, doc["id"], None, "baseline", preparer, clock, rng.uniform(3000, 5400), values=len(view.spread.values), ended=True)
    return counts


def other_work(clients: dict[str, Any], days: list[date], clock: Clock, rng: random.Random) -> dict[str, int]:
    prep, client, appr = clients["pat"], clients["rae"], clients["ari"]
    done = {"reconciliations": 0, "matches_decided": 0, "exceptions_closed": 0, "invoices": 0, "data_loads": 0, "workbooks": 0}
    profile = prep.get("/api/finops/recon/profiles").json()[0]["file"]
    clock.restart()

    def at(day: date, hour: int) -> None:
        clock.set(datetime(day.year, day.month, day.day, hour, rng.randint(0, 40), tzinfo=UTC))

    for n, day in enumerate(days[::2]):  # bank against ledger, on alternate days, fully closed but for the last
        at(day, 14)
        wid = prep.post("/api/finops/recon/workspaces", json={"name": f"Operating account, week {n // 2 + 1} batch {n % 2 + 1}", "profile": profile}).json()["id"]
        run = prep.post(f"/api/finops/recon/workspaces/{wid}/sample", json={}).json()
        done["reconciliations"] += 1
        if n == len(days[::2]) - 1:
            continue
        rid = run["run"]["id"]
        while True:
            g = next((g for g in run["result"]["groups"] if g["status"] == "proposed"), None)
            if g is None:
                break
            clock.step(rng, 1, 3)
            r = client.post(f"/api/finops/recon/runs/{rid}/accept", json={"group_id": g["id"], "note": "Agreed to the bank line and the ledger entry."})
            if r.status_code != 200:
                break
            run, rid = r.json(), r.json()["run"]["id"]
            done["matches_decided"] += 1
        while True:
            e = next((e for e in run["result"]["exceptions"] if e["status"] == "open"), None)
            if e is None:
                break
            clock.step(rng, 1, 3)
            r = client.post(f"/api/finops/recon/runs/{rid}/resolve", json={"exception_id": e["id"], "action": "explained", "note": "Timing difference, clears next statement."})
            if r.status_code != 200:
                break
            run, rid = r.json(), r.json()["run"]["id"]
            done["exceptions_closed"] += 1

    clock.restart()
    at(days[1], 16)
    prep.post("/api/finops/invoices/sample", json={})
    rows = client.get("/api/finops/invoices").json()
    done["invoices"] = len(rows)
    for row in [r for r in rows if r["open"]][:-3]:  # the last few stay open
        for e in [e for e in client.get(f"/api/finops/invoices/{row['doc_id']}").json()["outcome"]["exceptions"] if e["status"] == "open"]:
            clock.step(rng, 1, 4)
            bank = e["code"] == "BANK_DETAILS_CHANGED"  # the platform refuses to explain these away: the invoice goes back
            action = "rejected" if bank else "confirmed_not_duplicate" if "DUPLICATE" in e["code"] else "explained"
            note = "Bank change not confirmed by call-back; returned to the vendor." if bank else "Checked with the vendor and the purchase order."
            client.post(f"/api/finops/invoices/{row['doc_id']}/resolve", json={"exception_id": e["id"], "action": action, "note": note})

    clock.restart()
    for day in (days[2],):
        at(day, 15)
        prep.post("/api/finops/dq/sample", json={})
        run_id = client.get("/api/finops/dq/runs").json()[0]["id"]
        done["data_loads"] += 1
        while True:  # each decision makes a new run
            run_id = client.get("/api/finops/dq/runs").json()[0]["id"]
            held = [r for r in client.get(f"/api/finops/dq/runs/{run_id}").json()["result"]["records"] if r["decision"] == "review"]
            if len(held) <= 2:  # two are left for tomorrow
                break
            clock.step(rng, 1, 3)
            if appr.post(f"/api/finops/dq/runs/{run_id}/decide", json={"record_id": held[0]["id"], "action": "release", "note": "Checked the source record."}).status_code != 200:
                break

    clock.restart()
    for day in (days[3],):
        at(day, 17)
        prep.post("/api/finops/sheets/sample", json={})
        scan_id = client.get("/api/finops/sheets/scans").json()[0]["id"]
        done["workbooks"] += 1
        for f in client.get(f"/api/finops/sheets/scans/{scan_id}").json()["result"]["findings"]:
            clock.step(rng, 1, 3)
            client.post(f"/api/finops/sheets/scans/{scan_id}/review", json={"finding_id": f["id"], "action": "confirm", "note": "Seen in the workbook; owner told."})
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default="var/two-weeks")
    ap.add_argument("--end", default=None, help="the last working day, YYYY-MM-DD (default: today)")
    ap.add_argument("--seed", type=int, default=69)
    a = ap.parse_args()
    data = Path(a.data_dir).resolve()
    if data.exists():
        raise SystemExit(f"{data} already exists: a simulation only ever fills a new folder")
    data.mkdir(parents=True)
    os.environ["SPREADER_DATA"] = str(data)
    os.environ["FINOPS_OUTCOMES_DIR"] = str(data / "outcomes")

    from fastapi.testclient import TestClient

    from spreader import api

    days = working_days(date.fromisoformat(a.end) if a.end else datetime.now(UTC).date())
    clock, rng = Clock(datetime(days[0].year, days[0].month, days[0].day, 12, 0, tzinfo=UTC)), random.Random(a.seed)
    install(clock)
    svc = api.service()
    clients = {}
    for user in ("pat", "rae", "ari"):
        clients[user] = TestClient(api.app)
        clients[user].post("/api/auth/dev-login", json={"username": user})
    with svc.store.tx() as c:
        c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('simulated', ?)", (f"two weeks ending {days[-1].isoformat()}",))
    print(statements(svc, days, clock, rng, a.seed), flush=True)
    print(other_work(clients, days, clock, rng), flush=True)


if __name__ == "__main__":
    main()
