"""Organisation files: everything that differs between organisations in one checked place (DECISIONS D50)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from finops.core.config import load_config
from finops.core.organisation import OrganisationError, load, parse
from finops.invoice.config import APPolicy

ROOT = Path(__file__).resolve().parents[1]
ORGS = ROOT / "config" / "organisations"


def test_the_example_organisations_load_and_differ_where_they_should() -> None:
    bank, insurer = load(ORGS / "example-bank.env"), load(ORGS / "example-insurer.env")
    load(ORGS / "local-demo.env")
    differ = {k for k in bank if bank[k] != insurer[k]}
    assert differ == {"FINOPS_ORGANISATION", "FINOPS_AUTH_CONFIG", "SPREADER_PROFILE", "FINOPS_RETENTION_POLICY",
                      "FINOPS_AP_POLICY"}


def _flat(d: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(d, dict):
        out: dict[str, Any] = {}
        for k, v in d.items():
            out |= _flat(v, f"{prefix}{k}.")
        return out
    return {prefix.rstrip("."): d}


def test_an_organisations_payables_policy_changes_only_what_it_says() -> None:
    default, _ = load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "default-ap.yaml")
    strict, _ = load_config(APPolicy, ROOT / "config" / "finops" / "invoice" / "example-company-strict.yaml")
    a, b = _flat(default.model_dump(mode="json")), _flat(strict.model_dump(mode="json"))
    changed = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert changed and all(k.startswith(("id", "name", "matching.price_tolerance", "duplicates.window_days",
                                         "extra_labels", "wording", "labels")) for k in changed), sorted(changed)


@pytest.mark.parametrize("text,match", [
    ("FINOPS_OIDC_CLIENT_SECRET=abc\n", "secret"),
    ("FINOPS_DATA_KEY_FILE=k.key\n", "secret"),
    ("SOME_PASSWORD=x\n", "secret"),
    ("FINOPS_DEBUG=1\n", "unknown setting"),
    ("not a setting\n", "KEY=VALUE"),
    ("FINOPS_ORGANISATION=x\n", "missing"),
])
def test_organisation_files_refuse_secrets_typos_and_gaps(tmp_path: Path, text: str, match: str) -> None:
    f = tmp_path / "org.env"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(OrganisationError, match=match):
        parse(f)


def test_a_file_naming_another_organisations_sign_in_or_a_broken_file_does_not_start(tmp_path: Path) -> None:
    good = (ORGS / "example-bank.env").read_text(encoding="utf-8")
    f = tmp_path / "org.env"
    f.write_text(good.replace("FINOPS_ORGANISATION=example-bank", "FINOPS_ORGANISATION=other-bank"), encoding="utf-8")
    with pytest.raises(OrganisationError, match="sign-in file is for 'example-bank'"):
        load(f)
    f.write_text(good.replace("example-lender-overlay.yaml", "no-such-profile.yaml"), encoding="utf-8")
    with pytest.raises(OrganisationError):
        load(f)


def test_serve_refuses_an_invalid_organisation(tmp_path: Path) -> None:
    from spreader.cli import main

    f = tmp_path / "org.env"
    f.write_text("FINOPS_ORGANISATION=x\n", encoding="utf-8")
    assert main(["serve", "--org", str(f)]) == 1
