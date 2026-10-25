"""Stable identities: the same bytes or the same settings always give the same short id.

Reruns are only safe if the system can tell "the same input again" from "a changed input".
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(obj: Any, length: int = 16) -> str:
    """Hash of a JSON-able value with sorted keys, so dict order never changes the id."""
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()[:length]


def stable_xlsx(wb: Any) -> bytes:
    """Save an openpyxl workbook with fixed timestamps, so the same content always gives the same bytes.

    openpyxl writes the save time (to the second) into docProps/core.xml and every zip entry, so two saves of one
    workbook a second apart differ, and a hash of a generated test set would change every time it is generated."""
    import io
    import re
    import zipfile
    from datetime import datetime

    wb.properties.created = wb.properties.modified = datetime(2026, 1, 1)
    buf = io.BytesIO()
    wb.save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                body = re.sub(rb"<dcterms:modified([^>]*)>[^<]*</dcterms:modified>",
                              rb"<dcterms:modified\1>2026-01-01T00:00:00Z</dcterms:modified>", body)
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            dst.writestr(zi, body)
    return out.getvalue()
