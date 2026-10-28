"""Sign-in, sessions and the permission every API route needs (DECISIONS D43; identity in finops.core.identity).

The middleware runs before any route. For every /api path it establishes who is calling (a server-issued session
cookie, or a provider-signed bearer token in oidc mode), refuses the request if nobody is, and checks the route's
permission from ROUTE_PERMISSIONS. A route missing from that table is refused (403), so a new route is closed until
someone decides who may use it. Routes whose permission depends on the action (approve vs. correct) check again
inside the handler with identity.require().

Nothing the client sends can name the actor: the old X-Actor header is ignored, and the audit log records the
principal the server established.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from finops.core import identity as idn

COOKIE = "finops_session"

# (method, path pattern) -> permission. Patterns are full matches on the request path.
_ID = r"[^/]+"
ROUTE_PERMISSIONS: list[tuple[str, str, str]] = [
    # statement spreading
    ("GET", r"/api/profile", "view"), ("GET", r"/api/documents", "view"), ("GET", r"/api/outcomes", "view"),
    ("GET", r"/api/companies", "view"), ("GET", r"/api/evaluation", "view"),
    ("POST", r"/api/documents", "upload"),
    ("POST", rf"/api/documents/{_ID}/company", "edit"),
    ("POST", rf"/api/documents/{_ID}/runs", "upload"),
    ("GET", rf"/api/documents/{_ID}/pages/{_ID}\.png", "view"),
    ("GET", rf"/api/runs/{_ID}", "view"),
    ("POST", rf"/api/runs/{_ID}/actions", "view"),  # refined in the handler by action type
    ("GET", rf"/api/runs/{_ID}/events", "view"),
    ("GET", rf"/api/runs/{_ID}/source/{_ID}", "view"),
    ("GET", rf"/api/runs/{_ID}/export\.{_ID}", "export"),
    # analyst timing (ROI)
    ("GET", r"/api/sessions", "view"), ("POST", r"/api/sessions", "edit"),
    ("POST", rf"/api/sessions/{_ID}/heartbeat", "edit"), ("POST", rf"/api/sessions/{_ID}/end", "edit"),
    ("GET", r"/api/roi", "view"), ("PUT", r"/api/roi/assumptions", "admin"),
    # platform engines
    ("GET", r"/api/finops/overview", "view"), ("GET", r"/api/finops/roi", "view"),
    ("PUT", r"/api/finops/roi/assumptions", "admin"),
    ("GET", r"/api/finops/recon/profiles", "view"), ("GET", r"/api/finops/recon/workspaces", "view"),
    ("POST", r"/api/finops/recon/workspaces", "upload"),
    ("POST", rf"/api/finops/recon/workspaces/{_ID}/run", "upload"),
    ("POST", rf"/api/finops/recon/workspaces/{_ID}/sample", "upload"),
    ("GET", rf"/api/finops/recon/workspaces/{_ID}/events", "view"),
    ("GET", rf"/api/finops/recon/runs/{_ID}", "view"),
    ("GET", rf"/api/finops/recon/runs/{_ID}/export\.csv", "export"),
    ("POST", rf"/api/finops/recon/runs/{_ID}/accept", "review"),
    ("POST", rf"/api/finops/recon/runs/{_ID}/reject", "review"),
    ("POST", rf"/api/finops/recon/runs/{_ID}/manual", "review"),
    ("POST", rf"/api/finops/recon/runs/{_ID}/resolve", "review"),
    ("GET", r"/api/finops/invoices", "view"), ("POST", r"/api/finops/invoices", "upload"),
    ("POST", r"/api/finops/invoices/sample", "upload"),
    ("GET", r"/api/finops/invoices/export\.csv", "export"),
    ("GET", rf"/api/finops/invoices/{_ID}", "view"),
    ("GET", rf"/api/finops/invoices/{_ID}/events", "view"),
    ("POST", rf"/api/finops/invoices/{_ID}/reprocess", "upload"),
    ("POST", rf"/api/finops/invoices/{_ID}/correct", "edit"),
    ("POST", rf"/api/finops/invoices/{_ID}/resolve", "review"),  # bank-detail verification also needs approve
    ("GET", r"/api/finops/dq/datasets", "view"), ("GET", r"/api/finops/dq/runs", "view"),
    ("POST", r"/api/finops/dq/runs", "upload"), ("POST", r"/api/finops/dq/sample", "upload"),
    ("GET", rf"/api/finops/dq/runs/{_ID}", "view"),
    ("POST", rf"/api/finops/dq/runs/{_ID}/decide", "view"),  # refined in the handler by action
    ("GET", rf"/api/finops/dq/runs/{_ID}/export/{_ID}\.csv", "export"),
    ("GET", rf"/api/finops/dq/datasets/{_ID}/events", "view"),
    ("GET", r"/api/finops/sheets/scans", "view"), ("POST", r"/api/finops/sheets/scans", "upload"),
    ("POST", r"/api/finops/sheets/sample", "upload"),
    ("GET", rf"/api/finops/sheets/scans/{_ID}", "view"),
    ("POST", rf"/api/finops/sheets/scans/{_ID}/review", "review"),
    ("GET", rf"/api/finops/sheets/scans/{_ID}/export\.csv", "export"),
    ("GET", rf"/api/finops/sheets/models/{_ID}/events", "view"),
    # audit
    ("GET", r"/api/audit/verify", "audit"),
    ("GET", r"/api/auth/me", "view"),
]
_COMPILED = [(m, re.compile(p), perm) for m, p, perm in ROUTE_PERMISSIONS]
# Reachable without signing in: what the sign-in screen needs, and nothing else.
PUBLIC = {("GET", "/api/health"), ("GET", "/api/auth/config"), ("POST", "/api/auth/dev-login"),
          ("GET", "/api/auth/login"), ("GET", "/api/auth/callback"), ("POST", "/api/auth/logout")}


def permission_for(method: str, path: str) -> str | None:
    method = "GET" if method == "HEAD" else method
    for m, rx, perm in _COMPILED:
        if m == method and rx.fullmatch(path):
            return perm
    return None


class Auth:
    """The configured identity setup, built once per process (tests build their own with configure())."""

    def __init__(self, cfg: idn.AuthConfig, db: Any, provider: idn.OIDCProvider | None = None):
        self.cfg = cfg
        self.sessions = idn.Sessions(db, cfg)
        self.provider = provider or (idn.OIDCProvider(cfg.oidc) if cfg.oidc else None)


_auth: Auth | None = None


def auth() -> Auth:
    global _auth
    if _auth is None:
        from finops.api import db
        from spreader.api import ALLOWED_HOSTS

        cfg = idn.load_auth_config()
        idn.check_deployment(cfg, ALLOWED_HOSTS)
        _auth = Auth(cfg, db())
    return _auth


def configure(a: Auth | None) -> None:
    global _auth
    _auth = a


def _mode_header(a: Auth) -> bytes:
    return b"development-unverified" if a.cfg.mode == "development" else b"oidc"


def _json(status: int, body: dict[str, Any], mode: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    data = json.dumps(body).encode()
    start = {"type": "http.response.start", "status": status,
             "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode()),
                         (b"x-auth-mode", mode), (b"cache-control", b"no-store")]}
    return start, {"type": "http.response.body", "body": data}


def authenticate(a: Auth, headers: dict[str, str], cookies: dict[str, str]) -> idn.Principal | None:
    authz = headers.get("authorization", "")
    if authz:
        if a.cfg.mode != "oidc" or a.provider is None or not authz.lower().startswith("bearer "):
            raise idn.AuthError("Bearer tokens are accepted only with an identity provider configured")
        assert a.cfg.oidc is not None
        claims = a.provider.validate(authz[7:].strip(), a.cfg.oidc.audience or [a.cfg.oidc.client_id])
        return idn.oidc_principal(a.cfg, claims, via="bearer")
    return a.sessions.resolve(cookies.get(COOKIE))


def _cookies(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k and k not in out:
            out[k] = v
    return out


class AuthMiddleware:
    """Pure ASGI, so the principal set here is the one every handler (and its worker thread) sees."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        a = auth()
        mode = _mode_header(a)

        async def send_with_mode(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-auth-mode", mode)]
            await send(message)

        path, method = scope["path"], scope["method"]
        if not path.startswith("/api/") or (method, path) in PUBLIC:
            await self.app(scope, receive, send_with_mode)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        try:
            principal = authenticate(a, headers, _cookies(headers.get("cookie", "")))
        except idn.AuthError as exc:
            principal, reason = None, str(exc)
        else:
            reason = "Sign in first"
        if principal is None:
            start, body = _json(401, {"error": reason, "sign_in": True}, mode)
            await send(start)
            await send(body)
            return
        perm = permission_for(method, path)
        if perm is None or not principal.can(perm):
            msg = (f"Your roles ({', '.join(principal.roles) or 'none'}) do not allow this: needs '{perm}'" if perm
                   else "This route has no permission assigned and is closed")
            start, body = _json(403, {"error": msg}, mode)
            await send(start)
            await send(body)
            return
        token = idn.set_current(principal)
        try:
            await self.app(scope, receive, send_with_mode)
        finally:
            idn.reset_current(token)


router = APIRouter(prefix="/api/auth")


def _set_cookie(resp: Any, a: Auth, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=a.cfg.session.secure_cookie, path="/",
                    max_age=a.cfg.session.absolute_minutes * 60)


@router.get("/config")
def auth_config() -> dict[str, Any]:
    """What the sign-in screen shows. Development users are listed only in development mode."""
    a = auth()
    out: dict[str, Any] = {"mode": a.cfg.mode, "organization": a.cfg.organization}
    if a.cfg.mode == "development":
        out["warning"] = "Development sign-in: identities are not verified. Not for real data or real approvals."
        out["dev_users"] = [{"username": u.username, "name": u.name, "roles": u.roles} for u in a.cfg.dev_users]
    return out


@router.get("/me")
def me() -> dict[str, Any]:
    return idn.current().public()


@router.post("/dev-login")
async def dev_login(request: Request) -> Any:
    a = auth()
    if a.cfg.mode != "development":
        return JSONResponse(status_code=404, content={"error": "Development sign-in is not enabled"})
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Body must be JSON"})
    try:
        p = idn.dev_principal(a.cfg, str((body or {}).get("username", "")) if isinstance(body, dict) else "")
    except idn.AuthError as exc:
        return JSONResponse(status_code=401, content={"error": str(exc)})
    token = a.sessions.create(p, {"via": "development"})
    resp = JSONResponse(content=p.public())
    _set_cookie(resp, a, token)
    return resp


@router.post("/logout")
def logout(request: Request) -> Any:
    a = auth()
    token = request.cookies.get(COOKIE)
    p = a.sessions.resolve(token)
    a.sessions.revoke(token, p.actor if p else "unknown")
    resp = JSONResponse(content={"signed_out": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/login")
def oidc_login() -> Any:
    a = auth()
    if a.cfg.mode != "oidc" or a.provider is None or a.cfg.oidc is None:
        return JSONResponse(status_code=404, content={"error": "Single sign-on is not configured"})
    try:
        meta = a.provider.metadata()
    except idn.AuthError as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    state, nonce, verifier = a.sessions.start_pending()
    o = a.cfg.oidc
    q = urlencode({"response_type": "code", "client_id": o.client_id, "redirect_uri": o.redirect_uri,
                   "scope": " ".join(o.scopes), "state": state, "nonce": nonce,
                   "code_challenge": idn.challenge_of(verifier), "code_challenge_method": "S256"})
    return RedirectResponse(f"{meta['authorization_endpoint']}?{q}", status_code=302)


@router.get("/callback")
def oidc_callback(request: Request) -> Any:
    a = auth()
    if a.cfg.mode != "oidc" or a.provider is None or a.cfg.oidc is None:
        return JSONResponse(status_code=404, content={"error": "Single sign-on is not configured"})
    o = a.cfg.oidc
    params = request.query_params
    if params.get("error"):
        return JSONResponse(status_code=401, content={"error": "The identity provider refused the sign-in"})
    try:
        nonce, verifier = a.sessions.take_pending(params.get("state"))
        code = params.get("code")
        if not code or len(code) > 4096:
            raise idn.AuthError("No authorization code")
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": o.redirect_uri,
                "client_id": o.client_id, "code_verifier": verifier}
        if o.client_secret_env:
            secret = os.environ.get(o.client_secret_env)
            if not secret:
                raise idn.AuthError(f"The client secret is not set ({o.client_secret_env})")
            form["client_secret"] = secret
        try:
            r = a.provider.client().post(a.provider.metadata()["token_endpoint"], data=form)
            r.raise_for_status()
            tokens = r.json()
        except idn.AuthError:
            raise
        except Exception as exc:
            raise idn.AuthError(f"The identity provider did not issue tokens ({type(exc).__name__})") from exc
        claims = a.provider.validate(str(tokens.get("id_token", "")), [o.client_id], nonce=nonce)
        p = idn.oidc_principal(a.cfg, claims, via="session")
    except idn.AuthError as exc:
        return JSONResponse(status_code=401, content={"error": str(exc)})
    token = a.sessions.create(p, {"via": "oidc", "sub": p.subject, "issuer": o.issuer})
    resp = RedirectResponse("/", status_code=302)
    _set_cookie(resp, a, token)
    return resp
