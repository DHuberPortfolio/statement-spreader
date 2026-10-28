from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spreader.profile import Profile, load_profile

AUTH_TEST_CONFIG = Path(__file__).parent / "fixtures" / "auth-test.yaml"


@pytest.fixture(scope="session")
def profile() -> Profile:
    return load_profile()


@pytest.fixture(autouse=True)
def _private_outcomes(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test writes reviewer outcomes to its own folder: a test's approvals in the real var/outcomes would be
    learned from as if a reviewer had made them (found 2026-10-25: 123 outcomes from test runs)."""
    monkeypatch.setenv("FINOPS_OUTCOMES_DIR", str(tmp_path_factory.mktemp("outcomes")))


@pytest.fixture(autouse=True)
def _test_sign_in(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Every test gets its own sign-in setup (development users from fixtures/auth-test.yaml, sessions in a temporary
    database), so no test can reach the API without signing in and none touches var/."""
    from finops.core.audit import Database
    from finops.core.identity import load_auth_config
    from spreader import auth_api

    a = auth_api.Auth(load_auth_config(AUTH_TEST_CONFIG), Database(tmp_path_factory.mktemp("auth") / "auth.sqlite3"))
    auth_api.configure(a)
    yield a
    auth_api.configure(None)


def client_as(app: Any, username: str | None) -> Any:
    """A test client signed in as one of the development users in fixtures/auth-test.yaml (None: not signed in)."""
    from fastapi.testclient import TestClient

    c = TestClient(app)
    if username is not None:
        r = c.post("/api/auth/dev-login", json={"username": username})
        assert r.status_code == 200, r.text
    return c


def statement_html(title: str, unit: str, header: list[str], rows: list[tuple], hidden: list[tuple] | None = None,
                   before: str = "") -> str:
    """A small statement table in the style of an SEC filing ("$" and ")" in their own cells)."""
    def cells(vals: tuple) -> str:
        out = []
        for v in vals:
            if v is None:
                out.append("<td></td><td></td><td></td>")
            elif isinstance(v, str) and v.startswith("("):
                out.append(f"<td></td><td>{v[:-1]}</td><td>)</td>")
            else:
                out.append(f"<td>$</td><td>{v}</td><td></td>")
        return "".join(out)

    head = "".join(f'<td colspan="3">{h}</td>' for h in header)
    body = []
    for r in rows:
        label, *vals = r
        style = ' style="padding-left:12pt"' if label.startswith("  ") else ""
        body.append(f"<tr><td{style}>{label.strip()}</td>{cells(tuple(vals))}</tr>")
    for r in hidden or []:
        label, *vals = r
        body.append(f'<tr style="display:none"><td>{label}</td>{cells(tuple(vals))}</tr>')
    return (f"<html><body>{before}<p>{title}</p><p>{unit}</p><table>"
            f"<tr><td></td>{head}</tr>{''.join(body)}</table></body></html>")
