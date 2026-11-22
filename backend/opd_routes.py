"""
Outpatient department (OPD): registering outpatients, doctor schedules, appointment slots and the
appointment status workflow. DEMO DATA ONLY (see AGENTS.md).

Appointment and schedule times are the hospital's wall-clock time (no timezone), because a clinic's
hours are local. The server's clock is used to refuse booking the past.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import adt
import audit
from auth import AuthUser, current_user, require_roles
from database import get_session
from models import Appointment, Doctor, DoctorSchedule, Patient
from patient_routes import (
    _check_refs, _get_patient, _next_patient_code, _patient_out, camera_link_for, new_camera_token,
)
from permissions import DOCTORS, FRONT_DESK, REGISTRARS

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]

INACTIVE = ("cancelled", "no_show")          # these free the slot
# current status -> {next status: roles allowed}. Everything else is an illegal transition.
TRANSITIONS: Dict[str, Dict[str, tuple]] = {
    "scheduled": {"checked_in": FRONT_DESK, "cancelled": FRONT_DESK, "no_show": FRONT_DESK},
    "checked_in": {"in_consult": DOCTORS, "cancelled": FRONT_DESK, "no_show": FRONT_DESK},
    "in_consult": {"completed": DOCTORS},
    "completed": {},
    "cancelled": {},
    "no_show": {},
}


def now_local() -> datetime:
    """Hospital wall-clock 'now' (patched in tests)."""
    return datetime.now().replace(microsecond=0)


class OutpatientCreate(BaseModel):
    name: Name
    age: int = Field(ge=0, le=130)
    reason: Optional[Short] = None
    sex: Optional[str] = Field(default=None, pattern="^(female|male|other)$")
    date_of_birth: Optional[date] = None
    phone: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]] = None
    emergency_contact: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]] = None
    allergies: Optional[Short] = None


class AdmitOutpatient(BaseModel):
    doctor_id: uuid.UUID
    room_id: uuid.UUID
    bed_id: Optional[uuid.UUID] = None
    condition: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]] = None


class ScheduleBlock(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    slot_minutes: int = Field(default=15, ge=5, le=120)


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    start_at: datetime
    reason: Optional[Short] = None


class AppointmentChange(BaseModel):
    status: str = Field(pattern="^(checked_in|in_consult|completed|cancelled|no_show)$")


def _t(value: str) -> time:
    return time(int(value[:2]), int(value[3:]))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.replace(tzinfo=None).isoformat(timespec="minutes") if dt else None


# ── outpatients ──────────────────────────────────────────────────────────────

@router.post("/patients/register", status_code=201)
def register_outpatient(body: OutpatientCreate, request: Request, session: Session = Depends(get_session),
                        user: AuthUser = Depends(require_roles(*REGISTRARS))):
    """Create a patient record without admitting them: no room, no bed, no camera."""
    patient = None
    for _ in range(3):
        patient = Patient(
            patient_code=_next_patient_code(session), name=body.name, age=body.age,
            condition=body.reason or "Outpatient", status="outpatient",
            sex=body.sex, date_of_birth=body.date_of_birth, phone=body.phone,
            emergency_contact=body.emergency_contact, allergies=body.allergies,
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
    audit.record(session, user, "patient.register", "patient", patient.id, patient.patient_code, request)
    session.commit()
    return _patient_out(session, patient)


@router.post("/patients/{patient_id}/admit", status_code=201)
def admit_outpatient(patient_id: uuid.UUID, body: AdmitOutpatient, request: Request,
                     session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*REGISTRARS))):
    """Convert a registered outpatient into an admitted inpatient."""
    patient = _get_patient(session, patient_id)
    if patient.status != "outpatient":
        raise HTTPException(status_code=409, detail="Only registered outpatients can be admitted this way")
    _check_refs(session, body.doctor_id, body.room_id, body.bed_id)
    adt.ensure_bed_assignable(session, body.bed_id)
    token, token_hash = new_camera_token()
    patient.status = "admitted"
    patient.doctor_id, patient.room_id, patient.bed_id = body.doctor_id, body.room_id, body.bed_id
    if body.condition:
        patient.condition = body.condition
    patient.camera_token_hash = token_hash
    session.add(patient)
    adt.record_event(session, patient, "admitted", user, to_room=body.room_id, to_bed=body.bed_id)
    audit.record(session, user, "patient.admit", "patient", patient.id, patient.patient_code, request)
    session.commit()
    session.refresh(patient)
    link = camera_link_for(token)
    return {
        "patient": _patient_out(session, patient),
        "camera_link": link,
        "camera_link_note": None if link else "Phone gateway is off. Start the backend with VITALYN_PHONE_GATEWAY=1, then regenerate the QR.",
    }


# ── doctor schedules ─────────────────────────────────────────────────────────

def _doctor(session: Session, doctor_id: uuid.UUID) -> Doctor:
    doctor = session.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


def _blocks(session: Session, doctor_id: uuid.UUID) -> List[DoctorSchedule]:
    return list(session.exec(select(DoctorSchedule).where(DoctorSchedule.doctor_id == doctor_id)
                             .order_by(DoctorSchedule.weekday, DoctorSchedule.start_time)).all())


def _block_out(b: DoctorSchedule) -> Dict[str, Any]:
    return {"weekday": b.weekday, "start": b.start_time, "end": b.end_time, "slot_minutes": b.slot_minutes}


@router.get("/doctors/{doctor_id}/schedule")
def get_schedule(doctor_id: uuid.UUID, session: Session = Depends(get_session)):
    _doctor(session, doctor_id)
    return [_block_out(b) for b in _blocks(session, doctor_id)]


@router.put("/doctors/{doctor_id}/schedule")
def put_schedule(doctor_id: uuid.UUID, blocks: List[ScheduleBlock], request: Request,
                 session: Session = Depends(get_session), user: AuthUser = Depends(require_roles(*DOCTORS))):
    """Replace a doctor's weekly clinic hours. Administrators edit anyone's; a doctor only their own."""
    doctor = _doctor(session, doctor_id)
    if user.role != "admin" and (doctor.user_id is None or doctor.user_id != user.uuid):
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "You can only edit your own schedule."})
    if len(blocks) > 28:
        raise HTTPException(status_code=422, detail="Too many schedule blocks")
    ordered = sorted(blocks, key=lambda b: (b.weekday, b.start))
    for b in ordered:
        span = (datetime.combine(date.min, _t(b.end)) - datetime.combine(date.min, _t(b.start))).total_seconds() / 60
        if span <= 0:
            raise HTTPException(status_code=422, detail="Each block must end after it starts")
        if span < b.slot_minutes:
            raise HTTPException(status_code=422, detail="A block must fit at least one slot")
    for a, b in zip(ordered, ordered[1:]):
        if a.weekday == b.weekday and b.start < a.end:
            raise HTTPException(status_code=422, detail="Schedule blocks on the same day must not overlap")
    for old in _blocks(session, doctor_id):
        session.delete(old)
    for b in ordered:
        session.add(DoctorSchedule(doctor_id=doctor_id, weekday=b.weekday, start_time=b.start,
                                   end_time=b.end, slot_minutes=b.slot_minutes))
    audit.record(session, user, "schedule.update", "doctor", doctor_id, f"{len(ordered)} blocks", request)
    session.commit()
    return [_block_out(b) for b in _blocks(session, doctor_id)]


def _day_slots(session: Session, doctor_id: uuid.UUID, day: date) -> List[tuple]:
    slots = []
    for b in _blocks(session, doctor_id):
        if b.weekday != day.weekday():
            continue
        cur = datetime.combine(day, _t(b.start_time))
        end = datetime.combine(day, _t(b.end_time))
        step = timedelta(minutes=b.slot_minutes)
        while cur + step <= end:
            slots.append((cur, cur + step))
            cur += step
    return slots


def _busy(session: Session, doctor_id: uuid.UUID, start: datetime, end: datetime,
          exclude: Optional[uuid.UUID] = None) -> bool:
    stmt = select(Appointment).where(Appointment.doctor_id == doctor_id, Appointment.status.not_in(INACTIVE),
                                     Appointment.start_at < end, Appointment.end_at > start)
    if exclude is not None:
        stmt = stmt.where(Appointment.id != exclude)
    return session.exec(stmt).first() is not None


@router.get("/doctors/{doctor_id}/availability")
def availability(doctor_id: uuid.UUID, day: date = Query(..., alias="date"), session: Session = Depends(get_session)):
    _doctor(session, doctor_id)
    now = now_local()
    return [
        {"start": _iso(s), "end": _iso(e), "free": e > now and not _busy(session, doctor_id, s, e)}
        for s, e in _day_slots(session, doctor_id, day)
    ]


# ── appointments ─────────────────────────────────────────────────────────────

def _appointment_out(session: Session, a: Appointment) -> Dict[str, Any]:
    patient = session.get(Patient, a.patient_id) if a.patient_id else None
    doctor = session.get(Doctor, a.doctor_id) if a.doctor_id else None
    return {
        "id": str(a.id),
        "start_at": _iso(a.start_at), "end_at": _iso(a.end_at),
        "status": a.status, "reason": a.reason,
        "patient": {"id": str(patient.id), "patient_code": patient.patient_code, "name": patient.name, "age": patient.age,
                    "status": patient.status} if patient else None,
        "doctor": {"id": str(doctor.id), "name": doctor.name, "department": doctor.department} if doctor else None,
    }


@router.post("/appointments", status_code=201)
def book_appointment(body: AppointmentCreate, request: Request, session: Session = Depends(get_session),
                     user: AuthUser = Depends(require_roles(*FRONT_DESK))):
    patient = _get_patient(session, body.patient_id)
    _doctor(session, body.doctor_id)
    start = body.start_at.replace(tzinfo=None, second=0, microsecond=0)
    slot = next(((s, e) for s, e in _day_slots(session, body.doctor_id, start.date()) if s == start), None)
    if slot is None:
        raise HTTPException(status_code=422, detail="That time is not a slot in the doctor's schedule")
    if slot[1] <= now_local():
        raise HTTPException(status_code=422, detail="That slot is in the past")
    if _busy(session, body.doctor_id, *slot):
        raise HTTPException(status_code=409, detail="That slot is already booked")
    clash = session.exec(select(Appointment).where(
        Appointment.patient_id == patient.id, Appointment.status.not_in(INACTIVE),
        Appointment.start_at < slot[1], Appointment.end_at > slot[0])).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail="The patient already has an appointment at that time")
    appt = Appointment(patient_id=patient.id, doctor_id=body.doctor_id, start_at=slot[0], end_at=slot[1],
                       reason=body.reason or None, created_by=user.uuid)
    session.add(appt)
    audit.record(session, user, "appointment.book", "appointment", appt.id, _iso(slot[0]), request)
    session.commit()
    session.refresh(appt)
    return _appointment_out(session, appt)


@router.get("/appointments")
def list_appointments(
    day: Optional[date] = Query(None, alias="date"),
    doctor_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    status: Optional[str] = Query(None, pattern="^(scheduled|checked_in|in_consult|completed|cancelled|no_show)$"),
    session: Session = Depends(get_session),
):
    stmt = select(Appointment).order_by(Appointment.start_at)
    if day:
        stmt = stmt.where(Appointment.start_at >= datetime.combine(day, time.min),
                          Appointment.start_at < datetime.combine(day, time.min) + timedelta(days=1))
    if doctor_id:
        stmt = stmt.where(Appointment.doctor_id == doctor_id)
    if patient_id:
        stmt = stmt.where(Appointment.patient_id == patient_id)
    if status:
        stmt = stmt.where(Appointment.status == status)
    return [_appointment_out(session, a) for a in session.exec(stmt.limit(500)).all()]


@router.patch("/appointments/{appointment_id}")
def change_appointment(appointment_id: uuid.UUID, body: AppointmentChange, request: Request,
                       session: Session = Depends(get_session), user: AuthUser = Depends(current_user)):
    appt = session.get(Appointment, appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    allowed = TRANSITIONS[appt.status].get(body.status)
    if allowed is None:
        raise HTTPException(status_code=409, detail=f"An appointment that is {appt.status} cannot become {body.status}")
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": f"Your role ({user.role}) cannot do this."})
    if body.status in ("in_consult", "completed") and user.role != "admin":
        doctor = session.get(Doctor, appt.doctor_id) if appt.doctor_id else None
        if doctor is None or doctor.user_id is None or doctor.user_id != user.uuid:
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Only the appointment's own doctor can do this."})
    appt.status = body.status
    session.add(appt)
    audit.record(session, user, "appointment.status", "appointment", appt.id, body.status, request)
    session.commit()
    session.refresh(appt)
    return _appointment_out(session, appt)
