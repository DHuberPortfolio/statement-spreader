"""Which ratios and checks a profile now declares not applicable produced a value with the previous profile (D50).

    .venv/Scripts/python scripts/check_not_applicable.py 6b3af94   (the git ref of the earlier profiles)
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")
from spreader.ingest import read_document  # noqa: E402
from spreader.pipeline import spread_document  # noqa: E402
from spreader.profile import Profile, _overlay, load_profile  # noqa: E402

REF = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
base = yaml.safe_load(Path("config/profiles/us-commercial.yaml").read_text(encoding="utf-8"))
for ind in ("bank", "insurer"):
    old_raw = yaml.safe_load(subprocess.run(["git", "show", f"{REF}:config/profiles/us-{ind}.yaml"], capture_output=True,
                                            text=True, encoding="utf-8").stdout)
    old = Profile.model_validate(_overlay(base, old_raw))
    new = load_profile(f"config/profiles/us-{ind}.yaml")
    na = {k.split(":", 1)[1] for k in new.not_applicable if k.startswith("ratio:")}
    nac = {k.split(":", 1)[1] for k in new.not_applicable if k.startswith("check:")}
    man = json.loads(Path(f"eval/manifests/{ind}-dev.json").read_text())
    docs = sorted({e["path"] for e in man["entries"] if "/raw/" in e["path"]})
    hits: dict[str, int] = {}
    checks: dict[str, dict[str, int]] = {}
    for d in docs:
        try:
            s = spread_document(read_document(Path(d).name, Path(d).read_bytes()), old)[0]
        except Exception as exc:  # noqa: BLE001
            print("skip", d, type(exc).__name__)
            continue
        for r in s.ratios:
            if r.id in na and r.value is not None:
                hits[r.id] = hits.get(r.id, 0) + 1
        for c in s.checks:
            if c.id in nac:
                checks.setdefault(c.id, {}).setdefault(c.status.value, 0)
                checks[c.id][c.status.value] += 1
    print(ind, len(docs), "filings; not-applicable ratios that produced a value (ratio: count of filing-periods):", hits)
    print(ind, "not-applicable checks by status:", checks)
