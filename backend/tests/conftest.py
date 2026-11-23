"""
Test safety net: never let the test suite touch a real database.

backend/.env may point DATABASE_URL at Supabase; tests must always use a throwaway
SQLite file and a throwaway fall-event outbox. This runs before any app import.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="vitalyn-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test_app.db"
os.environ["VITALYN_OUTBOX_PATH"] = os.path.join(_tmp, "outbox.db")
os.environ.pop("VITALYN_PHONE_GATEWAY", None)
# Most auth tests exercise the administrator-approval flow; auto-approval has its own tests.
os.environ["VITALYN_AUTO_APPROVE"] = "off"
os.environ["VITALYN_CAMERA_PREFLIGHT"] = "off"


# ── authentication in tests ──────────────────────────────────────────────────
# Existing API tests run as a signed-in administrator. Tests that exercise real authentication
# (test_auth.py) remove this override themselves; test_rbac.py swaps in each role in turn.
import pytest  # noqa: E402


def _staff(role: str):
    import auth
    return auth.AuthUser(id=None, auth_id=None, email=f"{role}@tests.local", name=role.title(), role=role, status="active")


@pytest.fixture(autouse=True)
def _signed_in_as_admin():
    from main import app
    import auth
    previous = app.dependency_overrides.get(auth.current_user)
    app.dependency_overrides[auth.current_user] = lambda: _staff("admin")
    yield
    if previous is None:
        app.dependency_overrides.pop(auth.current_user, None)
    else:
        app.dependency_overrides[auth.current_user] = previous
