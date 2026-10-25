"""Download a few filings for the industry and IFRS overlays (banks, insurers, IFRS filers), outside the evaluation sets.

    .venv/Scripts/python scripts/fetch_coverage.py

The SEC's fair-access rules as in fetch_sec.py (identifying User-Agent, at most 5 requests a second). Filings land in
eval/coverage/raw/ (git-ignored); eval/coverage/manifest.json records each one's URL and SHA-256. For each group the
first company is the one the overlay's wording was written from; the others are only spread and hand-checked
(eval/coverage/checks.json), so the check is not on the documents the wording came from.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "coverage"
USER_AGENT = "StatementSpreader/0.1 research prototype (devinhuber.com)"
PAUSE = 0.2
GROUPS = {"us-bank": ("10-K", ["FITB", "HBAN", "KEY"]), "us-insurer": ("10-K", ["TRV", "ALL", "PGR"]),
          "ifrs-commercial": ("20-F", ["UL", "NVS", "BP"])}


def main() -> None:
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    path = OUT / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=90)
    ciks = {v["ticker"]: int(v["cik_str"]) for v in client.get("https://www.sec.gov/files/company_tickers.json").json().values()}
    time.sleep(PAUSE)
    for profile, (form, tickers) in GROUPS.items():
        for i, t in enumerate(tickers):
            if t in manifest and (OUT / "raw" / manifest[t]["file"]).exists():
                continue
            cik = ciks.get(t)
            if cik is None:
                print(f"{t}: no CIK")
                continue
            rec = client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
            time.sleep(PAUSE)
            pick = next((j for j, f in enumerate(rec["form"]) if f == form and rec["isInlineXBRL"][j]), None)
            if pick is None:
                print(f"{t}: no inline XBRL {form}")
                continue
            acc, doc = rec["accessionNumber"][pick], rec["primaryDocument"][pick]
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
            r = client.get(url)
            time.sleep(PAUSE)
            if r.status_code != 200:
                print(f"{t}: HTTP {r.status_code}")
                continue
            name = f"{t}-{acc}.htm"
            (OUT / "raw" / name).write_bytes(r.content)
            manifest[t] = {"ticker": t, "profile": profile, "role": "wording written from" if i == 0 else "hand-checked only",
                           "form": form, "cik": cik, "accession": acc, "period": rec["reportDate"][pick], "url": url,
                           "file": name, "sha256": hashlib.sha256(r.content).hexdigest()}
            print(f"{t}: {form} {acc} {len(r.content) / 1e6:.1f} MB")
            path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
