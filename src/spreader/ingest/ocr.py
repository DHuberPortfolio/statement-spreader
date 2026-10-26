"""Optical character recognition for scanned statement PDFs (DECISIONS D42).

Optional: installed with the `ocr` extra (`pip install -e .[ocr]`, which brings rapidocr-onnxruntime: a local ONNX
model, no system program, no network). Without it, a scan is refused with that reason, as before.

What it returns is what the PDF reader already works from: words with a box in PDF points (x0, x1, top, bottom), so
lines, cells, wrapped labels, statements and continued pages are found by exactly the same code as for a PDF with a
text layer, and the evidence box drawn on the page image lands on the printed number. Three things are added:

- **Confidence.** Each word carries the recogniser's score (`ocr_confidence`). The reader puts the lowest score of a
  cell on its SourceRef, and review flags every value read below `MIN_CONFIDENCE` (spreader.review): a number the
  model was unsure of goes to a person, never straight into an accepted spread. While `REVIEW_ALL` is on (the
  default), every value read from a scan is flagged, sure or not.
- **Deskew.** A scan is rarely square, and over a statement's width a 0.5 degree tilt moves a row by more than its own
  height, so labels and their numbers land on different lines. The recogniser's boxes come back square (they do not
  show the tilt), so the tilt is measured on the image: the angle, within 2 degrees, at which the rows of ink line up
  best (the sharpest horizontal projection), and the page is rotated straight before it is read.
- **Glued words.** The recogniser often drops the spaces in bold or tightly set text ("Researchanddevelopment",
  "CONSOLIDATEDSTATEMENTSOFOPERATIONS"). A run of letters that is not a known word is split into known words when
  it can be split completely; the vocabulary is the words of the template profiles (config/profiles) and the
  statement titles. Numbers are never changed: a cell that does not read as a clean amount stays text, and the
  value is missing and flagged, not guessed.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DPI = 200  # a common office-scanner resolution; also what the recogniser reads digits reliably at (D42)
MIN_CONFIDENCE = float(os.environ.get("SPREADER_OCR_MIN_CONFIDENCE", "0.90"))
# Every value read from a scan goes to a person, whatever its confidence, until OCR has been measured on real scans
# (D42): on printed-and-scanned 10-Ks the accepted values were silently wrong twice as often as with a text layer.
REVIEW_ALL = os.environ.get("SPREADER_OCR_REVIEW_ALL", "1") != "0"
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


def _cover(low: str, min_len: int = 1) -> list[int] | None:
    """Cut points that cover `low` completely with known words of at least `min_len` letters (fewest words; [] for
    ""), or None."""
    vocab = vocabulary()
    n = len(low)
    best: list[list[int] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        if best[i] is None:
            continue
        for j in range(i + min_len, min(n, i + 24) + 1):
            if low[i:j] in vocab and (best[j] is None or len(best[i]) + 1 < len(best[j])):  # type: ignore[arg-type]
                best[j] = [*best[i], j]  # type: ignore[misc]
    return best[n]


def _segment(letters: str) -> list[str] | None:
    """Known words covering `letters` completely (fewest words), or None. A long run may keep one unknown stretch,
    a name ("netincomeattributabletopfizerinc" -> net income attributable to pfizer inc), when it is at most a third
    of the run and the rest is at least two known words."""
    low = letters.lower()
    n = len(low)
    cuts = _cover(low)
    if cuts and 2 <= len(cuts) <= n // 2:
        pass
    elif n >= 12:
        cuts = None
        for size in range(3, n // 3 + 1):  # the shortest unknown stretch wins
            for i in range(0, n - size + 1):
                # around a name, no one-letter words ("a" would take the first letter of "acme")
                before, after = _cover(low[:i], 2), _cover(low[i + size:], 2)
                if before is not None and after is not None and len(before) + len(after) >= 2:
                    cuts = [*before, i + size, *[i + size + c for c in after]] if i else [size, *[size + c for c in after]]
                    break
            if cuts:
                break
        if not cuts:
            return None
    else:
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


def skew_angle(image: Any, limit: float = 2.0, step: float = 0.1) -> float:
    """The rotation (degrees, PIL's counter-clockwise sense) that makes a page's text rows horizontal: the angle whose
    horizontal ink profile is sharpest. Measured on a 1000-pixel-wide copy; 0.0 for a blank page."""
    import numpy as np
    from PIL import Image

    small = image.convert("L")
    if small.width > 1000:
        small = small.resize((1000, round(small.height * 1000 / small.width)))
    mask = np.asarray(small) < 128
    if mask.mean() < 0.002:  # a (nearly) blank page: every angle scores alike, so leave it as it is
        return 0.0
    ink = Image.fromarray((mask * 255).astype(np.uint8))

    def sharpness(angle: float) -> float:
        rows = np.asarray(ink.rotate(angle, resample=Image.NEAREST, fillcolor=0), dtype=np.float64).sum(axis=1)
        return float(np.square(np.diff(rows)).sum())

    level = sharpness(0.0)
    best, best_score = 0.0, level
    n = round(limit / step)
    for i in range(-n, n + 1):
        if i and (score := sharpness(i * step)) > best_score:
            best, best_score = i * step, score
    # Rotating resamples the page; only do it when the rows are clearly straighter, not for a marginal gain.
    return round(best, 2) if best_score > 1.1 * level else 0.0


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
    tilt = skew_angle(image)
    if abs(tilt) >= 0.1:  # rotated about the centre, so the page's coordinates are kept (the evidence box still fits)
        image = image.rotate(tilt, resample=3, expand=False, fillcolor=255)  # 3: bicubic
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
    words: list[dict] = []
    for r in boxes:
        box, text, score = r[0], str(r[1]), float(r[2])
        chars = r[3] if len(r) > 3 and r[3] else None  # one 4-point box per character, spaces included
        for w, x0, x1, top, bottom in _split_box(text, chars, box):
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
    """A lone "S" whose next word on the same line is an amount is the dollar sign read as a letter ("S 5,695"; in a
    statement the "$" sits at the left of a wide column, so the amount can be far to its right). Only the currency
    sign is changed; numbers are never."""
    for w in words:
        if w["text"] not in {"S", "s", "S(", "s("}:
            continue
        height = w["bottom"] - w["top"]
        mid = (w["top"] + w["bottom"]) / 2
        nxt = [o for o in words if o is not w and o["x0"] >= w["x1"] - 1
               and abs((o["top"] + o["bottom"]) / 2 - mid) < height / 2]
        if nxt and re.match(r"[(\d]", min(nxt, key=lambda o: o["x0"])["text"]):
            w["text"] = "$" + w["text"][1:]
    return words
