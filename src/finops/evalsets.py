"""Every evaluation set, by name: which files (or which generator and seed) make it up, and which are its answer key.

A number in the README is only traceable if one can say exactly what produced it. Each set has a *dataset version*
(a hash of every input and key file, and of how generated sets are generated) and a *key version* (the key files
alone). `scripts/eval_manifest.py` writes them to `eval/manifests/<set>.json` and checks the working tree against
them; every report records the versions of the sets it used (`finops.core.evaluation.provenance`), and the release
gate refuses to compare runs made on different versions.

Generated sets (reconciliation, data quality, spreadsheets) are hashed from the bytes their generator writes, so a
generator change that alters a set changes its version even though no file in the repository did.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from finops.core.fingerprint import sha256_bytes

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
MANIFESTS = EVAL / "manifests"

# The generator parameters the evaluations use (scripts/run_eval.py and the engines' run_report pass the same).
RECON_SEEDS = {"dev": 7, "holdout": 11, "stress": 13}
RECON_ROUND_SHARE = {"stress": 0.4}
RECON_SCALE = 300
DQ_SEEDS = {"dev": 21, "holdout": 22}
SHEETS_SEEDS = [31, 32]
INVOICE_SETS = ["dev", "holdout", "unseen", "unseen-e", "messy-31", "messy-32", "messy-33"]
# Calibration data for reconciliation rules (scripts/calibrate.py): seeds no evaluation uses, three kinds each.
RECON_CALIBRATION_SEEDS = range(2001, 2011)
RECON_CALIBRATION_KINDS = {"clean": (0.0, False), "stress": (0.4, False), "messy": (0.2, True)}
KEY_NAMES = {"truth.json", "key.json"}


@dataclass
class Entry:
    path: str  # relative to the repository, or "<generated>/..." for generator output
    sha256: str
    role: str  # "input" or "key"


@dataclass
class DataSet:
    name: str
    source: str  # how the set is made: "files" or the generator call
    entries: list[Entry] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)  # inputs recorded elsewhere but not on this machine (SEC filings)

    @property
    def version(self) -> str:
        return _digest([self.source] + [f"{e.role} {e.path} {e.sha256}" for e in self.entries])

    @property
    def key_version(self) -> str:
        return _digest([f"{e.path} {e.sha256}" for e in self.entries if e.role == "key"])

    def manifest(self) -> dict[str, Any]:
        return {"name": self.name, "source": self.source, "version": self.version, "key_version": self.key_version,
                "files": len(self.entries), "entries": [e.__dict__ for e in self.entries]}

    def summary(self) -> dict[str, Any]:
        """What a report records about the set it used."""
        committed = MANIFESTS / f"{self.name}.json"
        expected = json.loads(committed.read_text(encoding="utf-8"))["version"] if committed.exists() else None
        return {"name": self.name, "version": self.version, "key_version": self.key_version, "files": len(self.entries),
                "matches_manifest": None if expected is None else expected == self.version,
                **({"inputs_not_on_this_machine": len(self.absent)} if self.absent else {})}


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()[:16]


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.as_posix()


def _folder(name: str, folder: Path) -> DataSet:
    ds = DataSet(name, "files")
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix != ".md" and "__pycache__" not in p.parts:
            ds.entries.append(Entry(_rel(p), sha256_bytes(p.read_bytes()), "key" if p.name in KEY_NAMES else "input"))
    return ds


def workbook_content_hash(data: bytes) -> str:
    """A generated workbook is hashed by what it holds (every cell's value, type, number format, font colour and
    comment; sheet visibility; defined names), not by its zip bytes, which also depend on the openpyxl version that
    wrote them (CI installs the newest allowed one)."""
    import io

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data))
    parts: list[Any] = [sorted((n, str(d.attr_text)) for n, d in wb.defined_names.items())]
    for ws in wb.worksheets:
        parts.append([ws.title, ws.sheet_state])
        for row in ws.iter_rows():
            for c in row:
                if c.value is None and c.comment is None:
                    continue
                color = c.font.color.rgb if c.font and c.font.color is not None and isinstance(c.font.color.rgb, str) else None
                parts.append([c.coordinate, str(c.value), c.data_type, c.number_format, color,
                              c.comment.text if c.comment else None])
    return sha256_bytes(json.dumps(parts, default=str).encode())


def _generated(name: str, source: str, files: dict[str, bytes], keys: dict[str, Any]) -> DataSet:
    ds = DataSet(name, source)
    for n, data in sorted(files.items()):
        digest = workbook_content_hash(data) if n.endswith(".xlsx") else sha256_bytes(data)
        ds.entries.append(Entry(f"<generated>/{name}/{n}", digest, "input"))
    for n, obj in sorted(keys.items()):
        blob = json.dumps(obj, sort_keys=True, default=str).encode()
        ds.entries.append(Entry(f"<generated>/{name}/{n}", sha256_bytes(blob), "key"))
    return ds


def sec(split: str, prior: bool = False) -> DataSet:
    """SEC filings are not in the repository; their hashes are recorded in eval/sec/manifest.json when downloaded.
    prior=True: the 10-K filed a year before each one (manifest-prior.json; scripts/eval_company_memory.py)."""
    suffix = "-prior" if prior else ""
    manifest = json.loads((EVAL / "sec" / f"manifest{suffix}.json").read_text(encoding="utf-8"))
    ds = DataSet(f"sec-{split}{suffix}", f"files: SEC 10-K filings listed in eval/sec/manifest{suffix}.json "
                                         f"(downloaded by scripts/fetch_sec.py{' --prior' if prior else ''})")
    for t, m in sorted(manifest.items()):
        if m["split"] != split:
            continue
        raw = EVAL / "sec" / f"raw{suffix}" / m["file"]
        ds.entries.append(Entry(f"eval/sec/raw{suffix}/{m['file']}", m["sha256"], "input"))
        if not raw.exists():
            ds.absent.append(m["file"])
        if m.get("cal"):  # the calculation links shape the key (IMPROVEMENT_LOG #16)
            ds.entries.append(Entry(f"eval/sec/cal{suffix}/{m['cal']['file']}", m["cal"]["sha256"], "key"))
        key = EVAL / "sec" / f"keys{suffix}" / f"{t}.json"
        if key.exists():
            ds.entries.append(Entry(_rel(key), sha256_bytes(key.read_bytes()), "key"))
    return ds


def statements_synthetic() -> DataSet:
    ds = _folder("statements-synthetic", EVAL / "synthetic")
    ds.source = "files: generated by scripts/make_synthetic.py --seed 7 --count 40, committed"
    return ds


def recon(split: str) -> DataSet:
    from finops.recon.synthetic import generate

    seed, share = RECON_SEEDS[split], RECON_ROUND_SHARE.get(split, 0.0)
    bank, ledger, truth = generate(seed, RECON_SCALE, round_share=share)
    return _generated(f"recon-{split}", f"finops.recon.synthetic.generate(seed={seed}, scale={RECON_SCALE}, round_share={share})",
                      {"bank.csv": bank, "ledger.csv": ledger}, {"truth.json": truth})


def recon_calibration() -> DataSet:
    from finops.recon.synthetic import generate

    files: dict[str, bytes] = {}
    keys: dict[str, Any] = {}
    for seed in RECON_CALIBRATION_SEEDS:
        for kind, (share, messy) in RECON_CALIBRATION_KINDS.items():
            bank, ledger, truth = generate(seed, RECON_SCALE, round_share=share, messy=messy)
            files[f"{seed}-{kind}/bank.csv"], files[f"{seed}-{kind}/ledger.csv"] = bank, ledger
            keys[f"{seed}-{kind}/truth.json"] = truth
    return _generated("recon-calibration", f"finops.recon.synthetic.generate(seeds {RECON_CALIBRATION_SEEDS.start}-"
                      f"{RECON_CALIBRATION_SEEDS.stop - 1}, scale={RECON_SCALE}, kinds {RECON_CALIBRATION_KINDS})", files, keys)


def invoice(folder: str) -> DataSet:
    return _folder(f"invoice-{folder}", EVAL / "invoice" / folder)


def dq_synthetic(split: str) -> DataSet:
    from finops.dq.synthetic import generate

    seed = DQ_SEEDS[split]
    s = generate(seed)
    return _generated(f"dq-{split}", f"finops.dq.synthetic.generate({seed})",
                      {"portal.csv": s.portal_csv, "erp.xlsx": s.erp_xlsx, "previous.csv": s.previous_csv, "po.csv": s.po_csv},
                      {"vendor_truth.json": s.vendor_truth, "po_truth.json": s.po_truth})


def sheets_synthetic(seed: int) -> DataSet:
    from finops.sheets.synthetic import generate

    books, pairs = generate(seed)
    files = {b.name: b.data for b in books}
    files.update({p.before.name: p.before.data for p in pairs})
    files.update({p.after.name: p.after.data for p in pairs})
    truth = {"books": {b.name: {"faults": b.faults, "legit": b.legit} for b in books},
             "pairs": {f"{p.before.name} -> {p.after.name}": p.changes for p in pairs}}
    return _generated(f"sheets-synthetic-{seed}", f"finops.sheets.synthetic.generate({seed})", files, {"truth.json": truth})


def registry() -> dict[str, Callable[[], DataSet]]:
    """Every set, by name, built lazily (generating a set takes a few seconds)."""
    sets: dict[str, Callable[[], DataSet]] = {"sec-dev": lambda: sec("dev"), "sec-holdout": lambda: sec("holdout"),
                                               "statements-synthetic": statements_synthetic}
    if (EVAL / "sec" / "manifest-prior.json").exists():
        sets["sec-dev-prior"] = lambda: sec("dev", prior=True)
        sets["sec-holdout-prior"] = lambda: sec("holdout", prior=True)
    for split in RECON_SEEDS:
        sets[f"recon-{split}"] = lambda s=split: recon(s)  # type: ignore[misc]
    sets["recon-calibration"] = recon_calibration
    for f in INVOICE_SETS:
        if (EVAL / "invoice" / f).exists():
            sets[f"invoice-{f}"] = lambda f=f: invoice(f)  # type: ignore[misc]
    for split in DQ_SEEDS:
        sets[f"dq-{split}"] = lambda s=split: dq_synthetic(s)  # type: ignore[misc]
    for kind in ("dq", "sheets"):
        for folder in sorted((EVAL / kind).glob("independent-*")):
            sets[f"{kind}-{folder.name}"] = lambda k=kind, f=folder: _folder(f"{k}-{f.name}", f)  # type: ignore[misc]
    for seed in SHEETS_SEEDS:
        sets[f"sheets-synthetic-{seed}"] = lambda s=seed: sheets_synthetic(s)  # type: ignore[misc]
    return sets


def get(name: str) -> DataSet:
    return registry()[name]()


def summaries(names: list[str]) -> list[dict[str, Any]]:
    return [get(n).summary() for n in names]
