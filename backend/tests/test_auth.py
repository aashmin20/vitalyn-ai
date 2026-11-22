"""Authentication, roles, staff approval, audit. Tokens are signed with a locally generated key."""
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlmodel import Session, SQLModel, create_engine, select

import auth
import main  # noqa: F401
import test_backend  # noqa: F401  (imported first: installs its own session override)
from database import get_session
from main import app
from models import AuditLog, Doctor, User

URL = "https://proj.supabase.co"
KID = "test-key"
_priv = ec.generate_private_key(ec.SECP256R1())
PRIV_PEM = _priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
PUB_PEM = _priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _jwk():
    d = jwk.construct(PUB_PEM, "ES256").to_dict()
    d = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in d.items()}
    d.update(kid=KID, alg="ES256", use="sig")
    return d


def make_token(sub, email, *, exp=3600, aud="authenticated", iss=f"{URL}/auth/v1", key=PRIV_PEM, alg="ES256", full_name=None, kid=KID):
    claims = {"sub": sub, "email": email, "aud": aud, "iss": iss, "exp": int(time.time()) + exp,
              "user_metadata": {"full_name": full_name} if full_name else {}}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-test-key")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("VITALYN_AUTH", raising=False)
    auth._jwks_cache.update(at=0.0, keys=[])
    auth._user_cache.clear()
    auth._fails_clear = None
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_jwk()]})

    engine = create_engine(f"sqlite:///{tmp_path}/a.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    previous = dict(app.dependency_overrides)
    app.dependency_overrides.pop(auth.current_user, None)         # real auth for these tests
    app.dependency_overrides.pop(auth.current_identity, None)
    app.dependency_overrides[get_session] = override
    import auth_routes
    auth_routes._fails.clear()
    client = TestClient(app)
    client.engine = engine
    yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def add_user(client, role="nurse", status="active", email=None):
    sub = str(uuid.uuid4())
    email = email or f"{role}-{sub[:6]}@hospital.test"
    with Session(client.engine) as s:
        u = User(name=role.title(), email=email, auth_user_id=sub, role=role, status=status)
        s.add(u); s.commit(); s.refresh(u)
        return {"sub": sub, "email": email, "id": str(u.id), "token": make_token(sub, email)}


def bearer(u):
    return {"Authorization": f"Bearer {u['token']}"}


# ── token verification ───────────────────────────────────────────────────────

def test_requests_without_a_token_are_401(env):
    assert env.get("/api/v1/auth/me").status_code == 401


def test_valid_token_of_an_unknown_account_creates_a_pending_staff_row(env):
    sub = str(uuid.uuid4())
    r = env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {make_token(sub, 'new@hospital.test', full_name='New Nurse')}"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending" and body["role"] == "none" and body["name"] == "New Nurse"
    with Session(env.engine) as s:
        assert s.exec(select(User).where(User.auth_user_id == sub)).one().status == "pending"


@pytest.mark.parametrize("kwargs", [
    {"exp": -10},                                   # expired
    {"aud": "someone-else"},                        # wrong audience
    {"iss": "https://evil.example/auth/v1"},        # wrong issuer
])
def test_bad_claims_are_rejected(env, kwargs):
    r = env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {make_token(str(uuid.uuid4()), 'a@b.test', **kwargs)}"})
    assert r.status_code == 401


def test_token_signed_with_another_key_is_rejected(env):
    other = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    r = env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {make_token(str(uuid.uuid4()), 'a@b.test', key=other)}"})
    assert r.status_code == 401


def test_unknown_key_id_and_garbage_are_rejected(env):
    assert env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {make_token('x', 'a@b.test', kid='nope')}"}).status_code == 401
    assert env.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_algorithm_confusion_attack_is_rejected(env, monkeypatch):
    """A token HS256-signed with the PUBLIC key as the secret must not be accepted."""
    import base64, hashlib, hmac, json
    monkeypatch.setattr(auth, "supabase_request", lambda *a, **k: (401, {}))   # Supabase would refuse it too
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    body = b64(json.dumps({"sub": "attacker", "aud": "authenticated", "exp": int(time.time()) + 600,
                           "iss": f"{URL}/auth/v1", "email": "x@y.test"}).encode())
    sig = b64(hmac.new(PUB_PEM.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    assert env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {head}.{body}.{sig}"}).status_code == 401


def test_alg_none_is_rejected(env):
    import base64, json
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'x', 'aud': 'authenticated', 'exp': int(time.time()) + 600})}."
    assert env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_shared_secret_mode(env, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s3cret-for-tests-only-0123456789abcdef")
    good = jwt.encode({"sub": str(uuid.uuid4()), "email": "s@h.test", "aud": "authenticated", "exp": int(time.time()) + 600},
                      "s3cret-for-tests-only-0123456789abcdef", algorithm="HS256")
    assert env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {good}"}).status_code == 200
    bad = jwt.encode({"sub": "x", "aud": "authenticated", "exp": int(time.time()) + 600}, "wrong-secret-wrong-secret-0123456789", algorithm="HS256")
    assert env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_a_configured_shared_secret_does_not_break_es256_projects(env, monkeypatch):
    """Regression: a project that signs with ES256 keys must still work if SUPABASE_JWT_SECRET is filled in."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s3cret-for-tests-only-0123456789abcdef")
    token = make_token(str(uuid.uuid4()), "es@h.test")
    assert env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


# ── status and roles ─────────────────────────────────────────────────────────

def test_pending_and_disabled_accounts_cannot_use_the_api(env):
    pending, disabled = add_user(env, "nurse", "pending"), add_user(env, "nurse", "disabled")
    r = env.get("/api/v1/staff", headers=bearer(pending))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pending"
    assert env.get("/api/v1/staff", headers=bearer(disabled)).json()["detail"]["code"] == "disabled"
    assert env.get("/api/v1/auth/me", headers=bearer(pending)).status_code == 200     # may see own status


def test_only_admins_reach_admin_endpoints(env):
    admin = add_user(env, "admin")
    assert env.get("/api/v1/staff", headers=bearer(admin)).status_code == 200
    assert env.get("/api/v1/audit", headers=bearer(admin)).status_code == 200
    for role in ("doctor", "nurse", "receptionist"):
        u = add_user(env, role)
        assert env.get("/api/v1/staff", headers=bearer(u)).status_code == 403
        assert env.get("/api/v1/audit", headers=bearer(u)).status_code == 403


# ── CSRF (cookie sessions) ───────────────────────────────────────────────────

def test_cookie_sessions_need_the_csrf_header_for_changes(env):
    admin, target = add_user(env, "admin"), add_user(env, "nurse", "pending")
    env.cookies.set(auth.ACCESS_COOKIE, admin["token"])
    url = f"/api/v1/staff/{target['id']}"
    assert env.get("/api/v1/staff").status_code == 200                                    # reads are fine
    assert env.patch(url, json={"role": "nurse", "status": "active"}).status_code == 403   # no header
    ok = env.patch(url, json={"role": "nurse", "status": "active"}, headers={"X-Requested-With": "vitalyn"})
    assert ok.status_code == 200
    env.cookies.clear()


# ── staff approval rules ─────────────────────────────────────────────────────

def test_admin_approves_a_pending_account_and_it_is_audited(env):
    admin, nurse = add_user(env, "admin"), add_user(env, "nurse", "pending")
    r = env.patch(f"/api/v1/staff/{nurse['id']}", json={"role": "nurse", "status": "active"}, headers=bearer(admin))
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert env.get("/api/v1/staff", headers=bearer(nurse)).status_code == 403            # active, but not an admin
    log = env.get("/api/v1/audit", params={"action": "staff."}, headers=bearer(admin)).json()
    assert log[0]["action"] == "staff.update" and log[0]["actor_email"] == admin["email"]
    assert "status pending->active" in log[0]["detail"]


def test_activating_without_a_role_is_refused(env):
    admin, pending = add_user(env, "admin"), add_user(env, "none", "pending")
    r = env.patch(f"/api/v1/staff/{pending['id']}", json={"status": "active"}, headers=bearer(admin))
    assert r.status_code == 422 and "role" in r.json()["detail"].lower()


def test_invalid_role_and_status_values_are_refused(env):
    admin, u = add_user(env, "admin"), add_user(env, "nurse")
    assert env.patch(f"/api/v1/staff/{u['id']}", json={"role": "superuser"}, headers=bearer(admin)).status_code == 422
    assert env.patch(f"/api/v1/staff/{u['id']}", json={"status": "banned"}, headers=bearer(admin)).status_code == 422
    assert env.patch(f"/api/v1/staff/{uuid.uuid4()}", json={"role": "nurse"}, headers=bearer(admin)).status_code == 404


def test_admin_cannot_change_their_own_role_or_status(env):
    admin = add_user(env, "admin")
    assert env.patch(f"/api/v1/staff/{admin['id']}", json={"status": "disabled"}, headers=bearer(admin)).status_code == 409
    assert env.patch(f"/api/v1/staff/{admin['id']}", json={"role": "nurse"}, headers=bearer(admin)).status_code == 409


def test_one_admin_can_disable_another_when_an_admin_remains(env):
    first, second = add_user(env, "admin"), add_user(env, "admin")
    r = env.patch(f"/api/v1/staff/{second['id']}", json={"status": "disabled"}, headers=bearer(first))
    assert r.status_code == 200 and r.json()["status"] == "disabled"


def test_the_last_active_admin_can_never_be_removed(env, monkeypatch):
    sole = add_user(env, "admin")
    monkeypatch.setenv("VITALYN_AUTH", "off")             # demo mode: the caller is not a staff row
    r = env.patch(f"/api/v1/staff/{sole['id']}", json={"status": "disabled"})
    assert r.status_code == 409 and "at least one active administrator" in r.json()["detail"]
    assert env.patch(f"/api/v1/staff/{sole['id']}", json={"role": "nurse"}).status_code == 409


def test_making_someone_a_doctor_creates_their_doctor_record(env):
    admin, u = add_user(env, "admin"), add_user(env, "nurse", "pending")
    env.patch(f"/api/v1/staff/{u['id']}", json={"role": "doctor", "status": "active"}, headers=bearer(admin))
    with Session(env.engine) as s:
        assert s.exec(select(Doctor).where(Doctor.user_id == uuid.UUID(u["id"]))).first() is not None


# ── login / signup / logout through the backend ──────────────────────────────

def fake_supabase(monkeypatch, *, login_ok=True, sub=None, email="nurse@hospital.test"):
    sub = sub or str(uuid.uuid4())
    calls = []

    def fake(method, path, **kw):
        calls.append((method, path, kw.get("params"), kw.get("json")))
        if path == "/auth/v1/token" and (kw.get("params") or {}).get("grant_type") == "password":
            if not login_ok:
                return 400, {"error_code": "invalid_credentials"}
            return 200, {"access_token": make_token(sub, email), "refresh_token": "rt-123", "expires_in": 3600,
                         "user": {"id": sub, "email": email, "user_metadata": {"full_name": "Nina Nurse"}}}
        if path == "/auth/v1/token":
            return 200, {"access_token": make_token(sub, email), "refresh_token": "rt-456", "expires_in": 3600}
        if path == "/auth/v1/signup":
            return 200, {"user": {"id": sub}}
        return 200, {}

    monkeypatch.setattr(auth, "supabase_request", fake)
    import auth_routes
    monkeypatch.setattr(auth_routes, "supabase_request", fake)
    return sub, calls


def test_login_sets_httponly_cookies_and_returns_the_staff_status(env, monkeypatch):
    sub, calls = fake_supabase(monkeypatch)
    r = env.post("/api/v1/auth/login", json={"email": "Nurse@Hospital.test", "password": "whatever-123"})
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["email"] == "nurse@hospital.test"
    cookie_headers = " ".join(r.headers.get_list("set-cookie")).lower()
    assert auth.ACCESS_COOKIE in cookie_headers and "httponly" in cookie_headers and "samesite=lax" in cookie_headers
    assert "rt-123" in " ".join(r.headers.get_list("set-cookie"))
    assert env.get("/api/v1/auth/me").json()["email"] == "nurse@hospital.test"           # cookie now identifies us
    with Session(env.engine) as s:
        assert s.exec(select(User)).one().last_login_at is not None
        assert "auth.login" in [a.action for a in s.exec(select(AuditLog)).all()]


def test_wrong_password_is_a_generic_401_and_rate_limited(env, monkeypatch):
    fake_supabase(monkeypatch, login_ok=False)
    for _ in range(5):
        r = env.post("/api/v1/auth/login", json={"email": "x@h.test", "password": "bad"})
        assert r.status_code == 401 and r.json()["detail"] == "Incorrect email or password."
    assert env.post("/api/v1/auth/login", json={"email": "x@h.test", "password": "bad"}).status_code == 429
    assert env.post("/api/v1/auth/login", json={"email": "other@h.test", "password": "bad"}).status_code == 401   # per account


def test_signup_creates_a_pending_account_and_validates_input(env, monkeypatch):
    fake_supabase(monkeypatch)
    ok = env.post("/api/v1/auth/signup", json={"email": "new@h.test", "password": "long-enough-1", "full_name": "New Person"})
    assert ok.status_code == 201 and "administrator must approve" in ok.json()["message"]
    with Session(env.engine) as s:
        row = s.exec(select(User)).one()
        assert (row.status, row.role, row.name) == ("pending", "none", "New Person")
    assert env.post("/api/v1/auth/signup", json={"email": "a@h.test", "password": "short", "full_name": "A"}).status_code == 422
    assert env.post("/api/v1/auth/signup", json={"email": "not-an-email", "password": "long-enough-1", "full_name": "A"}).status_code == 422


def test_refresh_and_logout(env, monkeypatch):
    fake_supabase(monkeypatch)
    assert env.post("/api/v1/auth/refresh").status_code == 401                           # no cookie
    env.cookies.set(auth.REFRESH_COOKIE, "rt-123", path="/api/v1/auth")
    r = env.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and "rt-456" in " ".join(r.headers.get_list("set-cookie"))
    out = env.post("/api/v1/auth/logout")
    assert out.status_code == 200 and "max-age=0" in " ".join(out.headers.get_list("set-cookie")).lower()


def test_login_needs_supabase_configured(env, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert env.post("/api/v1/auth/login", json={"email": "a@h.test", "password": "x"}).status_code == 503


def test_auth_off_mode_is_an_explicit_open_demo(env, monkeypatch):
    monkeypatch.setenv("VITALYN_AUTH", "off")
    r = env.get("/api/v1/auth/me")
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["auth_off"] is True
    assert env.get("/api/v1/staff").status_code == 200


# ── audit ────────────────────────────────────────────────────────────────────

def test_patient_record_views_are_logged_once_per_window(env):
    import audit
    admin = add_user(env, "admin")
    me = auth.AuthUser(id=admin["id"], auth_id=admin["sub"], email=admin["email"], name="A", role="admin", status="active")
    with Session(env.engine) as s:
        for _ in range(3):
            audit.record_view(s, me, "patient", "P1")
        audit.record_view(s, me, "patient", "P2")
        views = s.exec(select(AuditLog).where(AuditLog.action == "patient.view")).all()
    assert sorted(v.entity_id for v in views) == ["P1", "P2"]


def test_audit_log_filters(env):
    admin = add_user(env, "admin")
    other = add_user(env, "nurse", "pending")
    env.patch(f"/api/v1/staff/{other['id']}", json={"role": "nurse", "status": "active"}, headers=bearer(admin))
    rows = env.get("/api/v1/audit", params={"actor": admin["email"].upper()}, headers=bearer(admin)).json()
    assert rows and all(r["actor_email"] == admin["email"] for r in rows)
    assert env.get("/api/v1/audit", params={"action": "nothing."}, headers=bearer(admin)).json() == []



# ── auto-approval (the demo default) ─────────────────────────────────────────

def test_auto_approval_makes_the_first_account_admin_and_later_ones_doctors(env, monkeypatch):
    monkeypatch.setenv("VITALYN_AUTO_APPROVE", "on")
    first = make_token(str(uuid.uuid4()), "first@hospital.test")
    me = env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {first}"}).json()
    assert (me["status"], me["role"]) == ("active", "admin")
    second = make_token(str(uuid.uuid4()), "second@hospital.test", full_name="Dr Second")
    me2 = env.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {second}"}).json()
    assert (me2["status"], me2["role"]) == ("active", "doctor")
    assert env.get("/api/v1/patients", headers={"Authorization": f"Bearer {second}"}).status_code == 200
    doctors = env.get("/api/v1/doctors", headers={"Authorization": f"Bearer {second}"}).json()
    assert any(d["name"] == "Dr Second" for d in doctors)


def test_auto_approval_activates_an_existing_pending_account_but_never_a_disabled_one(env, monkeypatch):
    add_user(env, "admin")
    pending, disabled = add_user(env, "none", "pending"), add_user(env, "nurse", "disabled")
    monkeypatch.setenv("VITALYN_AUTO_APPROVE", "on")
    monkeypatch.setenv("VITALYN_DEFAULT_ROLE", "nurse")
    me = env.get("/api/v1/auth/me", headers=bearer(pending)).json()
    assert (me["status"], me["role"]) == ("active", "nurse")
    assert env.get("/api/v1/patients", headers=bearer(disabled)).status_code == 403


def test_signup_message_says_you_can_sign_in_with_auto_approval(env, monkeypatch):
    monkeypatch.setenv("VITALYN_AUTO_APPROVE", "on")
    fake_supabase(monkeypatch, sub=str(uuid.uuid4()), email="quick@hospital.test")
    r = env.post("/api/v1/auth/signup", json={"full_name": "Quick Start", "email": "quick@hospital.test", "password": "longenough1"},
                 headers={"X-Requested-With": "vitalyn"})
    assert r.status_code == 201 and "sign in now" in r.json()["message"]
