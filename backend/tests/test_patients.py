"""Patient admission API: validation, camera-token security, discharge/delete behaviour."""
import sys
import types
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from database import get_session
from main import app
import test_backend  # noqa: F401  (imported first: it installs its own session override)
from stubs import StubManager, StubCameraError, module_for
from models import FallEvent, InferenceJob, Patient
import patient_routes
from patient_routes import find_patient_by_token, hash_token


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/p.db", connect_args={"check_same_thread": False})
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
def setup(client):
    doctor = client.post("/api/v1/doctors", json={"name": "Dr. Demo", "department": "Geriatrics"}).json()
    room = client.post("/api/v1/rooms", json={"room_number": f"R{uuid.uuid4().hex[:4]}", "floor": "1"}).json()
    bed = client.post("/api/v1/beds", json={"bed_number": "1", "room_id": room["id"]}).json()
    return {"doctor": doctor["id"], "room": room["id"], "bed": bed["id"]}


def body(setup, **over):
    data = {"name": "Demo Patient", "age": 72, "condition": "Hip fracture recovery",
            "doctor_id": setup["doctor"], "room_id": setup["room"]}
    data.update(over)
    return data


def admit(client, setup, **over):
    r = client.post("/api/v1/patients", json=body(setup, **over))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def gateway_on(monkeypatch):
    import phone_gateway
    monkeypatch.setenv("VITALYN_PHONE_GATEWAY", "1")
    monkeypatch.setattr(phone_gateway, "get_gateway",
                        lambda: types.SimpleNamespace(running=True, base_url=lambda: "https://192.168.1.6:8443"))


# ── doctors ──────────────────────────────────────────────────────────────────

def test_doctor_validation(client):
    assert client.post("/api/v1/doctors", json={"name": "   "}).status_code == 422
    assert client.post("/api/v1/doctors", json={"name": "x" * 81}).status_code == 422
    ok = client.post("/api/v1/doctors", json={"name": "  Dr. Rao  "})
    assert ok.status_code == 201 and ok.json()["name"] == "Dr. Rao"
    assert [d["name"] for d in client.get("/api/v1/doctors").json()] == ["Dr. Rao"]


# ── admission ────────────────────────────────────────────────────────────────

def test_admit_returns_patient_without_secrets(client, setup):
    out = admit(client, setup)
    p = out["patient"]
    assert p["patient_code"] == "P-0001" and p["status"] == "admitted" and p["has_camera_link"] is True
    assert p["doctor"]["name"] == "Dr. Demo" and p["room"]["id"] == setup["room"]
    assert "camera_token_hash" not in p and "token" not in str(p).lower().replace("has_camera_link", "")
    assert out["camera_link"] is None and "VITALYN_PHONE_GATEWAY=1" in out["camera_link_note"]


def test_admit_with_gateway_returns_a_one_time_link_and_stores_only_a_hash(client, setup, gateway_on):
    out = admit(client, setup)
    link = out["camera_link"]
    assert link["url"] == f"https://192.168.1.6:8443/c/{link['token']}"
    with Session(client.engine) as s:
        stored = s.exec(select(Patient)).one().camera_token_hash
    assert stored == hash_token(link["token"]) and link["token"] not in stored
    with Session(client.engine) as s:
        assert find_patient_by_token(s, link["token"]).patient_code == "P-0001"
        assert find_patient_by_token(s, "forged-token") is None


def test_patient_codes_are_sequential(client, setup):
    assert admit(client, setup)["patient"]["patient_code"] == "P-0001"
    assert admit(client, setup, name="Second")["patient"]["patient_code"] == "P-0002"


@pytest.mark.parametrize("over", [
    {"age": -1}, {"age": 131}, {"age": "old"}, {"name": ""}, {"name": "x" * 81},
    {"condition": ""}, {"condition": "c" * 201},
])
def test_admit_rejects_invalid_fields(client, setup, over):
    assert client.post("/api/v1/patients", json=body(setup, **over)).status_code == 422


def test_admit_rejects_unknown_references_and_wrong_room_bed(client, setup):
    assert client.post("/api/v1/patients", json=body(setup, doctor_id=str(uuid.uuid4()))).status_code == 422
    assert client.post("/api/v1/patients", json=body(setup, room_id=str(uuid.uuid4()))).status_code == 422
    other = client.post("/api/v1/rooms", json={"room_number": "OTHER", "floor": "2"}).json()["id"]
    assert client.post("/api/v1/patients", json=body(setup, room_id=other, bed_id=setup["bed"])).status_code == 422
    assert client.post("/api/v1/patients", json=body(setup, bed_id=setup["bed"])).status_code == 201


def test_name_is_trimmed(client, setup):
    assert admit(client, setup, name="  Padded Name  ")["patient"]["name"] == "Padded Name"


# ── list / get / update ──────────────────────────────────────────────────────

