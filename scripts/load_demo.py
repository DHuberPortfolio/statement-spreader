"""Load a few documents into a data folder so the app has something to show.

    .venv/Scripts/python scripts/load_demo.py var/demo
    SPREADER_DATA=var/demo .venv/Scripts/python -m uvicorn spreader.api:app --host 127.0.0.1 --port 8765

Uses SEC filings already downloaded by scripts/fetch_sec.py and the synthetic corpus.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from spreader.service import Service
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]


def main(data_dir: str) -> None:
    svc = Service(Store(Path(data_dir) / "spreader.sqlite3"))
    manifest = json.loads((ROOT / "eval" / "sec" / "manifest.json").read_text())
    files: list[Path] = []
    for t in ("AAPL", "KO", "PG"):
        if t in manifest and (ROOT / "eval" / "sec" / "raw" / manifest[t]["file"]).exists():
            files.append(ROOT / "eval" / "sec" / "raw" / manifest[t]["file"])
    syn = ROOT / "eval" / "synthetic"
    for case, fmt in (("s7-001-clean", "pdf"), ("s7-005-clean", "xlsx"), ("s7-031-no-unit-statement", "html"),
                      ("s7-032-footing-error", "html")):
        f = syn / case / f"statement.{fmt}"
        if f.exists():
            files.append(f)
    for f in files:
        name = f.name if f.parent.name == "raw" else f"{f.parent.name}.{f.suffix.lstrip('.')}"
        _, view = svc.upload(name, f.read_bytes(), "demo-loader")
        s = view.spread
        print(f"{name:45s} run {view.run['id']:3d} {view.run['status']:9s} "
              f"{len(s.values) if s else 0:4d} values, {sum(1 for i in s.review if i.severity.value == 'blocker') if s else 0} blockers")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "var/demo")
