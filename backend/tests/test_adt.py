"""Admission / transfer / discharge rules: one patient per bed, bed lifecycle, timeline, ward board."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import auth
import main  # noqa: F401
import test_backend  # noqa: F401
import patient_routes
from database import get_session
from main import app
from models import FallEvent
from stubs import StubManager, module_for
from conftest import _staff


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/adt.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as s:
            yield s

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = override
    c = TestClient(app)
    c.engine = engine
    yield c
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest.fixture
def ward(client):
    doctor = client.post("/api/v1/doctors", json={"name": "Dr. Demo"}).json()["id"]
    room = client.post("/api/v1/rooms", json={"room_number": f"R{uuid.uuid4().hex[:4]}", "floor": "1"}).json()["id"]
    beds = [client.post("/api/v1/beds", json={"bed_number": str(i), "room_id": room}).json()["id"] for i in (1, 2, 3)]
    return {"doctor": doctor, "room": room, "beds": beds}


def admit(client, ward, bed=0, **over):
    data = {"name": "Demo Patient", "age": 70, "condition": "Observation", "doctor_id": ward["doctor"],
            "room_id": ward["room"], "bed_id": ward["beds"][bed]}
    data.update(over)
    r = client.post("/api/v1/patients", json=data)
    assert r.status_code == 201, r.text
    return r.json()["patient"]


def bed_status(client, ward, i):
    board = client.get("/api/v1/ward-board").json()
    return next(b for r in board["rooms"] for b in r["beds"] if b["id"] == ward["beds"][i])


def test_one_patient_per_bed(client, ward):
    admit(client, ward, 0)
    r = client.post("/api/v1/patients", json={"name": "Other", "age": 5, "condition": "c", "doctor_id": ward["doctor"],
                                              "room_id": ward["room"], "bed_id": ward["beds"][0]})
    assert r.status_code == 409 and "occupied" in r.json()["detail"]


def test_admit_records_an_admission_event_and_new_fields(client, ward):
    p = admit(client, ward, sex="female", date_of_birth="1950-02-03", phone="555-0100",
              emergency_contact="Demo Relative", allergies="Penicillin (fictional)")
    assert p["sex"] == "female" and p["allergies"].startswith("Penicillin") and p["bed_number"] == "1"
    events = client.get(f"/api/v1/patients/{p['id']}/timeline").json()
    assert [e["kind"] for e in events] == ["admitted"]


def test_transfer_moves_patient_and_sends_old_bed_to_cleaning(client, ward):
    p = admit(client, ward, 0)
    r = client.post(f"/api/v1/patients/{p['id']}/transfer", json={"room_id": ward["room"], "bed_id": ward["beds"][1], "note": "Closer to nurses"})
    assert r.status_code == 200, r.text
    assert r.json()["patient"]["bed_id"] == ward["beds"][1]
    assert bed_status(client, ward, 0)["status"] == "cleaning"
    assert bed_status(client, ward, 1)["status"] == "occupied"
    kinds = [e["kind"] for e in client.get(f"/api/v1/patients/{p['id']}/timeline").json()]
    assert "transferred" in kinds


def test_transfer_needs_a_free_ready_bed(client, ward):
    a, b = admit(client, ward, 0), admit(client, ward, 1)
    url = f"/api/v1/patients/{a['id']}/transfer"
    assert client.post(url, json={"room_id": ward["room"], "bed_id": ward["beds"][1]}).status_code == 409   # occupied
    client.patch(f"/api/v1/beds/{ward['beds'][2]}/status", json={"status": "maintenance"})
    assert client.post(url, json={"room_id": ward["room"], "bed_id": ward["beds"][2]}).status_code == 409   # not ready
    assert client.post(url, json={"room_id": ward["room"], "bed_id": ward["beds"][0]}).status_code == 409   # same bed
    assert b["bed_id"] == ward["beds"][1]


def test_transfer_validates_references_and_state(client, ward):
    p = admit(client, ward, 0)
    url = f"/api/v1/patients/{p['id']}/transfer"
    assert client.post(url, json={"room_id": str(uuid.uuid4()), "bed_id": ward["beds"][1]}).status_code == 422
    other_room = client.post("/api/v1/rooms", json={"room_number": "ZZ9", "floor": "2"}).json()["id"]
    assert client.post(url, json={"room_id": other_room, "bed_id": ward["beds"][1]}).status_code == 422   # bed not in room
    client.post(f"/api/v1/patients/{p['id']}/discharge")
    assert client.post(url, json={"room_id": ward["room"], "bed_id": ward["beds"][2]}).status_code == 409


def test_transfer_ends_only_that_patients_live_session(client, ward, monkeypatch):
    mgr = StubManager()
    monkeypatch.setitem(__import__("sys").modules, "live_pipeline", module_for(mgr))
    a, b = admit(client, ward, 0), admit(client, ward, 1)
    mgr.start(ward["room"], 0, patient_id=a["id"])
    mgr.start(ward["room"], 1, patient_id=b["id"])
    r = client.post(f"/api/v1/patients/{a['id']}/transfer", json={"room_id": ward["room"], "bed_id": ward["beds"][2]})
    assert r.json()["monitoring_stopped"] is True
    assert mgr.get(a["id"]) is None and mgr.get(b["id"]) is not None


def test_discharge_frees_bed_to_cleaning_stores_summary_and_revokes_camera(client, ward):
    p = admit(client, ward, 0)
    r = client.post(f"/api/v1/patients/{p['id']}/discharge",
                    json={"type": "home", "diagnosis": "Recovered", "instructions": "Rest", "follow_up_date": "2030-01-15"})
    assert r.status_code == 200 and r.json()["status"] == "discharged" and not r.json()["has_camera_link"]
    assert bed_status(client, ward, 0)["status"] == "cleaning"


def test_cleaning_bed_cannot_be_given_out_until_made_available(client, ward):
    p = admit(client, ward, 0)
    client.post(f"/api/v1/patients/{p['id']}/discharge")
    body = {"name": "Next", "age": 9, "condition": "c", "doctor_id": ward["doctor"], "room_id": ward["room"], "bed_id": ward["beds"][0]}
    assert client.post("/api/v1/patients", json=body).status_code == 409
    assert client.patch(f"/api/v1/beds/{ward['beds'][0]}/status", json={"status": "available"}).status_code == 200
    assert client.post("/api/v1/patients", json=body).status_code == 201


def test_discharge_summary_appears_in_timeline_and_validates(client, ward):
    p = admit(client, ward, 0)
    assert client.post(f"/api/v1/patients/{p['id']}/discharge", json={"type": "bogus"}).status_code == 422
    client.post(f"/api/v1/patients/{p['id']}/discharge", json={"type": "ama", "diagnosis": "Left against advice"})
    last = client.get(f"/api/v1/patients/{p['id']}/timeline").json()[0]
    assert last["kind"] == "discharged" and last["summary"]["type"] == "ama"


def test_readmit_restores_stay_with_a_new_qr_and_event(client, ward):
    p = admit(client, ward, 0)
    client.post(f"/api/v1/patients/{p['id']}/discharge")
    client.patch(f"/api/v1/beds/{ward['beds'][0]}/status", json={"status": "available"})
    assert client.post(f"/api/v1/patients/{p['id']}/readmit", json={"room_id": ward["room"], "bed_id": ward["beds"][1]}).status_code == 201
    got = client.get(f"/api/v1/patients/{p['id']}").json()
    assert got["status"] == "admitted" and got["discharged_at"] is None and got["has_camera_link"]
    assert client.post(f"/api/v1/patients/{p['id']}/readmit", json={"room_id": ward["room"]}).status_code == 409
    assert [e["kind"] for e in client.get(f"/api/v1/patients/{p['id']}/timeline").json()][0] == "readmitted"


def test_bed_status_rules(client, ward):
    p = admit(client, ward, 0)
    assert client.patch(f"/api/v1/beds/{ward['beds'][0]}/status", json={"status": "cleaning"}).status_code == 409   # occupied
    assert client.patch(f"/api/v1/beds/{ward['beds'][1]}/status", json={"status": "occupied"}).status_code == 422
    assert client.patch(f"/api/v1/beds/{uuid.uuid4()}/status", json={"status": "available"}).status_code == 404
    assert client.patch(f"/api/v1/beds/{ward['beds'][1]}/status", json={"status": "maintenance"}).status_code == 200
    assert p["status"] == "admitted"


def test_patching_location_requires_transfer(client, ward):
    p = admit(client, ward, 0)
    r = client.patch(f"/api/v1/patients/{p['id']}", json={"bed_id": ward["beds"][1]})
    assert r.status_code == 422 and "Transfer" in r.json()["detail"]
    assert client.patch(f"/api/v1/patients/{p['id']}", json={"condition": "Better"}).status_code == 200


def test_ward_board_counts_occupants_monitoring_and_alerts(client, ward, monkeypatch):
    mgr = StubManager()
    monkeypatch.setitem(__import__("sys").modules, "live_pipeline", module_for(mgr))
    p = admit(client, ward, 0)
    mgr.start(ward["room"], 0, patient_id=p["id"])
    with Session(client.engine) as s:
        s.add(FallEvent(patient_id=uuid.UUID(p["id"]), room_id=uuid.UUID(ward["room"]), confidence=0.9))
        s.commit()
    client.patch(f"/api/v1/beds/{ward['beds'][2]}/status", json={"status": "maintenance"})
    board = client.get("/api/v1/ward-board").json()
    assert board["counts"] == {"occupied": 1, "available": 1, "cleaning": 0, "maintenance": 1}
    occ = board["rooms"][0]["beds"][0]["patient"]
    assert occ["monitored"] is True and occ["active_alerts"] == 1


def test_receptionist_board_hides_clinical_details_and_fall_timeline(client, ward):
    p = admit(client, ward, 0)
    with Session(client.engine) as s:
        s.add(FallEvent(patient_id=uuid.UUID(p["id"]), confidence=0.9))
        s.commit()
    app.dependency_overrides[auth.current_user] = lambda: _staff("receptionist")
    occ = client.get("/api/v1/ward-board").json()["rooms"][0]["beds"][0]["patient"]
    assert "condition" not in occ and "monitored" not in occ and "active_alerts" not in occ
    kinds = [e["kind"] for e in client.get(f"/api/v1/patients/{p['id']}/timeline").json()]
    assert "fall_event" not in kinds


def test_fall_events_show_in_a_clinical_timeline(client, ward):
    p = admit(client, ward, 0)
    with Session(client.engine) as s:
        s.add(FallEvent(patient_id=uuid.UUID(p["id"]), confidence=0.9))
        s.commit()
    kinds = [e["kind"] for e in client.get(f"/api/v1/patients/{p['id']}/timeline").json()]
    assert "fall_event" in kinds


def test_patient_search_by_name_code_or_phone(client, ward):
    a = admit(client, ward, 0, name="Asha Demo", phone="555-0101")
    admit(client, ward, 1, name="Ravi Demo", phone="555-0202")
    names = lambda q: sorted(p["name"] for p in client.get("/api/v1/patients", params={"q": q}).json())
    assert names("asha") == ["Asha Demo"]
    assert names(a["patient_code"]) == ["Asha Demo"]
    assert names("0202") == ["Ravi Demo"]
    assert names("zzz") == []
    assert len(names("")) == 2