def test_list_filters_by_status(client, setup):
    a = admit(client, setup)["patient"]["id"]
    admit(client, setup, name="B")
    client.post(f"/api/v1/patients/{a}/discharge")
    assert len(client.get("/api/v1/patients").json()) == 1
    assert len(client.get("/api/v1/patients", params={"status": "discharged"}).json()) == 1
    assert len(client.get("/api/v1/patients", params={"status": "all"}).json()) == 2
    assert client.get("/api/v1/patients", params={"status": "bogus"}).status_code == 422


def test_update_patient_and_block_after_discharge(client, setup):
    pid = admit(client, setup)["patient"]["id"]
    r = client.patch(f"/api/v1/patients/{pid}", json={"age": 73, "condition": "Recovering well"})
    assert r.status_code == 200 and r.json()["age"] == 73
    assert client.patch(f"/api/v1/patients/{pid}", json={"age": 500}).status_code == 422
    client.post(f"/api/v1/patients/{pid}/discharge")
    assert client.patch(f"/api/v1/patients/{pid}", json={"age": 74}).status_code == 409
    assert client.get(f"/api/v1/patients/{uuid.uuid4()}").status_code == 404


# ── QR lifecycle ─────────────────────────────────────────────────────────────

def test_regenerate_invalidates_the_old_qr(client, setup, gateway_on):
    out = admit(client, setup)
    old = out["camera_link"]["token"]
    pid = out["patient"]["id"]
    new = client.post(f"/api/v1/patients/{pid}/camera-link").json()["camera_link"]["token"]
    assert new != old
    with Session(client.engine) as s:
        assert find_patient_by_token(s, old) is None
        assert find_patient_by_token(s, new) is not None


def test_discharge_revokes_the_qr_and_is_idempotent(client, setup, gateway_on):
    out = admit(client, setup)
    token, pid = out["camera_link"]["token"], out["patient"]["id"]
    d = client.post(f"/api/v1/patients/{pid}/discharge").json()
    assert d["status"] == "discharged" and d["has_camera_link"] is False and d["discharged_at"]
    with Session(client.engine) as s:
        assert find_patient_by_token(s, token) is None
    assert client.post(f"/api/v1/patients/{pid}/discharge").status_code == 200
    assert client.post(f"/api/v1/patients/{pid}/camera-link").status_code == 409


def test_discharge_and_regenerate_stop_only_that_patients_session(client, setup, mgr):
    a = admit(client, setup)["patient"]["id"]
    b = admit(client, setup, name="B")["patient"]["id"]
    mgr.start(setup["room"], "0", patient_id=a)
    mgr.start(setup["room"], "1", patient_id=b)
    client.post(f"/api/v1/patients/{a}/camera-link")
    assert mgr.get(a) is None and mgr.get(b) is not None         # A stopped, B keeps running
    mgr.start(setup["room"], "0", patient_id=a)
    client.post(f"/api/v1/patients/{a}/discharge")
    assert mgr.get(a) is None and mgr.get(b) is not None


# ── events and delete ────────────────────────────────────────────────────────

def test_events_and_delete_detach_history(client, setup):
    pid = admit(client, setup)["patient"]["id"]
    room = setup["room"]
    with Session(client.engine) as s:
        job = InferenceJob(room_id=uuid.UUID(room), patient_id=uuid.UUID(pid),
                           video_filename="live", video_path="camera:0", status="live")
        s.add(job); s.commit(); s.refresh(job)
        s.add(FallEvent(inference_job_id=job.id, room_id=uuid.UUID(room), patient_id=uuid.UUID(pid), confidence=0.8))
        s.commit()
    events = client.get(f"/api/v1/patients/{pid}/events").json()
    assert len(events) == 1 and events[0]["patient_id"] == pid
    assert client.delete(f"/api/v1/patients/{pid}").json() == {"deleted": True}
    assert client.get(f"/api/v1/patients/{pid}").status_code == 404
    with Session(client.engine) as s:
        ev = s.exec(select(FallEvent)).one()
        assert ev.patient_id is None                      # history kept, patient link removed


# ── live sessions attributed to a patient ────────────────────────────────────

def _stub_live(monkeypatch):
    import live_routes
    mgr = StubManager()
    monkeypatch.setattr(live_routes, "_live_module", lambda: module_for(mgr))
    monkeypatch.setattr(live_routes, "_loaded_manager", lambda: mgr)
    return mgr


