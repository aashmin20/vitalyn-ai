"""
Admission, transfer and discharge workflow: transfers, re-admission, patient timeline,
bed status and the ward board. DEMO DATA ONLY (see AGENTS.md).
"""
from __future__ import annotations

import json
import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlmodel import Session, select

import adt
import audit
from auth import AuthUser, current_user, require_roles
from database import get_session
from models import AdtEvent, Bed, Doctor, FallEvent, Patient, Room, User
from patient_routes import (
    _check_refs, _get_patient, _kick_phone, _patient_out, _stop_live_if_patient,
    camera_link_for, new_camera_token,
)
from permissions import ADMIN, CLINICAL, REGISTRARS

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class TransferBody(BaseModel):
    room_id: uuid.UUID
    bed_id: uuid.UUID                       # a transfer always lands in a specific free bed
    note: Optional[Note] = None


class ReadmitBody(BaseModel):
    room_id: uuid.UUID
    bed_id: Optional[uuid.UUID] = None
    doctor_id: Optional[uuid.UUID] = None
    condition: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]] = None


class BedStatusBody(BaseModel):
    status: str = Field(pattern="^(available|cleaning|maintenance)$")


def _iso(dt) -> Optional[str]:
    return None if dt is None else dt.isoformat() + ("Z" if dt.tzinfo is None else "")


# ── transfer ─────────────────────────────────────────────────────────────────

@router.post("/patients/{patient_id}/transfer")
def transfer_patient(patient_id: uuid.UUID, body: TransferBody, request: Request,
                     session: Session = Depends(get_session),
                     user: AuthUser = Depends(require_roles(*CLINICAL))):
    patient = _get_patient(session, patient_id)
    if patient.status != "admitted":
        raise HTTPException(status_code=409, detail="Only admitted patients can be transferred")
    _check_refs(session, None, body.room_id, body.bed_id)
    if body.bed_id == patient.bed_id:
        raise HTTPException(status_code=409, detail="The patient is already in that bed")
    adt.ensure_bed_assignable(session, body.bed_id, exclude=patient.id)

    old_room, old_bed = patient.room_id, patient.bed_id
    patient.room_id, patient.bed_id = body.room_id, body.bed_id
    session.add(patient)
    if old_bed:                                           # the bed they left needs cleaning
        previous = session.get(Bed, old_bed)
        if previous is not None:
            previous.status = "cleaning"
            session.add(previous)
    adt.record_event(session, patient, "transferred", user, from_room=old_room, from_bed=old_bed,
                     to_room=body.room_id, to_bed=body.bed_id, note=body.note)
    audit.record(session, user, "patient.transfer", "patient", patient.id, patient.patient_code, request)
    session.commit()
    # The camera watched the old room: end that session (staff reopen it in the new room).
    stopped = _stop_live_if_patient(patient.id)
    session.refresh(patient)
    return {"patient": _patient_out(session, patient), "monitoring_stopped": stopped}


# ── discharge is in patient_routes; readmit lives here ────────────────────────

@router.post("/patients/{patient_id}/readmit", status_code=201)
def readmit_patient(patient_id: uuid.UUID, body: ReadmitBody, request: Request,
                    session: Session = Depends(get_session),
                    user: AuthUser = Depends(require_roles(*REGISTRARS))):
    patient = _get_patient(session, patient_id)
    if patient.status != "discharged":
        raise HTTPException(status_code=409, detail="Only discharged patients can be re-admitted")
    _check_refs(session, body.doctor_id, body.room_id, body.bed_id)
    adt.ensure_bed_assignable(session, body.bed_id)
    token, token_hash = new_camera_token()
    patient.status = "admitted"
    patient.discharged_at = None
    patient.room_id, patient.bed_id = body.room_id, body.bed_id
    if body.doctor_id:
        patient.doctor_id = body.doctor_id
    if body.condition:
        patient.condition = body.condition
    patient.camera_token_hash = token_hash
    session.add(patient)
    adt.record_event(session, patient, "readmitted", user, to_room=body.room_id, to_bed=body.bed_id)
    audit.record(session, user, "patient.readmit", "patient", patient.id, patient.patient_code, request)
    session.commit()
    session.refresh(patient)
    link = camera_link_for(token)
    return {
        "patient": _patient_out(session, patient),
        "camera_link": link,
        "camera_link_note": None if link else "Phone gateway is off. Start the backend with VITALYN_PHONE_GATEWAY=1, then regenerate the QR.",
    }


# ── timeline ─────────────────────────────────────────────────────────────────

def _place(session: Session, room_id, bed_id) -> Optional[str]:
    room = session.get(Room, room_id) if room_id else None
    bed = session.get(Bed, bed_id) if bed_id else None
    if room is None:
        return None
    return f"Room {room.room_number}" + (f", bed {bed.bed_number}" if bed else "")


