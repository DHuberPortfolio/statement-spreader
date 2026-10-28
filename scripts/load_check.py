"""Local load check: several signed-in users reading and correcting at once, through the app (in-process, no network).

    .venv/Scripts/python scripts/load_check.py [--readers 8] [--writers 4] [--rounds 25]

Prints request counts, failures and latency percentiles. Measures this machine with SQLite and one process; it is
not a capacity claim for a server deployment (DECISIONS D47).
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(tempfile.mkdtemp(prefix="load-"))
os.environ["SPREADER_DATA"] = str(DATA)
os.environ["FINOPS_OUTCOMES_DIR"] = str(DATA / "outcomes")
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from spreader import api  # noqa: E402


def signed_in(user: str) -> TestClient:
    c = TestClient(api.app)
    assert c.post("/api/auth/dev-login", json={"username": user}).status_code == 200
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readers", type=int, default=8)
    ap.add_argument("--writers", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=25)
    a = ap.parse_args()
    pat = signed_in("pat")
    doc = (ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html").read_bytes()
    view = pat.post("/api/documents", files={"file": ("s.htm", doc)}).json()
    run = view["run"]["id"]
    values = [v for v in view["spread"]["values"] if v["value"] is not None]
    lat: dict[str, list[float]] = {"read": [], "write": []}
    outcome: dict[str, int] = {}
    lock = threading.Lock()

    def note(kind: str, seconds: float, status: str) -> None:
        with lock:
            lat[kind].append(seconds)
            outcome[f"{kind} {status}"] = outcome.get(f"{kind} {status}", 0) + 1

    def reader() -> None:
        c = signed_in("vic")
        for _ in range(a.rounds):
            t = time.perf_counter()
            r = c.get(f"/api/runs/{run}")
            note("read", time.perf_counter() - t, str(r.status_code))

    def writer(i: int) -> None:
        c = signed_in("rae")
        for k in range(a.rounds):
            v = values[(i * a.rounds + k) % len(values)]
            t = time.perf_counter()
            r = c.post(f"/api/runs/{run}/actions", json={"type": "correct_value", "line": v["line"], "period": v["period"],
                                                         "value": str(v["value"]), "reason": "load check"})
            status = str(r.status_code) + ("" if r.status_code == 200 else " " + r.json().get("error", r.json().get("detail", ""))[:60])
            note("write", time.perf_counter() - t, status)

    threads = [threading.Thread(target=reader) for _ in range(a.readers)] + \
              [threading.Thread(target=writer, args=(i,)) for i in range(a.writers)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0
    for kind, xs in lat.items():
        xs.sort()
        if xs:
            print(f"{kind}: {len(xs)} requests, median {statistics.median(xs) * 1000:.0f} ms, "
                  f"95th percentile {xs[int(0.95 * (len(xs) - 1))] * 1000:.0f} ms, slowest {xs[-1] * 1000:.0f} ms")
    print("outcomes:", dict(sorted(outcome.items())))
    print(f"{a.readers} readers and {a.writers} writers, {a.rounds} rounds each, {wall:.1f} s wall time; data {DATA}")
    errors = sum(n for k, n in outcome.items() if k.split()[1].startswith("5"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