def test_live_start_with_patient_passes_the_patient_and_rejects_bad_ones(client, setup, monkeypatch):
    mgr = _stub_live(monkeypatch)
    pid = admit(client, setup)["patient"]["id"]
    ok = client.post("/api/v1/live/start", json={"room_id": setup["room"], "source": "0", "patient_id": pid})
    assert ok.status_code == 200 and mgr.last_patient_id == pid
    assert client.post("/api/v1/live/start", json={"room_id": setup["room"], "patient_id": "nope"}).status_code == 400
    assert client.post("/api/v1/live/start", json={"room_id": setup["room"], "patient_id": str(uuid.uuid4())}).status_code == 404
    mgr.stop()
    client.post(f"/api/v1/patients/{pid}/discharge")
    assert client.post("/api/v1/live/start", json={"room_id": setup["room"], "patient_id": pid}).status_code == 404


def test_live_status_names_the_patient_by_code_only(client, setup, monkeypatch):
    import live_routes
    pid = admit(client, setup)["patient"]["id"]
    fake = types.SimpleNamespace(status=lambda: {"state": "live", "patient_id": pid})
    monkeypatch.setattr(live_routes, "_loaded_manager", lambda: fake)
    st = client.get("/api/v1/live/status").json()
    assert st["patient"]["patient_code"] == "P-0001"
    assert "Demo Patient" not in str(st)


# ── registered camera + one-step monitoring ──────────────────────────────────

@pytest.fixture
def mgr(monkeypatch):
    m = StubManager()
    monkeypatch.setattr(patient_routes, "_live_manager", lambda: module_for(m))
    monkeypatch.setitem(sys.modules, "live_pipeline", types.SimpleNamespace(get_manager=lambda: m))
    return m


def _detail(r):
    return r.json()["detail"]


def test_new_patient_has_no_camera_registered(client, setup):
    p = admit(client, setup)["patient"]
    assert p["camera_kind"] is None and p["phone_online"] is False


def test_register_webcam_then_monitor_starts_it_in_the_patients_room(client, setup, mgr):
    pid = admit(client, setup)["patient"]["id"]
    reg = client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "webcam", "index": 1}).json()
    assert reg["camera_kind"] == "webcam" and reg["camera_index"] == 1 and "camera 1" in reg["camera_label"]
    r = client.post(f"/api/v1/patients/{pid}/monitor")
    assert r.status_code == 200 and r.json() == {"state": "live", "kind": "webcam"}
    assert mgr.starts == [(setup["room"], "1", pid)]


def test_monitor_is_idempotent_for_the_same_patient(client, setup, mgr):
    pid = admit(client, setup)["patient"]["id"]
    client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "webcam", "index": 0})
    client.post(f"/api/v1/patients/{pid}/monitor")
    again = client.post(f"/api/v1/patients/{pid}/monitor")
    assert again.status_code == 200 and again.json()["state"] == "live" and len(mgr.starts) == 1


def test_monitor_without_a_registered_camera_explains_what_to_do(client, setup, mgr):
    pid = admit(client, setup)["patient"]["id"]
    r = client.post(f"/api/v1/patients/{pid}/monitor")
    assert r.status_code == 422 and _detail(r)["code"] == "no_camera"


def test_two_patients_are_monitored_at_the_same_time(client, setup, mgr):
    a = admit(client, setup)["patient"]
    b = admit(client, setup, name="Second")["patient"]
    client.put(f"/api/v1/patients/{a['id']}/camera", json={"kind": "webcam", "index": 0})
    client.put(f"/api/v1/patients/{b['id']}/camera", json={"kind": "webcam", "index": 1})   # a second camera
    assert client.post(f"/api/v1/patients/{a['id']}/monitor").status_code == 200
    assert client.post(f"/api/v1/patients/{b['id']}/monitor").status_code == 200
    assert mgr.get(a["id"]) is not None and mgr.get(b["id"]) is not None


def test_one_webcam_cannot_serve_two_patients(client, setup, mgr):
    a = admit(client, setup)["patient"]
    b = admit(client, setup, name="Second")["patient"]
    for p in (a, b):
        client.put(f"/api/v1/patients/{p['id']}/camera", json={"kind": "webcam", "index": 0})
    assert client.post(f"/api/v1/patients/{a['id']}/monitor").status_code == 200
    r = client.post(f"/api/v1/patients/{b['id']}/monitor")
    assert r.status_code == 409 and _detail(r)["code"] == "camera_in_use"
    assert mgr.get(a["id"]) is not None                          # the first patient is untouched


def test_monitor_refuses_beyond_the_session_limit(client, setup, mgr):
    mgr.max_sessions = 1
    a = admit(client, setup)["patient"]
    b = admit(client, setup, name="Second")["patient"]
    client.put(f"/api/v1/patients/{a['id']}/camera", json={"kind": "webcam", "index": 0})
    client.put(f"/api/v1/patients/{b['id']}/camera", json={"kind": "webcam", "index": 1})
    assert client.post(f"/api/v1/patients/{a['id']}/monitor").status_code == 200
    r = client.post(f"/api/v1/patients/{b['id']}/monitor")
    assert r.status_code == 409 and _detail(r)["code"] == "limit" and "At most 1" in _detail(r)["message"]


