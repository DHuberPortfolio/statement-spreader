"""What the local model costs per document: its time per row, GPU power, and the cost per 1,000 documents.

    llama-server -m Qwen3-4B-Instruct-2507-Q4_K_M.gguf -ngl 99 -c 8192 --host 127.0.0.1 --port 8088
    .venv/Scripts/python scripts/measure_model_cost.py --out eval/reports/model-cost-<date>.json
    .venv/Scripts/python scripts/measure_model_cost.py --from eval/reports/model-cost-2026-10-29.json

Spreads every input of an evaluation manifest with the rules alone, then asks the model about every labelled row (the
shadow role, D52) with an empty cache, so every answer is a real call. GPU power is sampled with nvidia-smi twice a
second; the idle draw is measured for 10 s first. The live role (D48) only asks about rows no rule placed, so its time
is the unplaced rows times the measured time per call. `--from` recomputes the costs from a saved measurement.

Prices are inputs, not measurements: pass today's published electricity price and GPU hourly rate. Counts the GPU's
own power only (not the rest of the computer) and no hardware cost.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class PowerSampler:
    """GPU power draw (W) from nvidia-smi, sampled twice a second while in use."""

    def __init__(self) -> None:
        self.samples: list[float] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            r = subprocess.run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True)
            with contextlib.suppress(ValueError, IndexError):
                self.samples.append(float(r.stdout.strip().splitlines()[0]))
            self._stop.wait(0.5)

    def __enter__(self) -> PowerSampler:
        self._t.start()
        return self

    def __exit__(self, *a: object) -> None:
        self._stop.set()
        self._t.join()


def measure(url: str, model_name: str, manifest: Path) -> dict:
    import httpx

    from spreader.ingest import read_document
    from spreader.llm import local as local_mod
    from spreader.pipeline import spread_document
    from spreader.profile import load_profile
    from spreader.shadow import second_opinions

    for _ in range(120):
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise SystemExit(f"no model server at {url}")
    local_mod.CACHE = Path(tempfile.mkdtemp()) / "fresh-cache.sqlite3"  # every answer a real call
    mapper = local_mod.LocalModelMapper(url, model_name=model_name)
    profile = load_profile()
    docs = [e["path"] for e in json.loads(manifest.read_text())["entries"] if e["role"] == "input"]

    with PowerSampler() as idle:
        time.sleep(10)
    per_doc = []
    with PowerSampler() as busy:
        for path in docs:
            ir = read_document(Path(path).name, (ROOT / path).read_bytes())
            t0 = time.perf_counter()
            spread = spread_document(ir, profile)[0]
            t1 = time.perf_counter()
            asked = mapper.calls + mapper.errors
            ops = second_opinions(spread, profile, mapper)
            t2 = time.perf_counter()
            unplaced = sum(1 for o in ops if o.platform_line is None and not o.platform_excluded)
            per_doc.append({"doc": Path(path).name, "rows": len(ops), "unplaced": unplaced,
                            "calls": mapper.calls + mapper.errors - asked, "rules_s": t1 - t0, "model_s": t2 - t1})
    n = len(per_doc)
    rules_s = sum(d["rules_s"] for d in per_doc)
    model_s = sum(d["model_s"] for d in per_doc)
    rows = [d["rows"] for d in per_doc]
    return {
        "measured_at": time.strftime("%Y-%m-%d"), "model": model_name, "manifest": manifest.name,
        "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True,
                              text=True).stdout.strip(),
        "documents": n, "rows_total": sum(rows), "rows_per_doc_mean": statistics.mean(rows),
        "rows_per_doc_median": statistics.median(rows), "rows_per_doc_max": max(rows),
        "unplaced_total": sum(d["unplaced"] for d in per_doc),
        "model_calls": mapper.calls, "model_errors": mapper.errors, "cache_hits": mapper.cache_hits,
        "rules_seconds_total": rules_s, "rules_seconds_per_doc": rules_s / n,
        "model_seconds_total": model_s, "model_seconds_per_doc": model_s / n,
        "model_seconds_per_call": model_s / max(1, mapper.calls + mapper.errors),
        "gpu_idle_watts": statistics.mean(idle.samples), "gpu_busy_watts_mean": statistics.mean(busy.samples),
        "power_samples": len(busy.samples), "per_doc": per_doc,
    }


def costs(r: dict, price_kwh: float, gpu_hourly: float) -> list[str]:
    out = [f"{r['documents']} documents, {r['rows_per_doc_mean']:.1f} rows each on average; "
           f"rules engine {r['rules_seconds_per_doc']:.3f} s per document; model {r['model_seconds_per_call']:.3f} s "
           f"per row, {r['model_errors']} errors; GPU {r['gpu_idle_watts']:.1f} W idle, {r['gpu_busy_watts_mean']:.1f} W busy"]
    roles = {"shadow (every row)": r["model_seconds_per_doc"],
             "live (unplaced rows only)": r["unplaced_total"] / r["documents"] * r["model_seconds_per_call"]}
    for name, s in roles.items():
        hours = s * 1000 / 3600
        kwh = r["gpu_busy_watts_mean"] * hours / 1000
        out.append(f"{name}: {s:.2f} s per document, {3600 / s:.0f} documents per hour; per 1,000 documents "
                   f"{hours:.2f} GPU-hours, {kwh:.2f} kWh = ${kwh * price_kwh:.2f} at ${price_kwh}/kWh, "
                   f"${hours * gpu_hourly:.2f} at ${gpu_hourly}/GPU-hour")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8088")
    ap.add_argument("--model-name", default="Qwen3-4B-Instruct-2507-Q4_K_M")
    ap.add_argument("--manifest", default=str(ROOT / "eval" / "manifests" / "sec-dev.json"))
    ap.add_argument("--out", help="where to save the measurement (JSON)")
    ap.add_argument("--from", dest="saved", help="recompute costs from a saved measurement instead of measuring")
    ap.add_argument("--price-kwh", type=float, default=0.1447, help="$ per kWh (default: EIA, U.S. commercial, Aug 2026)")
    ap.add_argument("--gpu-hourly", type=float, default=0.27, help="$ per GPU-hour (default: RunPod RTX A5000, Secure Cloud, Oct 2026)")
    args = ap.parse_args()
    if args.saved:
        r = json.loads(Path(args.saved).read_text(encoding="utf-8"))
    else:
        r = measure(args.url, args.model_name, Path(args.manifest))
        if args.out:
            Path(args.out).write_text(json.dumps(r, indent=2), encoding="utf-8")
    print("\n".join(costs(r, args.price_kwh, args.gpu_hourly)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
