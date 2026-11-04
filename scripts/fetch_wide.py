"""Collect a wide, random sample of real SEC filings, one filing per company (the wide set, D66).

    .venv/Scripts/python scripts/fetch_wide.py                # fill the quotas in QUOTAS
    .venv/Scripts/python scripts/fetch_wide.py --scale 4      # four times as many; companies already held stay
    .venv/Scripts/python scripts/fetch_wide.py --out eval/vocab --seed 67 --quota "energy=40,utilities=30"   # a set of its own

Companies are drawn at random (a fixed seed, so the draw repeats) from the SEC's ticker list, by industry and by size, so
nobody picks the easy ones. Filings already used anywhere in eval/ are skipped: a company is in one set only. The SEC's
fair-access rules as in fetch_sec.py. Filings land in eval/wide/raw, calculation links in eval/wide/cal (both git-ignored,
re-downloadable); eval/wide/manifest.json records each filing's source, hash and split. Half of each industry is sealed:
it is measured once, never studied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import zlib
from pathlib import Path
from typing import Any

import httpx
from fetch_sec import PAUSE, USER_AGENT
from fetch_sec_calc import calc_linkbase

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "wide"
SEED = 66
QUOTAS = {"manufacturing": 13, "retail": 10, "technology": 12, "healthcare": 12, "energy": 12, "financial services": 7,
          "banking": 10, "insurance": 8, "real estate": 8, "transportation": 8, "consumer goods": 10}
QUARTERLY_EVERY = 5  # one filing in five is a 10-Q
PROFILES = {"banking": "us-bank", "insurance": "us-insurer"}


def sector_of(sic: int) -> str | None:
    """The industry a Standard Industrial Classification code falls in; None for what the set leaves out (shells)."""
    if sic in {6770, 6199} or not sic:
        return None  # blank-check companies have no operations to spread
    if 6020 <= sic <= 6036:
        return "banking"
    if 6300 <= sic <= 6411:
        return "insurance"
    if 6500 <= sic <= 6799:
        return "real estate"
    if 6000 <= sic <= 6299:
        return "financial services"
    if 2830 <= sic <= 2836 or 3840 <= sic <= 3851 or 8000 <= sic <= 8099:
        return "healthcare"
    if 3570 <= sic <= 3579 or 3660 <= sic <= 3679 or 7370 <= sic <= 7379:
        return "technology"
    if 4900 <= sic <= 4949:
        return "utilities"
    if 1000 <= sic <= 1499 or 2900 <= sic <= 2999 or 4950 <= sic <= 4999:
        return "energy"
    if 4000 <= sic <= 4799:
        return "transportation"
    if 5200 <= sic <= 5999:
        return "retail"
    if 2000 <= sic <= 2399 or 2500 <= sic <= 2599 or 2840 <= sic <= 2844 or 3100 <= sic <= 3199 or 5000 <= sic <= 5199:
        return "consumer goods"
    if 2400 <= sic <= 3999:
        return "manufacturing"
    return None


def held_ciks() -> set[int]:
    """Every company already in an evaluation set."""
    out: set[int] = set()
    for path in [ROOT / "eval/sec/manifest.json", ROOT / "eval/coverage/manifest.json", ROOT / "eval/wide/manifest.json",
                 *ROOT.glob("eval/industry/*/manifest.json")]:
        data = json.loads(path.read_text())
        out |= {int(m["cik"]) for m in data.values() if isinstance(m, dict) and m.get("cik")}
    return out


def held_accessions() -> set[str]:
    """Every filing already in a collected set."""
    return {m["accession"] for path in ROOT.glob("eval/*/manifest.json") for m in json.loads(path.read_text()).values()
            if isinstance(m, dict) and m.get("accession")}


def get(client: httpx.Client, url: str) -> httpx.Response:
    for wait in (1, 5, 20):
        r = client.get(url)
        time.sleep(PAUSE)
        if r.status_code not in {429, 503}:
            return r
        time.sleep(wait)
    return r


def pick_filing(rec: dict[str, list[Any]], want: str) -> int | None:
    for i, form in enumerate(rec["form"]):
        if form == want and rec["isInlineXBRL"][i]:
            return i
    return None


def split_by_sector(manifest: dict[str, dict[str, Any]]) -> None:
    """Half of each industry sealed, by a hash of the CIK: nobody chooses, and the mix of industries matches."""
    for sector in {m["sector"] for m in manifest.values()}:
        members = sorted((m for m in manifest.values() if m["sector"] == sector), key=lambda m: zlib.crc32(str(m["cik"]).encode()))
        for i, m in enumerate(members):
            m.setdefault("split", "dev" if i % 2 == 0 else "sealed")


def main(scale: int, out: Path = OUT, seed: int = SEED, quotas: dict[str, int] = QUOTAS) -> None:
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "cal").mkdir(parents=True, exist_ok=True)
    path = out / "manifest.json"
    manifest: dict[str, dict[str, Any]] = json.loads(path.read_text()) if path.exists() else {}
    client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=60)
    tickers = list(client.get("https://www.sec.gov/files/company_tickers.json").json().values())
    time.sleep(PAUSE)
    # The SEC lists companies largest first: thirds of the list stand for size.
    third = len(tickers) // 3
    sizes = {t["ticker"]: ("large" if i < third else "mid" if i < 2 * third else "small") for i, t in enumerate(tickers)}
    order = tickers[:]
    random.Random(seed).shuffle(order)
    held = held_ciks() - ({int(m["cik"]) for m in manifest.values()} if out == OUT else set())
    seen = {int(m["cik"]) for m in manifest.values()}
    want = {s: n * scale for s, n in quotas.items()}
    have: dict[tuple[str, str], int] = {}
    count = dict.fromkeys(quotas, 0)
    for m in manifest.values():
        count[m["sector"]] += 1
        have[(m["sector"], m["size"])] = have.get((m["sector"], m["size"]), 0) + 1
    failures: list[str] = []
    accessions = held_accessions() | {m["accession"] for m in manifest.values()}
    done = len(manifest)
    for t in order:
        if all(count[s] >= want[s] for s in want):
            break
        cik = int(t["cik_str"])
        if cik in held or cik in seen:
            continue
        seen.add(cik)
        r = get(client, f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if r.status_code != 200:
            failures.append(f"{t['ticker']}: submissions HTTP {r.status_code}")
            continue
        sub = r.json()
        sector = sector_of(int(sub.get("sic") or 0))
        size = sizes[t["ticker"]]
        # No size may take more than half an industry's places, or small companies would crowd out the rest.
        if sector not in want or count[sector] >= want[sector] or have.get((sector, size), 0) * 2 >= want[sector]:
            continue
        rec = sub["filings"]["recent"]
        form = "10-Q" if done % QUARTERLY_EVERY == QUARTERLY_EVERY - 1 else "10-K"
        pick = pick_filing(rec, form)
        if pick is None:
            form = "10-K"
            pick = pick_filing(rec, form)
        if pick is None or rec["filingDate"][pick] < "2024-06-01":
            failures.append(f"{t['ticker']}: no recent inline XBRL filing")
            continue
        acc, doc = rec["accessionNumber"][pick], rec["primaryDocument"][pick]
        if acc in accessions:  # a combined filing is one document under several companies: it must not land on both sides of a seal
            failures.append(f"{t['ticker']}: same combined filing as a company already held")
            continue
        accessions.add(acc)
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
        r = get(client, url)
        if r.status_code != 200:
            failures.append(f"{t['ticker']}: filing HTTP {r.status_code}")
            continue
        key = re.sub(r"[^A-Za-z0-9]", "_", t["ticker"])
        name = f"{key}-{acc}.htm"
        (out / "raw" / name).write_bytes(r.content)
        entry = {"ticker": t["ticker"], "company": sub.get("name"), "cik": cik, "sic": int(sub["sic"]), "sic_description": sub.get("sicDescription"),
                 "sector": sector, "size": size, "profile": PROFILES.get(sector, "us-commercial"), "form": form, "accession": acc,
                 "filed": rec["filingDate"][pick], "period": rec["reportDate"][pick], "url": url, "file": name,
                 "sha256": hashlib.sha256(r.content).hexdigest()}
        content, where = calc_linkbase(client, cik, acc)
        if content is not None:
            (out / "cal" / f"{key}_cal.xml").write_bytes(content)
            entry["cal"] = {"file": f"{key}_cal.xml", "url": where, "sha256": hashlib.sha256(content).hexdigest()}
        else:
            failures.append(f"{t['ticker']}: no calculation links ({where})")
        time.sleep(PAUSE)
        manifest[key] = entry
        count[sector] += 1
        have[(sector, size)] = have.get((sector, size), 0) + 1
        done += 1
        print(f"{done:4d} {sector:18s} {size:5s} {form} {t['ticker']:7s} {len(r.content) / 1e6:5.1f} MB", flush=True)
        path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    split_by_sector(manifest)
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    (out / "collection-log.txt").write_text("\n".join(failures) + "\n")
    print(f"{len(manifest)} filings; {len(failures)} companies or links not used (collection-log.txt)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--quota", default="", help="sector=count,sector=count; the default is QUOTAS")
    a = ap.parse_args()
    q = {k.strip(): int(v) for k, v in (p.split("=") for p in a.quota.split(",") if p)} or QUOTAS
    sys.exit(main(a.scale, Path(a.out).resolve(), a.seed, q))
