"""
Patient admission and doctor endpoints.

DEMO DATA ONLY: patient details here must be fictional until real-patient use has
been authorised (see AGENTS.md). Names never appear in URLs, logs or QR codes: the
camera QR carries a random secret token whose SHA-256 hash is all the database keeps.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sys
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import adt
import audit
from auth import AuthUser, current_user, require_roles
from database import get_session
from permissions import ADMIN, CLINICAL, DOCTORS, REGISTRARS
from models import Bed, Doctor, FallEvent, InferenceJob, Patient, Room

log = logging.getLogger("vitalyn.patients")

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Dept = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class DoctorCreate(BaseModel):
    name: Name
    department: Optional[Dept] = None


class PatientCreate(BaseModel):
    name: Name
    age: int = Field(ge=0, le=130)
    condition: ShortText
    doctor_id: uuid.UUID
    room_id: uuid.UUID
    bed_id: Optional[uuid.UUID] = None
    sex: Optional[str] = Field(default=None, pattern="^(female|male|other)$")
    date_of_birth: Optional[date] = None
    phone: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]] = None
    emergency_contact: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]] = None
    allergies: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]] = None


class DischargeSummary(BaseModel):
    type: str = Field(default="home", pattern="^(home|transfer|ama|other)$")
    diagnosis: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]] = None
    instructions: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]] = None
    follow_up_date: Optional[date] = None


class CameraRegistration(BaseModel):
    kind: str = Field(pattern="^webcam$")             # phones register themselves by connecting
    index: int = Field(ge=0, le=9)


class PatientUpdate(BaseModel):
    name: Optional[Name] = None
    age: Optional[int] = Field(default=None, ge=0, le=130)
    condition: Optional[ShortText] = None
    doctor_id: Optional[uuid.UUID] = None
    room_id: Optional[uuid.UUID] = None
    bed_id: Optional[uuid.UUID] = None
    sex: Optional[str] = Field(default=None, pattern="^(female|male|other)$")
    date_of_birth: Optional[date] = None
    phone: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]] = None
    emergency_contact: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]] = None
    allergies: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]] = None


# ── token helpers ────────────────────────────────────────────────────────────

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_camera_token() -> tuple[str, str]:
    """(secret token for the QR, hash to store). 128 random bits."""
    token = secrets.token_urlsafe(16)
    return token, hash_token(token)


def camera_link_for(token: str) -> Optional[Dict[str, str]]:
    """The URL a phone opens, or None while the phone gateway is off."""
    if os.getenv("VITALYN_PHONE_GATEWAY") != "1":
        return None
    try:
        from phone_gateway import get_gateway
        base = get_gateway().base_url()
    except Exception:
        base = None
    return {"token": token, "url": f"{base}/c/{token}"} if base else None


def find_patient_by_token(session: Session, token: str) -> Optional[Patient]:
    """The admitted patient whose QR secret this is (constant-time hash comparison)."""
    digest = hash_token(token)
    patient = session.exec(select(Patient).where(Patient.camera_token_hash == digest)).first()
    if patient is None or patient.status != "admitted" or not patient.camera_token_hash:
        return None
    return patient if secrets.compare_digest(patient.camera_token_hash, digest) else None


def _gateway_module():
    """The phone gateway module if it is loaded (it is only imported when the gateway is enabled)."""
    return sys.modules.get("phone_gateway")


def _phone_online(patient_id: str) -> bool:
    gw = _gateway_module()
    fn = getattr(gw, "phone_online", None)
    return bool(fn(patient_id)) if fn else False


def _kick_phone(patient_id: str, reason: str) -> None:
    gw = _gateway_module()
    fn = getattr(gw, "kick_standby", None)
    if fn:
        try:
            fn(patient_id, reason)
        except Exception as exc:  # never let a dropped phone block a discharge
            log.warning("Could not disconnect phone for %s: %s", patient_id, exc)


def _clear_camera(patient: Patient) -> None:
    patient.camera_kind = None
    patient.camera_index = None
    patient.camera_label = None
    patient.camera_registered_at = None


def _stop_live_if_patient(patient_id: uuid.UUID) -> bool:
    """End this patient's live session (used on discharge/regenerate/delete). Others keep running."""
    mod = sys.modules.get("live_pipeline")
    getter = getattr(mod, "get_manager", None)
    if getter is None:
        return False
    manager = getter()
    if manager.get(str(patient_id)) is not None:
        manager.stop(patient_id=str(patient_id))
        return True
    return False


# ── serialisation ────────────────────────────────────────────────────────────

