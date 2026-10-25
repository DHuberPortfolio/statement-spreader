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
