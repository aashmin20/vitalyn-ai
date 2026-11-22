"""
Live camera endpoints.

  POST /api/v1/live/start    start a session on a camera/video source for a room
  POST /api/v1/live/stop     stop the running session
  GET  /api/v1/live/status   current state and counters
  GET  /api/v1/live/stream   MJPEG video with pose overlay
  GET  /api/v1/live/events   Server-Sent Events (fall_detected, status, heartbeat)

The ML engine is imported lazily so the backend still starts without ML deps.
Only one session runs at a time. Every fall event is a *potential* fall that a
human must verify.
"""
from __future__ import annotations

import ipaddress
import json
import re
import logging
import os
import queue
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urlparse
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from auth import require_roles
from database import get_session
from permissions import CLINICAL
from models import Room

log = logging.getLogger("vitalyn.live_routes")

ML_ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "ml-engine")

router = APIRouter(prefix="/api/v1/live", dependencies=[Depends(require_roles(*CLINICAL))])


def _live_module():
    """Import the ML live pipeline on demand (503 if ML deps are missing)."""
    try:
        if ML_ENGINE_PATH not in sys.path:
            sys.path.insert(0, ML_ENGINE_PATH)
        import live_pipeline
        return live_pipeline
    except Exception as exc:  # ImportError, torch/cv2 missing, ...
        log.error("Live pipeline unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=f"Live detection unavailable: {exc}")


def get_manager() -> Any:
    return _live_module().get_manager()


def _loaded_manager() -> Optional[Any]:
    """The live manager if the ML module is fully imported, else None.

    sys.modules can hold a *partially initialised* live_pipeline while the first
    start request is still importing torch/ultralytics, so check for the attribute.
    """
    mod = sys.modules.get("live_pipeline")
    getter = getattr(mod, "get_manager", None)
    return getter() if getter else None


def live_state() -> str:
    """Camera component for /health without forcing an ML import."""
    manager = _loaded_manager()
    return manager.status().get("state", "idle") if manager else "idle"


BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ALLOWED_DIRS = [
    os.path.join(BACKEND_DIR, "uploads"),
    os.path.abspath(os.path.join(BACKEND_DIR, "..", "datasets")),
]


def phone_gateway_enabled() -> bool:
    return os.getenv("VITALYN_PHONE_GATEWAY") == "1"


def _phone_registry():
    if ML_ENGINE_PATH not in sys.path:
        sys.path.insert(0, ML_ENGINE_PATH)
    from phone_source import get_registry
    return get_registry()


def urls_enabled() -> bool:
    return os.getenv("VITALYN_LIVE_ALLOW_URLS") == "1"


def _is_local_network_host(host: str) -> bool:
    """True only if every address the host resolves to is private/loopback/link-local.
    Keeps URL sources to phones/cameras on the LAN and blocks public hosts."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    addrs = {info[4][0].split("%")[0] for info in infos}
    if not addrs:
        return False
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            return False
    return True


_PHONE_RE = re.compile(r"iphone|ipad|android|phone", re.I)


def opencv_camera_order(names: list) -> list:
    """Order names the way OpenCV indexes them on macOS.

    macOS's camera list puts the built-in camera first, but OpenCV (AVFoundation)
    lists Continuity Camera phones first: on a MacBook Air with an iPhone connected,
    OpenCV index 0 was the iPhone and index 1 the FaceTime camera. That order is not
    guaranteed on every Mac, so the UI also offers an 'identify cameras' step.
    """
    phones = [n for n in names if _PHONE_RE.search(n)]
    others = [n for n in names if not _PHONE_RE.search(n)]
    return phones + others


_camera_cache: dict = {"at": 0.0, "names": None}


def list_camera_names() -> list:
    """Camera names the OS reports (macOS: system_profiler, no camera access needed).
    Index order follows the OS device order, which matches OpenCV's index on macOS in
    practice but is not guaranteed, so the UI labels these as 'camera N'."""
    now = time.time()
    if _camera_cache["names"] is not None and now - _camera_cache["at"] < 10:
        return _camera_cache["names"]
    names: list = []
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["system_profiler", "SPCameraDataType", "-json"],
                capture_output=True, text=True, timeout=8,
            ).stdout
            names = [c.get("_name", "Camera") for c in json.loads(out).get("SPCameraDataType", [])]
        except Exception as exc:
            log.warning("Could not list cameras: %s", exc)
    _camera_cache.update(at=now, names=names)
    return names


def validate_source(raw: str) -> str:
    """
    Only accept sources the operator intended:
      * a camera index ("0", "1", ...)
      * a video file inside an allowed folder (backend/uploads, datasets/, or
        VITALYN_LIVE_ALLOWED_DIRS, os.pathsep-separated)
      * an rtsp:// or http(s):// stream, only if VITALYN_LIVE_ALLOW_URLS=1
    The API has no authentication, so arbitrary paths/URLs would let any client
    make the server read local files or probe the network.
    """
    value = (raw or "").strip()
    if value.isdigit():
        return value
    if value.startswith("phone:"):
        if _phone_registry().get(value[len("phone:"):]) is None:
            raise HTTPException(status_code=422, detail="Phone link not found or expired. Create a new phone link.")
        return value
    if "://" in value:
        if not urls_enabled():
            raise HTTPException(
                status_code=422,
                detail="Phone/IP camera URLs are disabled. Start the backend with VITALYN_LIVE_ALLOW_URLS=1 to enable them.",
            )
        parsed = urlparse(value)
        if parsed.scheme.lower() not in ("rtsp", "http", "https") or not parsed.hostname:
            raise HTTPException(status_code=422, detail="Only rtsp://, http:// or https:// camera URLs are supported.")
        if not _is_local_network_host(parsed.hostname):
            raise HTTPException(
                status_code=422,
                detail="Camera URL must point to a device on your local network (private IP or .local name).",
            )
        return value
    allowed = list(DEFAULT_ALLOWED_DIRS)
    allowed += [d for d in os.getenv("VITALYN_LIVE_ALLOWED_DIRS", "").split(os.pathsep) if d]
    real = os.path.realpath(value)
    for root in allowed:
        root_real = os.path.realpath(root)
        if real == root_real or real.startswith(root_real + os.sep):
            if os.path.isfile(real):
                return real
            raise HTTPException(status_code=422, detail=f"Video file not found: {value}")
    raise HTTPException(
        status_code=422,
        detail="Source must be a camera index (e.g. 0) or a video inside backend/uploads or datasets/.",
    )


class StartRequest(BaseModel):
    room_id: str
    patient_id: Optional[str] = None     # attribute the session (and its alerts) to an admitted patient
    source: str = "0"      # webcam index, file path, or rtsp/http URL


@router.get("/sources")
def live_sources():
    """What the Live Camera page can offer: OS-reported cameras and whether URLs are enabled."""
    names = opencv_camera_order(list_camera_names()) or ["Default camera"]
    return {
        "cameras": [{"index": i, "label": n} for i, n in enumerate(names)],
        "urls_enabled": urls_enabled(),
        "phone_link_enabled": phone_gateway_enabled(),
    }


@router.post("/phone-link")
def create_phone_link():
    """Create a one-session link the phone opens to stream its camera to this Mac."""
    if not phone_gateway_enabled():
        raise HTTPException(
            status_code=422,
            detail="Phone links are off. Restart the backend with VITALYN_PHONE_GATEWAY=1 to enable them.",
        )
    from phone_gateway import get_gateway
    gateway = get_gateway()
    if not gateway.running:
        raise HTTPException(status_code=503, detail="Phone gateway is not running. Check the backend log.")
    registry = _phone_registry()
    source = registry.create()
    return {
        "token": source.token,
        "url": f"{gateway.base_url()}/p/{source.token}",
        "expires_in": registry.expires_in(source.token),
    }


@router.get("/phone-link/{token}")
def phone_link_status(token: str):
    registry = _phone_registry()
    source = registry.get(token)
    if source is None:
        return {"exists": False, "connected": False}
    age = source.age_s()
    return {
        "exists": True,
        "connected": source.connected,
        "frames": source.frames_received,
        "last_frame_age_s": None if age is None else round(age, 1),
        "expires_in": registry.expires_in(token),
    }


@router.delete("/phone-link/{token}")
def delete_phone_link(token: str):
    _phone_registry().remove(token)
    return {"deleted": True}


@router.get("/snapshot")
def live_snapshot(index: int = Query(0, ge=0, le=9)):
    """One still frame from camera `index` so the user can see which camera is which.
    Not stored. Unavailable while a live session is using the camera."""
    mod = _live_module()
    if any(getattr(sess, "source", None) == index for sess in mod.get_manager().running_sessions()):
        raise HTTPException(status_code=409, detail="That camera is in use. Stop its session before previewing it.")
    try:
        jpeg = mod.grab_snapshot(index)
    except mod.CameraError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/start")
def start_live(req: StartRequest, session: Session = Depends(get_session)):
    try:
        room_uuid = uuid.UUID(req.room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room_id format")
    if session.get(Room, room_uuid) is None:
        raise HTTPException(status_code=404, detail="Room not found")

    patient_id = None
    if req.patient_id:
        try:
            pid = uuid.UUID(req.patient_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
        from models import Patient
        patient = session.get(Patient, pid)
        if patient is None or patient.status != "admitted":
            raise HTTPException(status_code=404, detail="Admitted patient not found")
        patient_id = str(pid)
    source = validate_source(req.source)
    mod = _live_module()
    try:
        live = mod.get_manager().start(str(room_uuid), source, patient_id=patient_id)
    except RuntimeError as exc:
        if isinstance(exc, mod.CameraError):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=409, detail=str(exc))
    return live.status()


@router.post("/stop")
def stop_live(patient_id: Optional[str] = None):
    """Stop one patient's session (?patient_id=...) or, with no patient given, every running session."""
    manager = get_manager()
    stopped = manager.stop(patient_id=patient_id) if patient_id else manager.stop()
    return {"stopped": stopped, **manager.status()}


def _enrich(session: Session, status: dict) -> dict:
    pid = status.get("patient_id")
    if pid:
        from models import Patient, Room
        try:
            patient = session.get(Patient, uuid.UUID(pid))
        except ValueError:
            patient = None
        if patient is not None:
            room = session.get(Room, patient.room_id) if patient.room_id else None
            status["patient"] = {"patient_code": patient.patient_code,
                                 "room_number": room.room_number if room else None}
    return status


@router.get("/status")
def live_status(session: Session = Depends(get_session)):
    manager = _loaded_manager()
    status = manager.status() if manager else {"state": "idle", "sessions": []}
    # Staff need to know who is being monitored, but the name stays out of this feed.
    _enrich(session, status)
    for item in status.get("sessions", []):
        _enrich(session, item)
    return status


def _mjpeg(live):
    last_id = 0
    while live.running:
        jpeg, fid = live.next_jpeg(last_id, timeout=1.0)
        if jpeg is None or fid == last_id:
            continue
        last_id = fid
        yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
               + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")


@router.get("/stream")
def live_stream(patient_id: Optional[str] = None):
    """MJPEG for one patient's session (?patient_id=...); with none given, the most recent session."""
    manager = get_manager()
    live = manager.get(patient_id) if patient_id else manager.session
    if live is None or not live.running:
        raise HTTPException(status_code=409, detail="No live session is running for that patient")
    return StreamingResponse(
        _mjpeg(live),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


def _sse(manager):
    """Server-Sent Events for EVERY monitored patient: a fall alarm must reach the dashboard
    whichever patient is on screen. Each message carries `patient_id`."""
    q = manager.subscribe()
    try:
        yield f"data: {json.dumps({'type': 'status', **manager.status()})}\n\n"
        while True:
            try:
                msg = q.get(timeout=15)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {json.dumps(msg)}\n\n"
    finally:
        manager.unsubscribe(q)


@router.get("/events")
def live_events():
    return StreamingResponse(
        _sse(get_manager()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