def _patient_out(session: Session, p: Patient) -> Dict[str, Any]:
    doctor = session.get(Doctor, p.doctor_id) if p.doctor_id else None
    room = session.get(Room, p.room_id) if p.room_id else None
    bed = session.get(Bed, p.bed_id) if p.bed_id else None
    return {
        "id": str(p.id),
        "patient_code": p.patient_code,
        "name": p.name,
        "age": p.age,
        "condition": p.condition,
        "doctor": {"id": str(doctor.id), "name": doctor.name} if doctor else None,
        "room": {"id": str(room.id), "room_number": room.room_number} if room else None,
        "bed_id": str(p.bed_id) if p.bed_id else None,
        "bed_number": bed.bed_number if bed else None,
        "sex": p.sex,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "phone": p.phone,
        "emergency_contact": p.emergency_contact,
        "allergies": p.allergies,
        "status": p.status,
        "admitted_at": p.admitted_at.isoformat() + ("Z" if p.admitted_at.tzinfo is None else ""),
        "discharged_at": (p.discharged_at.isoformat() + ("Z" if p.discharged_at.tzinfo is None else ""))
        if p.discharged_at else None,
        "has_camera_link": bool(p.camera_token_hash),
        "camera_kind": p.camera_kind,
        "camera_label": p.camera_label,
        "camera_index": p.camera_index,
        "camera_registered_at": (p.camera_registered_at.isoformat() + ("Z" if p.camera_registered_at.tzinfo is None else ""))
        if p.camera_registered_at else None,
        "phone_online": _phone_online(str(p.id)),
    }


def _next_patient_code(session: Session) -> str:
    codes = session.exec(select(Patient.patient_code)).all()
    highest = max((int(c[2:]) for c in codes if c.startswith("P-") and c[2:].isdigit()), default=0)
    return f"P-{highest + 1:04d}"


def _get_patient(session: Session, patient_id: uuid.UUID) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def _check_refs(session: Session, doctor_id, room_id, bed_id) -> None:
    if doctor_id is not None and session.get(Doctor, doctor_id) is None:
        raise HTTPException(status_code=422, detail="Doctor not found")
    if room_id is not None and session.get(Room, room_id) is None:
        raise HTTPException(status_code=422, detail="Room not found")
    if bed_id is not None:
        bed = session.get(Bed, bed_id)
        if bed is None:
            raise HTTPException(status_code=422, detail="Bed not found")
        if room_id is not None and bed.room_id != room_id:
            raise HTTPException(status_code=422, detail="Bed is not in the selected room")


# ── doctors ──────────────────────────────────────────────────────────────────

@router.get("/doctors")
def list_doctors(session: Session = Depends(get_session)):
    doctors = session.exec(select(Doctor).order_by(Doctor.name)).all()
    return [{"id": str(d.id), "name": d.name, "department": d.department} for d in doctors]


@router.post("/doctors", status_code=201)
def create_doctor(body: DoctorCreate, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*ADMIN))):
    doctor = Doctor(name=body.name, department=body.department)
    session.add(doctor)
    audit.record(session, user, "doctor.create", "doctor", doctor.id, doctor.name, request)
    session.commit()
    session.refresh(doctor)
    return {"id": str(doctor.id), "name": doctor.name, "department": doctor.department}


# ── patients ─────────────────────────────────────────────────────────────────

@router.get("/patients")
def list_patients(
    status: str = Query("admitted", pattern="^(admitted|discharged|outpatient|all)$"),
    q: Optional[str] = Query(None, max_length=80),
    session: Session = Depends(get_session),
):
    stmt = select(Patient).order_by(Patient.admitted_at.desc())
    if status != "all":
        stmt = stmt.where(Patient.status == status)
    if q and q.strip():
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"      # name, code or phone
        stmt = stmt.where(or_(Patient.name.ilike(like), Patient.patient_code.ilike(like), Patient.phone.ilike(like)))
    return [_patient_out(session, p) for p in session.exec(stmt).all()]


@router.post("/patients", status_code=201)
def admit_patient(body: PatientCreate, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*REGISTRARS))):
    _check_refs(session, body.doctor_id, body.room_id, body.bed_id)
    adt.ensure_bed_assignable(session, body.bed_id)
    token, token_hash = new_camera_token()
    patient = None
    for _ in range(3):                      # retry if two admissions pick the same code at once
        patient = Patient(
            patient_code=_next_patient_code(session),
            name=body.name, age=body.age, condition=body.condition,
            doctor_id=body.doctor_id, room_id=body.room_id, bed_id=body.bed_id,
            sex=body.sex, date_of_birth=body.date_of_birth, phone=body.phone,
            emergency_contact=body.emergency_contact, allergies=body.allergies,
            camera_token_hash=token_hash,
        )
        session.add(patient)
        try:
            session.commit()
            break
        except IntegrityError:
            session.rollback()
            patient = None
    if patient is None:
        raise HTTPException(status_code=409, detail="Could not allocate a patient code; try again")
    session.refresh(patient)
    adt.record_event(session, patient, "admitted", user, to_room=patient.room_id, to_bed=patient.bed_id)
    audit.record(session, user, "patient.admit", "patient", patient.id,
                 f"{patient.patient_code} room {body.room_id}", request)
    session.commit()
    link = camera_link_for(token)
    return {
        "patient": _patient_out(session, patient),
        # The QR secret is shown once. Regenerate it later if it is lost.
        "camera_link": link,
        "camera_link_note": None if link else "Phone gateway is off. Start the backend with VITALYN_PHONE_GATEWAY=1, then regenerate the QR.",
    }


