"""
Sign up, sign in, refresh and sign out, proxied to Supabase Auth.

The browser never sees the Supabase tokens: they are stored in httpOnly cookies, so page scripts
cannot read them. New accounts are active at once (auto-approval, the default) or PENDING until an
administrator approves them when VITALYN_AUTO_APPROVE=off.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

import audit
from auth import (
    ACCESS_COOKIE, REFRESH_COOKIE, AuthUser, auth_configured, auth_off, auto_approve, current_identity,
    provision_user, supabase_request,
)
from database import get_session

router = APIRouter(prefix="/api/v1/auth")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 14

# Brute-force guard: 5 failed sign-ins per IP+email in 10 minutes.
MAX_FAILS = 5
FAIL_WINDOW_S = 600
_fails: Dict[str, List[float]] = {}
_fails_lock = threading.Lock()


class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address")
        return v


class SignupBody(Credentials):
    full_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=72)


def _need_supabase() -> None:
    if not auth_configured():
        raise HTTPException(status_code=503, detail="Sign-in is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY in backend/.env.")


def _rate_key(request: Request, email: str) -> str:
    return f"{request.client.host if request.client else '?'}|{email}"


def _check_rate(key: str) -> None:
    now = time.time()
    with _fails_lock:
        recent = [t for t in _fails.get(key, []) if now - t < FAIL_WINDOW_S]
        _fails[key] = recent
        if len(recent) >= MAX_FAILS:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in a few minutes.")


def _register_fail(key: str) -> None:
    with _fails_lock:
        _fails.setdefault(key, []).append(time.time())


def _set_cookies(response: Response, request: Request, access: str, refresh: str, expires_in: int) -> None:
    secure = request.url.scheme == "https"
    response.set_cookie(ACCESS_COOKIE, access, max_age=int(expires_in or 3600), httponly=True,
                        samesite="lax", secure=secure, path="/")
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=REFRESH_COOKIE_MAX_AGE, httponly=True,
                        samesite="lax", secure=secure, path="/api/v1/auth")


def _me(user: AuthUser) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "status": user.status,
            "auth_off": auth_off()}


@router.post("/signup", status_code=201)
def signup(body: SignupBody, request: Request, session: Session = Depends(get_session)):
    _need_supabase()
    status, data = supabase_request("POST", "/auth/v1/signup", json={
        "email": body.email, "password": body.password, "data": {"full_name": body.full_name.strip()},
    })
    if status >= 400:
        message = (data or {}).get("msg") or (data or {}).get("error_description") or "Could not create the account."
        raise HTTPException(status_code=422 if status in (400, 422) else 502, detail=str(message)[:200])
    user = data.get("user") if isinstance(data, dict) and isinstance(data.get("user"), dict) else data
    if isinstance(user, dict) and user.get("id"):
        row = provision_user(session, {"sub": user["id"], "email": body.email,
                                       "user_metadata": {"full_name": body.full_name.strip()}})
        audit.record(session, None, "auth.signup", "user", row.id, body.email, request)
        session.commit()
    if auto_approve():
        return {"message": "Account created. You can sign in now."}
    return {"message": "Account created. An administrator must approve it before you can use VITALYN."}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, session: Session = Depends(get_session)):
    _need_supabase()
    key = _rate_key(request, body.email)
    _check_rate(key)
    status, data = supabase_request("POST", "/auth/v1/token", params={"grant_type": "password"},
                                    json={"email": body.email, "password": body.password})
    if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
        if isinstance(data, dict) and data.get("error_code") == "email_not_confirmed":
            raise HTTPException(status_code=403, detail="Confirm your email address first, then sign in.")
        _register_fail(key)
        audit.record(session, None, "auth.login_failed", "user", None, body.email, request)
        session.commit()
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    sb_user = data.get("user") or {}
    user = provision_user(session, {"sub": sb_user.get("id"), "email": body.email,
                                    "user_metadata": sb_user.get("user_metadata") or {}})
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    me = AuthUser(id=str(user.id), auth_id=user.auth_user_id, email=user.email, name=user.name,
                  role=user.role, status=user.status)
    audit.record(session, me, "auth.login", "user", user.id, None, request)
    session.commit()
    _set_cookies(response, request, data["access_token"], data.get("refresh_token", ""), data.get("expires_in", 3600))
    return _me(me)


@router.post("/refresh")
def refresh(request: Request, response: Response):
    _need_supabase()
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    status, data = supabase_request("POST", "/auth/v1/token", params={"grant_type": "refresh_token"},
                                    json={"refresh_token": token})
    if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
        response.delete_cookie(ACCESS_COOKIE, path="/")
        response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    _set_cookies(response, request, data["access_token"], data.get("refresh_token", token), data.get("expires_in", 3600))
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    access = request.cookies.get(ACCESS_COOKIE)
    if access and auth_configured():
        try:
            supabase_request("POST", "/auth/v1/logout", token=access)      # best effort
        except HTTPException:
            pass
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"ok": True}


@router.get("/me")
def me(identity: AuthUser = Depends(current_identity)):
    return _me(identity)
