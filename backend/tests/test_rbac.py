"""The role matrix: every role against every kind of endpoint. 403 means the role is blocked."""
import uuid

import pytest
from fastapi.testclient import TestClient

import auth
import main  # noqa: F401
import test_backend  # noqa: F401  (installs its own DB override first)
from main import app
from permissions import ADMIN, ANY_STAFF, CLINICAL, DOCTORS, FRONT_DESK, REGISTRARS
from stubs import StubManager, module_for

ROLES = ("admin", "doctor", "nurse", "receptionist")
UID = str(uuid.uuid4())

# (method, path, body, roles allowed)
MATRIX = [
    # rooms / beds
    ("get", "/api/v1/rooms", None, ANY_STAFF),
    ("get", "/api/v1/beds", None, ANY_STAFF),
    ("post", "/api/v1/rooms", {"room_number": "RB1", "floor": "1"}, ADMIN),
    ("post", "/api/v1/beds", {"bed_number": "1"}, ADMIN),
    ("get", f"/api/v1/beds/{UID}/occupancy", None, CLINICAL),
    # patients
    ("get", "/api/v1/patients", None, ANY_STAFF),
    ("get", "/api/v1/doctors", None, ANY_STAFF),
    ("post", "/api/v1/doctors", {"name": "Dr X"}, ADMIN),
    ("post", "/api/v1/patients", {"name": "N", "age": 1, "condition": "c", "doctor_id": UID, "room_id": UID}, REGISTRARS),
    ("get", f"/api/v1/patients/{UID}", None, ANY_STAFF),
    ("patch", f"/api/v1/patients/{UID}", {"age": 5}, REGISTRARS),
    ("post", f"/api/v1/patients/{UID}/discharge", None, DOCTORS),
    ("delete", f"/api/v1/patients/{UID}", None, ADMIN),
    ("post", f"/api/v1/patients/{UID}/transfer", {"room_id": UID, "bed_id": UID}, CLINICAL),
    ("post", f"/api/v1/patients/{UID}/readmit", {"room_id": UID}, REGISTRARS),
    ("get", f"/api/v1/patients/{UID}/timeline", None, ANY_STAFF),
    ("patch", f"/api/v1/beds/{UID}/status", {"status": "available"}, CLINICAL),
    ("get", "/api/v1/ward-board", None, ANY_STAFF),
    ("post", "/api/v1/patients/register", {"name": "N", "age": 1}, REGISTRARS),
    ("post", f"/api/v1/patients/{UID}/admit", {"doctor_id": UID, "room_id": UID}, REGISTRARS),
    ("get", f"/api/v1/doctors/{UID}/schedule", None, ANY_STAFF),
    ("put", f"/api/v1/doctors/{UID}/schedule", [], DOCTORS),
    ("get", f"/api/v1/doctors/{UID}/availability?date=2030-01-07", None, ANY_STAFF),
    ("post", "/api/v1/appointments", {"patient_id": UID, "doctor_id": UID, "start_at": "2030-01-07T09:00"}, FRONT_DESK),
    ("get", "/api/v1/appointments", None, ANY_STAFF),
    ("post", f"/api/v1/patients/{UID}/camera-link", None, CLINICAL),
    ("put", f"/api/v1/patients/{UID}/camera", {"kind": "webcam", "index": 0}, CLINICAL),
    ("delete", f"/api/v1/patients/{UID}/camera", None, CLINICAL),
    ("post", f"/api/v1/patients/{UID}/monitor", None, CLINICAL),
    ("post", f"/api/v1/patients/{UID}/monitor/stop", None, CLINICAL),
    ("get", f"/api/v1/patients/{UID}/events", None, CLINICAL),
    # monitoring, video and alerts
    ("get", "/api/v1/live/status", None, CLINICAL),
    ("get", "/api/v1/live/sources", None, CLINICAL),
    ("post", "/api/v1/live/stop", None, CLINICAL),
    ("get", "/api/v1/jobs", None, CLINICAL),
    ("get", f"/api/v1/jobs/{UID}/results", None, CLINICAL),
    ("get", f"/api/v1/videos/{UID}/stream", None, CLINICAL),
    ("get", "/api/v1/alerts", None, CLINICAL),
    ("patch", f"/api/v1/alerts/{UID}/acknowledge", None, CLINICAL),
    ("patch", f"/api/v1/alerts/{UID}/resolve", None, CLINICAL),
    ("get", "/api/v1/events/falls", None, CLINICAL),
    ("patch", f"/api/v1/events/falls/{UID}/resolve", None, CLINICAL),
    ("get", "/api/v1/occupancy/history", None, CLINICAL),
    # dashboard
    ("get", "/api/v1/dashboard/overview", None, ANY_STAFF),
    ("get", "/api/v1/dashboard/event-summary", None, CLINICAL),
    # administration
    ("get", "/api/v1/staff", None, ADMIN),
    ("get", "/api/v1/audit", None, ADMIN),
]


