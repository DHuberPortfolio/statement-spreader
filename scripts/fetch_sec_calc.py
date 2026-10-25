"""Download each SEC filing's XBRL calculation linkbase (the file that says which concept adds up to which).

    .venv/Scripts/python scripts/fetch_sec_calc.py

The answer-key builder uses it to tell a total from its parts: a filing can tag both "total revenues" and
"net sales" (one of its parts) on lines that map to the same template line, and adding them double counts.
Same fair-access rules as fetch_sec.py (identifying User-Agent, at most 5 requests a second). Files are cached
in eval/sec/cal/ (git-ignored, like the filings); the manifest records each file's URL and SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "eval" / "sec" / "cal"
MANIFEST = ROOT / "eval" / "sec" / "manifest.json"
USER_AGENT = "StatementSpreader/0.1 research prototype (devinhuber.com)"
PAUSE = 0.2


def main() -> None:
    CAL.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text())
    client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=60)
    got, missing = 0, []
    for t, m in sorted(manifest.items()):
        out = CAL / f"{t}_cal.xml"
        if out.exists() and m.get("cal", {}).get("sha256") == hashlib.sha256(out.read_bytes()).hexdigest():
            got += 1
            continue
        folder = f"https://www.sec.gov/Archives/edgar/data/{m['cik']}/{m['accession'].replace('-', '')}"
        r = client.get(f"{folder}/index.json")
        time.sleep(PAUSE)
        if r.status_code != 200:
            missing.append(f"{t}: index HTTP {r.status_code}")
            continue
        names = [i["name"] for i in r.json().get("directory", {}).get("item", [])]
        # Most filers ship the links as <name>_cal.xml; some embed them in the taxonomy schema (.xsd) instead.
        cal = next((n for n in names if n.lower().endswith("_cal.xml")), None) or next(
            (n for n in names if n.lower().endswith(".xsd")), None)
        if cal is None:
            missing.append(f"{t}: neither _cal.xml nor a schema in the filing")
            continue
        r = client.get(f"{folder}/{cal}")
        time.sleep(PAUSE)
        if r.status_code != 200:
            missing.append(f"{t}: {cal} HTTP {r.status_code}")
            continue
        if b"calculationArc" not in r.content:
            missing.append(f"{t}: {cal} holds no calculation links")
            continue
        out.write_bytes(r.content)
        m["cal"] = {"file": out.name, "url": f"{folder}/{cal}", "sha256": hashlib.sha256(r.content).hexdigest()}
        got += 1
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print(f"{got} calculation linkbases cached; missing: {missing or 'none'}")


if __name__ == "__main__":
    main()
