"""The `spreader` command (declared in pyproject.toml).

    spreader serve [--host 127.0.0.1] [--port 8765]            # the review app, as in the README
    spreader spread FILE [--out OUT] [--profile PROFILE.yaml]  # one document -> spread (.xlsx, .csv or .json by OUT)
    spreader gate --dataset D.yaml --source ID=FILE ...         # data-quality gate on export files
    spreader scan WORKBOOK [--previous OLD.xlsx] [--out DIR]    # spreadsheet risk scan (the workbook is only read)

`spread` is for a quick look or a script. It does not record a run or a review, so its export says it was not
approved; spreads that go anywhere are reviewed and approved in the app.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from .export import to_csv, to_json, to_xlsx
from .ingest import IngestError, read_document
from .pipeline import spread_document
from .profile import load_profile


def _spread(args: argparse.Namespace) -> int:
    src = Path(args.file)
    profile = load_profile(args.profile)
    try:
        spread, _ = spread_document(read_document(src.name, src.read_bytes()), profile)
    except IngestError as exc:
        print(f"{src.name}: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else src.with_suffix(".spread.json")
    meta = {"filename": src.name, "approved": None, "exported_at": datetime.now(UTC).isoformat()}
    if out.suffix == ".xlsx":
        body = to_xlsx(spread, profile, meta)
    elif out.suffix == ".csv":
        body = to_csv(spread, profile)
    else:
        body = to_json(spread, meta)
    out.write_bytes(body)
    found = ", ".join(sorted(spread.statements)) or "none"
    print(f"{src.name}: statements found: {found}; {len(spread.review)} review items; written to {out}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("spreader.api:app", host=args.host, port=args.port)
    return 0


def _gate(args: argparse.Namespace) -> int:
    """Run the data-quality gate on files, without the app: accepted records, a quarantine report and a JSON result.
    Decisions by people (releases, corrections) need the app, where they are recorded and controlled."""
    import json

    from finops.core.config import ConfigError, load_config
    from finops.dq.config import DatasetSpec
    from finops.dq.engine import GateInputError, SourceInput, accepted_rows, gate
    from finops.dq.service import _csv, quarantine_rows

    try:
        spec, version = load_config(DatasetSpec, args.dataset)
    except ConfigError as exc:
        print(f"dataset configuration: {exc}", file=sys.stderr)
        return 2

    def pairs(items: list[str], what: str) -> list[tuple[str, Path]]:
        out = []
        for it in items:
            name, sep, path = it.partition("=")
            if not sep or not name or not path:
                raise SystemExit(f"--{what} takes NAME=FILE, got '{it}'")
            out.append((name, Path(path)))
        return out

    try:
        inputs = [SourceInput(s, p.name, p.read_bytes()) for s, p in pairs(args.source, "source")]
        refs = {n: (p.name, p.read_bytes()) for n, p in pairs(args.reference or [], "reference")}
        prev = (Path(args.previous).name, Path(args.previous).read_bytes()) if args.previous else None
    except OSError as exc:
        print(f"cannot read {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    try:
        res = gate(spec, inputs, refs, prev, config_version=version)
    except GateInputError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = accepted_rows(res)
    (out / f"{spec.id}-accepted.csv").write_bytes(_csv([res.columns] + [[r.get(c, "") for c in res.columns] for r in rows]))
    (out / f"{spec.id}-quarantine.csv").write_bytes(_csv(quarantine_rows(res)))
    (out / f"{spec.id}-result.json").write_text(json.dumps(json.loads(res.model_dump_json()), indent=1), encoding="utf-8")
    c = res.counts()
    print(f"{spec.name}: {c['accepted']} accepted, {c['review']} for review, {c['rejected']} rejected, {c['duplicate']} duplicate rows "
          f"(loaded once); {len(res.carried_forward)} last accepted version(s) carried forward; written to {out}")
    for w in res.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 1 if args.strict and (c["review"] or c["rejected"]) else 0


def _scan(args: argparse.Namespace) -> int:
    """Scan one workbook (and compare it with an earlier version): findings as JSON and CSV. Reviews (confirm,
    dismiss) need the app, where they are recorded and carried to the next version."""
    from finops.core.config import ConfigError, load_config
    from finops.sheets.config import ScanSpec
    from finops.sheets.service import scan_bytes
    from finops.sheets.workbook import WorkbookError

    try:
        spec, version = load_config(ScanSpec, args.config)
    except ConfigError as exc:
        print(f"scanner configuration: {exc}", file=sys.stderr)
        return 2
    src = Path(args.workbook)
    try:
        data = src.read_bytes()
        prev = (Path(args.previous).name, Path(args.previous).read_bytes()) if args.previous else None
    except OSError as exc:
        print(f"cannot read {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    try:
        res = scan_bytes(src.name, data, spec, version, prev)
    except WorkbookError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{src.stem}-scan.json").write_text(res.model_dump_json(indent=1), encoding="utf-8")
    c = res.counts()
    print(f"{src.name}: {c['error']} error(s), {c['risk']} risk(s), {c['anomaly']} anomalies"
          + (f", {c['material_changes']} material change(s) since {res.previous}" if prev else "") + f"; written to {out}")
    for f in res.findings:
        if f.severity != "anomaly" or args.all:
            where = f"{f.sheet}!{f.cell}" if f.sheet else (f.cell or "")
            print(f"  {f.severity:7} {f.kind:22} {where:24} {f.detail}")
    for ch in res.changes:
        if ch.material:
            print(f"  change  {ch.kind:22} {ch.sheet}!{ch.cell or ''}  {ch.detail}")
    for n in res.notes:
        print(f"note: {n}", file=sys.stderr)
    return 1 if args.strict and c["error"] else 0


def _data_dir(args: argparse.Namespace) -> Path:
    return Path(args.data or os.environ.get("SPREADER_DATA") or Path(__file__).resolve().parents[2] / "var")


def _vault_cmd(args: argparse.Namespace) -> int:
    """Data keys and encrypting stored files (DECISIONS D45)."""
    from finops.core.vault import Vault, VaultError, load_keys, new_key

    data = _data_dir(args)
    if args.action == "new-key":
        out = Path(args.out)
        if out.exists():
            print(f"{out} exists; not overwritten (a lost key means unreadable files)")
            return 1
        if out.resolve().is_relative_to(data.resolve()):
            print("Keep the key outside the data folder it protects")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(new_key() + "\n", encoding="ascii")
        print(f"Wrote a new 256-bit data key to {out}. Back it up separately from the data; set FINOPS_DATA_KEY_FILE to it.")
        return 0
    key_file = args.key or os.environ.get("FINOPS_DATA_KEY_FILE")
    try:
        v = Vault(load_keys(key_file, data)) if key_file else Vault([])
    except VaultError as exc:
        print(f"Key problem: {exc}")
        return 1
    folders = [data / "documents", data / "finops-files"]
    if args.action == "status":
        plain = enc = 0
        for f in folders:
            for path in f.rglob("*") if f.exists() else []:
                if path.is_file() and not path.name.endswith(".tmp"):
                    if v.is_encrypted(path):
                        enc += 1
                    else:
                        plain += 1
        print(f"{data}: {enc} encrypted, {plain} plain stored files; key configured: {'yes' if v.encrypting else 'no'}")
        return 1 if plain and v.encrypting else 0
    if not v.encrypting:
        print("No data key: set FINOPS_DATA_KEY_FILE or pass --key")
        return 1
    try:
        totals: dict[str, int] = {}
        for f in folders:
            if f.exists():
                for k, n in v.migrate(f).items():
                    totals[k] = totals.get(k, 0) + n
    except VaultError as exc:
        print(f"Stopped: {exc}. Files already done stay encrypted; run again after fixing the key.")
        return 1
    print(f"{data}: " + ", ".join(f"{n} {k}" for k, n in totals.items()))
    return 0


def _retention_cmd(args: argparse.Namespace) -> int:
    """Retention, erasure and legal holds from the command line (DECISIONS D46). Prints JSON; exit 1 on any failure."""
    import json

    from finops.core import retention as rt

    p = rt.platform_from_env(_data_dir(args))
    actor = rt.operator()
    policy = rt.load_policy(args.policy or os.environ.get("FINOPS_RETENTION_POLICY")
                            or Path(__file__).resolve().parents[2] / "config" / "finops" / "retention" / "default.yaml")
    try:
        if args.action in {"plan", "run"}:
            out = rt.run(p, policy, actor, apply=args.action == "run")
            print(json.dumps(out, indent=2, default=str))
            return 1 if out["failed"] or (args.action == "run" and out["incomplete"]) else 0
        if args.action == "erase":
            print(json.dumps(rt.erase(p, args.engine, args.unit, args.reason or "", actor), indent=2))
        elif args.action == "hold":
            print(json.dumps({"hold": rt.place_hold(p.db, args.engine, args.unit, args.reason or "", actor)}))
        elif args.action == "release":
            rt.release_hold(p.db, int(args.hold_id), actor, args.reason or "")
            print(json.dumps({"released": int(args.hold_id)}))
        else:
            print(json.dumps(rt.holds(p.db, active_only=False), indent=2))
    except rt.RetentionError as exc:
        print(f"Refused: {exc}")
        return 1
    return 0


def _backup_cmd(args: argparse.Namespace) -> int:
    """Consistent backups, backup checks and audit anchors (DECISIONS D47). Exit 1 when a check finds a problem."""
    import json

    from finops.core import backup as bk

    try:
        if args.action == "backup":
            m = bk.backup(_data_dir(args), Path(args.path))
            print(f"Backed up {len(m['databases'])} databases and {len(m['files'])} files to {args.path}"
                  f" (key not included; anchor {m['anchor']['statement']['id']}/{m['anchor']['platform']['id']})")
            return 0
        if args.action == "verify-backup":
            problems = bk.verify_backup(Path(args.path))
        elif args.action == "anchor":
            a = bk.anchor(_data_dir(args))
            out = Path(args.path)
            if out.exists():
                print(f"{out} exists; not overwritten")
                return 1
            out.write_text(json.dumps(a, indent=2), encoding="utf-8")
            print(f"Anchor written to {out}: keep a copy where the data folder's owner cannot change it")
            return 0
        else:
            problems = bk.check_anchor(_data_dir(args), json.loads(Path(args.path).read_text(encoding="utf-8")))
    except bk.BackupError as exc:
        print(f"Refused: {exc}")
        return 1
    for line in problems:
        print("PROBLEM", line)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="spreader", description="Financial statement spreading with review.")
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("serve", help="run the review app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(run=_serve)
    p = sub.add_parser("spread", help="spread one document (HTML, PDF or Excel) to a file")
    p.add_argument("file")
    p.add_argument("--out", help="output path; .xlsx, .csv or .json (default: FILE.spread.json)")
    p.add_argument("--profile", help="profile or organisation overlay YAML (default: the US commercial template)")
    p.set_defaults(run=_spread)
    g = sub.add_parser("gate", help="check records before another system loads them (data-quality gate)")
    g.add_argument("--dataset", required=True, help="dataset configuration, e.g. config/finops/dq/vendors.yaml")
    g.add_argument("--source", action="append", required=True, metavar="SOURCE=FILE", help="a source id from the configuration and its file")
    g.add_argument("--reference", action="append", metavar="DATASET=FILE", help="a file of another dataset this one refers to")
    g.add_argument("--previous", help="the last accepted export of this dataset (for changes to controlled fields)")
    g.add_argument("--out", default="dq-out", help="folder for the accepted, quarantine and result files")
    g.add_argument("--strict", action="store_true", help="exit with 1 when any record is held (for scheduled pipelines)")
    g.set_defaults(run=_gate)
    k = sub.add_parser("scan", help="scan a workbook for spreadsheet risks (never changes it)")
    k.add_argument("workbook")
    k.add_argument("--previous", help="an earlier version, to report material formula changes")
    k.add_argument("--config", default=str(Path(__file__).resolve().parents[2] / "config" / "finops" / "sheets" / "default.yaml"))
    k.add_argument("--out", default="scan-out", help="folder for the JSON result")
    k.add_argument("--all", action="store_true", help="also print the low-confidence anomalies")
    k.add_argument("--strict", action="store_true", help="exit with 1 when a definite error is found")
    k.set_defaults(run=_scan)
    v = sub.add_parser("vault", help="data keys and encryption of stored files")
    v.add_argument("action", choices=["new-key", "status", "migrate"])
    v.add_argument("--out", default="finops-data.key", help="new-key: where to write the key (outside the data folder)")
    v.add_argument("--key", help="key file (default FINOPS_DATA_KEY_FILE)")
    v.add_argument("--data", help="data folder (default SPREADER_DATA, else var/)")
    v.set_defaults(run=_vault_cmd)
    r = sub.add_parser("retention", help="retention policy, erasure and legal holds")
    r.add_argument("action", choices=["plan", "run", "erase", "hold", "release", "holds"])
    r.add_argument("--engine", choices=["statement", "invoice", "recon", "dq", "sheets"])
    r.add_argument("--unit", help="statement document id, or doc:<12 hex>, workspace:<id>, dataset:<id>, model:<name>")
    r.add_argument("--reason", help="why (erase, hold) or who authorised it (release)")
    r.add_argument("--hold-id", help="release: the hold's id")
    r.add_argument("--policy", help="retention policy YAML (default FINOPS_RETENTION_POLICY, else config default)")
    r.add_argument("--data", help="data folder (default SPREADER_DATA, else var/)")
    r.set_defaults(run=_retention_cmd)
    b = sub.add_parser("backup", help="consistent backup, backup check, audit anchors")
    b.add_argument("action", choices=["backup", "verify-backup", "anchor", "check-anchor"])
    b.add_argument("path", help="backup folder (backup, verify-backup) or anchor file (anchor, check-anchor)")
    b.add_argument("--data", help="data folder (default SPREADER_DATA, else var/)")
    b.set_defaults(run=_backup_cmd)
    args = ap.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    raise SystemExit(main())
