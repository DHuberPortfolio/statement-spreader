"""Scanned statement packages for measuring OCR (DECISIONS D42).

    .venv/Scripts/python scripts/make_scans.py                       # from eval/sec/pdf/*.pdf (printed dev 10-Ks)
    .venv/Scripts/python scripts/make_scans.py --source <folder>     # the printed PDFs live elsewhere

A real scanned package is the statements and a few pages around them, not a 150-page annual report, so each package
is the page range the text-layer PDF reader used for its statements (eval/sec/pdf/eval-overnight.json), widened by
two pages on each side (titles, notes and other tables around the statements stay in as distractors). Three copies
of the same pages are written to eval/sec/scans/ (git-ignored PDFs; manifest.json committed):

- text/    the same pages with their text layer: the baseline that isolates what OCR changes;
- clean/   rendered at 200 dpi in grey, light sensor noise, JPEG at quality 80, re-wrapped as an image-only PDF;
- skewed/  the same as clean, rotated by 0.3 to 0.8 degrees (direction and amount fixed per ticker).

Each ticker is assigned to a half by hash ("tune" or "check"): OCR settings are tuned on the tune half only, and the
check half is measured once at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import zlib
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "eval" / "sec"
OUT = SEC / "scans"
DPI = 200
NOISE_SD = 6.0  # grey levels
JPEG_QUALITY = 80


def half_of(ticker: str) -> str:
    return "tune" if zlib.crc32(f"ocr:{ticker}".encode()) % 2 == 0 else "check"


def page_range(doc: dict, n_pages: int) -> list[int] | None:
    pages = sorted({p for ps in doc.get("pages", {}).values() for p in ps})
    if not pages:
        return None
    return list(range(max(1, pages[0] - 2), min(n_pages, pages[-1] + 2) + 1))


def image_pdf(images: list[Image.Image]) -> bytes:
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=DPI)
    return buf.getvalue()


def degrade(img: Image.Image, rng: random.Random, angle: float) -> Image.Image:
    arr = np.asarray(img.convert("L"), dtype=np.float32)
    noise = np.random.default_rng(rng.randrange(2**32)).normal(0, NOISE_SD, arr.shape)
    out = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), "L")
    if angle:
        out = out.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return Image.open(io.BytesIO(buf.getvalue()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SEC / "pdf"), help="folder with the printed <TICKER>.pdf files")
    args = ap.parse_args()
    source = Path(args.source)
    report = json.loads((SEC / "pdf" / "eval-overnight.json").read_text(encoding="utf-8"))
    by_doc = {d["doc"].split(":", 1)[1]: d for d in report["documents"] if d["doc"].startswith("sec:")}
    manifest: dict[str, dict] = {}
    for variant in ("text", "clean", "skewed"):
        (OUT / variant).mkdir(parents=True, exist_ok=True)
    for ticker, d in sorted(by_doc.items()):
        src = source / f"{ticker}.pdf"
        if not src.exists():
            print(f"{ticker}: no printed PDF")
            continue
        pdf = pdfium.PdfDocument(str(src))
        pages = page_range(d, len(pdf))
        if pages is None:
            print(f"{ticker}: the text reader found no statement pages; left out")
            continue
        text = pdfium.PdfDocument.new()
        text.import_pages(pdf, [p - 1 for p in pages])
        buf = io.BytesIO()
        text.save(buf)
        rendered = [pdf[p - 1].render(scale=DPI / 72, grayscale=True).to_pil() for p in pages]
        rng = random.Random(f"scan:{ticker}")
        angle = round(rng.choice([-1, 1]) * rng.uniform(0.3, 0.8), 2)
        variants = {"text": buf.getvalue(),
                    "clean": image_pdf([degrade(im, random.Random(f"clean:{ticker}:{i}"), 0) for i, im in enumerate(rendered)]),
                    "skewed": image_pdf([degrade(im, random.Random(f"skew:{ticker}:{i}"), angle) for i, im in enumerate(rendered)])}
        entry = {"source": src.name, "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "pages": pages,
                 "half": half_of(ticker), "skew_degrees": angle}
        for name, data in variants.items():
            (OUT / name / f"{ticker}.pdf").write_bytes(data)
            entry[f"{name}_sha256"] = hashlib.sha256(data).hexdigest()
        manifest[ticker] = entry
        print(f"{ticker}: pages {pages[0]}-{pages[-1]} ({len(pages)}), {entry['half']}, skew {angle}")
    (OUT / "manifest.json").write_text(json.dumps({"dpi": DPI, "noise_sd": NOISE_SD, "jpeg_quality": JPEG_QUALITY,
                                                   "pages_from": "eval/sec/pdf/eval-overnight.json statement pages +-2",
                                                   "packages": manifest}, indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8")
    print(f"{len(manifest)} packages written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
