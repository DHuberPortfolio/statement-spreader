"""Scanned statement PDFs read by OCR (spreader.ingest.ocr, DECISIONS D42).

Most tests here need no OCR model: they hand the PDF reader the words an OCR pass would return (taken from a
synthetic statement's text layer), so the wiring, the confidence flags and the refusal are tested in every CI job.
The end-to-end test runs the real recogniser and is skipped when the optional `ocr` extra is not installed.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium
import pytest

from spreader.contracts import ReviewKind
from spreader.ingest import IngestError, ocr, read_document
from spreader.pipeline import spread_document

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.pdf"


def _image_only(pdf: bytes, dpi: int = 100) -> bytes:
    """The same pages as pictures: no text layer, as a scanner would produce."""
    doc = pdfium.PdfDocument(pdf)
    images = [doc[i].render(scale=dpi / 72, grayscale=True).to_pil() for i in range(len(doc))]
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=dpi)
    return buf.getvalue()


def _text_words(pdf: bytes) -> list[list[dict]]:
    with pdfplumber.open(io.BytesIO(pdf)) as p:
        return [pg.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["fontname", "size"])
                for pg in p.pages]


@pytest.fixture()
def fake_ocr(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """OCR that returns the text layer's words, each with confidence 0.99 unless a test lowers one."""
    pages = _text_words(SAMPLE.read_bytes())
    low: dict[str, float] = {}

    def page_words(data: bytes, i: int) -> tuple[list[dict], float, float]:
        words = [{**w, "fontname": "ocr", "ocr_confidence": low.get(w["text"], 0.99)} for w in pages[i]]
        return words, 612.0, 792.0

    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "page_words", page_words)
    return {"low": low}


def test_a_scan_without_the_ocr_extra_is_refused_with_how_to_fix_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "available", lambda: False)
    with pytest.raises(IngestError, match="no text layer.*optional OCR component"):
        read_document("scan.pdf", _image_only(SAMPLE.read_bytes()))


def test_a_scan_is_read_through_the_same_reader_and_says_so(fake_ocr: dict, profile: Any) -> None:
    text = spread_document(read_document("s.pdf", SAMPLE.read_bytes()), profile)[0]
    ir = read_document("scan.pdf", _image_only(SAMPLE.read_bytes()))
    assert any(w.startswith("OCR:") for w in ir.warnings)
    scan = spread_document(ir, profile)[0]
    # Same words in, same spread out: every value and period the text layer gave, the scan gives.
    assert {(v.line, v.period, v.value) for v in scan.values} == {(v.line, v.period, v.value) for v in text.values}
    refs = [pv.ref for r in ir.tables for row in r.rows for pv in row.tokens if pv.ref]
    assert refs and all(r.ocr_confidence == 0.99 for r in refs)


def test_a_low_confidence_digit_is_flagged_not_trusted(fake_ocr: dict, profile: Any) -> None:
    text = spread_document(read_document("s.pdf", SAMPLE.read_bytes()), profile)[0]
    target = next(v for v in text.values if v.status.value == "extracted" and v.refs and not v.flags)
    fake_ocr["low"][target.refs[0].text] = 0.62
    scan = spread_document(read_document("scan.pdf", _image_only(SAMPLE.read_bytes())), profile)[0]
    v = scan.value(target.line, target.period)
    items = [i for i in scan.review if i.kind is ReviewKind.UNREADABLE and i.id.startswith("ocr:")]
    assert items and "62% confidence" in items[0].message
    assert v is not None and v.flags, "a number the recogniser was unsure of must not be accepted without a person"


def test_too_many_scanned_pages_are_refused(fake_ocr: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "MAX_PAGES", 0)
    with pytest.raises(IngestError, match="OCR reads at most 0"):
        read_document("scan.pdf", _image_only(SAMPLE.read_bytes()))


def test_glued_words_are_split_only_into_known_words() -> None:
    assert ocr.split_glued("Researchanddevelopment") == ["Research", "and", "development"]
    assert ocr.split_glued("Short-terminvestments") == ["Short-term", "investments"]
    assert ocr.split_glued("Accountsreceivable,net") == ["Accounts", "receivable,", "net"]
    assert ocr.split_glued("5,539$") == ["5,539", "$"]
    assert ocr.split_glued("Goodwill") == ["Goodwill"]  # a known word is left alone
    assert ocr.split_glued("Xyzzyplughq") == ["Xyzzyplughq"]  # cannot be covered by known words: left as read
    # one unknown stretch (a company name) inside a long glued label is allowed; an unknown long word is not split
    assert ocr.split_glued("netincomeattributabletoacmeinc") == ["net", "income", "attributable", "to", "acme", "inc"]
    assert ocr.split_glued("Teleconferencing") == ["Teleconferencing"]
    assert ocr.split_glued("(1,234)") == ["(1,234)"]  # numbers are never changed