@router.get("/patients/{patient_id}")
def get_patient(patient_id: uuid.UUID, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(current_user)):
    patient = _get_patient(session, patient_id)
    audit.record_view(session, user, "patient", patient.id, request)
    return _patient_out(session, patient)


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: uuid.UUID, body: PatientUpdate, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*REGISTRARS))):
    patient = _get_patient(session, patient_id)
    if patient.status == "discharged":
        raise HTTPException(status_code=409, detail="Discharged patients cannot be edited")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("room_id", patient.room_id) != patient.room_id or changes.get("bed_id", patient.bed_id) != patient.bed_id:
        raise HTTPException(status_code=422, detail="Use Transfer to move a patient to another room or bed")
    changes.pop("room_id", None)
    changes.pop("bed_id", None)
    _check_refs(session, changes.get("doctor_id"), patient.room_id, None)
    for key, value in changes.items():
        setattr(patient, key, value)
    session.add(patient)
    audit.record(session, user, "patient.update", "patient", patient.id, "fields: " + ", ".join(sorted(changes)), request)
    session.commit()
    session.refresh(patient)
    return _patient_out(session, patient)


@router.post("/patients/{patient_id}/camera-link")
def regenerate_camera_link(patient_id: uuid.UUID, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*CLINICAL))):
    """Issue a new QR secret. The previous QR stops working and any live session using it ends."""
    patient = _get_patient(session, patient_id)
    if patient.status != "admitted":
        raise HTTPException(status_code=409, detail="Discharged patients have no camera link")
    token, token_hash = new_camera_token()
    patient.camera_token_hash = token_hash
    if patient.camera_kind == "phone":
        _clear_camera(patient)                      # the old phone no longer holds a valid QR
    session.add(patient)
    audit.record(session, user, "patient.camera_link_regenerated", "patient", patient.id, None, request)
    session.commit()
    _stop_live_if_patient(patient.id)
    _kick_phone(str(patient.id), "QR code replaced")
    link = camera_link_for(token)
    return {
        "camera_link": link,
        "camera_link_note": None if link else "Phone gateway is off. Start the backend with VITALYN_PHONE_GATEWAY=1 and regenerate again.",
    }


@router.post("/patients/{patient_id}/discharge")
def discharge_patient(patient_id: uuid.UUID, request: Request, body: Optional[DischargeSummary] = None, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*DOCTORS))):
    patient = _get_patient(session, patient_id)
    if patient.status == "discharged":
        return _patient_out(session, patient)
    if patient.status == "outpatient":
        raise HTTPException(status_code=409, detail="Outpatients are not admitted, so there is nothing to discharge")
    patient.status = "discharged"
    patient.discharged_at = datetime.now(timezone.utc)
    patient.camera_token_hash = None            # the QR stops working immediately
    _clear_camera(patient)
    session.add(patient)
    if patient.bed_id:                          # the bed must be cleaned before the next patient
        bed = session.get(Bed, patient.bed_id)
        if bed is not None:
            bed.status = "cleaning"
            session.add(bed)
    summary = (body or DischargeSummary()).model_dump(mode="json")
    adt.record_event(session, patient, "discharged", user, from_room=patient.room_id, from_bed=patient.bed_id,
                     summary=summary)
    audit.record(session, user, "patient.discharge", "patient", patient.id, patient.patient_code, request)
    session.commit()
    _stop_live_if_patient(patient.id)
    _kick_phone(str(patient.id), "Patient discharged")
    session.refresh(patient)
    return _patient_out(session, patient)


@router.delete("/patients/{patient_id}")
def delete_patient(patient_id: uuid.UUID, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*ADMIN))):
    """Hard delete (demo cleanup / erasure). Fall events and jobs are kept but detached from the patient."""
    patient = _get_patient(session, patient_id)
    _stop_live_if_patient(patient.id)
    _kick_phone(str(patient.id), "Patient record deleted")
    for model in (FallEvent, InferenceJob):
        for row in session.exec(select(model).where(model.patient_id == patient.id)).all():
            row.patient_id = None
            session.add(row)
    session.delete(patient)
    audit.record(session, user, "patient.delete", "patient", patient.id, patient.patient_code, request)
    session.commit()
    return {"deleted": True}


