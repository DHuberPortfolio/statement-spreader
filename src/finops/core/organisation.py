"""One file per organisation: which configuration each part of the platform uses (DECISIONS D50).

    .venv/Scripts/spreader serve --org config/organisations/example-bank.env

An organisation file is KEY=VALUE lines naming the sign-in, statement profile, retention policy and payables policy
(paths relative to the repository). `load` validates every named file with the same loader the engine uses before
anything starts, so a typo stops the start rather than running on a default. Secrets never go in it: the identity
provider's client secret and the data key stay in the environment (D43, D45).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KEYS = {"FINOPS_ORGANISATION", "FINOPS_AUTH_CONFIG", "SPREADER_PROFILE", "FINOPS_RETENTION_POLICY", "FINOPS_AP_POLICY"}
FORBIDDEN = {"FINOPS_OIDC_CLIENT_SECRET", "FINOPS_DATA_KEY", "FINOPS_DATA_KEY_FILE"}


class OrganisationError(ValueError):
    pass


def parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise OrganisationError(f"{path.name} line {n}: expected KEY=VALUE")
        if key in FORBIDDEN or "SECRET" in key or "PASSWORD" in key:
            raise OrganisationError(f"{path.name} line {n}: {key} is a secret; set it in the environment, not here")
        if key not in KEYS:
            raise OrganisationError(f"{path.name} line {n}: unknown setting {key} (known: {sorted(KEYS)})")
        out[key] = value
    missing = KEYS - set(out)
    if missing:
        raise OrganisationError(f"{path.name}: missing {sorted(missing)}")
    return out


def load(path: str | Path) -> dict[str, str]:
    """Parse and validate an organisation file; returns the settings with absolute paths."""
    from finops.core.config import load_config
    from finops.invoice.config import APPolicy
    from spreader.profile import load_profile

    from .identity import load_auth_config
    from .retention import load_policy

    settings = parse(Path(path))
    resolved = {k: (v if k == "FINOPS_ORGANISATION" else str((ROOT / v).resolve())) for k, v in settings.items()}
    try:
        auth = load_auth_config(resolved["FINOPS_AUTH_CONFIG"])
        load_profile(resolved["SPREADER_PROFILE"])
        load_policy(resolved["FINOPS_RETENTION_POLICY"])
        load_config(APPolicy, resolved["FINOPS_AP_POLICY"])
    except Exception as exc:  # noqa: BLE001 - any invalid file stops the start, with its message
        raise OrganisationError(f"{Path(path).name}: {exc}") from exc
    if auth.organization != settings["FINOPS_ORGANISATION"]:
        raise OrganisationError(f"{Path(path).name}: the sign-in file is for '{auth.organization}', "
                                f"not '{settings['FINOPS_ORGANISATION']}'")
    return resolved


def apply(path: str | Path) -> dict[str, str]:
    settings = load(path)
    os.environ.update(settings)
    return settings
