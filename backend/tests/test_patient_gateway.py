"""Patient camera QR: standby protocol, registration, staff-initiated start, one patient at a time."""
import sys
import threading
import time
import types
import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from starlette.websockets import WebSocketDisconnect

import main  # noqa: F401  (creates the tables in the throwaway test database)
import phone_gateway
from phone_gateway import gateway_app, start_phone_monitoring, kick_standby, phone_online
from stubs import StubManager
from database import engine
from models import Doctor, Patient, Room
from patient_routes import new_camera_token

IPHONE = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) AppleWebKit/605.1.15"}


def jpeg():
    ok, buf = cv2.imencode(".jpg", np.full((48, 64, 3), 120, dtype=np.uint8))
    return buf.tobytes()


@pytest.fixture
def env(monkeypatch):
    import phone_source
    reg = phone_source.PhoneRegistry()
    monkeypatch.setattr(phone_source, "_registry", reg)
    mgr = StubManager(registry=reg)
    monkeypatch.setitem(sys.modules, "live_pipeline", types.SimpleNamespace(get_manager=lambda: mgr))
    phone_gateway._patient_sources.clear()
    phone_gateway._grace_timers.clear()
    phone_gateway._standby.clear()
    monkeypatch.setattr(phone_gateway, "DISCONNECT_GRACE_S", 0.3)
    return types.SimpleNamespace(registry=reg, manager=mgr, client=TestClient(gateway_app))


def make_patient(code="P-0001", name="Secret Name", with_room=True, status="admitted"):
    token, token_hash = new_camera_token()
    with Session(engine) as s:
        room = Room(room_number=f"R{uuid.uuid4().hex[:4]}", floor="1")
        doctor = Doctor(name="Dr. Demo")
        s.add(room); s.add(doctor); s.commit(); s.refresh(room); s.refresh(doctor)
        p = Patient(patient_code=f"{code}-{uuid.uuid4().hex[:4]}", name=name, age=70, condition="demo",
                    doctor_id=doctor.id, room_id=room.id if with_room else None,
                    status=status, camera_token_hash=token_hash)
        s.add(p); s.commit(); s.refresh(p)
        return {"token": token, "id": str(p.id), "code": p.patient_code,
                "room_id": str(room.id), "room": room.room_number}


def connect(env, p, headers=IPHONE):
    """Open the phone socket and consume the initial standby/live message."""
    return env.client.websocket_connect(f"/c/{p['token']}/ws", headers=headers)


def patient_row(pid):
    with Session(engine) as s:
        return s.get(Patient, uuid.UUID(pid))


def info(p):
    return {"id": p["id"], "code": p["code"], "room_id": p["room_id"], "room_number": p["room"]}


# ── page and token checks ────────────────────────────────────────────────────

def test_page_shows_code_and_room_but_never_the_name(env):
    p = make_patient(name="Jane Secretname")
    page = env.client.get(f"/c/{p['token']}")
    assert page.status_code == 200
    assert p["code"] in page.text and p["room"] in page.text and "Jane Secretname" not in page.text
    assert f"/c/{p['token']}/ws" in page.text and "standby" in page.text


def test_page_rejects_unknown_revoked_and_discharged(env):
    assert env.client.get("/c/forged").status_code == 404
    assert env.client.get(f"/c/{make_patient(status='discharged')['token']}").status_code == 404


