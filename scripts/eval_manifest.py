"""Write or check the manifest of every evaluation set (finops.evalsets).

    .venv/Scripts/python scripts/eval_manifest.py write            # after a deliberate change to a set or its key
    .venv/Scripts/python scripts/eval_manifest.py check            # every set against its committed manifest
    .venv/Scripts/python scripts/eval_manifest.py check --files    # also hash the downloaded SEC filings

`check` exits 1 when a set's files (or its generator's output) no longer match the committed manifest: an answer key
edited by hand, a regenerated set, a generator that now writes something else. A change to a set is allowed, but it
has to be deliberate: rewrite the manifest in the same commit and say why in the commit message. SEC filings are not
in the repository (CI never has them); their recorded hashes are part of the set's version, and `--files` checks the
local copies against them.
"""

from __future__ import annotations

import argparse
import json
import sys

from finops.core.fingerprint import sha256_bytes
from finops.evalsets import MANIFESTS, ROOT, registry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["write", "check"])
    ap.add_argument("--only", default=None, help="comma-separated set names")
    ap.add_argument("--files", action="store_true", help="check: also hash inputs recorded elsewhere (SEC filings)")
    args = ap.parse_args()
    sets = registry()
    names = args.only.split(",") if args.only else sorted(sets)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    bad = 0
    for n in names:
        ds = sets[n]()
        path = MANIFESTS / f"{n}.json"
        if args.action == "write":
            path.write_text(json.dumps(ds.manifest(), indent=1) + "\n", encoding="utf-8")
            print(f"{n:28s} {ds.version}  ({len(ds.entries)} files) written")
            continue
        if not path.exists():
            print(f"{n:28s} NO MANIFEST (run: eval_manifest.py write --only {n})")
            bad += 1
            continue
        want = json.loads(path.read_text(encoding="utf-8"))
        problems = []
        if want["version"] != ds.version:
            old = {e["path"]: e["sha256"] for e in want["entries"]}
            new = {e.path: e.sha256 for e in ds.entries}
            problems += [f"changed {p}" for p in sorted(old.keys() & new.keys()) if old[p] != new[p]]
            problems += [f"added {p}" for p in sorted(new.keys() - old.keys())]
            problems += [f"removed {p}" for p in sorted(old.keys() - new.keys())]
            if want["source"] != ds.source:
                problems.append(f"source {want['source']!r} -> {ds.source!r}")
        if args.files:
            for e in ds.entries:
                f = ROOT / e.path
                if not e.path.startswith("<generated>") and f.exists() and sha256_bytes(f.read_bytes()) != e.sha256:
                    problems.append(f"local file differs from its recorded hash: {e.path}")
        status = "ok" if not problems else "CHANGED"
        absent = f", {len(ds.absent)} inputs not on this machine" if ds.absent else ""
        print(f"{n:28s} {ds.version}  {status}{absent}")
        for p in problems[:20]:
            print(f"    {p}")
        bad += bool(problems)
    if args.action == "check":
        print(f"{len(names) - bad} of {len(names)} sets match their manifests.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
