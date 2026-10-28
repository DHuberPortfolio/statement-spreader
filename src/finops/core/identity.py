"""Who is acting, and what they may do (DECISIONS D43).

Identity is established by the server, never taken from the request: a name in a header, body or cookie that the
server did not issue proves nothing. Two ways in:

- `oidc`: the organisation's identity provider (any OpenID Connect provider: Entra ID, Okta, Auth0, Keycloak,
  Google Workspace...). Browsers sign in with the authorization-code flow and PKCE and get a server-side session;
  API clients send a bearer token. Token signatures, issuer, audience, expiry and nonce are checked with PyJWT
  against the provider's published keys. If the provider cannot be reached, nothing protected is served.
- `development`: named test users from a file, chosen on a sign-in screen, for running the prototype on one
  machine. It refuses to start with FINOPS_ENV=production or on any host name that is not local, every response
  says so (X-Auth-Mode), the app shows a banner, and every audit entry carries a `dev:` prefix, so a development
  identity can never be mistaken for a verified one.

Roles come from the provider's claims through the organisation's role map; permissions are fixed here and granted
to roles by configuration. A user with no mapped role can do nothing. Separation of duties is a separate list of
rules (config `separation_of_duties`) checked by the engines where the action happens.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import ipaddress
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "finops" / "auth" / "development.yaml"

# Every permission the application checks. Roles are granted subsets of these in configuration; a name not listed
# here is refused when the configuration loads, so a typo can never grant or silently drop access.
PERMISSIONS = {
    "view": "See documents, runs, results and review queues",
    "upload": "Upload documents and files, start runs, load sample data",
    "edit": "Correct values, remap lines, set a document's company, correct held records",
    "review": "Resolve exceptions, accept or reject proposed matches, confirm or dismiss findings",
    "approve": "Approve a spread, release held master data, verify changed bank details",
    "export": "Download exports",
    "audit": "Read audit trails and verify their integrity",
    "admin": "Change ROI assumptions and run retention",
}


class AuthError(Exception):
    """Not signed in, or the credential is not valid (HTTP 401)."""


class Forbidden(Exception):
    """Signed in, but not allowed to do this (HTTP 403)."""


class OIDCSettings(BaseModel):
    issuer: str
    client_id: str
    audience: list[str] = Field(default_factory=list)  # accepted `aud` values for bearer tokens; client_id is always accepted for ID tokens
    client_secret_env: str | None = None  # the NAME of the environment variable holding the secret, never the secret
    redirect_uri: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256", "PS256"])
    roles_claim: str = "roles"  # a list of strings in the token, e.g. "groups" (Okta), "roles" (Entra app roles)
    actor_claim: str = "preferred_username"  # what the audit log shows; the stable `sub` is recorded at sign-in
    required_claims: dict[str, str] = Field(default_factory=dict)  # e.g. {"tid": "<tenant id>"}: other tenants refused
    leeway_seconds: int = Field(default=60, ge=0, le=300)
    http_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    @field_validator("algorithms")
    @classmethod
    def _asymmetric_only(cls, v: list[str]) -> list[str]:
        bad = [a for a in v if a.lower() == "none" or a.upper().startswith("HS")]
        if bad or not v:
            raise ValueError("only asymmetric signature algorithms are accepted (RS*, ES*, PS*, EdDSA)")
        return v

    @field_validator("issuer", "redirect_uri")
    @classmethod
    def _https(cls, v: str) -> str:
        host = v.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        if not v.startswith("https://") and host not in {"localhost", "127.0.0.1"}:
            raise ValueError("must be https (plain http is allowed only for localhost test providers)")
        return v


class DevUser(BaseModel):
    username: str = Field(pattern=r"^[a-z][a-z0-9._-]{1,30}$")
    name: str
    roles: list[str]


class SessionSettings(BaseModel):
    absolute_minutes: int = Field(default=480, ge=5, le=24 * 60)
    idle_minutes: int = Field(default=30, ge=1, le=24 * 60)
    secure_cookie: bool = True


class SeparationOfDuties(BaseModel):
    """Who may not do what, on top of permissions. Each rule is checked where the action happens."""
    approver_not_uploader: bool = True  # a statement spread is approved by someone other than whoever uploaded it
    approver_not_corrector: bool = True  # ... and other than anyone who corrected or remapped its values


class AuthConfig(BaseModel):
    mode: Literal["oidc", "development"]
    organization: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    roles: dict[str, list[str]]  # app role -> permissions
    role_map: dict[str, list[str]] = Field(default_factory=dict)  # provider claim value -> app roles
    oidc: OIDCSettings | None = None
    dev_users: list[DevUser] = Field(default_factory=list)
    session: SessionSettings = Field(default_factory=SessionSettings)
    separation_of_duties: SeparationOfDuties = Field(default_factory=SeparationOfDuties)

    @model_validator(mode="after")
    def _consistent(self) -> AuthConfig:
        for role, perms in self.roles.items():
            unknown = set(perms) - set(PERMISSIONS)
            if unknown:
                raise ValueError(f"role '{role}' grants unknown permissions: {sorted(unknown)}")
        for claim, roles in self.role_map.items():
            unknown = set(roles) - set(self.roles)
            if unknown:
                raise ValueError(f"role_map '{claim}' names roles that are not defined: {sorted(unknown)}")
        if self.mode == "oidc" and self.oidc is None:
            raise ValueError("mode oidc needs an `oidc:` section")
        if self.mode == "oidc" and self.dev_users:
            raise ValueError("dev_users are not allowed in oidc mode")
        if self.mode == "development":
            if not self.dev_users:
                raise ValueError("development mode needs at least one dev user")
            for u in self.dev_users:
                unknown = set(u.roles) - set(self.roles)
                if unknown:
                    raise ValueError(f"dev user '{u.username}' has undefined roles: {sorted(unknown)}")
        return self


@dataclass(frozen=True)
class Principal:
    subject: str  # stable id: the provider's `sub`, or `dev:<username>`
    actor: str  # what audit entries show: verified name, or `dev:<username>`
    name: str
    roles: tuple[str, ...]
    permissions: frozenset[str]
    mode: str
    organization: str
    via: str = "session"  # session | bearer

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def public(self) -> dict[str, Any]:
        return {"actor": self.actor, "name": self.name, "roles": list(self.roles), "permissions": sorted(self.permissions),
                "mode": self.mode, "organization": self.organization, "verified": self.mode == "oidc"}


_current: contextvars.ContextVar[Principal | None] = contextvars.ContextVar("finops_principal", default=None)


def set_current(p: Principal | None) -> contextvars.Token[Principal | None]:
    return _current.set(p)


def reset_current(token: contextvars.Token[Principal | None]) -> None:
    _current.reset(token)


def current() -> Principal:
    p = _current.get()
    if p is None:
        raise AuthError("Sign in first")
    return p


def require(permission: str) -> Principal:
    """The signed-in principal, if they hold `permission`; otherwise Forbidden (or AuthError if nobody is signed in)."""
    if permission not in PERMISSIONS:
        raise KeyError(permission)  # a programming error: the check would never pass
    p = current()
    if not p.can(permission):
        raise Forbidden(f"Your roles ({', '.join(p.roles) or 'none'}) do not allow this: needs '{permission}'")
    return p


def permissions_for(cfg: AuthConfig, roles: list[str]) -> frozenset[str]:
    return frozenset(perm for r in roles for perm in cfg.roles.get(r, []))


def load_auth_config(path: str | Path | None = None) -> AuthConfig:
    p = Path(path or os.environ.get("FINOPS_AUTH_CONFIG") or DEFAULT_CONFIG)
    cfg, _ = load_config(AuthConfig, p)
    return cfg


def _is_local_host(h: str) -> bool:
    h = h.strip().lower()
    if h in {"localhost", "testserver"} or h.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(h.strip("[]")).is_loopback
    except ValueError:
        return False


def check_deployment(cfg: AuthConfig, allowed_hosts: list[str], environment: str | None = None) -> None:
    """Refuse a configuration that would let development sign-in pass for real security."""
    env = (environment if environment is not None else os.environ.get("FINOPS_ENV", "development")).lower()
    if cfg.mode == "development":
        if env == "production":
            raise ConfigError("Development sign-in cannot run with FINOPS_ENV=production: configure oidc")
        remote = [h for h in allowed_hosts if not _is_local_host(h)]
        if remote:
            raise ConfigError(f"Development sign-in is local only; these host names are not: {remote}")
    if cfg.mode == "oidc" and env == "production" and not cfg.session.secure_cookie:
        raise ConfigError("Production needs secure (HTTPS-only) session cookies")


def dev_principal(cfg: AuthConfig, username: str) -> Principal:
    for u in cfg.dev_users:
        if u.username == username:
            return Principal(subject=f"dev:{u.username}", actor=f"dev:{u.username}", name=u.name, roles=tuple(u.roles),
                             permissions=permissions_for(cfg, u.roles), mode="development", organization=cfg.organization)
    raise AuthError("Unknown development user")


# -- OpenID Connect -----------------------------------------------------------------------------------------------


@dataclass
class OIDCProvider:
    """Discovery, keys and token checks for one provider. `http` is an httpx.Client (tests pass a mock transport)."""
    settings: OIDCSettings
    http: Any = None
    _meta: dict[str, Any] | None = None
    _keys: dict[str, Any] = field(default_factory=dict)
    _keys_fetched: float = 0.0

    def client(self) -> Any:
        if self.http is None:
            import httpx

            self.http = httpx.Client(timeout=self.settings.http_timeout_seconds, follow_redirects=False)
        return self.http

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            r = self.client().get(url)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # network, TLS, HTTP status or JSON: the provider is unavailable, fail closed
            raise AuthError(f"The identity provider could not be reached ({type(exc).__name__})") from exc
        if not isinstance(data, dict):
            raise AuthError("The identity provider returned an unexpected response")
        return data

    def metadata(self) -> dict[str, Any]:
        if self._meta is None:
            meta = self._get_json(self.settings.issuer.rstrip("/") + "/.well-known/openid-configuration")
            if meta.get("issuer") != self.settings.issuer:
                raise AuthError("The identity provider's discovery document names a different issuer")
            for k in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                if not isinstance(meta.get(k), str):
                    raise AuthError(f"The identity provider's discovery document has no {k}")
            self._meta = meta
        return self._meta

    def _key(self, kid: str | None) -> Any:
        import jwt

        def load() -> None:
            jwks = self._get_json(self.metadata()["jwks_uri"])
            keys = {}
            for k in jwks.get("keys", []) if isinstance(jwks.get("keys"), list) else []:
                try:
                    keys[k.get("kid")] = jwt.PyJWK(k)
                except Exception:  # an unusable key in the set is skipped, never trusted
                    continue
            self._keys, self._keys_fetched = keys, time.monotonic()

        if not self._keys or (kid not in self._keys and time.monotonic() - self._keys_fetched > 60):
            load()  # unknown key id: the provider may have rotated keys; refetch at most once a minute
        key = self._keys.get(kid) if kid is not None else (next(iter(self._keys.values())) if len(self._keys) == 1 else None)
        if key is None:
            raise AuthError("The token was signed with a key the identity provider does not publish")
        return key

    def validate(self, token: str, audience: list[str], nonce: str | None = None) -> dict[str, Any]:
        """Claims of a token whose signature, issuer, audience, time window (and nonce) all check out."""
        import jwt

        if not isinstance(token, str) or token.count(".") != 2 or len(token) > 16_384:
            raise AuthError("Malformed token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("Malformed token") from exc
        if header.get("alg") not in self.settings.algorithms:
            raise AuthError("Token algorithm not accepted")
        key = self._key(header.get("kid"))
        try:
            claims = jwt.decode(token, key=key.key, algorithms=self.settings.algorithms, audience=audience,
                                issuer=self.settings.issuer, leeway=self.settings.leeway_seconds,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Token expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthError(f"Token rejected ({type(exc).__name__})") from exc
        if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise AuthError("Token nonce does not match this sign-in")
        for k, v in self.settings.required_claims.items():
            if str(claims.get(k)) != v:
                raise AuthError(f"Token is for a different organisation ({k})")
        return claims


def oidc_principal(cfg: AuthConfig, claims: dict[str, Any], via: str) -> Principal:
    assert cfg.oidc is not None
    raw = claims.get(cfg.oidc.roles_claim, [])
    values = [raw] if isinstance(raw, str) else [str(x) for x in raw] if isinstance(raw, list) else []
    roles = sorted({r for v in values for r in cfg.role_map.get(v, [])})
    actor = str(claims.get(cfg.oidc.actor_claim) or claims["sub"])[:120]
    return Principal(subject=str(claims["sub"]), actor=actor, name=str(claims.get("name") or actor)[:120],
                     roles=tuple(roles), permissions=permissions_for(cfg, roles), mode="oidc",
                     organization=cfg.organization, via=via)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


# -- Server-side sessions -----------------------------------------------------------------------------------------

SESSION_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS auth_sessions (
        id_hash TEXT PRIMARY KEY,          -- sha256 of the cookie value; the value itself is never stored
        subject TEXT NOT NULL,
        actor TEXT NOT NULL,
        name TEXT NOT NULL,
        roles TEXT NOT NULL,               -- JSON list, as granted at sign-in
        mode TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_seen REAL NOT NULL,
        expires_at REAL NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS auth_pending (
        state_hash TEXT PRIMARY KEY,
        nonce TEXT NOT NULL,
        verifier TEXT NOT NULL,
        created_at REAL NOT NULL
    )""",
]
PENDING_SECONDS = 600


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Sessions:
    """Sessions in the platform database (finops.core.audit.Database); sign-ins and sign-outs go to its audit chain."""

    def __init__(self, db: Any, cfg: AuthConfig, clock: Any = time.time):
        self.db, self.cfg, self.clock = db, cfg, clock
        with db.tx() as c:
            for stmt in SESSION_SCHEMA:
                c.execute(stmt)

    def create(self, p: Principal, detail: dict[str, Any]) -> str:
        import json

        token = secrets.token_urlsafe(32)
        t = self.clock()
        with self.db.tx() as c:
            c.execute("INSERT INTO auth_sessions (id_hash, subject, actor, name, roles, mode, created_at, last_seen, expires_at)"
                      " VALUES (?,?,?,?,?,?,?,?,?)",
                      (_h(token), p.subject, p.actor, p.name, json.dumps(list(p.roles)), p.mode, t, t,
                       t + self.cfg.session.absolute_minutes * 60))
            self.db.append_event(c, "auth", f"subject:{p.subject}", p.actor, "sign_in",
                                 {"mode": p.mode, "roles": list(p.roles), **detail})
        return token

    def resolve(self, token: str | None) -> Principal | None:
        import json

        if not token or len(token) > 200:
            return None
        t = self.clock()
        rows = self.db.query("SELECT * FROM auth_sessions WHERE id_hash = ?", (_h(token),))
        if not rows:
            return None
        r = rows[0]
        if r["revoked"] or t >= r["expires_at"] or t - r["last_seen"] > self.cfg.session.idle_minutes * 60:
            return None
        if r["mode"] != self.cfg.mode:  # a session from another mode (e.g. development) is worthless after a switch
            return None
        roles = [x for x in json.loads(r["roles"]) if x in self.cfg.roles]
        with self.db.tx() as c:
            c.execute("UPDATE auth_sessions SET last_seen = ? WHERE id_hash = ?", (t, r["id_hash"]))
        return Principal(subject=r["subject"], actor=r["actor"], name=r["name"], roles=tuple(roles),
                         permissions=permissions_for(self.cfg, roles), mode=r["mode"], organization=self.cfg.organization)

    def revoke(self, token: str | None, actor: str) -> None:
        if not token:
            return
        with self.db.tx() as c:
            row = c.execute("SELECT subject FROM auth_sessions WHERE id_hash = ? AND revoked = 0", (_h(token),)).fetchone()
            if row:
                c.execute("UPDATE auth_sessions SET revoked = 1 WHERE id_hash = ?", (_h(token),))
                self.db.append_event(c, "auth", f"subject:{row['subject']}", actor, "sign_out", {})

    def start_pending(self) -> tuple[str, str, str]:
        """(state, nonce, PKCE verifier) for one sign-in attempt, usable once within ten minutes."""
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        verifier, _ = pkce_pair()
        t = self.clock()
        with self.db.tx() as c:
            c.execute("DELETE FROM auth_pending WHERE created_at < ?", (t - PENDING_SECONDS,))
            c.execute("INSERT INTO auth_pending VALUES (?,?,?,?)", (_h(state), nonce, verifier, t))
        return state, nonce, verifier

    def take_pending(self, state: str | None) -> tuple[str, str]:
        if not state or len(state) > 200:
            raise AuthError("Sign-in state is missing")
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM auth_pending WHERE state_hash = ?", (_h(state),)).fetchone()
            c.execute("DELETE FROM auth_pending WHERE state_hash = ?", (_h(state),))  # single use, even on failure
        if row is None or self.clock() - row["created_at"] > PENDING_SECONDS:
            raise AuthError("This sign-in link has expired or was already used; start again")
        return row["nonce"], row["verifier"]


def challenge_of(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


__all__ = ["PERMISSIONS", "AuthConfig", "AuthError", "Forbidden", "OIDCProvider", "Principal", "Sessions", "current",
           "require", "load_auth_config", "check_deployment", "dev_principal", "oidc_principal"]