def test_invalid_qr_is_refused_with_close_code_4404(env):
    with env.client.websocket_connect("/c/forged/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4404 and env.manager.starts == []


# ── standby + registration ───────────────────────────────────────────────────

def test_connecting_puts_the_phone_in_standby_and_registers_it_to_the_patient(env):
    p = make_patient()
    assert patient_row(p["id"]).camera_kind is None
    with connect(env, p) as ws:
        assert ws.receive_text() == "standby"
        assert phone_online(p["id"]) is True
        row = patient_row(p["id"])
        assert row.camera_kind == "phone" and row.camera_label == "iPhone (iOS 18)" and row.camera_registered_at
    assert phone_online(p["id"]) is False
    assert patient_row(p["id"]).camera_kind == "phone"            # registration outlives the connection
    assert env.manager.starts == []                                # connecting alone never starts monitoring


def test_registration_time_is_kept_when_the_phone_reconnects(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text()
    first = patient_row(p["id"]).camera_registered_at
    with connect(env, p) as ws:
        ws.receive_text()
    assert patient_row(p["id"]).camera_registered_at == first


def test_two_phones_for_one_patient_is_refused(env):
    p = make_patient()
    with connect(env, p) as first:
        first.receive_text()
        with connect(env, p) as dup:
            with pytest.raises(WebSocketDisconnect) as e:
                dup.receive_text()
    assert e.value.code == 4409 and "already connected" in e.value.reason


# ── the user taps Start on the phone ─────────────────────────────────────────

def test_start_request_begins_monitoring_for_that_patient_and_room(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text()
        ws.send_text("start_request")
        ws.send_bytes(jpeg()); ws.send_bytes(jpeg())
        time.sleep(0.3)
    room_id, source, patient_id = env.manager.starts[0]
    assert (room_id, patient_id) == (p["room_id"], p["id"]) and source.startswith("phone:")
    assert p["token"] not in source                       # the QR secret is not the source token


def test_frames_before_a_session_exists_are_ignored(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text()
        ws.send_bytes(jpeg())
    assert env.manager.starts == [] and env.registry._sources == {}


def test_two_patients_can_stream_at_the_same_time(env):
    a, b = make_patient(), make_patient(code="P-0002")
    with connect(env, a) as first:
        first.receive_text(); first.send_text("start_request"); time.sleep(0.2)
        with connect(env, b) as second:
            second.receive_text(); second.send_text("start_request"); time.sleep(0.2)
            assert env.manager.get(a["id"]) is not None and env.manager.get(b["id"]) is not None
    assert len(env.manager.starts) == 2


def test_start_request_is_refused_when_the_camera_limit_is_reached(env):
    env.manager.max_sessions = 1
    a, b = make_patient(), make_patient(code="P-0002")
    with connect(env, a) as first:
        first.receive_text(); first.send_text("start_request"); time.sleep(0.2)
        with connect(env, b) as second:
            second.receive_text()
            second.send_text("start_request")
            msg = second.receive_text()
    assert msg.startswith("busy:") and "At most 1" in msg
    assert len(env.manager.starts) == 1


def test_start_request_without_a_room_is_refused(env):
    p = make_patient(with_room=False)
    with connect(env, p) as ws:
        ws.receive_text(); ws.send_text("start_request")
        assert "no room" in ws.receive_text()


def test_start_failure_is_reported_and_leaves_no_dangling_link(env):
    p = make_patient()
    env.manager.start = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("camera busy"))
    with connect(env, p) as ws:
        ws.receive_text(); ws.send_text("start_request")
        assert "Could not start" in ws.receive_text()
    assert env.registry._sources == {}


# ── staff start it from the dashboard ────────────────────────────────────────

def test_staff_start_tells_the_standby_phone_to_start_and_frames_flow(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text()                                              # standby
        ok, message = start_phone_monitoring(info(p))                  # what POST /monitor does
        assert ok and message == ""
        assert ws.receive_text() == "start"
        ws.send_bytes(jpeg()); ws.send_bytes(jpeg())
        time.sleep(0.3)
    room_id, source, patient_id = env.manager.starts[0]
    assert (room_id, patient_id) == (p["room_id"], p["id"])
    assert env.registry.get(source[len("phone:"):]) is not None


def test_staff_start_when_the_phone_is_offline_says_so(env):
    p = make_patient()
    ok, message = start_phone_monitoring(info(p))
    assert ok is False and "offline" in message


def test_staff_start_is_refused_when_the_camera_limit_is_reached(env):
    env.manager.max_sessions = 1
    a, b = make_patient(), make_patient(code="P-0002")
    with connect(env, a) as first:
        first.receive_text(); first.send_text("start_request"); time.sleep(0.2)
        with connect(env, b) as second:
            second.receive_text()
            ok, message = start_phone_monitoring(info(b))
    assert ok is False and "At most 1" in message


def test_phone_returns_to_standby_when_monitoring_stops_and_can_start_again(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text()
        assert start_phone_monitoring(info(p))[0] and ws.receive_text() == "start"
        env.manager.stop()                                             # staff press Stop monitoring
        assert ws.receive_text() == "stop"                             # phone told to switch its camera off
        assert phone_online(p["id"]) is True                           # still connected, in standby
        assert start_phone_monitoring(info(p))[0] and ws.receive_text() == "start"      # again, no re-scan
    assert len(env.manager.starts) == 2


# ── drops, grace period, revocation ──────────────────────────────────────────

def test_session_stops_after_grace_if_the_phone_does_not_return(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text(); ws.send_text("start_request"); time.sleep(0.2)
    assert env.manager.stops == []
    time.sleep(0.8)
    assert env.manager.stops == [p["id"]]


def test_reconnecting_within_grace_resumes_the_same_session(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text(); ws.send_text("start_request"); time.sleep(0.2)
    with connect(env, p) as ws:
        assert ws.receive_text() == "live"                             # re-attached, camera should resume
        time.sleep(0.6)                                                # longer than the grace period
    assert len(env.manager.starts) == 1 and env.manager.stops == []


def test_kicking_the_phone_closes_it_with_a_reason(env):
    p = make_patient()
    with connect(env, p) as ws:
        ws.receive_text()
        assert kick_standby(p["id"], "QR code replaced") is True
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4404 and e.value.reason == "QR code replaced"
    assert kick_standby(p["id"], "again") is False


def test_device_labels():
    f = phone_gateway._device_label
    assert f("Mozilla/5.0 (iPhone; CPU iPhone OS 26_6_1 like Mac OS X)") == "iPhone (iOS 26)"
    assert f("Mozilla/5.0 (Linux; Android 14; Pixel 8)") == "Android phone (14)"
    assert f("Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X)") == "iPad (iPadOS 17)"
    assert f("") == "Phone browser"
