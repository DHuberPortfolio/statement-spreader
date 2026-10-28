"""Uploaded files encrypted at rest (DECISIONS D45).

Every engine stores what people upload (statements, bank and ledger exports, invoices, master-data exports,
workbooks) as files named by their SHA-256. With a data key configured, those files are written encrypted with
AES-256-GCM (the `cryptography` library): a short header, a random 96-bit nonce, then the ciphertext. The file's
name is bound in as associated data, so one stored file cannot be swapped for another without the read failing.

The key lives outside the data folder: FINOPS_DATA_KEY_FILE names a file holding one or more base64 keys, one per
line; the first encrypts, all can decrypt (so a key can be rotated: add the new key first, run `spreader vault
migrate`, then drop the old one). A key file inside the data folder is refused, because a copy of the folder would
carry its own key.

What this does not cover, stated in DATA_LIFECYCLE.md: the SQLite databases (spreads, review notes, audit payloads)
are not encrypted by the application; a deployment puts them on an encrypted volume. Files written before a key was
configured stay readable as plain files until `spreader vault migrate` encrypts them.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = b"FOV1"
NONCE = 12


class VaultError(Exception):
    """A key problem or a file that does not decrypt: never served as if it were the original."""


def _key_id(key: bytes) -> bytes:
    return hashlib.sha256(b"finops-vault-key-id" + key).digest()[:8]


@dataclass
class Vault:
    keys: list[bytes] = field(default_factory=list, repr=False)  # first one encrypts; never printed

    def __post_init__(self) -> None:
        for k in self.keys:
            if len(k) != 32:
                raise VaultError("Data keys must be 32 bytes (256 bits)")
        self._by_id = {_key_id(k): k for k in self.keys}

    @property
    def encrypting(self) -> bool:
        return bool(self.keys)

    def seal(self, name: str, data: bytes) -> bytes:
        if not self.keys:
            return data
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(NONCE)
        return MAGIC + _key_id(self.keys[0]) + nonce + AESGCM(self.keys[0]).encrypt(nonce, data, name.encode())

    def open(self, name: str, blob: bytes) -> bytes:
        if not blob.startswith(MAGIC):
            return blob  # written before encryption was configured; `spreader vault migrate` encrypts it
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        kid, nonce, body = blob[4:12], blob[12:12 + NONCE], blob[12 + NONCE:]
        key = self._by_id.get(kid)
        if key is None:
            raise VaultError(f"{name} was encrypted with a key that is not configured")
        try:
            return AESGCM(key).decrypt(nonce, body, name.encode())
        except InvalidTag as exc:
            raise VaultError(f"{name} does not decrypt: it was altered, or belongs under another name") from exc

    def write(self, path: Path, data: bytes) -> None:
        """Atomic: a crash leaves the old file or the new one, never half a file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(self.seal(path.name, data))
        tmp.replace(path)

    def read(self, path: Path) -> bytes:
        return self.open(path.name, path.read_bytes())

    def is_encrypted(self, path: Path) -> bool:
        with path.open("rb") as f:
            return f.read(4) == MAGIC

    def migrate(self, folder: Path) -> dict[str, int]:
        """Encrypt every plain stored file under `folder` with the active key, and re-encrypt files under an older
        key. Safe to run again: done files are skipped."""
        if not self.keys:
            raise VaultError("No data key configured (FINOPS_DATA_KEY_FILE)")
        counts = {"encrypted": 0, "re-encrypted": 0, "already": 0}
        active = _key_id(self.keys[0])
        for p in sorted(folder.rglob("*")):
            if not p.is_file() or p.suffix in {".sqlite3", ".key", ".tmp"} or p.name.endswith(("-wal", "-shm")):
                continue
            blob = p.read_bytes()
            if blob.startswith(MAGIC) and blob[4:12] == active:
                counts["already"] += 1
                continue
            plain = self.open(p.name, blob)
            self.write(p, plain)
            counts["re-encrypted" if blob.startswith(MAGIC) else "encrypted"] += 1
        return counts


def load_keys(key_file: str | Path, data_dir: str | Path | None = None) -> list[bytes]:
    path = Path(key_file).resolve()
    if data_dir is not None:
        d = Path(data_dir).resolve()
        if path == d or d in path.parents:
            raise VaultError("The data key must not be stored inside the data folder it protects")
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="ascii").splitlines() if ln.strip() and not ln.startswith("#")]
    except (OSError, UnicodeDecodeError) as exc:
        raise VaultError(f"Cannot read the data key file ({type(exc).__name__})") from exc
    try:
        keys = [base64.b64decode(ln, validate=True) for ln in lines]
    except ValueError as exc:
        raise VaultError("The data key file must hold base64 keys, one per line") from exc
    if not keys:
        raise VaultError("The data key file is empty")
    return keys


def new_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


_vault: Vault | None = None


def vault(data_dir: str | Path | None = None) -> Vault:
    """The process's vault, from FINOPS_DATA_KEY_FILE. Without a key, files are stored as they are, which is refused
    with FINOPS_ENV=production (fail-safe: production never silently stores plain files)."""
    global _vault
    if _vault is None:
        key_file = os.environ.get("FINOPS_DATA_KEY_FILE")
        if key_file:
            _vault = Vault(load_keys(key_file, data_dir))
        elif os.environ.get("FINOPS_ENV", "development").lower() == "production":
            raise VaultError("FINOPS_ENV=production needs FINOPS_DATA_KEY_FILE: uploaded files would be stored unencrypted")
        else:
            _vault = Vault([])
    return _vault


def set_vault(v: Vault | None) -> None:
    """Tests and the CLI set the vault explicitly."""
    global _vault
    _vault = v
