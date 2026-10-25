"""Download recent 10-K filings (inline XBRL) for the SEC evaluation set.

Follows the SEC's fair-access rules: a User-Agent that identifies the requester, and fewer than
10 requests a second (this script waits between requests). Files are cached in eval/sec/raw/
(git-ignored); eval/sec/manifest.json records exactly which filing each file is, with its hash,
so anyone can re-download the same documents.

    .venv/Scripts/python scripts/fetch_sec.py            # the default ticker list
    .venv/Scripts/python scripts/fetch_sec.py AAPL MSFT  # just these
    .venv/Scripts/python scripts/fetch_sec.py --prior    # the 10-K filed before each one in the manifest
                                                         # (eval/sec/raw-prior, eval/sec/manifest-prior.json)
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import zlib
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "eval" / "sec" / "raw"
MANIFEST = ROOT / "eval" / "sec" / "manifest.json"
RAW_PRIOR = ROOT / "eval" / "sec" / "raw-prior"
MANIFEST_PRIOR = ROOT / "eval" / "sec" / "manifest-prior.json"
USER_AGENT = "StatementSpreader/0.1 research prototype (devinhuber.com)"
PAUSE = 0.2  # seconds between requests: at most 5 a second, half the SEC's limit

# Non-financial companies across industries and sizes. Banks and insurers use different
# statements and are out of scope for this template.
TICKERS = [
    "AAPL", "MSFT", "KO", "PG", "CAT", "HD", "NKE", "PEP", "JNJ", "XOM", "UNP", "MMM", "DE", "LOW", "TGT",
    "COST", "WMT", "ADBE", "CSCO", "INTC", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "F", "BA", "HON", "MCD",
    "SBUX", "DIS", "NFLX", "PFE", "MRK", "CVX", "LMT", "UPS", "FDX", "ORCL", "IBM", "TXN", "QCOM", "AMD",
    "CMG", "DPZ", "SHAK", "BOOT", "YETI", "DUOL", "ETSY", "ROKU", "CROX", "HAS", "MAT", "ULTA", "LULU",
    "DECK", "POOL", "FAST", "SNA", "GPC", "ODFL", "CHRW", "EXPD",
]


def split_of(ticker: str) -> str:
    """A fixed split by hash: tuning looks only at 'dev'; 'holdout' is for honest measurement."""
    return "dev" if zlib.crc32(ticker.encode()) % 2 == 0 else "holdout"


def main(tickers: list[str], prior: bool = False) -> None:
    current = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    raw_dir, manifest_path = (RAW_PRIOR, MANIFEST_PRIOR) if prior else (RAW, MANIFEST)
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=60)
    ciks = client.get("https://www.sec.gov/files/company_tickers.json").json()
    by_ticker = {v["ticker"]: int(v["cik_str"]) for v in ciks.values()}
    time.sleep(PAUSE)
    for t in tickers:
        if t in manifest and (raw_dir / manifest[t]["file"]).exists():
            continue
        if prior and t not in current:
            print(f"{t}: not in the current manifest")
            continue
        cik = by_ticker.get(t)
        if cik is None:
            print(f"{t}: no CIK")
            continue
        sub = client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
        time.sleep(PAUSE)
        rec = sub["filings"]["recent"]
        pick = None
        # The newest inline-XBRL 10-K; with --prior, the newest one filed before the filing in the manifest (the
        # year whose figures that filing prints as its comparative column).
        after = rec["accessionNumber"].index(current[t]["accession"]) if prior and current[t]["accession"] in rec["accessionNumber"] else -1
        if prior and after < 0:
            print(f"{t}: the current filing is not in the recent list")
            continue
        for i, form in enumerate(rec["form"]):
            if i > after and form == "10-K" and rec["isInlineXBRL"][i]:
                pick = i
                break
        if pick is None:
            print(f"{t}: no inline XBRL 10-K in recent filings")
            continue
        acc = rec["accessionNumber"][pick]
        doc = rec["primaryDocument"][pick]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
        r = client.get(url)
        time.sleep(PAUSE)
        if r.status_code != 200:
            print(f"{t}: HTTP {r.status_code} for {url}")
            continue
        name = f"{t}-{acc}.htm"
        (raw_dir / name).write_bytes(r.content)
        manifest[t] = {"ticker": t, "company": sub.get("name"), "cik": cik, "accession": acc, "filed": rec["filingDate"][pick],
                       "period": rec["reportDate"][pick], "url": url, "file": name, "bytes": len(r.content),
                       "sha256": hashlib.sha256(r.content).hexdigest(), "split": split_of(t)}
        if prior:
            manifest[t]["follows_up"] = current[t]["accession"]
        print(f"{t}: {acc} {len(r.content) / 1e6:.1f} MB ({manifest[t]['split']})")
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--prior"]
    use_prior = "--prior" in sys.argv[1:]
    main(args or (sorted(json.loads(MANIFEST.read_text())) if use_prior else TICKERS), prior=use_prior)
