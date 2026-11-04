"""Plain names for saved test reports (D64).

A report name such as ``stmt-insurer-dev-d62`` is a batch of test statements, not a company: statements (stmt), the
insurers among them, the practice split, measured at decision 62. Finance users see the plain name; the raw name stays
in the technical area, where engineers look it up.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_BATCH = re.compile(r"^stmt(?:-(?P<group>bank|insurer))?-(?P<split>dev|holdout)(?:-d(?P<update>\d+))?(?P<rest>.*)$")
GROUPS = {"public": "Public companies", "bank": "Banks", "insurer": "Insurers"}
SPLITS = {"holdout": "Validation set", "dev": "Practice set"}


def _words(text: str) -> str:
    return re.sub(r"[-_]+", " ", text).strip()


def describe_report(name: str) -> dict[str, Any]:
    """What a saved report is, in words a finance reader can use."""
    m = _BATCH.match(name)
    if m:
        group = m["group"] or "public"
        update = int(m["update"]) if m["update"] else None
        rest = _words(m["rest"])
        title = f"{GROUPS[group]}, {SPLITS[m['split']].lower()}"
        if update is not None:
            title += f", update {update}"
        if rest:
            title += f" ({rest})"
        return {"title": title, "group": group, "split": m["split"], "update": update, "plain_batch": not rest}
    if name.startswith(("syn-", "stmt-syn-")):
        label = _words(name.split("syn-", 1)[1])
        return {"title": f"Generated statements ({label})", "group": "generated", "split": None, "update": None,
                "plain_batch": False}
    return {"title": _words(name).capitalize(), "group": "other", "split": None, "update": None, "plain_batch": False}


def latest_batches(folder: Path) -> dict[tuple[str, str], Path]:
    """The newest update of each batch, by update number: file dates change when a report is copied."""
    best: dict[tuple[str, str], tuple[int, Path]] = {}
    for path in folder.glob("stmt*-d*.json"):
        about = describe_report(path.stem)
        if not about["plain_batch"] or about["update"] is None:
            continue
        key = (about["group"], about["split"])
        if key not in best or about["update"] > best[key][0]:
            best[key] = (about["update"], path)
    return {k: v[1] for k, v in best.items()}
