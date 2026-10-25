"""Draft an invoice-wording overlay for an unknown supplier layout with a local model.

    llama-server -m Qwen3-4B-Instruct-2507-Q4_K_M.gguf -ngl 99 -c 8192 --host 127.0.0.1 --port 8088
    .venv/Scripts/python scripts/suggest_invoice_labels.py eval/invoice/unseen-e/invoices/inv-00*.pdf \
        --n 3 --out config/finops/invoice/suggested-layout-e.yaml

Writes a YAML overlay that `extends: default-ap.yaml`, headed as an UNREVIEWED draft. A person
reads it, corrects it and saves it as the company's overlay; nothing applies it automatically.
Answers are cached in var/llm-cache.sqlite3, so a rerun is repeatable without the GPU.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import yaml

from finops.core.config import load_config
from finops.invoice.config import APPolicy
from finops.invoice.suggest import LocalAsk, suggest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="PDF invoices of one layout (globs allowed)")
    ap.add_argument("--n", type=int, default=3, help="how many of them to read")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="http://127.0.0.1:8088")
    ap.add_argument("--policy", default=str(ROOT / "config" / "finops" / "invoice" / "default-ap.yaml"))
    args = ap.parse_args()
    files = sorted({f for pattern in args.files for f in glob.glob(pattern)})[: args.n]
    policy, version = load_config(APPolicy, args.policy)
    ask = LocalAsk(args.model, "qwen3-4b-instruct-2507-q4km")
    draft = suggest([Path(f).read_bytes() for f in files], policy, ask)
    out = Path(args.out)
    header = (f"# DRAFT suggested by a local model (Qwen3-4B, {ask.calls} calls, {ask.cache_hits} cached, {ask.errors} errors)\n"
              f"# from {len(files)} invoice(s): {', '.join(Path(f).name for f in files)}\n"
              f"# against policy {policy.id} {version}. UNREVIEWED: check every line before using it.\n"
              f"# What the model was asked and answered: {json.dumps(draft['considered'])}\n")
    body = {"extends": Path(args.policy).name, "id": out.stem, "name": f"Draft wording for {out.stem}",
            "extra_labels": draft["extra_labels"], "extra_columns": draft["extra_columns"]}
    out.write_text(header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
