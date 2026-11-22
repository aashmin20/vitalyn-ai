"""Admission / transfer / discharge rules shared by the patient and ADT routes."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from auth import AuthUser
from models import AdtEvent, Bed, Patient

# A bed is stored as "active" in older rows; both mean it can be given to a patient.
ASSIGNABLE = ("active", "available")
SETTABLE = ("available", "cleaning", "maintenance")


def occupant(session: Session, bed_id: uuid.UUID, exclude: Optional[uuid.UUID] = None) -> Optional[Patient]:
    stmt = select(Patient).where(Patient.bed_id == bed_id, Patient.status == "admitted")
    if exclude is not None:
        stmt = stmt.where(Patient.id != exclude)
    return session.exec(stmt).first()


def ensure_bed_assignable(session: Session, bed_id: Optional[uuid.UUID], exclude: Optional[uuid.UUID] = None) -> None:
    """One admitted patient per bed, and only beds that are ready."""
    if bed_id is None:
        return
    bed = session.get(Bed, bed_id)
    if bed is None:
        raise HTTPException(status_code=422, detail="Bed not found")
    if occupant(session, bed_id, exclude) is not None:
        raise HTTPException(status_code=409, detail="That bed is already occupied")
    if bed.status not in ASSIGNABLE:
        raise HTTPException(status_code=409, detail=f"That bed is not available (it is {bed.status})")


def record_event(session: Session, patient: Patient, kind: str, user: Optional[AuthUser], *,
                 from_room=None, from_bed=None, to_room=None, to_bed=None,
                 note: Optional[str] = None, summary: Any = None) -> AdtEvent:
    event = AdtEvent(
        patient_id=patient.id, kind=kind, by_user_id=user.uuid if user else None,
        from_room_id=from_room, from_bed_id=from_bed, to_room_id=to_room, to_bed_id=to_bed,
        note=note[:200] if note else None,
        summary=json.dumps(summary, default=str) if summary else None,
    )
    session.add(event)
    return event
