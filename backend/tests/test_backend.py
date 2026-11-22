"""
Test cases for VITALYN backend database models and API endpoints.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine
from datetime import datetime, timezone
import uuid

from models import BaseModel, Room, Bed, InferenceJob, OccupancyRecord, FallEvent, Alert, User
from database import get_session
from main import app

# Test database setup
DATABASE_URL = "sqlite:///./test_vitalyn.db"
engine = create_engine(DATABASE_URL)

def override_get_session():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_session] = override_get_session

@pytest.fixture(scope="module")
def client():
    BaseModel.metadata.create_all(engine)
    client = TestClient(app)
    yield client
    BaseModel.metadata.drop_all(engine)

@pytest.fixture
def session():
    with Session(engine) as session:
        yield session

# Database Model Tests
def test_room_model():
    room_data = {
        "room_number": "101",
        "floor": "2",
        "status": "active"
    }
    
    room = Room(**room_data)
    assert room.room_number == "101"
    assert room.floor == "2"
    assert room.status == "active"
    assert isinstance(room.id, uuid.UUID)

def test_bed_model():
    bed_data = {
        "bed_number": "B01",
        "room_id": uuid.uuid4(),
        "status": "active"
    }
    
    bed = Bed(**bed_data)
    assert bed.bed_number == "B01"
    assert bed.status == "active"
    assert isinstance(bed.id, uuid.UUID)

def test_inference_job_model():
    job_data = {
        "room_id": uuid.uuid4(),
        "video_filename": "test_video.mp4",
        "video_path": "/tmp/test_video.mp4",
        "status": "queued",
        "progress": 0.0
    }
    
    job = InferenceJob(**job_data)
    assert job.video_filename == "test_video.mp4"
    assert job.status == "queued"
    assert job.progress == 0.0
    assert isinstance(job.id, uuid.UUID)

def test_occupancy_record_model():
    record_data = {
        "bed_id": uuid.uuid4(),
        "inference_job_id": uuid.uuid4(),
        "occupancy_status": "occupied",
        "confidence": 0.95
    }
    
    record = OccupancyRecord(**record_data)
    assert record.occupancy_status == "occupied"
    assert record.confidence == 0.95
    assert isinstance(record.id, uuid.UUID)

def test_fall_event_model():
    event_data = {
        "inference_job_id": uuid.uuid4(),
        "room_id": uuid.uuid4(),
        "bed_id": uuid.uuid4(),
        "event_type": "potential_fall",
        "confidence": 0.88,
        "status": "active"
    }
    
    event = FallEvent(**event_data)
    assert event.event_type == "potential_fall"
    assert event.confidence == 0.88
    assert event.status == "active"
    assert isinstance(event.id, uuid.UUID)

def test_alert_model():
    alert_data = {
        "fall_event_id": uuid.uuid4(),
        "alert_type": "fall",
        "severity": "high",
        "status": "active"
    }
    
    alert = Alert(**alert_data)
    assert alert.alert_type == "fall"
    assert alert.severity == "high"
    assert alert.status == "active"
    assert isinstance(alert.id, uuid.UUID)

def test_user_model():
    user_data = {
        "name": "Test User",
        "email": "test@example.com",
        "password_hash": "hashed_password",
        "role": "operator"
    }
    
    user = User(**user_data)
    assert user.name == "Test User"
    assert user.email == "test@example.com"
    assert user.role == "operator"
    assert isinstance(user.id, uuid.UUID)

# API Endpoint Tests

def test_health_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data

def test_detailed_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"].startswith("SQLite")
    assert "components" in data

def test_create_and_list_rooms(client):
    room_data = {
        "room_number": "201",
        "floor": "2",
        "status": "active"
    }
    
    response = client.post("/api/v1/rooms", json=room_data)
    assert response.status_code == 200
    created_room = response.json()
    assert created_room["room_number"] == "201"
    assert created_room["floor"] == "2"
    assert "id" in created_room
    
    list_response = client.get("/api/v1/rooms")
    assert list_response.status_code == 200
    rooms = list_response.json()
    assert len(rooms) >= 1
    assert any(room["room_number"] == "201" for room in rooms)

def test_create_and_get_room(client):
    room_data = {
        "room_number": "202",
        "floor": "3",
        "status": "active"
    }
    
    create_response = client.post("/api/v1/rooms", json=room_data)
    assert create_response.status_code == 200
    created_room = create_response.json()
    room_id = created_room["id"]
    
    get_response = client.get(f"/api/v1/rooms/{room_id}")
    assert get_response.status_code == 200
    retrieved_room = get_response.json()
    assert retrieved_room["room_number"] == "202"
    assert retrieved_room["id"] == room_id

def test_create_and_list_beds(client):
    room_data = {
        "room_number": "303",
        "floor": "3",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    bed_data = {
        "bed_number": "B01",
        "room_id": room_id,
        "status": "active"
    }
    
    create_bed_response = client.post("/api/v1/beds", json=bed_data)
    assert create_bed_response.status_code == 200
    created_bed = create_bed_response.json()
    assert created_bed["bed_number"] == "B01"
    assert created_bed["room_id"] == room_id
    assert "id" in created_bed
    
    list_beds_response = client.get("/api/v1/beds")
    assert list_beds_response.status_code == 200
    beds = list_beds_response.json()
    assert len(beds) >= 1
    assert any(bed["bed_number"] == "B01" for bed in beds)

def test_create_and_get_bed(client):
    room_data = {
        "room_number": "404",
        "floor": "4",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    bed_data = {
        "bed_number": "B02",
        "room_id": room_id,
        "status": "active"
    }
    
    create_bed_response = client.post("/api/v1/beds", json=bed_data)
    assert create_bed_response.status_code == 200
    created_bed = create_bed_response.json()
    bed_id = created_bed["id"]
    
    get_bed_response = client.get(f"/api/v1/beds/{bed_id}")
    assert get_bed_response.status_code == 200
    retrieved_bed = get_bed_response.json()
    assert retrieved_bed["bed_number"] == "B02"
    assert retrieved_bed["id"] == bed_id

def test_create_and_list_inference_jobs(client):
    room_data = {
        "room_number": "505",
        "floor": "5",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    job_data = {
        "room_id": room_id,
        "video_filename": "test_video.mp4",
        "video_path": "/tmp/test_video.mp4",
        "status": "queued",
        "progress": 0.0
    }
    
    create_job_response = client.post("/api/v1/jobs", json=job_data)
    assert create_job_response.status_code == 200
    created_job = create_job_response.json()
    assert created_job["video_filename"] == "test_video.mp4"
    assert created_job["status"] == "queued"
    assert "id" in created_job
    
    list_jobs_response = client.get("/api/v1/jobs")
    assert list_jobs_response.status_code == 200
    jobs = list_jobs_response.json()
    assert len(jobs) >= 1
    assert any(job["video_filename"] == "test_video.mp4" for job in jobs)

def test_create_and_get_job(client):
    room_data = {
        "room_number": "606",
        "floor": "6",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    job_data = {
        "room_id": room_id,
        "video_filename": "test_video2.mp4",
        "video_path": "/tmp/test_video2.mp4",
        "status": "queued",
        "progress": 0.0
    }
    
    create_job_response = client.post("/api/v1/jobs", json=job_data)
    assert create_job_response.status_code == 200
    created_job = create_job_response.json()
    job_id = created_job["id"]
    
    get_job_response = client.get(f"/api/v1/jobs/{job_id}")
    assert get_job_response.status_code == 200
    retrieved_job = get_job_response.json()
    assert retrieved_job["video_filename"] == "test_video2.mp4"
    assert retrieved_job["id"] == job_id

def test_create_occupancy_record(client):
    room_data = {
        "room_number": "707",
        "floor": "7",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    bed_data = {
        "bed_number": "B03",
        "room_id": room_id,
        "status": "active"
    }
    
    create_bed_response = client.post("/api/v1/beds", json=bed_data)
    assert create_bed_response.status_code == 200
    bed = create_bed_response.json()
    bed_id = bed["id"]
    
    job_data = {
        "room_id": room_id,
        "video_filename": "test_video3.mp4",
        "video_path": "/tmp/test_video3.mp4",
        "status": "queued",
        "progress": 0.0
    }
    
    create_job_response = client.post("/api/v1/jobs", json=job_data)
    assert create_job_response.status_code == 200
    job = create_job_response.json()
    job_id = job["id"]
    
    record_data = {
        "bed_id": bed_id,
        "inference_job_id": job_id,
        "occupancy_status": "occupied",
        "confidence": 0.95
    }
    
    create_response = client.post("/api/v1/occupancy/records", json=record_data)
    assert create_response.status_code == 200
    created_record = create_response.json()
    assert created_record["occupancy_status"] == "occupied"
    assert created_record["confidence"] == 0.95
    assert "id" in created_record
    
    get_response = client.get("/api/v1/occupancy/current")
    assert get_response.status_code == 200
    current_occupancy = get_response.json()
    assert len(current_occupancy) >= 1
    assert any(record["bed_number"] == "B03" for record in current_occupancy)

def test_create_and_list_fall_events(client):
    room_data = {
        "room_number": "808",
        "floor": "8",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    job_data = {
        "room_id": room_id,
        "video_filename": "test_video4.mp4",
        "video_path": "/tmp/test_video4.mp4",
        "status": "queued",
        "progress": 0.0
    }
    
    create_job_response = client.post("/api/v1/jobs", json=job_data)
    assert create_job_response.status_code == 200
    job = create_job_response.json()
    job_id = job["id"]
    
    event_data = {
        "inference_job_id": job_id,
        "room_id": room_id,
        "bed_id": str(uuid.uuid4()),
        "event_type": "potential_fall",
        "confidence": 0.88,
        "status": "active"
    }
    
    create_response = client.post("/api/v1/events/falls", json=event_data)
    assert create_response.status_code == 200
    created_event = create_response.json()
    assert created_event["event_type"] == "potential_fall"
    assert created_event["confidence"] == 0.88
    assert "id" in created_event
    
    list_response = client.get("/api/v1/events/falls")
    assert list_response.status_code == 200
    events = list_response.json()
    assert len(events) >= 1
    assert any(event["event_type"] == "potential_fall" for event in events)

def test_create_and_list_alerts(client):
    room_data = {
        "room_number": "909",
        "floor": "9",
        "status": "active"
    }
    
    create_room_response = client.post("/api/v1/rooms", json=room_data)
    assert create_room_response.status_code == 200
    room = create_room_response.json()
    room_id = room["id"]
    
    job_data = {
        "room_id": room_id,
        "video_filename": "test_video5.mp4",
        "video_path": "/tmp/test_video5.mp4",
        "status": "queued",
        "progress": 0.0
    }
    
    create_job_response = client.post("/api/v1/jobs", json=job_data)
    assert create_job_response.status_code == 200
    job = create_job_response.json()
    job_id = job["id"]
    
    event_data = {
        "inference_job_id": job_id,
        "room_id": room_id,
        "bed_id": str(uuid.uuid4()),
        "event_type": "potential_fall",
        "confidence": 0.88,
        "status": "active"
    }
    
    create_event_response = client.post("/api/v1/events/falls", json=event_data)
    assert create_event_response.status_code == 200
    event = create_event_response.json()
    event_id = event["id"]
    
    alert_data = {
        "fall_event_id": event_id,
        "alert_type": "fall",
        "severity": "high",
        "status": "active"
    }
    
    create_response = client.post("/api/v1/alerts", json=alert_data)
    assert create_response.status_code == 200
    created_alert = create_response.json()
    assert created_alert["alert_type"] == "fall"
    assert created_alert["severity"] == "high"
    assert "id" in created_alert
    
    list_response = client.get("/api/v1/alerts")
    assert list_response.status_code == 200
    alerts = list_response.json()
    assert len(alerts) >= 1
    assert any(alert["alert_type"] == "fall" for alert in alerts)

def test_dashboard_overview(client):
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_beds" in data
    assert "occupied_beds" in data
    assert "vacant_beds" in data
    assert "occupied_percentage" in data
    assert "active_fall_events" in data

def test_dashboard_occupancy_trends(client):
    response = client.get("/api/v1/dashboard/occupancy-trends")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_dashboard_event_summary(client):
    response = client.get("/api/v1/dashboard/event-summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_events" in data
    assert "active_events" in data
    assert "acknowledged_events" in data
    assert "resolved_events" in data

# Lifecycle sync between alerts and fall events

def _make_event_with_alert(client, room_number):
    room = client.post("/api/v1/rooms", json={"room_number": room_number, "floor": "1"}).json()
    job = client.post("/api/v1/jobs", json={
        "room_id": room["id"], "video_filename": "t.mp4", "video_path": "/tmp/t.mp4",
    }).json()
    event = client.post("/api/v1/events/falls", json={
        "inference_job_id": job["id"], "room_id": room["id"],
        "confidence": 0.9, "status": "active",
    }).json()
    alert = client.post("/api/v1/alerts", json={
        "fall_event_id": event["id"], "alert_type": "potential_fall", "severity": "high",
    }).json()
    return event["id"], alert["id"]


def test_acknowledge_alert_updates_fall_event(client):
    event_id, alert_id = _make_event_with_alert(client, "L01")
    op = str(uuid.uuid4())
    r = client.patch(f"/api/v1/alerts/{alert_id}/acknowledge", params={"acknowledged_by": op})
    assert r.status_code == 200
    assert client.get(f"/api/v1/events/falls/{event_id}").json()["status"] == "acknowledged"


def test_resolve_alert_resolves_fall_event(client):
    event_id, alert_id = _make_event_with_alert(client, "L02")
    op = str(uuid.uuid4())
    client.patch(f"/api/v1/alerts/{alert_id}/acknowledge", params={"acknowledged_by": op})
    client.patch(f"/api/v1/alerts/{alert_id}/resolve", params={"resolved_by": op})
    ev = client.get(f"/api/v1/events/falls/{event_id}").json()
    assert ev["status"] == "resolved"
    assert ev["resolved_at"] is not None


def test_resolve_fall_event_resolves_its_alerts(client):
    event_id, alert_id = _make_event_with_alert(client, "L03")
    client.patch(f"/api/v1/events/falls/{event_id}/resolve", params={"resolved_by": str(uuid.uuid4())})
    assert client.get(f"/api/v1/alerts/{alert_id}").json()["status"] == "resolved"


def test_occupancy_timestamps_are_utc_with_z(client):
    room = client.post("/api/v1/rooms", json={"room_number": "L04", "floor": "1"}).json()
    bed = client.post("/api/v1/beds", json={"bed_number": "1", "room_id": room["id"]}).json()
    client.post("/api/v1/occupancy/records", json={
        "bed_id": bed["id"], "occupancy_status": "occupied", "confidence": 0.9,
    })
    current = client.get("/api/v1/occupancy/current").json()
    assert current and all(c["observed_at"].endswith("Z") for c in current)
    trends = client.get("/api/v1/dashboard/occupancy-trends").json()
    assert trends and all(t["observed_at"].endswith("Z") for t in trends)


def test_health_reports_real_components(client):
    data = client.get("/health").json()
    assert data["components"]["database"] == "ok"
    assert data["components"]["fall_model"] in ("ok", "missing")
    assert data["status"] in ("healthy", "degraded")


# Live camera routes (ML pipeline replaced by a stub)

from stubs import StubManager, StubCameraError as _StubCameraError, module_for


@pytest.fixture
def stub_live(monkeypatch):
    import live_routes
    mgr = StubManager()
    monkeypatch.setattr(live_routes, "_live_module", lambda: module_for(mgr))
    monkeypatch.setattr(live_routes, "_loaded_manager", lambda: mgr)
    return mgr


def _room(client, number):
    return client.post("/api/v1/rooms", json={"room_number": number, "floor": "1"}).json()["id"]


def test_live_start_validates_room(client, stub_live):
    assert client.post("/api/v1/live/start", json={"room_id": "nope"}).status_code == 400
    assert client.post("/api/v1/live/start", json={"room_id": str(uuid.uuid4())}).status_code == 404


def test_live_start_stop_and_conflict(client, stub_live):
    room_id = _room(client, "LV1")
    ok = client.post("/api/v1/live/start", json={"room_id": room_id, "source": "0"})
    assert ok.status_code == 200 and ok.json()["state"] == "live"
    again = client.post("/api/v1/live/start", json={"room_id": room_id})
    assert again.status_code == 409
    assert client.post("/api/v1/live/stop").json()["stopped"] is True


def test_live_start_camera_error_is_422(client, stub_live):
    stub_live.fail = _StubCameraError("Cannot open camera source 0")
    room_id = _room(client, "LV2")
    r = client.post("/api/v1/live/start", json={"room_id": room_id})
    assert r.status_code == 422 and "Cannot open camera" in r.json()["detail"]


def test_live_stream_requires_a_running_session_for_that_patient(client, stub_live):
    assert client.get("/api/v1/live/stream").status_code == 409
    assert client.get("/api/v1/live/stream", params={"patient_id": "nobody"}).status_code == 409


def test_live_stream_serves_mjpeg_for_the_requested_patient(client, stub_live):
    stub_live.start("room", "0", patient_id="A")
    stub_live.start("room2", "1", patient_id="B")
    r = client.get("/api/v1/live/stream", params={"patient_id": "A"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert b"image/jpeg" in r.content and b"stubjpeg" in r.content
    assert stub_live.get("A") is None and stub_live.get("B") is not None      # only A's stream was consumed


def test_live_events_is_one_global_feed(stub_live):
    import json
    import live_routes
    resp = live_routes.live_events()
    assert resp.media_type == "text/event-stream"
    gen = live_routes._sse(stub_live)
    first = next(gen)
    assert first.startswith("data: ") and json.loads(first[6:])["type"] == "status"
    stub_live.subscribers[0].put({"type": "fall_detected", "patient_id": "A", "confidence": 0.9})
    stub_live.subscribers[0].put({"type": "fall_detected", "patient_id": "B", "confidence": 0.8})
    seen = [json.loads(next(gen)[6:])["patient_id"] for _ in range(2)]
    assert seen == ["A", "B"]                                  # alarms from every patient on one feed
    gen.close()
    assert stub_live.subscribers == []                         # unsubscribed on disconnect


def test_live_snapshot_returns_jpeg_and_blocks_only_that_camera(client, stub_live):
    r = client.get("/api/v1/live/snapshot", params={"index": 1})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content.endswith(b"1")
    assert client.get("/api/v1/live/snapshot", params={"index": 99}).status_code == 422
    stub_live.start("room", "0", patient_id="A")               # camera 0 is now in use
    assert client.get("/api/v1/live/snapshot", params={"index": 0}).status_code == 409
    assert client.get("/api/v1/live/snapshot", params={"index": 1}).status_code == 200


def test_stop_can_target_one_patient_or_everyone(client, stub_live):
    stub_live.start("r1", "0", patient_id="A")
    stub_live.start("r2", "1", patient_id="B")
    assert client.post("/api/v1/live/stop", params={"patient_id": "A"}).json()["stopped"] is True
    assert stub_live.get("A") is None and stub_live.get("B") is not None
    assert client.post("/api/v1/live/stop").json()["stopped"] is True
    assert stub_live.running_sessions() == []


def test_live_status_lists_every_running_session(client, stub_live):
    stub_live.start("r1", "0", patient_id="A")
    stub_live.start("r2", "1", patient_id="B")
    st = client.get("/api/v1/live/status").json()
    assert st["state"] == "live" and {x["patient_id"] for x in st["sessions"]} == {"A", "B"}


# Live source validation

def test_validate_source_accepts_camera_index():
    from live_routes import validate_source
    assert validate_source(" 0 ") == "0"


def test_validate_source_rejects_paths_outside_allowed_dirs(tmp_path):
    from fastapi import HTTPException
    from live_routes import validate_source
    f = tmp_path / "x.mp4"
    f.write_bytes(b"x")
    with pytest.raises(HTTPException) as e:
        validate_source(str(f))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_source("/etc/passwd")


def test_validate_source_allows_configured_dir(tmp_path, monkeypatch):
    from live_routes import validate_source
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    monkeypatch.setenv("VITALYN_LIVE_ALLOWED_DIRS", str(tmp_path))
    assert validate_source(str(f)) == os.path.realpath(str(f))


def test_validate_source_blocks_traversal(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from live_routes import validate_source
    monkeypatch.setenv("VITALYN_LIVE_ALLOWED_DIRS", str(tmp_path))
    with pytest.raises(HTTPException):
        validate_source(str(tmp_path) + "/../../etc/passwd")


def test_validate_source_urls_disabled_by_default(monkeypatch):
    from fastapi import HTTPException
    from live_routes import validate_source
    monkeypatch.delenv("VITALYN_LIVE_ALLOW_URLS", raising=False)
    with pytest.raises(HTTPException):
        validate_source("rtsp://10.0.0.5/stream")
    monkeypatch.setenv("VITALYN_LIVE_ALLOW_URLS", "1")
    assert validate_source("rtsp://10.0.0.5/stream").startswith("rtsp://")
    with pytest.raises(HTTPException):
        validate_source("file:///etc/passwd")


def test_validate_source_urls_must_be_on_local_network(monkeypatch):
    from fastapi import HTTPException
    from live_routes import validate_source
    monkeypatch.setenv("VITALYN_LIVE_ALLOW_URLS", "1")
    assert validate_source("http://192.168.1.20:8080/video").startswith("http://")
    assert validate_source("rtsp://10.0.0.7:554/live").startswith("rtsp://")
    for bad in ("http://8.8.8.8/stream", "rtsp://1.1.1.1/x", "http://does-not-exist.invalid/v"):
        with pytest.raises(HTTPException) as e:
            validate_source(bad)
        assert e.value.status_code == 422


def test_live_sources_endpoint(client, monkeypatch):
    import live_routes
    monkeypatch.setattr(live_routes, "list_camera_names", lambda: ["FaceTime HD Camera", "iPhone Camera"])
    monkeypatch.delenv("VITALYN_LIVE_ALLOW_URLS", raising=False)
    data = client.get("/api/v1/live/sources").json()
    assert data["cameras"] == [
        {"index": 0, "label": "iPhone Camera"},          # OpenCV lists phones first
        {"index": 1, "label": "FaceTime HD Camera"},
    ]
    assert data["urls_enabled"] is False
    monkeypatch.setenv("VITALYN_LIVE_ALLOW_URLS", "1")
    assert client.get("/api/v1/live/sources").json()["urls_enabled"] is True


def test_live_sources_falls_back_when_no_names(client, monkeypatch):
    import live_routes
    monkeypatch.setattr(live_routes, "list_camera_names", lambda: [])
    assert client.get("/api/v1/live/sources").json()["cameras"] == [{"index": 0, "label": "Default camera"}]


def test_opencv_camera_order_puts_phone_first():
    from live_routes import opencv_camera_order
    assert opencv_camera_order(["FaceTime HD Camera", "Someone's iPhone Camera"]) == [
        "Someone's iPhone Camera", "FaceTime HD Camera",
    ]
    assert opencv_camera_order(["FaceTime HD Camera"]) == ["FaceTime HD Camera"]
    assert opencv_camera_order([]) == []


def test_live_sources_uses_opencv_order(client, monkeypatch):
    import live_routes
    monkeypatch.setattr(live_routes, "list_camera_names", lambda: ["FaceTime HD Camera", "iPhone Camera"])
    cams = client.get("/api/v1/live/sources").json()["cameras"]
    assert cams[0] == {"index": 0, "label": "iPhone Camera"}
    assert cams[1] == {"index": 1, "label": "FaceTime HD Camera"}


# Phone camera gateway

@pytest.fixture
def phone_registry(monkeypatch):
    import phone_gateway  # noqa: F401  (puts ml-engine on sys.path)
    import phone_source
    reg = phone_source.PhoneRegistry()
    monkeypatch.setattr(phone_source, "_registry", reg)
    return reg


def _jpeg_bytes():
    import cv2
    import numpy as np
    ok, buf = cv2.imencode(".jpg", np.full((48, 64, 3), 120, dtype=np.uint8))
    return buf.tobytes()


def test_gateway_page_requires_valid_token(phone_registry):
    from phone_gateway import gateway_app
    c = TestClient(gateway_app)
    assert c.get("/p/unknown-token").status_code == 404
    token = phone_registry.create().token
    page = c.get(f"/p/{token}")
    assert page.status_code == 200 and token in page.text and "getUserMedia" in page.text


def test_gateway_websocket_streams_frames_into_source(phone_registry):
    from phone_gateway import gateway_app
    src = phone_registry.create()
    c = TestClient(gateway_app)
    with c.websocket_connect(f"/p/{src.token}/ws") as ws:
        ws.send_bytes(_jpeg_bytes())
        ws.send_bytes(_jpeg_bytes())
        ws.send_bytes(b"garbage")                 # ignored, does not break the stream
        assert src.connected
    assert src.frames_received == 2 and src.connected is False


def test_gateway_websocket_rejects_unknown_token_and_second_phone(phone_registry):
    from starlette.websockets import WebSocketDisconnect
    from phone_gateway import gateway_app
    c = TestClient(gateway_app)
    with c.websocket_connect("/p/nope/ws") as ws:           # accepted, then closed with a reason the page can show
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4404
    src = phone_registry.create()
    with c.websocket_connect(f"/p/{src.token}/ws"):
        with c.websocket_connect(f"/p/{src.token}/ws") as second:
            with pytest.raises(WebSocketDisconnect) as e2:
                second.receive_text()
        assert e2.value.code == 4409


def test_gateway_tells_phone_when_session_ended(phone_registry):
    from phone_gateway import gateway_app
    src = phone_registry.create()
    c = TestClient(gateway_app)
    with c.websocket_connect(f"/p/{src.token}/ws") as ws:
        src.close()
        ws.send_bytes(_jpeg_bytes())
        assert ws.receive_text() == "ended"


def test_ensure_cert_creates_and_reuses(tmp_path):
    from phone_gateway import ensure_cert
    cert, key = ensure_cert("192.168.1.50", str(tmp_path))
    first = open(cert, "rb").read()
    assert oct(os.stat(key).st_mode & 0o777) == "0o600"
    assert ensure_cert("192.168.1.50", str(tmp_path)) == (cert, key)
    assert open(cert, "rb").read() == first                       # reused
    ensure_cert("192.168.1.77", str(tmp_path))                    # new LAN address -> regenerated
    assert open(cert, "rb").read() != first


def test_phone_link_api_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("VITALYN_PHONE_GATEWAY", raising=False)
    r = client.post("/api/v1/live/phone-link")
    assert r.status_code == 422 and "VITALYN_PHONE_GATEWAY=1" in r.json()["detail"]
    assert client.get("/api/v1/live/sources").json()["phone_link_enabled"] is False


def test_phone_link_api_create_status_delete(client, monkeypatch, phone_registry):
    import types
    import phone_gateway
    monkeypatch.setenv("VITALYN_PHONE_GATEWAY", "1")
    fake_gw = types.SimpleNamespace(running=True, base_url=lambda: "https://192.168.1.6:8443")
    monkeypatch.setattr(phone_gateway, "get_gateway", lambda: fake_gw)
    link = client.post("/api/v1/live/phone-link").json()
    assert link["url"] == f"https://192.168.1.6:8443/p/{link['token']}" and link["expires_in"] > 0
    st = client.get(f"/api/v1/live/phone-link/{link['token']}").json()
    assert st == {**st, "exists": True, "connected": False, "frames": 0}
    assert client.delete(f"/api/v1/live/phone-link/{link['token']}").json() == {"deleted": True}
    assert client.get(f"/api/v1/live/phone-link/{link['token']}").json()["exists"] is False


def test_validate_source_accepts_only_live_phone_links(phone_registry):
    from fastapi import HTTPException
    from live_routes import validate_source
    token = phone_registry.create().token
    assert validate_source(f"phone:{token}") == f"phone:{token}"
    with pytest.raises(HTTPException) as e:
        validate_source("phone:forged-token")
    assert e.value.status_code == 422


def test_cert_is_a_valid_ios_server_certificate(tmp_path):
    from cryptography import x509
    from phone_gateway import ensure_cert
    cert_path, _ = ensure_cert("192.168.1.50", str(tmp_path))
    cert = x509.load_pem_x509_certificate(open(cert_path, "rb").read())
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in eku
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature is True
    assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days <= 398   # Apple's maximum


def test_old_cert_without_server_auth_is_replaced(tmp_path):
    import datetime
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from phone_gateway import ensure_cert
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "old")])
    now = datetime.datetime.now(datetime.timezone.utc)
    old = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
           .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=365))
           .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("192.168.1.50"))]), False)
           .sign(key, hashes.SHA256()))
    (tmp_path / "phone-gateway.crt").write_bytes(old.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "phone-gateway.key").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    before = (tmp_path / "phone-gateway.crt").read_bytes()
    ensure_cert("192.168.1.50", str(tmp_path))
    assert (tmp_path / "phone-gateway.crt").read_bytes() != before
