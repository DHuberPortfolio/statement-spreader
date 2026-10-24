"""Readers that turn a file into a DocumentIR: tables of positioned tokens with source references.

Every reader returns the same shape, so everything after ingestion is format-blind.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..contracts import DocumentIR, SourceFormat

MAX_BYTES = 40 * 1024 * 1024  # a 10-K with inline XBRL is ~2-10 MB; refuse anything absurd


class IngestError(ValueError):
    """The file could not be read as a supported statement document."""


def doc_id_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_format(filename: str, data: bytes) -> SourceFormat:
    """Decide the format from the bytes first, the file name second."""
    head = data[:8]
    if head.startswith(b"%PDF"):
        return SourceFormat.PDF
    if head.startswith(b"PK\x03\x04"):
        name = filename.lower()
        if name.endswith((".xlsx", ".xlsm")):
            return SourceFormat.XLSX
        raise IngestError("A zip file that is not an .xlsx workbook is not supported")
    sample = data[:4096].lower()
    if b"<html" in sample or b"<table" in sample or b"<?xml" in sample or b"<!doctype html" in sample:
        return SourceFormat.HTML
    raise IngestError("Unsupported file: expected HTML, PDF or an .xlsx workbook")


def read_document(filename: str, data: bytes) -> DocumentIR:
    if len(data) > MAX_BYTES:
        raise IngestError(f"File is {len(data) / 1e6:.1f} MB; the limit is {MAX_BYTES / 1e6:.0f} MB")
    if not data:
        raise IngestError("File is empty")
    fmt = sniff_format(filename, data)
    if fmt is SourceFormat.HTML:
        from .html_tables import read_html

        return read_html(filename, data)
    if fmt is SourceFormat.PDF:
        from .pdf_tables import read_pdf

        return read_pdf(filename, data)
    from .xlsx_tables import read_xlsx

    return read_xlsx(filename, data)


def read_path(path: str | Path) -> DocumentIR:
    p = Path(path)
    return read_document(p.name, p.read_bytes())