@router.get("/patients/{patient_id}/events", dependencies=[Depends(require_roles(*CLINICAL))])
def patient_events(patient_id: uuid.UUID, session: Session = Depends(get_session)) -> List[FallEvent]:
    _get_patient(session, patient_id)
    return session.exec(
        select(FallEvent).where(FallEvent.patient_id == patient_id).order_by(FallEvent.created_at.desc())
    ).all()


# ── registered camera + one-step monitoring ──────────────────────────────────

@router.put("/patients/{patient_id}/camera")
def register_webcam(patient_id: uuid.UUID, body: CameraRegistration, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*CLINICAL))):
    """Register this Mac's webcam as the patient's camera (a phone registers itself by connecting)."""
    patient = _get_patient(session, patient_id)
    if patient.status != "admitted":
        raise HTTPException(status_code=409, detail="Discharged patients have no camera")
    if patient.camera_kind == "phone":
        _kick_phone(str(patient.id), "Camera replaced by the Mac webcam")
    patient.camera_kind = "webcam"
    patient.camera_index = body.index
    patient.camera_label = f"Mac webcam (camera {body.index})"
    patient.camera_registered_at = datetime.now(timezone.utc)
    session.add(patient)
    audit.record(session, user, "patient.camera_register", "patient", patient.id, patient.camera_label, request)
    session.commit()
    session.refresh(patient)
    return _patient_out(session, patient)


@router.delete("/patients/{patient_id}/camera")
def unregister_camera(patient_id: uuid.UUID, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*CLINICAL))):
    patient = _get_patient(session, patient_id)
    _stop_live_if_patient(patient.id)
    _kick_phone(str(patient.id), "Camera unregistered")
    _clear_camera(patient)
    session.add(patient)
    audit.record(session, user, "patient.camera_unregister", "patient", patient.id, None, request)
    session.commit()
    session.refresh(patient)
    return _patient_out(session, patient)


def _problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _live_manager():
    """The ML live manager (imports the heavy ML modules on first use)."""
    ml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml-engine")
    if ml_path not in sys.path:
        sys.path.insert(0, ml_path)
    import live_pipeline
    return live_pipeline


@router.post("/patients/{patient_id}/monitor")
def monitor_patient(patient_id: uuid.UUID, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*CLINICAL))):
    """
    Open live monitoring for this patient using the camera registered to them.
    Never stops another patient's session: that must be an explicit choice.
    """
    patient = _get_patient(session, patient_id)
    audit.record(session, user, "monitor.open", "patient", patient.id, patient.patient_code, request)
    session.commit()
    if patient.status != "admitted":
        raise _problem(409, "discharged", "This patient has been discharged.")
    if patient.room_id is None:
        raise _problem(422, "no_room", "Assign the patient to a room first.")
    if not patient.camera_kind:
        raise _problem(422, "no_camera", "No camera is registered for this patient. Choose the Mac webcam or pair a phone.")

    try:
        mod = _live_manager()
    except Exception as exc:
        raise _problem(503, "ml_unavailable", f"Live detection unavailable: {str(exc)[:120]}")
    manager = mod.get_manager()
    pid = str(patient.id)

    if manager.get(pid) is not None:
        return {"state": "live", "kind": patient.camera_kind}              # already monitoring: nothing to do

    if patient.camera_kind == "webcam":
        try:
            manager.start(str(patient.room_id), str(patient.camera_index or 0), patient_id=pid)
        except mod.CameraError as exc:
            raise _problem(422, "camera_unavailable", str(exc))
        except mod.SessionLimitError as exc:
            raise _problem(409, "limit", str(exc))
        except mod.CameraInUseError as exc:
            raise _problem(409, "camera_in_use", str(exc))
        except RuntimeError as exc:
            raise _problem(409, "busy", str(exc))
        return {"state": "live", "kind": "webcam"}

    # phone: it must be online in standby; the gateway then tells it to start its camera
    gw = _gateway_module()
    starter = getattr(gw, "start_phone_monitoring", None)
    if starter is None or not _phone_online(pid):
        raise _problem(409, "phone_offline",
                       "The registered phone is offline. Open the patient's camera link on the phone and leave the page open.")
    info = {"id": pid, "code": patient.patient_code, "room_id": str(patient.room_id), "room_number": ""}
    ok, message = starter(info)
    if not ok:
        raise _problem(409, "phone_unavailable", message)
    return {"state": "starting", "kind": "phone"}


@router.post("/patients/{patient_id}/monitor/stop")
def stop_monitoring(patient_id: uuid.UUID, request: Request, session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*CLINICAL))):
    patient = _get_patient(session, patient_id)
    stopped = _stop_live_if_patient(patient.id)
    audit.record(session, user, "monitor.stop", "patient", patient.id, patient.patient_code, request)
    session.commit()
    return {"stopped": stopped}