@pytest.fixture
def as_role(monkeypatch, tmp_path):
    import live_routes
    from sqlmodel import Session, SQLModel, create_engine
    from database import get_session
    engine = create_engine(f"sqlite:///{tmp_path}/rbac.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    previous_session = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = override
    mgr = StubManager()
    monkeypatch.setattr(live_routes, "_live_module", lambda: module_for(mgr))
    monkeypatch.setattr(live_routes, "_loaded_manager", lambda: mgr)
    client = TestClient(app)

    def switch(role):
        app.dependency_overrides[auth.current_user] = lambda: auth.AuthUser(
            id=None, auth_id=None, email=f"{role}@t.local", name=role, role=role, status="active")
        return client

    yield switch
    if previous_session is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = previous_session


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("method,path,body,allowed", MATRIX, ids=[f"{m.upper()} {p.replace(UID, '{id}')}" for m, p, _, _ in MATRIX])
def test_role_matrix(as_role, role, method, path, body, allowed):
    client = as_role(role)
    r = client.request(method.upper(), path, json=body)
    if role in allowed:
        assert r.status_code not in (401, 403), f"{role} should reach {method.upper()} {path}, got {r.status_code}"
    else:
        assert r.status_code == 403, f"{role} must be blocked from {method.upper()} {path}, got {r.status_code}"
        assert r.json()["detail"]["code"] == "forbidden"


def test_alert_actions_record_the_signed_in_staff_member(as_role):
    """Acknowledging/resolving stores the real staff member and writes an audit row."""
    from sqlmodel import Session, select
    from database import get_session
    from models import Alert, AuditLog, FallEvent, User

    client = as_role("nurse")
    engine = next(app.dependency_overrides[get_session]()).get_bind()
    with Session(engine) as s:
        nurse = User(name="Nina", email=f"nina-{uuid.uuid4().hex[:6]}@t.local", auth_user_id=uuid.uuid4().hex,
                     role="nurse", status="active")
        s.add(nurse); s.commit(); s.refresh(nurse)
        ev = FallEvent(confidence=0.9); s.add(ev); s.commit(); s.refresh(ev)
        al = Alert(fall_event_id=ev.id, alert_type="potential_fall", severity="high"); s.add(al); s.commit(); s.refresh(al)
        nurse_id, alert_id = str(nurse.id), str(al.id)
    app.dependency_overrides[auth.current_user] = lambda: auth.AuthUser(
        id=nurse_id, auth_id=None, email="n@t.local", name="Nina", role="nurse", status="active")
    r = client.patch(f"/api/v1/alerts/{alert_id}/acknowledge")
    assert r.status_code == 200 and r.json()["acknowledged_by"] == nurse_id and r.json()["status"] == "acknowledged"
    with Session(engine) as s:
        assert "alert.acknowledge" in [a.action for a in s.exec(select(AuditLog)).all()]


def test_unauthenticated_requests_are_refused_everywhere(monkeypatch):
    """With no override at all, protected endpoints answer 401 (not data)."""
    app.dependency_overrides.pop(auth.current_user, None)
    monkeypatch.delenv("VITALYN_AUTH", raising=False)
    client = TestClient(app)
    for method, path, body, _ in MATRIX:
        assert client.request(method.upper(), path, json=body).status_code == 401, path
    assert client.get("/health").status_code == 200          # health stays public
