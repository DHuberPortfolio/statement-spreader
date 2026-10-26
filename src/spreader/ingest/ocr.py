"""Optical character recognition for scanned statement PDFs (DECISIONS D42).

Optional: installed with the `ocr` extra (`pip install -e .[ocr]`, which brings rapidocr-onnxruntime: a local ONNX
model, no system program, no network). Without it, a scan is refused with that reason, as before.

What it returns is what the PDF reader already works from: words with a box in PDF points (x0, x1, top, bottom), so
lines, cells, wrapped labels, statements and continued pages are found by exactly the same code as for a PDF with a
text layer, and the evidence box drawn on the page image lands on the printed number. Three things are added:

- **Confidence.** Each word carries the recogniser's score (`ocr_confidence`). The reader puts the lowest score of a
  cell on its SourceRef, and review flags every value read below `MIN_CONFIDENCE` (spreader.review): a number the
  model was unsure of goes to a person, never straight into an accepted spread.
- **Deskew.** A scan is rarely square. The text boxes' own slope is measured (median of the long boxes) and every box
  is rotated back about the page centre, so a 0.5 degree tilt does not split one printed row into two lines.
- **Glued words.** The recogniser often drops the spaces in bold or tightly set text ("Researchanddevelopment",
  "CONSOLIDATEDSTATEMENTSOFOPERATIONS"). A run of letters that is not a known word is split into known words when
  it can be split completely; the vocabulary is the words of the template profiles (config/profiles) and the
  statement titles. Numbers are never changed: a cell that does not read as a clean amount stays text, and the
  value is missing and flagged, not guessed.
"""

from __future__ import annotations

import math
import os
import re
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any

DPI = 200  # a common office-scanner resolution; also what the recogniser reads digits reliably at (D42)
MIN_CONFIDENCE = float(os.environ.get("SPREADER_OCR_MIN_CONFIDENCE", "0.90"))
MAX_PAGES = int(os.environ.get("SPREADER_OCR_MAX_PAGES", "60"))
PROFILE_DIR = Path(__file__).resolve().parents[3] / "config" / "profiles"

_COMMON = """a an and as at by for from in of on or per the to with less plus net total other
consolidated combined condensed statement statements operations income loss earnings comprehensive balance sheet sheets
cash flows flow financial position condition changes stockholders shareholders shareowners equity deficit retained
years year ended ending months fiscal notes accompanying integral part these except share shares amounts
thousands millions billions dollars data table contents page form annual report incorporated corporation company
companies holdings group inc corp
january february march april may june july august september october november december""".split()  # noqa: SIM905
_MONTHS = set(_COMMON[_COMMON.index("january"):])


class OCRError(RuntimeError):
    """The recogniser failed on a page (the reader turns it into a clear refusal)."""


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _engine() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    threads = int(os.environ.get("SPREADER_OCR_THREADS", "-1"))  # -1: every core; set lower when running in parallel
    return RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=threads)


@lru_cache(maxsize=1)
def vocabulary() -> frozenset[str]:
    words = set(_COMMON)
    for p in PROFILE_DIR.glob("*.yaml"):
        words.update(w for w in re.findall(r"[a-z]+", p.read_text(encoding="utf-8").lower()) if len(w) > 2 or w in _COMMON)
    return frozenset(words)