@router.get("/patients/{patient_id}/timeline")
def patient_timeline(patient_id: uuid.UUID, session: Session = Depends(get_session),
                     user: AuthUser = Depends(current_user)) -> List[Dict[str, Any]]:
    patient = _get_patient(session, patient_id)
    items: List[Dict[str, Any]] = []
    for e in session.exec(select(AdtEvent).where(AdtEvent.patient_id == patient.id)).all():
        by = session.get(User, e.by_user_id) if e.by_user_id else None
        items.append({
            "kind": e.kind,
            "at": _iso(e.created_at),
            "by": by.name if by else None,
            "from": _place(session, e.from_room_id, e.from_bed_id),
            "to": _place(session, e.to_room_id, e.to_bed_id),
            "note": e.note,
            "summary": json.loads(e.summary) if e.summary else None,
        })
    if user.role in CLINICAL:                             # fall events are clinical information
        for f in session.exec(select(FallEvent).where(FallEvent.patient_id == patient.id)).all():
            items.append({
                "kind": "fall_event", "at": _iso(f.started_at or f.created_at), "by": None,
                "from": None, "to": _place(session, f.room_id, f.bed_id),
                "note": f"Possible fall ({f.status}). Needs human review.", "summary": None,
            })
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items


# ── beds and the ward board ──────────────────────────────────────────────────

@router.patch("/beds/{bed_id}/status")
def set_bed_status(bed_id: uuid.UUID, body: BedStatusBody, request: Request,
                   session: Session = Depends(get_session),
                   user: AuthUser = Depends(require_roles(*CLINICAL))):
    bed = session.get(Bed, bed_id)
    if bed is None:
        raise HTTPException(status_code=404, detail="Bed not found")
    if adt.occupant(session, bed_id) is not None:
        raise HTTPException(status_code=409, detail="The bed is occupied; transfer or discharge the patient first")
    bed.status = body.status
    session.add(bed)
    audit.record(session, user, "bed.status", "bed", bed.id, body.status, request)
    session.commit()
    return {"id": str(bed.id), "status": bed.status}


@router.patch("/rooms/{room_id}/status")
def set_room_status(room_id: uuid.UUID, body: BedStatusBody, request: Request,
                    session: Session = Depends(get_session),
                    user: AuthUser = Depends(require_roles(*ADMIN))):
    """Mark a whole room cleaning / under maintenance / ready. Applies to every vacant
    bed; occupied beds are left alone (move the patient first) and reported back."""
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    changed, skipped = [], []
    for bed in session.exec(select(Bed).where(Bed.room_id == room_id).order_by(Bed.bed_number)).all():
        if adt.occupant(session, bed.id) is not None:
            skipped.append(bed.bed_number)
            continue
        bed.status = body.status
        session.add(bed)
        changed.append(bed.bed_number)
    audit.record(session, user, "room.status", "room", room.id,
                 {"status": body.status, "beds": changed, "skipped_occupied": skipped}, request)
    session.commit()
    return {"id": str(room.id), "status": body.status, "changed": changed, "skipped_occupied": skipped}


def _monitored_ids() -> set:
    import sys
    mod = sys.modules.get("live_pipeline")
    getter = getattr(mod, "get_manager", None)
    if getter is None:
        return set()
    return {str(s.patient_id) for s in getter().running_sessions() if getattr(s, "patient_id", None)}


@router.get("/ward-board")
def ward_board(session: Session = Depends(get_session), user: AuthUser = Depends(current_user)):
    """Every room with its beds and who is in them. Monitoring state and alerts are clinical-only."""
    clinical = user.role in CLINICAL
    monitored = _monitored_ids() if clinical else set()
    active_falls: Dict[str, int] = {}
    if clinical:
        for f in session.exec(select(FallEvent).where(FallEvent.status == "active", FallEvent.patient_id.is_not(None))).all():
            active_falls[str(f.patient_id)] = active_falls.get(str(f.patient_id), 0) + 1

    patients = session.exec(select(Patient).where(Patient.status == "admitted")).all()
    by_bed = {p.bed_id: p for p in patients if p.bed_id}
    doctors = {d.id: d.name for d in session.exec(select(Doctor)).all()}

    def occupant_out(p: Patient) -> Dict[str, Any]:
        out = {"id": str(p.id), "patient_code": p.patient_code, "name": p.name, "age": p.age,
               "doctor": doctors.get(p.doctor_id)}
        if clinical:
            out.update(condition=p.condition, monitored=str(p.id) in monitored,
                       active_alerts=active_falls.get(str(p.id), 0))
        return out

    rooms = []
    for room in session.exec(select(Room).order_by(Room.room_number)).all():
        beds = []
        for bed in session.exec(select(Bed).where(Bed.room_id == room.id).order_by(Bed.bed_number)).all():
            p = by_bed.get(bed.id)
            status = "occupied" if p else ("available" if bed.status == "active" else bed.status)
            beds.append({"id": str(bed.id), "bed_number": bed.bed_number, "status": status,
                         "patient": occupant_out(p) if p else None})
        unassigned = [occupant_out(p) for p in patients if p.room_id == room.id and not p.bed_id]
        summary = {s: sum(1 for b in beds if b["status"] == s)
                   for s in ("occupied", "available", "cleaning", "maintenance")}
        rooms.append({"id": str(room.id), "room_number": room.room_number, "floor": room.floor,
                      "beds": beds, "unassigned": unassigned, "summary": summary})
    counts = {s: sum(1 for r in rooms for b in r["beds"] if b["status"] == s)
              for s in ("occupied", "available", "cleaning", "maintenance")}
    return {"rooms": rooms, "counts": counts}