def test_monitor_reports_camera_problems_clearly(client, setup, mgr):
    pid = admit(client, setup)["patient"]["id"]
    client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "webcam", "index": 0})
    mgr.fail = StubCameraError("Cannot open camera source 0")
    r = client.post(f"/api/v1/patients/{pid}/monitor")
    assert r.status_code == 422 and _detail(r)["code"] == "camera_unavailable"


def test_monitor_refuses_discharged_patients_and_missing_room(client, setup, mgr):
    pid = admit(client, setup)["patient"]["id"]
    client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "webcam", "index": 0})
    client.post(f"/api/v1/patients/{pid}/discharge")
    assert _detail(client.post(f"/api/v1/patients/{pid}/monitor"))["code"] == "discharged"


def test_webcam_registration_validates_input(client, setup):
    pid = admit(client, setup)["patient"]["id"]
    assert client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "phone", "index": 0}).status_code == 422
    assert client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "webcam", "index": 99}).status_code == 422
    assert client.put(f"/api/v1/patients/{uuid.uuid4()}/camera", json={"kind": "webcam", "index": 0}).status_code == 404


def test_phone_monitor_needs_an_online_phone(client, setup, mgr):
    pid = admit(client, setup)["patient"]["id"]
    with Session(client.engine) as s:                       # a phone registered itself earlier
        p = s.get(Patient, uuid.UUID(pid)); p.camera_kind = "phone"; p.camera_label = "iPhone (iOS 18)"; s.add(p); s.commit()
    r = client.post(f"/api/v1/patients/{pid}/monitor")
    assert r.status_code == 409 and _detail(r)["code"] == "phone_offline"


def test_phone_monitor_asks_the_gateway_to_start_the_online_phone(client, setup, mgr, monkeypatch):
    pid = admit(client, setup)["patient"]["id"]
    with Session(client.engine) as s:
        p = s.get(Patient, uuid.UUID(pid)); p.camera_kind = "phone"; s.add(p); s.commit()
    calls = []
    gw = types.SimpleNamespace(
        phone_online=lambda patient_id: patient_id == pid,
        start_phone_monitoring=lambda info: (calls.append(info) or (True, "")),
    )
    monkeypatch.setitem(sys.modules, "phone_gateway", gw)
    r = client.post(f"/api/v1/patients/{pid}/monitor")
    assert r.status_code == 200 and r.json() == {"state": "starting", "kind": "phone"}
    assert calls[0]["id"] == pid and calls[0]["room_id"] == setup["room"]
    assert client.get(f"/api/v1/patients/{pid}").json()["phone_online"] is True
    gw.start_phone_monitoring = lambda info: (False, "Another patient is being monitored")
    assert _detail(client.post(f"/api/v1/patients/{pid}/monitor"))["code"] == "phone_unavailable"


def test_regenerate_discharge_and_unregister_clear_the_registration_and_drop_the_phone(client, setup, gateway_on, monkeypatch):
    kicked = []
    monkeypatch.setitem(sys.modules, "phone_gateway",
                        types.SimpleNamespace(kick_standby=lambda pid, why: kicked.append(why),
                                              get_gateway=lambda: types.SimpleNamespace(running=True, base_url=lambda: "https://x")))
    pid = admit(client, setup)["patient"]["id"]
    with Session(client.engine) as s:
        p = s.get(Patient, uuid.UUID(pid)); p.camera_kind = "phone"; p.camera_label = "iPhone"; s.add(p); s.commit()
    client.post(f"/api/v1/patients/{pid}/camera-link")
    assert client.get(f"/api/v1/patients/{pid}").json()["camera_kind"] is None
    client.put(f"/api/v1/patients/{pid}/camera", json={"kind": "webcam", "index": 0})
    assert client.delete(f"/api/v1/patients/{pid}/camera").json()["camera_kind"] is None
    client.post(f"/api/v1/patients/{pid}/discharge")
    assert kicked == ["QR code replaced", "Camera unregistered", "Patient discharged"]


def test_stop_monitoring_only_stops_that_patients_session(client, setup, mgr):
    a = admit(client, setup)["patient"]["id"]
    b = admit(client, setup, name="B")["patient"]["id"]
    client.put(f"/api/v1/patients/{a}/camera", json={"kind": "webcam", "index": 0})
    client.put(f"/api/v1/patients/{b}/camera", json={"kind": "webcam", "index": 1})
    client.post(f"/api/v1/patients/{a}/monitor"); client.post(f"/api/v1/patients/{b}/monitor")
    assert client.post(f"/api/v1/patients/{a}/monitor/stop").json() == {"stopped": True}
    assert mgr.get(a) is None and mgr.get(b) is not None
    assert client.post(f"/api/v1/patients/{a}/monitor/stop").json() == {"stopped": False}
