"""Sign-in, roles and separation of duties through the real application boundary (DECISIONS D43).

The OIDC tests run a small identity provider in-process: an RSA key pair, a discovery document, a key set and a token
endpoint served through httpx's mock transport. It proves the integration boundary (discovery, PKCE, state, nonce,
signature, issuer, audience, expiry, tenant) - not that a particular live provider is configured correctly.
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from conftest import client_as
from finops.core import identity as idn
from finops.core.audit import Database
from finops.core.config import ConfigError, load_raw
from spreader import api, auth_api
from spreader.service import Service
from spreader.store import Store

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "https://idp.test.localhost"  # not https-checked: *.localhost counts as local only for dev hosts, so use https
CLIENT = "finops-test-client"


# -- a local OpenID provider ---------------------------------------------------------------------------------------


class Provider:
    def __init__(self, issuer: str = ISSUER, kid: str = "k1") -> None:
        self.issuer, self.kid = issuer, kid
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption())
        pub = self.key.public_key().public_numbers()
        b64 = lambda n: base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()  # noqa: E731
        self.jwk = {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": b64(pub.n), "e": b64(pub.e)}
        self.down = False
        self.pending_nonce: str | None = None
        self.token_claims: dict[str, Any] = {}
        self.token_requests: list[dict[str, str]] = []

    def token(self, **over: Any) -> str:
        t = int(time.time())
        claims = {"iss": self.issuer, "sub": "user-123", "aud": CLIENT, "iat": t, "exp": t + 300,
                  "preferred_username": "alice@example.test", "name": "Alice", "roles": ["FinOps.Approver"]}
        claims.update(over)
        claims = {k: v for k, v in claims.items() if v is not None}
        headers = {"kid": over.pop("_kid", self.kid)} if "_kid" in over else {"kid": self.kid}
        claims.pop("_kid", None)
        return jwt.encode(claims, self.pem, algorithm="RS256", headers=headers)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down", request=request)
        url = str(request.url)
        if url == self.issuer + "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": self.issuer, "authorization_endpoint": self.issuer + "/authorize",
                                             "token_endpoint": self.issuer + "/token", "jwks_uri": self.issuer + "/jwks"})
        if url == self.issuer + "/jwks":
            return httpx.Response(200, json={"keys": [self.jwk]})
        if url == self.issuer + "/token" and request.method == "POST":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            return httpx.Response(200, json={"id_token": self.token(nonce=self.pending_nonce, **self.token_claims),
                                             "token_type": "Bearer"})
        return httpx.Response(404)

    def http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def oidc_config(**over: Any) -> idn.AuthConfig:
    base = load_raw(ROOT / "config" / "finops" / "auth" / "roles-base.yaml")
    raw = {**base, "mode": "oidc", "organization": "test-bank",
           "oidc": {"issuer": ISSUER, "client_id": CLIENT, "redirect_uri": "https://app.test/api/auth/callback",
                    "roles_claim": "roles"},
           "role_map": {"FinOps.Preparer": ["preparer"], "FinOps.Approver": ["approver"], "FinOps.Auditor": ["auditor"]},
           "session": {"secure_cookie": False}}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(raw.get(k), dict):
            raw[k] = {**raw[k], **v}
        else:
            raw[k] = v
    return idn.AuthConfig.model_validate(raw)


@pytest.fixture()
def oidc(tmp_path: Path) -> Any:
    prov = Provider()
    cfg = oidc_config()
    a = auth_api.Auth(cfg, Database(tmp_path / "auth.sqlite3"), provider=idn.OIDCProvider(cfg.oidc, http=prov.http()))  # type: ignore[arg-type]
    auth_api.configure(a)
    return prov, a


@pytest.fixture()
def statements(tmp_path: Path, profile: Any, monkeypatch: pytest.MonkeyPatch) -> Service:
    svc = Service(Store(tmp_path / "db.sqlite3"), profile=profile)
    monkeypatch.setattr(api, "service", lambda: svc)
    return svc


def _sample_html() -> bytes:
    """A clean synthetic statement package (no blockers), the one the smoke check approves."""
    return (ROOT / "eval" / "synthetic" / "s7-001-clean" / "statement.html").read_bytes()


# -- 1. unauthenticated requests are refused --------------------------------------------------------------------------


def _example_path(pattern: str) -> str:
    return re.sub(r"\[\^/\]\+", "1", pattern).replace("\\.", ".")


def test_every_protected_route_refuses_a_caller_who_is_not_signed_in(statements: Service) -> None:
    c = TestClient(api.app)
    for method, pattern, _ in auth_api.ROUTE_PERMISSIONS:
        r = c.request(method, _example_path(pattern), json={})
        assert r.status_code == 401, (method, pattern, r.status_code)
        assert r.json()["sign_in"] is True


def test_every_api_route_in_the_source_has_a_permission_and_unknown_routes_are_closed() -> None:
    decl = re.compile(r'@(app|router)\.(get|post|put|patch|delete)\("([^"]+)"')
    prefixes = {"src/finops/api.py": "/api/finops", "src/spreader/auth_api.py": "/api/auth", "src/spreader/admin_api.py": "/api/admin"}
    missing = []
    for f in ["src/spreader/api.py", "src/spreader/roi_api.py", "src/finops/api.py", "src/spreader/auth_api.py",
              "src/spreader/admin_api.py"]:
        for _, method, path in decl.findall((ROOT / f).read_text(encoding="utf-8")):
            full = prefixes.get(f, "") + path
            if not full.startswith("/api/") or (method.upper(), full) in auth_api.PUBLIC:
                continue
            if auth_api.permission_for(method.upper(), _example_path(re.sub(r"\{[^}]+\}", "x", full))) is None:
                missing.append((method, full))
    assert not missing, f"routes without a permission (they would be refused): {missing}"
    assert client_as(api.app, "dana").get("/api/not-a-route").status_code == 403


# -- 2. a forged name cannot establish identity ------------------------------------------------------------------------


def test_a_reviewer_name_header_is_not_identity(statements: Service) -> None:
    anon = TestClient(api.app)
    assert anon.get("/api/documents", headers={"X-Actor": "ari"}).status_code == 401
    pat = client_as(api.app, "pat")
    r = pat.post("/api/documents", files={"file": ("a.htm", _sample_html())}, headers={"X-Actor": "ari"})
    assert r.status_code == 200
    events = statements.store.query("SELECT actor FROM events")
    assert {e["actor"] for e in events} == {"dev:pat"}, "the audit log must name the signed-in user, not the header"


def test_a_cookie_the_server_did_not_issue_is_worthless(statements: Service) -> None:
    c = TestClient(api.app)
    c.cookies.set(auth_api.COOKIE, "dev:ari")
    assert c.get("/api/documents").status_code == 401
    c.cookies.set(auth_api.COOKIE, "x" * 5000)
    assert c.get("/api/documents").status_code == 401


def test_development_sign_in_refuses_unknown_users_and_odd_bodies() -> None:
    c = TestClient(api.app)
    assert c.post("/api/auth/dev-login", json={"username": "mallory"}).status_code == 401
    assert c.post("/api/auth/dev-login", json=["pat"]).status_code == 401
    assert c.post("/api/auth/dev-login", content=b"pat", headers={"content-type": "application/json"}).status_code == 400


# -- 3. each role can do what it is granted, and nothing else ----------------------------------------------------------


@pytest.mark.parametrize("user", ["pat", "rae", "ari", "aud", "adm", "vic", "nobody"])
def test_each_role_is_refused_every_route_it_is_not_granted(user: str, _test_sign_in: Any) -> None:
    # Allowed routes are not called here (they would act on the real data folder); the engine tests and the smoke
    # check exercise them. Every refusal goes through the real middleware.
    p = idn.dev_principal(_test_sign_in.cfg, user)
    c = client_as(api.app, user)
    refused = 0
    for method, pattern, perm in auth_api.ROUTE_PERMISSIONS:
        if not p.can(perm):
            r = c.request(method, _example_path(pattern), json={})
            assert r.status_code == 403, (user, method, pattern, r.status_code)
            refused += 1
    granted = {perm for _, _, perm in auth_api.ROUTE_PERMISSIONS if p.can(perm)}
    assert granted == set(p.permissions) & {perm for _, _, perm in auth_api.ROUTE_PERMISSIONS}
    assert refused > 0 or user == "never"


def test_the_role_table_keeps_approving_apart_from_administering(_test_sign_in: Any) -> None:
    roles = _test_sign_in.cfg.roles
    assert not [r for r, perms in roles.items() if "approve" in perms and "admin" in perms]
    # only the one-analyst role (D51) both uploads and approves; the two-person roles keep them apart
    assert [r for r, perms in roles.items() if "approve" in perms and "upload" in perms] == ["analyst"]


def test_statement_actions_need_the_permission_of_the_action(statements: Service) -> None:
    run = client_as(api.app, "pat").post("/api/documents", files={"file": ("a.htm", _sample_html())}).json()["run"]["id"]
    vic, rae, pat = client_as(api.app, "vic"), client_as(api.app, "rae"), client_as(api.app, "pat")
    assert vic.post(f"/api/runs/{run}/actions", json={"type": "approve"}).status_code == 403
    assert rae.post(f"/api/runs/{run}/actions", json={"type": "approve"}).status_code == 403  # reviewers do not approve
    assert pat.post(f"/api/runs/{run}/actions", json={"type": "resolve_item", "item": "x", "note": "y"}).status_code == 403
    assert client_as(api.app, "adm").post(f"/api/runs/{run}/actions", json={"type": "approve"}).status_code == 403
    assert vic.get(f"/api/runs/{run}/export.json").status_code == 403
    assert client_as(api.app, "aud").get(f"/api/runs/{run}/export.json").status_code == 200


def test_bank_detail_verification_and_record_release_need_approve() -> None:
    rae = client_as(api.app, "rae")
    r = rae.post("/api/finops/invoices/x/resolve", json={"exception_id": "e", "action": "verified_independently", "note": "n"})
    assert r.status_code == 403
    r = rae.post("/api/finops/dq/runs/1/decide", json={"record_id": "r", "action": "release", "note": "n"})
    assert r.status_code == 403


# -- 4. changing an identifier does not get round a refusal -------------------------------------------------------------


def test_changing_the_resource_id_does_not_bypass_authorization(statements: Service) -> None:
    pat = client_as(api.app, "pat")
    first = pat.post("/api/documents", files={"file": ("a.htm", _sample_html())}).json()["run"]["id"]
    vic = client_as(api.app, "vic")
    for rid in [first, first + 1, 0, -1, 10**9, "1;DROP", "../1"]:
        assert vic.post(f"/api/runs/{rid}/actions", json={"type": "approve"}).status_code in {403, 404, 422}  # 422: not an id at all
        assert vic.get(f"/api/runs/{rid}/export.csv").status_code in {403, 404}
    assert TestClient(api.app).get(f"/api/runs/{first}").status_code == 401


# -- 5. tokens: expired, malformed, wrong signer, wrong audience... are refused ----------------------------------------


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_valid_provider_token_signs_in_with_mapped_roles(oidc: Any) -> None:
    prov, _ = oidc
    c = TestClient(api.app)
    me = c.get("/api/auth/me", headers=_bearer(prov.token()))
    assert me.status_code == 200, me.text
    assert me.json()["actor"] == "alice@example.test" and me.json()["roles"] == ["approver"] and me.json()["verified"]
    assert me.headers["x-auth-mode"] == "oidc"


@pytest.mark.parametrize("case", ["expired", "not_yet", "wrong_issuer", "wrong_audience", "no_sub", "unknown_kid",
                                  "tampered", "alg_none", "hs256_confusion", "other_key", "garbage", "huge"])
def test_bad_tokens_are_refused(oidc: Any, case: str) -> None:
    prov, _ = oidc
    t = int(time.time())
    if case == "expired":
        tok = prov.token(exp=t - 3600, iat=t - 7200)
    elif case == "not_yet":
        tok = prov.token(nbf=t + 3600)
    elif case == "wrong_issuer":
        tok = prov.token(iss="https://evil.example")
    elif case == "wrong_audience":
        tok = prov.token(aud="someone-else")
    elif case == "no_sub":
        tok = prov.token(sub=None)
    elif case == "unknown_kid":
        tok = prov.token(_kid="k9")
    elif case == "tampered":
        h, p, s = prov.token().split(".")
        body = json.loads(base64.urlsafe_b64decode(p + "=="))
        body["roles"] = ["FinOps.Admin", "FinOps.Approver"]
        p2 = base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=").decode()
        tok = f"{h}.{p2}.{s}"
    elif case == "alg_none":
        tok = jwt.encode({"iss": ISSUER, "sub": "x", "aud": CLIENT, "iat": t, "exp": t + 300}, None, algorithm="none")
    elif case == "hs256_confusion":
        pub = prov.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode()).rstrip(b"=").decode()
        p = base64.urlsafe_b64encode(json.dumps({"iss": ISSUER, "sub": "x", "aud": CLIENT, "iat": t, "exp": t + 300}).encode()).rstrip(b"=").decode()
        import hashlib
        import hmac

        sig = base64.urlsafe_b64encode(hmac.new(pub, f"{h}.{p}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        tok = f"{h}.{p}.{sig}"
    elif case == "other_key":
        tok = Provider().token()  # same issuer and kid, but signed by a key the provider does not publish
    elif case == "garbage":
        tok = "not.a.token"
    else:
        tok = "a." + "b" * 20000 + ".c"
    r = TestClient(api.app).get("/api/auth/me", headers=_bearer(tok))
    assert r.status_code == 401, (case, r.text)


def test_tokens_are_refused_when_the_provider_is_unreachable(oidc: Any) -> None:
    prov, a = oidc
    a.provider._keys = {}  # nothing cached
    prov.down = True
    assert TestClient(api.app).get("/api/auth/me", headers=_bearer(prov.token())).status_code == 401
    assert TestClient(api.app).get("/api/auth/login").status_code == 503


def test_a_token_from_another_tenant_is_refused(tmp_path: Path) -> None:
    prov = Provider()
    cfg = oidc_config(oidc={**oidc_config().oidc.model_dump(), "required_claims": {"tid": "tenant-a"}})  # type: ignore[union-attr]
    auth_api.configure(auth_api.Auth(cfg, Database(tmp_path / "a.sqlite3"), idn.OIDCProvider(cfg.oidc, http=prov.http())))  # type: ignore[arg-type]
    c = TestClient(api.app)
    assert c.get("/api/auth/me", headers=_bearer(prov.token(tid="tenant-a"))).status_code == 200
    assert c.get("/api/auth/me", headers=_bearer(prov.token(tid="tenant-b"))).status_code == 401
    assert c.get("/api/auth/me", headers=_bearer(prov.token())).status_code == 401


def test_a_user_whose_groups_map_to_no_role_can_do_nothing(oidc: Any) -> None:
    prov, _ = oidc
    c = TestClient(api.app)
    tok = prov.token(roles=["Some.Other.Group"])
    assert c.get("/api/auth/me", headers=_bearer(tok)).status_code == 403
    assert c.get("/api/documents", headers=_bearer(tok)).status_code == 403


def test_browser_sign_in_uses_state_nonce_and_pkce_once(oidc: Any) -> None:
    prov, _ = oidc
    c = TestClient(api.app, follow_redirects=False)
    r = c.get("/api/auth/login")
    assert r.status_code == 302
    q = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    assert q["code_challenge_method"] == "S256" and q["client_id"] == CLIENT and q["response_type"] == "code"
    prov.pending_nonce = q["nonce"]
    r = c.get("/api/auth/callback", params={"code": "abc", "state": q["state"]})
    assert r.status_code == 302, r.text
    sent = prov.token_requests[-1]
    challenge = base64.urlsafe_b64encode(__import__("hashlib").sha256(sent["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert challenge == q["code_challenge"], "the verifier sent must match the challenge"
    assert c.get("/api/auth/me").json()["actor"] == "alice@example.test"
    # the same state cannot be used twice
    assert TestClient(api.app).get("/api/auth/callback", params={"code": "abc", "state": q["state"]}).status_code == 401


def test_browser_sign_in_refuses_a_wrong_nonce_or_unknown_state(oidc: Any) -> None:
    prov, _ = oidc
    c = TestClient(api.app, follow_redirects=False)
    q = {k: v[0] for k, v in parse_qs(urlparse(c.get("/api/auth/login").headers["location"]).query).items()}
    prov.pending_nonce = "a-different-nonce"
    assert c.get("/api/auth/callback", params={"code": "abc", "state": q["state"]}).status_code == 401
    assert c.get("/api/auth/callback", params={"code": "abc", "state": "made-up"}).status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_development_sign_in_is_off_when_a_provider_is_configured(oidc: Any) -> None:
    assert TestClient(api.app).post("/api/auth/dev-login", json={"username": "pat"}).status_code == 404


# -- sessions: expiry and sign-out -----------------------------------------------------------------------------------


def test_sessions_expire_when_idle_or_too_old_and_end_at_sign_out(tmp_path: Path, _test_sign_in: Any) -> None:
    clock = [1_000_000.0]
    s = idn.Sessions(Database(tmp_path / "s.sqlite3"), _test_sign_in.cfg, clock=lambda: clock[0])
    p = idn.dev_principal(_test_sign_in.cfg, "pat")
    tok = s.create(p, {})
    assert s.resolve(tok) is not None
    clock[0] += _test_sign_in.cfg.session.idle_minutes * 60 + 1
    assert s.resolve(tok) is None, "idle too long"
    tok2 = s.create(p, {})
    for _ in range(int(_test_sign_in.cfg.session.absolute_minutes / 10) + 2):
        clock[0] += 600
        s.resolve(tok2)
    assert s.resolve(tok2) is None, "past the absolute limit even when active"
    tok3 = s.create(p, {})
    s.revoke(tok3, p.actor)
    assert s.resolve(tok3) is None


def test_sign_out_ends_the_session_through_the_api() -> None:
    c = client_as(api.app, "pat")
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout", json={}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401


# -- 6. separation of duties is enforced by the server ---------------------------------------------------------------


def test_the_uploader_cannot_approve_their_own_spread(statements: Service) -> None:
    dana = client_as(api.app, "dana")
    run = dana.post("/api/documents", files={"file": ("a.htm", _sample_html())}).json()["run"]["id"]
    r = dana.post(f"/api/runs/{run}/actions", json={"type": "approve"})
    assert r.status_code == 403 and "uploaded" in r.json()["detail"]
    r = client_as(api.app, "erin").post(f"/api/runs/{run}/actions", json={"type": "approve"})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["state"]["approved"]["by"] == "dev:erin"


def test_a_corrector_cannot_approve_and_the_rule_is_configurable(statements: Service, _test_sign_in: Any) -> None:
    pat, erin = client_as(api.app, "pat"), client_as(api.app, "erin")
    view = pat.post("/api/documents", files={"file": ("a.htm", _sample_html())}).json()
    run = view["run"]["id"]
    v = next(x for x in view["spread"]["values"] if x["value"] is not None)
    r = erin.post(f"/api/runs/{run}/actions", json={"type": "correct_value", "line": v["line"], "period": v["period"],
                                                    "value": str(v["value"]), "reason": "checked against the page"})
    assert r.status_code == 200, r.text
    r = erin.post(f"/api/runs/{run}/actions", json={"type": "approve"})
    assert r.status_code == 403 and "corrected" in r.json()["detail"]
    _test_sign_in.cfg.separation_of_duties.approver_not_corrector = False  # an organisation that allows it
    try:
        assert erin.post(f"/api/runs/{run}/actions", json={"type": "approve"}).status_code == 200
    finally:
        _test_sign_in.cfg.separation_of_duties.approver_not_corrector = True


def test_by_default_one_analyst_uploads_corrects_and_approves_their_own_spread(statements: Service,
                                                                                _test_sign_in: Any) -> None:
    """D51: the shipped configuration has no second checker. The analyst's correction and approval both stand and
    are recorded under their name (the record later used to learn from them)."""
    shipped = idn.load_auth_config(ROOT / "config" / "finops" / "auth" / "development.yaml")
    assert not shipped.separation_of_duties.approver_not_uploader
    assert not shipped.separation_of_duties.approver_not_corrector
    assert {"upload", "edit", "review", "approve"} <= set(shipped.roles["analyst"])
    assert "admin" not in shipped.roles["analyst"]
    _test_sign_in.cfg.separation_of_duties = shipped.separation_of_duties
    ana = client_as(api.app, "ana")
    view = ana.post("/api/documents", files={"file": ("a.htm", _sample_html())}).json()
    run = view["run"]["id"]
    v = next(x for x in view["spread"]["values"] if x["value"] is not None)
    r = ana.post(f"/api/runs/{run}/actions", json={"type": "correct_value", "line": v["line"], "period": v["period"],
                                                   "value": str(v["value"]), "reason": "checked against the page"})
    assert r.status_code == 200, r.text
    r = ana.post(f"/api/runs/{run}/actions", json={"type": "approve"})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["state"]["approved"]["by"] == "dev:ana"
    assert {e["actor"] for e in statements.store.query("SELECT actor FROM events")} == {"dev:ana"}


# -- 7. the audit log names the verified actor --------------------------------------------------------------------------


def test_audit_entries_name_the_identity_the_server_verified(oidc: Any, statements: Service) -> None:
    prov, a = oidc
    a.cfg.role_map["FinOps.Preparer"] = ["preparer"]
    tok = prov.token(roles=["FinOps.Preparer"], preferred_username="pat@bank.test", sub="sub-pat")
    r = TestClient(api.app).post("/api/documents", files={"file": ("a.htm", _sample_html())},
                                 headers={**_bearer(tok), "X-Actor": "somebody-else"})
    assert r.status_code == 200, r.text
    assert {e["actor"] for e in statements.store.query("SELECT actor FROM events")} == {"pat@bank.test"}


def test_sign_ins_are_recorded_in_the_platform_audit_chain(_test_sign_in: Any) -> None:
    client_as(api.app, "pat")
    ev = _test_sign_in.sessions.db.events("auth")
    assert ev and ev[-1]["kind"] == "sign_in" and ev[-1]["actor"] == "dev:pat"
    assert _test_sign_in.sessions.db.verify_chain() == (True, None)


# -- 8. development sign-in cannot pass for production ----------------------------------------------------------------


def test_development_sign_in_refuses_production_and_remote_hosts(_test_sign_in: Any) -> None:
    cfg = _test_sign_in.cfg
    with pytest.raises(ConfigError, match="production"):
        idn.check_deployment(cfg, ["127.0.0.1"], environment="production")
    with pytest.raises(ConfigError, match="local only"):
        idn.check_deployment(cfg, ["127.0.0.1", "finops.example.com"], environment="development")
    idn.check_deployment(cfg, ["127.0.0.1", "localhost", "testserver", "[::1]"], environment="development")


def test_development_mode_says_so_on_every_response_and_in_every_audit_entry(statements: Service) -> None:
    c = client_as(api.app, "pat")
    r = c.get("/api/documents")
    assert r.headers["x-auth-mode"] == "development-unverified"
    assert TestClient(api.app).get("/api/health").headers["x-auth-mode"] == "development-unverified"
    cfg = TestClient(api.app).get("/api/auth/config").json()
    assert cfg["mode"] == "development" and "not verified" in cfg["warning"]
    me = c.get("/api/auth/me").json()
    assert me["actor"].startswith("dev:") and me["verified"] is False
    assert c.get("/api/documents", headers=_bearer("x.y.z")).status_code == 401  # no bearer tokens in development


def test_a_development_session_is_worthless_once_a_provider_is_configured(tmp_path: Path, _test_sign_in: Any) -> None:
    db = _test_sign_in.sessions.db
    tok = _test_sign_in.sessions.create(idn.dev_principal(_test_sign_in.cfg, "dana"), {})
    oidc_sessions = idn.Sessions(db, oidc_config())
    assert oidc_sessions.resolve(tok) is None


def test_configuration_mistakes_are_refused_when_loading() -> None:
    base = load_raw(ROOT / "config" / "finops" / "auth" / "roles-base.yaml")
    bad = [
        {**base, "mode": "development", "organization": "x", "dev_users": []},
        {**base, "mode": "oidc", "organization": "x"},
        {**base, "mode": "development", "organization": "x", "roles": {"r": ["view", "approv"]},
         "dev_users": [{"username": "aa", "name": "A", "roles": ["r"]}]},
        {**base, "mode": "oidc", "organization": "x", "oidc": {"issuer": "http://idp.example.com", "client_id": "c",
                                                              "redirect_uri": "https://a/cb"}},
        {**base, "mode": "oidc", "organization": "x", "oidc": {"issuer": "https://idp.example.com", "client_id": "c",
                                                              "redirect_uri": "https://a/cb", "algorithms": ["HS256"]}},
        {**base, "mode": "development", "organization": "x", "role_map": {"g": ["superuser"]},
         "dev_users": [{"username": "aa", "name": "A", "roles": ["viewer"]}]},
    ]
    for raw in bad:
        with pytest.raises(ValueError):
            idn.AuthConfig.model_validate(raw)


# -- 9. a second provider and organisation is configuration only -------------------------------------------------------


def test_two_example_organisations_load_and_map_their_own_groups() -> None:
    entra = idn.load_auth_config(ROOT / "config" / "finops" / "auth" / "example-entra-id.yaml")
    okta = idn.load_auth_config(ROOT / "config" / "finops" / "auth" / "example-okta.yaml")
    assert entra.oidc and okta.oidc and entra.oidc.issuer != okta.oidc.issuer
    assert entra.oidc.client_secret_env == okta.oidc.client_secret_env == "FINOPS_OIDC_CLIENT_SECRET"
    claims = {"sub": "s", "groups": ["finance-controllers"], "email": "c@insurer.test"}
    p = idn.oidc_principal(okta, claims, via="bearer")
    assert set(p.roles) == {"reviewer", "approver"} and p.actor == "c@insurer.test"
    p2 = idn.oidc_principal(entra, {"sub": "s", "roles": ["finance-controllers"]}, via="bearer")
    assert p2.roles == () and not p2.permissions, "one organisation's group names mean nothing to another"
    assert okta.separation_of_duties.approver_not_corrector is False and entra.separation_of_duties.approver_not_corrector


def test_no_secret_is_kept_in_a_sign_in_file() -> None:
    for f in (ROOT / "config" / "finops" / "auth").glob("*.yaml"):
        text = f.read_text(encoding="utf-8").lower()
        assert "client_secret:" not in text and "private_key" not in text, f.name


def test_download_names_cannot_break_the_header_and_exports_name_the_user(tmp_path: Path) -> None:
    from finops import api as fapi
    from finops.sheets.service import SheetsService
    from finops.sheets.synthetic import generate

    database = Database(tmp_path / "f.sqlite3")
    fapi.configure(database, sheets_service=SheetsService(database, tmp_path / "files",
                                                          ROOT / "config" / "finops" / "sheets" / "default.yaml"))
    try:
        books, _ = generate(41)
        pat = client_as(api.app, "pat")
        evil = 'budget"\r\nSet-Cookie: x=1; été.xlsx'
        r = pat.post("/api/finops/sheets/scans", files={"workbook": (evil, books[0].data, "application/octet-stream")})
        assert r.status_code == 200, r.text
        scan = r.json()["id"] if "id" in r.json() else r.json()["scan"]
        out = pat.get(f"/api/finops/sheets/scans/{scan}/export.csv")
        assert out.status_code == 200
        cd = out.headers["content-disposition"]
        assert "set-cookie" not in {k.lower() for k in out.headers}
        assert re.fullmatch(r'attachment; filename="[A-Za-z0-9._-]+"', cd), cd
        ev = [e for e in database.events("sheets") if e["kind"] == "exported"]
        assert ev and ev[-1]["actor"] == "dev:pat"
    finally:
        fapi.configure(None)  # type: ignore[arg-type]
