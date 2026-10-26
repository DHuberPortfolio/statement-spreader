"""Download banks' and insurers' latest 10-K (inline XBRL) and calculation links, for answer keys (DECISIONS D41).

    .venv/Scripts/python scripts/fetch_industry.py            # both industries
    .venv/Scripts/python scripts/fetch_industry.py bank       # one

The SEC's fair-access rules as in fetch_sec.py (identifying User-Agent, at most 5 requests a second). Filings land in
eval/industry/<industry>/raw/ and their calculation linkbases in eval/industry/<industry>/cal/ (both git-ignored,
re-downloadable); eval/industry/<industry>/manifest.json records each one's URL, accession and SHA-256, and its split
by ticker hash (fetch_sec.split_of): the overlays are tuned on dev filings only and measured on the holdout.

None of these companies is in eval/coverage (the six filings the overlays' wording was first written from and
smoke-tested on stay apart).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx
from fetch_sec import PAUSE, USER_AGENT, split_of
from fetch_sec_calc import calc_linkbase

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "industry"

# US commercial and regional banks, and US property-casualty and life insurers, of several sizes.
TICKERS = {
    "bank": ["JPM", "BAC", "WFC", "C", "USB", "PNC", "TFC", "MTB", "RF", "CFG", "ZION", "CMA", "FHN", "WAL", "EWBC",
             "SNV", "CFR", "WBS", "FCNCA", "BPOP", "ONB", "HWC", "PB", "SSB"],
    "insurer": ["CB", "AIG", "HIG", "CINF", "WRB", "AFG", "SIGI", "THG", "KMPR", "MET", "PRU", "LNC", "PFG", "UNM",
                "GL", "AFL", "CNO", "HMN", "ORI", "RGA", "L", "ACGL", "AXS", "EIG"],
}
PROFILES = {"bank": "config/profiles/us-bank.yaml", "insurer": "config/profiles/us-insurer.yaml"}


def fetch(industry: str, client: httpx.Client, ciks: dict[str, int]) -> None:
    folder = OUT / industry
    (folder / "raw").mkdir(parents=True, exist_ok=True)
    (folder / "cal").mkdir(parents=True, exist_ok=True)
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    for t in TICKERS[industry]:
        m = manifest.get(t)
        if m and (folder / "raw" / m["file"]).exists() and (not m.get("cal") or (folder / "cal" / m["cal"]["file"]).exists()):
            continue
        cik = ciks.get(t)
        if cik is None:
            print(f"{t}: no CIK")
            continue
        rec = client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
        time.sleep(PAUSE)
        pick = next((i for i, f in enumerate(rec["form"]) if f == "10-K" and rec["isInlineXBRL"][i]), None)
        if pick is None:
            print(f"{t}: no inline XBRL 10-K")
            continue
        acc, doc = rec["accessionNumber"][pick], rec["primaryDocument"][pick]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
        r = client.get(url)
        time.sleep(PAUSE)
        if r.status_code != 200:
            print(f"{t}: HTTP {r.status_code}")
            continue
        name = f"{t}-{acc}.htm"
        (folder / "raw" / name).write_bytes(r.content)
        entry = {"ticker": t, "industry": industry, "split": split_of(t), "cik": cik, "accession": acc,
                 "period": rec["reportDate"][pick], "url": url, "file": name, "sha256": hashlib.sha256(r.content).hexdigest()}
        content, where = calc_linkbase(client, cik, acc)
        if content is not None:
            (folder / "cal" / f"{t}_cal.xml").write_bytes(content)
            entry["cal"] = {"file": f"{t}_cal.xml", "url": where, "sha256": hashlib.sha256(content).hexdigest()}
        else:
            print(f"{t}: no calculation links ({where})")
        manifest[t] = entry
        print(f"{industry} {t}: {acc} {len(r.content) / 1e6:.1f} MB, {entry['split']}")
        path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True))


def main(industries: list[str]) -> None:
    client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=90)
    ciks = {v["ticker"]: int(v["cik_str"]) for v in client.get("https://www.sec.gov/files/company_tickers.json").json().values()}
    time.sleep(PAUSE)
    for industry in industries:
        fetch(industry, client, ciks)


if __name__ == "__main__":
    main(sys.argv[1:] or list(TICKERS))
