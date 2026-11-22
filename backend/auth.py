"""
Authentication and role-based access for the VITALYN API (Supabase Auth).

Staff sign in through the backend (see auth_routes.py), which keeps the Supabase tokens in
httpOnly cookies. Every request then carries the access token; this module checks it and
loads the staff member:

  token  ->  verify (JWKS / shared secret / Supabase user endpoint)  ->  staff row  ->  role

Only the PUBLIC anon key is used (server side). The Supabase service-role key is never needed.
Set VITALYN_AUTH=off to run an open demo with no login (never for anything shared).
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import httpx
from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlmodel import Session, select

from database import get_session
from models import User

log = logging.getLogger("vitalyn.auth")

ROLES = ("admin", "doctor", "nurse", "receptionist")
ACCESS_COOKIE = "vitalyn_at"
REFRESH_COOKIE = "vitalyn_rt"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "vitalyn"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ALLOWED_ALGS = {"ES256", "RS256", "HS256"}


class AuthError(Exception):
    """The token is missing, malformed, expired or not issued by our Supabase project."""


# ── configuration ────────────────────────────────────────────────────────────

def auth_off() -> bool:
    return os.getenv("VITALYN_AUTH", "on").strip().lower() == "off"


def supabase_url() -> str:
    return (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")


def anon_key() -> str:
    return (os.getenv("SUPABASE_ANON_KEY") or "").strip()


def jwt_secret() -> str:
    return (os.getenv("SUPABASE_JWT_SECRET") or "").strip()


def auth_configured() -> bool:
    return bool(supabase_url() and anon_key())


@dataclass(frozen=True)
class AuthUser:
    id: Optional[str]            # our staff row id (None only in VITALYN_AUTH=off demo mode)
    auth_id: Optional[str]
    email: str
    name: str
    role: str
    status: str

    @property
    def uuid(self) -> Optional[uuid.UUID]:
        return uuid.UUID(self.id) if self.id else None


DEMO_ADMIN = AuthUser(id=None, auth_id=None, email="demo@local", name="Demo admin (auth off)", role="admin", status="active")


# ── talking to Supabase Auth (patched in tests) ──────────────────────────────

def supabase_request(method: str, path: str, *, json: Optional[dict] = None, params: Optional[dict] = None,
                     token: Optional[str] = None) -> tuple[int, Any]:
    headers = {"apikey": anon_key(), "Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {token or anon_key()}"
    try:
        r = httpx.request(method, f"{supabase_url()}{path}", json=json, params=params, headers=headers, timeout=10)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Cannot reach the authentication service.") from exc
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body


def fetch_jwks() -> dict:
    r = httpx.get(f"{supabase_url()}/auth/v1/.well-known/jwks.json", timeout=5)
    r.raise_for_status()
    return r.json()


# ── token verification ───────────────────────────────────────────────────────

_jwks_cache: Dict[str, Any] = {"at": 0.0, "keys": []}
_user_cache: Dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
JWKS_TTL_S = 3600
USER_CACHE_TTL_S = 60


def _jwks_keys(force: bool = False) -> list:
    with _cache_lock:
        if force or time.time() - _jwks_cache["at"] > JWKS_TTL_S or not _jwks_cache["keys"]:
            try:
                _jwks_cache["keys"] = fetch_jwks().get("keys", [])
                _jwks_cache["at"] = time.time()
            except Exception as exc:
                log.warning("Could not fetch JWKS: %s", exc)
        return list(_jwks_cache["keys"])


def _verify_via_user_endpoint(token: str) -> dict:
    """Legacy HS256 projects without a local secret: let Supabase validate the token (cached briefly)."""
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _user_cache.get(digest)
        if hit and now - hit[0] < USER_CACHE_TTL_S:
            return hit[1]
    status, body = supabase_request("GET", "/auth/v1/user", token=token)
    if status != 200 or not isinstance(body, dict) or not body.get("id"):
        raise AuthError("token rejected")
    claims = {"sub": body["id"], "email": body.get("email"), "user_metadata": body.get("user_metadata") or {}}
    with _cache_lock:
        _user_cache[digest] = (now, claims)
        if len(_user_cache) > 500:
            _user_cache.clear()
    return claims


def verify_token(token: str) -> dict:
    """Return the verified claims or raise AuthError."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise AuthError("malformed token") from exc
    alg = header.get("alg")
    if alg not in ALLOWED_ALGS:                      # also rejects "none"
        raise AuthError("unsupported algorithm")

    secret = jwt_secret()
    try:
        if alg == "HS256":
            if secret:                               # the shared secret only ever verifies HS256 tokens
                return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
            return _verify_via_user_endpoint(token)
        kid = header.get("kid")
        keys = _jwks_keys()
        key = next((k for k in keys if k.get("kid") == kid), None)
        if key is None:                              # key rotation: refresh once
            key = next((k for k in _jwks_keys(force=True) if k.get("kid") == kid), None)
        if key is None:
            raise AuthError("unknown signing key")
        return jwt.decode(
            token, key, algorithms=[alg], audience="authenticated", issuer=f"{supabase_url()}/auth/v1",
        )
    except JWTError as exc:
        raise AuthError(str(exc)) from exc


# ── the staff row behind a token ─────────────────────────────────────────────

def provision_user(session: Session, claims: dict) -> User:
    """First sight of a Supabase account: create a PENDING staff row. An admin must approve it."""
    sub = claims.get("sub")
    user = session.exec(select(User).where(User.auth_user_id == sub)).first()
    if user is not None:
        return user
    email = (claims.get("email") or "").lower()
    meta = claims.get("user_metadata") or {}
    user = User(
        name=(meta.get("full_name") or email.split("@")[0] or "Staff").strip()[:80],
        email=email or f"{sub}@unknown.invalid",
        auth_user_id=sub,
        status="pending",
        role="none",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _token_from_request(request: Request) -> tuple[Optional[str], bool]:
    """(token, came_from_cookie). Authorization: Bearer takes priority (API clients, tests)."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip(), False
    cookie = request.cookies.get(ACCESS_COOKIE)
    return (cookie, True) if cookie else (None, False)


def current_identity(request: Request, session: Session = Depends(get_session)) -> AuthUser:
    """Who is calling (any staff status). Used by /auth/me so pending users can see their status."""
    if auth_off():
        return DEMO_ADMIN
    token, from_cookie = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    if (from_cookie and request.method in UNSAFE_METHODS
            and request.headers.get(CSRF_HEADER, "").lower() != CSRF_VALUE):
        raise HTTPException(status_code=403, detail="Missing request header")      # CSRF guard
    try:
        claims = verify_token(token)
    except AuthError as exc:
        log.warning("Rejected access token on %s %s: %s", request.method, request.url.path, exc)   # never the token itself
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    user = provision_user(session, claims)
    return AuthUser(id=str(user.id), auth_id=user.auth_user_id, email=user.email, name=user.name,
                    role=user.role, status=user.status)


def current_user(identity: AuthUser = Depends(current_identity)) -> AuthUser:
    """An ACTIVE (approved) staff member."""
    if identity.status != "active":
        code = "pending" if identity.status == "pending" else "disabled"
        raise HTTPException(
            status_code=403,
            detail={"code": code, "message": "Your account is waiting for administrator approval."
                    if code == "pending" else "Your account has been disabled."},
        )
    return identity


def require_roles(*roles: str) -> Callable[..., AuthUser]:
    """Dependency factory: the caller must be active and hold one of `roles`."""
    allowed = set(roles)

    def checker(user: AuthUser = Depends(current_user)) -> AuthUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": f"Your role ({user.role}) cannot do this."},
            )
        return user

    return checker
