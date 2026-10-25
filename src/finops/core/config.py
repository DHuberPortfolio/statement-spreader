"""Configuration files: YAML, validated before anything runs, with company overlays.

A company adapts an engine by writing a small file that starts with `extends: <base file>` and
changes only what differs (its column names, its tolerances). Mappings are merged key by key;
lists are replaced, not appended, so an overlay can never half-inherit a rule list.

Validation happens here, once, with messages a person can act on. An engine never starts with
a configuration it has not validated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from .fingerprint import content_hash

T = TypeVar("T", bound=BaseModel)
MAX_DEPTH = 5


class ConfigError(ValueError):
    """The configuration is invalid; the message names the file and the field."""


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_raw(path: Path, _depth: int = 0) -> dict[str, Any]:
    if _depth > MAX_DEPTH:
        raise ConfigError(f"{path}: 'extends' chain is deeper than {MAX_DEPTH} (a loop?)")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: not valid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: the top level must be a mapping of settings")
    parent = data.pop("extends", None)
    if parent:
        base = load_raw((path.parent / str(parent)).resolve(), _depth + 1)
        data = deep_merge(base, data)
    return data


def validate(model: type[T], data: dict[str, Any], where: str) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or '(top)'}: {e['msg']}" for e in exc.errors())
        raise ConfigError(f"{where}: {problems}") from exc


def load_config(model: type[T], path: str | Path) -> tuple[T, str]:
    """Load, merge overlays, validate. Returns (config, version) where version is a content hash.

    The version changes whenever any effective setting changes, so a run records exactly which
    rules produced it, and a rerun under different rules is never mistaken for the same run.
    """
    p = Path(path)
    data = load_raw(p)
    return validate(model, data, p.name), content_hash(data)