def _segment(letters: str) -> list[str] | None:
    """Known words covering `letters` completely (fewest words), or None."""
    low = letters.lower()
    vocab = vocabulary()
    n = len(low)
    best: list[list[int] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        if best[i] is None:
            continue
        for j in range(i + 1, min(n, i + 24) + 1):
            if low[i:j] in vocab and (best[j] is None or len(best[i]) + 1 < len(best[j])):  # type: ignore[arg-type]
                best[j] = [*best[i], j]  # type: ignore[misc]
    cuts = best[n]
    if not cuts or len(cuts) < 2 or len(cuts) > n // 2:
        return None
    out, start = [], 0
    for c in cuts:
        out.append(letters[start:c])
        start = c
    return out


def split_glued(token: str) -> list[str]:
    """'Researchanddevelopment' -> ['Research', 'and', 'development']; 'Short-terminvestments' -> ['Short-term',
    'investments']. Each run of 6 or more letters that is not a known word is split when known words cover it
    completely (fewest words wins); anything else, digits included, is left exactly as read."""
    # A comma or closing bracket directly followed by a letter ("receivable,net", "(Gains)losses"), and a "$" stuck
    # to the end of a number ("5,539$", the next column's dollar sign) are word boundaries the recogniser dropped.
    # A month glued to its day or year ("September27,", "December31,2022") and a day glued to a year ("31,2022").
    token = re.sub(r"^((?i:" + "|".join(sorted(_MONTHS)) + r"))(?=\d)", r"\1 ", token)
    token = re.sub(r"(?<=\b\d\d,)(?=(?:19|20)\d\d\b)|(?<=\b\d,)(?=(?:19|20)\d\d\b)", " ", token)
    if " " in token:
        return [w for x in token.split() for w in split_glued(x)]
    pieces = [x for x in re.split(r"(?<=[,)])(?=[A-Za-z(])|(?<=\d)(?=\$)", token) if x]
    if len(pieces) > 1:
        return [w for x in pieces for w in split_glued(x)]
    vocab = vocabulary()
    out: list[str] = []
    for m in re.finditer(r"[A-Za-z]{6,}|[^A-Za-z]+|[A-Za-z]{1,5}", token):
        run = m.group(0)
        seg = None if not run.isalpha() or len(run) < 6 or run.lower() in vocab else _segment(run)
        if seg:
            if out:
                out[-1] += seg[0]
                out.extend(seg[1:])
            else:
                out.extend(seg)
        elif out:
            out[-1] += run
        else:
            out.append(run)
    return out or [token]


def _angle(box: list[list[float]]) -> float | None:
    (x0, y0), (x1, y1) = box[0], box[1]
    if x1 - x0 < 60:  # short boxes give a noisy slope
        return None
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def _split_box(text: str, chars: list[list[list[float]]] | None, box: list[list[float]]
               ) -> list[tuple[str, float, float, float, float]]:
    """One recognised box -> words (text, x0, x1, top, bottom) in pixels. With per-character boxes, a word ends at a
    space or at a gap wider than 1.5 character widths (a label and the numbers printed after it, "Cash $ 5,539",
    come back as one box; the gaps tell them apart). Without them, words share the box in proportion to length."""
    xs, ys = [p[0] for p in box], [p[1] for p in box]
    top, bottom = min(ys), max(ys)
    if chars and len(chars) == len(text):
        widths = sorted(max(p[0] for p in c) - min(p[0] for p in c) for c, ch in zip(chars, text, strict=True) if ch != " ")
        gap_limit = 1.5 * (widths[len(widths) // 2] if widths else 10)
        words: list[tuple[str, float, float, float, float]] = []
        cur, x0, x1, prev_x1 = "", 0.0, 0.0, None
        for ch, c in zip(text, chars, strict=True):
            cx0, cx1 = min(p[0] for p in c), max(p[0] for p in c)
            if ch == " " or (prev_x1 is not None and cx0 - prev_x1 > gap_limit):
                if cur:
                    words.append((cur, x0, x1, top, bottom))
                cur = ""
                if ch == " ":
                    prev_x1 = None
                    continue
            if not cur:
                x0 = cx0
            cur += ch
            x1, prev_x1 = cx1, cx1
        if cur:
            words.append((cur, x0, x1, top, bottom))
        return words
    parts = text.split()
    total = sum(len(w) for w in parts) + max(0, len(parts) - 1)
    out, x, w0, w1 = [], min(xs), min(xs), max(xs)
    for w in parts:
        span = (w1 - w0) * len(w) / max(1, total)
        out.append((w, x, x + span, top, bottom))
        x += span + (w1 - w0) / max(1, total)
    return out


def page_words(data: bytes, page_index: int) -> tuple[list[dict], float, float]:
    """OCR one page: (words in PDF points, page width, page height). Each word dict has the keys the PDF reader uses
    (text, x0, x1, top, bottom, size, fontname) plus ocr_confidence."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        page = doc[page_index]
        width, height = page.get_size()
        image = page.render(scale=DPI / 72, grayscale=True).to_pil()
        page.close()
    finally:
        doc.close()
    result = None
    for attempt in (1, 2):  # the runtime can fail to allocate under memory pressure; one retry, then say so
        try:
            result, _ = _engine()(image, use_cls=False, return_word_box=True)
            break
        except Exception as exc:  # noqa: BLE001 - onnxruntime raises its own exception types
            if attempt == 2:
                raise OCRError(f"OCR failed on page {page_index + 1}: {type(exc).__name__}") from exc
            import gc

            gc.collect()
    k = 72 / DPI
    boxes = [r for r in (result or []) if str(r[1]).strip()]
    angles = [a for a in (_angle(r[0]) for r in boxes) if a is not None and abs(a) < 5]
    tilt = statistics.median(angles) if len(angles) >= 5 else 0.0
    cx, cy = image.width / 2, image.height / 2
    cos, sin = math.cos(math.radians(-tilt)), math.sin(math.radians(-tilt))

    def straighten(pts: list[list[float]]) -> list[list[float]]:
        if not tilt:
            return [[float(x), float(y)] for x, y in pts]
        return [[cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos] for x, y in pts]

    words: list[dict] = []
    for r in boxes:
        box, text, score = r[0], str(r[1]), float(r[2])
        chars = r[3] if len(r) > 3 and r[3] else None  # one 4-point box per character, spaces included
        if chars:
            chars = [straighten(c) for c in chars]
        for w, x0, x1, top, bottom in _split_box(text, chars, straighten(box)):
            pieces = split_glued(w)
            total = sum(len(p) for p in pieces) + len(pieces) - 1
            x = x0
            for piece in pieces:
                span = (x1 - x0) * len(piece) / max(1, total)
                words.append({"text": piece, "x0": x * k, "x1": (x + span) * k, "top": top * k, "bottom": bottom * k,
                              "size": (bottom - top) * k * 0.8, "fontname": "ocr", "ocr_confidence": score})
                x += span + (x1 - x0) / max(1, total)
    return _dollar_signs(words), float(width), float(height)


def _dollar_signs(words: list[dict]) -> list[dict]:
    """A lone "S" just before an amount on the same line is the dollar sign read as a letter ("S 5,695"). Only the
    currency sign is changed; numbers are never."""
    for w in words:
        if w["text"] not in {"S", "s", "S(", "s("}:
            continue
        height = w["bottom"] - w["top"]
        mid = (w["top"] + w["bottom"]) / 2
        nxt = [o for o in words if o is not w and o["x0"] >= w["x1"] - 1 and o["x0"] - w["x1"] < 4 * height
               and abs((o["top"] + o["bottom"]) / 2 - mid) < height / 2]
        if nxt and re.match(r"[(\d]", min(nxt, key=lambda o: o["x0"])["text"]):
            w["text"] = "$" + w["text"][1:]
    return words
