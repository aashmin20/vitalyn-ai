"""Outpatient department: registration, schedules, slots, booking rules, status workflow."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import auth
import main  # noqa: F401
import test_backend  # noqa: F401
import opd_routes
from conftest import _staff
from database import get_session
from main import app
from models import Doctor

MONDAY = "2030-01-07"          # a Monday in the future
NOW = datetime(2030, 1, 7, 8, 0)


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/opd.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    monkeypatch.setattr(opd_routes, "now_local", lambda: NOW)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = override
    c = TestClient(app)
    c.engine = engine
    yield c
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest.fixture
def clinic(client):
    doctor = client.post("/api/v1/doctors", json={"name": "Dr. Demo", "department": "OPD"}).json()["id"]
    r = client.put(f"/api/v1/doctors/{doctor}/schedule", json=[{"weekday": 0, "start": "09:00", "end": "10:00", "slot_minutes": 20}])
    assert r.status_code == 200, r.text
    patient = client.post("/api/v1/patients/register", json={"name": "Out Patient", "age": 40, "phone": "555-0111"}).json()
    return {"doctor": doctor, "patient": patient["id"]}


def book(client, clinic, at="09:00", **over):
    data = {"patient_id": clinic["patient"], "doctor_id": clinic["doctor"], "start_at": f"{MONDAY}T{at}"}
    data.update(over)
    return client.post("/api/v1/appointments", json=data)


def test_register_outpatient_has_no_room_bed_or_camera(client):
    r = client.post("/api/v1/patients/register", json={"name": "  Walk In ", "age": 33, "reason": "Cough", "sex": "male"})
    assert r.status_code == 201
    p = r.json()
    assert p["status"] == "outpatient" and p["name"] == "Walk In" and p["condition"] == "Cough"
    assert p["room"] is None and p["bed_id"] is None and not p["has_camera_link"]
    assert [x["id"] for x in client.get("/api/v1/patients?status=outpatient").json()] == [p["id"]]
    assert client.get("/api/v1/patients").json() == []                       # not in the admitted list
    assert client.post("/api/v1/patients/register", json={"name": "x", "age": 999}).status_code == 422


def test_outpatient_cannot_be_discharged_or_monitored(client):
    p = client.post("/api/v1/patients/register", json={"name": "Walk In", "age": 33}).json()
    assert client.post(f"/api/v1/patients/{p['id']}/discharge").status_code == 409
    assert client.post(f"/api/v1/patients/{p['id']}/camera-link").status_code == 409


def test_admit_converts_an_outpatient_once(client):
    doctor = client.post("/api/v1/doctors", json={"name": "Dr. A"}).json()["id"]
    room = client.post("/api/v1/rooms", json={"room_number": "O1", "floor": "1"}).json()["id"]
    bed = client.post("/api/v1/beds", json={"bed_number": "1", "room_id": room}).json()["id"]
    p = client.post("/api/v1/patients/register", json={"name": "Walk In", "age": 33}).json()
    r = client.post(f"/api/v1/patients/{p['id']}/admit", json={"doctor_id": doctor, "room_id": room, "bed_id": bed, "condition": "Pneumonia"})
    assert r.status_code == 201 and r.json()["patient"]["status"] == "admitted" and r.json()["patient"]["bed_number"] == "1"
    assert client.post(f"/api/v1/patients/{p['id']}/admit", json={"doctor_id": doctor, "room_id": room}).status_code == 409
    kinds = [e["kind"] for e in client.get(f"/api/v1/patients/{p['id']}/timeline").json()]
    assert kinds == ["admitted"]


def test_schedule_validation_and_replace(client, clinic):
    url = f"/api/v1/doctors/{clinic['doctor']}/schedule"
    bad = [
        [{"weekday": 0, "start": "10:00", "end": "09:00"}],                                   # ends before start
        [{"weekday": 0, "start": "09:00", "end": "09:10", "slot_minutes": 30}],               # no whole slot fits
        [{"weekday": 0, "start": "09:00", "end": "11:00"}, {"weekday": 0, "start": "10:30", "end": "12:00"}],  # overlap
        [{"weekday": 9, "start": "09:00", "end": "10:00"}],
        [{"weekday": 0, "start": "9:00", "end": "10:00"}],
    ]
    for payload in bad:
        assert client.put(url, json=payload).status_code == 422, payload
    ok = client.put(url, json=[{"weekday": 1, "start": "13:00", "end": "14:00", "slot_minutes": 30}])
    assert ok.status_code == 200 and client.get(url).json() == [{"weekday": 1, "start": "13:00", "end": "14:00", "slot_minutes": 30}]
    assert client.put(f"/api/v1/doctors/{uuid.uuid4()}/schedule", json=[]).status_code == 404


def test_availability_lists_slots_and_marks_booked_ones(client, clinic):
    free = lambda: [s["free"] for s in client.get(f"/api/v1/doctors/{clinic['doctor']}/availability", params={"date": MONDAY}).json()]
    assert free() == [True, True, True]
    assert book(client, clinic, "09:20").status_code == 201
    assert free() == [True, False, True]
    assert client.get(f"/api/v1/doctors/{clinic['doctor']}/availability", params={"date": "2030-01-08"}).json() == []   # Tuesday


def test_booking_rules(client, clinic):
    assert book(client, clinic, "09:05").status_code == 422                      # not a slot boundary
    assert book(client, clinic, "11:00").status_code == 422                      # outside the schedule
    assert book(client, clinic, "09:00").status_code == 201
    assert book(client, clinic, "09:00").status_code == 409                      # doctor already booked
    other = client.post("/api/v1/patients/register", json={"name": "Second", "age": 5}).json()["id"]
    assert book(client, clinic, "09:00", patient_id=other).status_code == 409    # same doctor, same slot
    assert book(client, clinic, "09:20", patient_id=str(uuid.uuid4())).status_code == 404
    assert book(client, clinic, "09:20", doctor_id=str(uuid.uuid4())).status_code == 404


def test_patient_cannot_hold_two_appointments_at_once(client, clinic):
    doctor2 = client.post("/api/v1/doctors", json={"name": "Dr. B"}).json()["id"]
    client.put(f"/api/v1/doctors/{doctor2}/schedule", json=[{"weekday": 0, "start": "09:00", "end": "10:00", "slot_minutes": 20}])
    assert book(client, clinic, "09:00").status_code == 201
    assert book(client, clinic, "09:00", doctor_id=doctor2).status_code == 409


def test_past_slots_are_refused_and_not_free(client, clinic, monkeypatch):
    monkeypatch.setattr(opd_routes, "now_local", lambda: datetime(2030, 1, 7, 9, 30))
    assert book(client, clinic, "09:00").status_code == 422
    slots = client.get(f"/api/v1/doctors/{clinic['doctor']}/availability", params={"date": MONDAY}).json()
    assert [s["free"] for s in slots] == [False, True, True]


def test_cancelled_slot_can_be_rebooked(client, clinic):
    appt = book(client, clinic, "09:00").json()
    assert client.patch(f"/api/v1/appointments/{appt['id']}", json={"status": "cancelled"}).status_code == 200
    assert book(client, clinic, "09:00").status_code == 201


def test_legal_status_transitions_only(client, clinic):
    appt = book(client, clinic).json()
    url = f"/api/v1/appointments/{appt['id']}"
    move = lambda s: client.patch(url, json={"status": s}).status_code
    assert move("completed") == 409                  # cannot skip check-in and consultation
    assert move("in_consult") == 409
    assert move("checked_in") == 200
    assert move("checked_in") == 409
    assert move("in_consult") == 200
    assert move("cancelled") == 409                  # a consultation in progress cannot be cancelled
    assert move("completed") == 200
    assert move("scheduled") == 422 and move("no_show") == 409                # finished is final
    assert client.patch(f"/api/v1/appointments/{uuid.uuid4()}", json={"status": "cancelled"}).status_code == 404


def test_list_filters_and_ordering(client, clinic):
    book(client, clinic, "09:40")
    book(client, clinic, "09:00", patient_id=client.post("/api/v1/patients/register", json={"name": "Two", "age": 2}).json()["id"])
    rows = client.get("/api/v1/appointments", params={"date": MONDAY, "doctor_id": clinic["doctor"]}).json()
    assert [r["start_at"] for r in rows] == [f"{MONDAY}T09:00", f"{MONDAY}T09:40"]
    assert client.get("/api/v1/appointments", params={"date": "2030-01-08"}).json() == []
    assert len(client.get("/api/v1/appointments", params={"patient_id": clinic["patient"]}).json()) == 1
    assert client.get("/api/v1/appointments", params={"status": "bogus"}).status_code == 422


def _make_doctor_user(client, name):
    with Session(client.engine) as s:
        from models import User
        u = User(name=name, email=f"{name}@t.local", role="doctor", status="active")
        s.add(u); s.commit(); s.refresh(u)
        d = Doctor(name=name, user_id=u.id)
        s.add(d); s.commit(); s.refresh(d)
        return str(u.id), str(d.id)


def _as(user_id, role):
    app.dependency_overrides[auth.current_user] = lambda: auth.AuthUser(
        id=user_id, auth_id=None, email=f"{role}@t.local", name=role, role=role, status="active")


def test_only_the_appointments_own_doctor_runs_the_consultation(client):
    uid_a, doc_a = _make_doctor_user(client, "a")
    uid_b, _ = _make_doctor_user(client, "b")
    client.put(f"/api/v1/doctors/{doc_a}/schedule", json=[{"weekday": 0, "start": "09:00", "end": "10:00"}])
    pid = client.post("/api/v1/patients/register", json={"name": "P", "age": 1}).json()["id"]
    appt = client.post("/api/v1/appointments", json={"patient_id": pid, "doctor_id": doc_a, "start_at": f"{MONDAY}T09:00"}).json()
    url = f"/api/v1/appointments/{appt['id']}"
    assert client.patch(url, json={"status": "checked_in"}).status_code == 200
    _as(uid_b, "doctor")
    assert client.patch(url, json={"status": "in_consult"}).status_code == 403       # someone else's patient
    _as(uid_a, "doctor")
    assert client.patch(url, json={"status": "in_consult"}).status_code == 200


def test_receptionist_checks_in_but_cannot_run_a_consultation_and_nurse_only_views(client, clinic):
    appt = book(client, clinic).json()
    url = f"/api/v1/appointments/{appt['id']}"
    app.dependency_overrides[auth.current_user] = lambda: _staff("receptionist")
    assert client.patch(url, json={"status": "checked_in"}).status_code == 200
    assert client.patch(url, json={"status": "in_consult"}).status_code == 403
    app.dependency_overrides[auth.current_user] = lambda: _staff("nurse")
    assert client.get("/api/v1/appointments").status_code == 200
    assert client.patch(url, json={"status": "cancelled"}).status_code == 403
    assert book(client, clinic, "09:20").status_code == 403


def test_a_doctor_edits_only_their_own_schedule(client):
    uid_a, doc_a = _make_doctor_user(client, "a")
    _, doc_b = _make_doctor_user(client, "b")
    _as(uid_a, "doctor")
    block = [{"weekday": 2, "start": "09:00", "end": "12:00"}]
    assert client.put(f"/api/v1/doctors/{doc_a}/schedule", json=block).status_code == 200
    assert client.put(f"/api/v1/doctors/{doc_b}/schedule", json=block).status_code == 403
