"""Load the real filings into the app under their real company names, so they can be opened one by one (D68).

    .venv/Scripts/python scripts/load_library.py var/demo
    .venv/Scripts/python scripts/load_library.py var/demo --limit 10
    .venv/Scripts/python scripts/load_library.py var/two-weeks --sample 40   # a mix of industries, left unworked in the queue

The sealed halves are never loaded: once a filing has been opened in the app it is no longer an unseen test. Banks and insurers
are left out too, because the app spreads every document on one template and theirs would look wrong on the commercial one.
A filing already in the app is skipped, so a stopped load can simply be run again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SETS = ("eval/sec", "eval/wide", "eval/vocab")


def _entries(root: Path, name: str) -> dict[str, dict[str, Any]]:
    path = root / name / "manifest.json"
    if not path.exists():
        return {}
    return {k: m for k, m in json.loads(path.read_text(encoding="utf-8")).items() if isinstance(m, dict) and m.get("file")}


def sealed_hashes(root: Path) -> set[str]:
    return {m["sha256"] for name in SETS for m in _entries(root, name).values() if m.get("split") == "sealed" and m.get("sha256")}


def library_files(root: Path = ROOT) -> list[tuple[Path, dict[str, Any]]]:
    """Every filing the app may show: not sealed, and on the commercial template."""
    sealed = sealed_hashes(root)
    out: list[tuple[Path, dict[str, Any]]] = []
    for name in SETS:
        for m in _entries(root, name).values():
            path = root / name / "raw" / m["file"]
            if m.get("split") == "sealed" or m.get("profile", "us-commercial") != "us-commercial" or not path.exists():
                continue
            if m.get("sha256") in sealed or hashlib.sha256(path.read_bytes()).hexdigest() in sealed:
                print(f"Left out {m['file']}: a combined filing, the same file as a sealed one")
                continue
            out.append((path, m))
    return sorted(out, key=lambda item: (item[1].get("company") or item[1].get("ticker") or "").lower())


def sample(files: list[tuple[Path, dict[str, Any]]], count: int, seed: int = 70) -> list[tuple[Path, dict[str, Any]]]:
    """A mix: one filing from each industry in turn, at random within it, so nobody picks the easy ones."""
    rng = random.Random(seed)
    groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for item in files:
        groups.setdefault(item[1].get("sector", "original set"), []).append(item)
    for members in groups.values():
        rng.shuffle(members)
    out: list[tuple[Path, dict[str, Any]]] = []
    while len(out) < count and any(groups.values()):
        for name in sorted(groups):
            if groups[name] and len(out) < count:
                out.append(groups[name].pop())
    return out


def main() -> None:
    from spreader.service import Service, doc_id_for
    from spreader.store import Store

    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default="var/demo")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0, help="a mix of this many filings, by industry")
    a = ap.parse_args()
    svc = Service(Store(Path(a.data_dir) / "spreader.sqlite3"))
    files = sample(library_files(), a.sample) if a.sample else library_files()
    done = failed = 0
    print(f"{len(files)} filings to load", flush=True)
    for path, m in files[: a.limit or None]:
        data = path.read_bytes()
        if svc.store.document(doc_id_for(data)) is not None:
            continue
        try:
            doc, view = svc.upload(path.name, data, "library-loader")
            if not doc.get("company_name") and m.get("company"):
                with svc.store.tx() as c:
                    c.execute("UPDATE documents SET company_name=? WHERE id=?", (m["company"], doc["id"]))
            done += 1
            print(f"{done:4d} {m.get('ticker', ''):8s} {doc.get('company_name') or m.get('company')}: run {view.run['status']}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad filing must not stop the rest
            failed += 1
            print(f"FAILED {path.name}: {type(exc).__name__}: {exc}", flush=True)
    print(f"Loaded {done}, failed {failed}, of {len(files)}", flush=True)


if __name__ == "__main__":
    main()