def test_a_wide_gap_inside_one_box_separates_label_and_number() -> None:
    text = "Cash $ 5,539"
    xs = [0, 10, 20, 30, 300, 310, 330, 340, 350, 360, 370, 380]  # a 270-pixel gap before "$"
    chars = [[[x, 0], [x + 9, 0], [x + 9, 20], [x, 20]] for x in xs]
    words = ocr._split_box(text, chars, [[0, 0], [389, 0], [389, 20], [0, 20]])
    assert [w[0] for w in words] == ["Cash", "$", "5,539"]
    assert words[0][2] < 50 and words[2][1] > 320


@pytest.mark.skipif(not ocr.available(), reason="the optional OCR extra is not installed")
def test_the_recogniser_reads_a_scanned_statement(profile: Any) -> None:
    text = spread_document(read_document("s.pdf", SAMPLE.read_bytes()), profile)[0]
    scan = spread_document(read_document("scan.pdf", _image_only(SAMPLE.read_bytes(), dpi=200)), profile)[0]
    want = {(v.line, v.period): v.value for v in text.values if v.status.value == "extracted"}
    got = {(v.line, v.period): v.value for v in scan.values}
    same = sum(1 for k, x in want.items() if got.get(k) == x)
    assert same >= 0.9 * len(want), f"{same} of {len(want)} read values match the text layer"
    wrong_unflagged = [v for v in scan.values if (v.line, v.period) in want and v.value != want[(v.line, v.period)]
                       and not v.flags]
    assert len(wrong_unflagged) <= 1


@pytest.mark.skipif(not ocr.available(), reason="the optional OCR extra is not installed")
def test_the_tilt_of_a_scan_is_measured_and_a_blank_page_is_left_alone() -> None:
    from PIL import Image, ImageDraw

    page = Image.new("L", (1700, 2200), 255)
    draw = ImageDraw.Draw(page)
    for y in range(200, 2000, 60):  # rows of "text": dark bars with gaps, like a printed statement
        for x in range(150, 1550, 120):
            draw.rectangle([x, y, x + 90, y + 22], fill=0)
    assert abs(ocr.skew_angle(page.rotate(0.6, fillcolor=255)) + 0.6) <= 0.1
    assert ocr.skew_angle(page) == 0.0
    assert ocr.skew_angle(Image.new("L", (1700, 2200), 255)) == 0.0


def test_dates_glued_by_the_recogniser_are_split() -> None:
    assert ocr.split_glued("September27,") == ["September", "27,"]
    assert ocr.split_glued("December31,2022") == ["December", "31,", "2022"]


def test_an_s_read_for_a_dollar_sign_before_an_amount_is_a_dollar_sign() -> None:
    words = [{"text": "S", "x0": 10, "x1": 14, "top": 0, "bottom": 10},
             {"text": "5,695", "x0": 20, "x1": 40, "top": 0, "bottom": 10},
             {"text": "S", "x0": 100, "x1": 104, "top": 0, "bottom": 10},
             {"text": "Corp", "x0": 110, "x1": 130, "top": 0, "bottom": 10},
             # "Total assets S ... 39,868": the "$" at the left of a wide column, far from its number
             {"text": "S", "x0": 10, "x1": 14, "top": 50, "bottom": 60},
             {"text": "39,868", "x0": 300, "x1": 330, "top": 50, "bottom": 60}]
    assert [w["text"] for w in ocr._dollar_signs(words)] == ["$", "5,695", "S", "Corp", "$", "39,868"]


def test_a_recogniser_failure_is_a_clear_refusal_not_an_empty_spread(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(data: bytes, i: int) -> tuple[list[dict], float, float]:
        raise ocr.OCRError(f"OCR failed on page {i + 1}: RuntimeException")

    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "page_words", broken)
    with pytest.raises(IngestError, match="OCR failed on page 1"):
        read_document("scan.pdf", _image_only(SAMPLE.read_bytes()))
