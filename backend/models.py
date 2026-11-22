"""
VITALYN database models.

All UUIDs (primary keys and foreign keys) are stored as CHAR(36) WITH hyphens
via the AutoUUID TypeDecorator.  This ensures JOIN conditions work because
both sides of a FK relationship use the same string representation.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Optional, List, Any

from sqlalchemy import Column, ForeignKey, types as sa_types
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import SQLModel, Field, Relationship


# ---------------------------------------------------------------------------
# Custom UUID column type — CHAR(36), accepts str or uuid.UUID on write
# ---------------------------------------------------------------------------

class AutoUUID(sa_types.TypeDecorator):
    """Stores UUIDs as 36-char hyphenated strings; always returns uuid.UUID on load."""

    impl = sa_types.CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        # Native UUID columns on Postgres (Supabase); hyphenated CHAR(36) on SQLite.
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(sa_types.CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value: Any, dialect: Any) -> Optional[uuid.UUID]:
        if value is None:
            return None
        return uuid.UUID(str(value))


def _pk_col() -> Column:
    """Return a fresh AutoUUID primary-key column.  Called per-model to avoid column sharing."""
    return Column("id", AutoUUID, primary_key=True, default=uuid.uuid4)


def _fk_col(name: str, fk_target: str) -> Column:
    return Column(name, AutoUUID, ForeignKey(fk_target), nullable=True)


# ---------------------------------------------------------------------------
# Base model (non-table)
# ---------------------------------------------------------------------------

class BaseModel(SQLModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
            if v.tzinfo is None
            else v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        }


# ---------------------------------------------------------------------------
# Table models — each defines its own `id` sa_column so AutoUUID is used
# ---------------------------------------------------------------------------

class Room(BaseModel, table=True):
    __tablename__ = "room"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    room_number: str = Field(index=True, unique=True)
    floor: str
    status: str = Field(default="active")

    beds: List["Bed"] = Relationship(back_populates="room")


class Bed(BaseModel, table=True):
    __tablename__ = "bed"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    bed_number: str = Field(index=True)
    room_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("room_id", "room.id"))
    status: str = Field(default="active")

    room: Optional[Room] = Relationship(back_populates="beds")
    occupancy_records: List["OccupancyRecord"] = Relationship(back_populates="bed")


class InferenceJob(BaseModel, table=True):
    __tablename__ = "inference_job"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    room_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("room_id", "room.id"))
    video_filename: str
    video_path: str
    patient_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("patient_id", "patient.id"))
    status: str = Field(default="queued")
    progress: float = Field(default=0.0)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    room: Optional[Room] = Relationship()
    occupancy_records: List["OccupancyRecord"] = Relationship(back_populates="inference_job")
    fall_events: List["FallEvent"] = Relationship(back_populates="inference_job")


class OccupancyRecord(BaseModel, table=True):
    __tablename__ = "occupancy_record"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    bed_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("bed_id", "bed.id"))
    inference_job_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("inference_job_id", "inference_job.id"))
    occupancy_status: str  # occupied | vacant | uncertain
    confidence: float
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    bed: Optional[Bed] = Relationship(back_populates="occupancy_records")
    inference_job: Optional[InferenceJob] = Relationship(back_populates="occupancy_records")


class FallEvent(BaseModel, table=True):
    __tablename__ = "fall_event"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    inference_job_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("inference_job_id", "inference_job.id"))
    room_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("room_id", "room.id"))
    bed_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("bed_id", "bed.id"))
    patient_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("patient_id", "patient.id"))
    event_type: str = Field(default="potential_fall")
    confidence: float
    status: str = Field(default="active")  # active | acknowledged | resolved
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    resolved_by: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("resolved_by", "user.id"))
    resolved_at: Optional[datetime] = None

    inference_job: Optional[InferenceJob] = Relationship(back_populates="fall_events")
    alerts: List["Alert"] = Relationship(back_populates="fall_event")


class Alert(BaseModel, table=True):
    __tablename__ = "alert"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    fall_event_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("fall_event_id", "fall_event.id"))
    alert_type: str
    severity: str  # high | medium | low
    status: str = Field(default="active")  # active | acknowledged | resolved
    acknowledged_by: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("acknowledged_by", "user.id"))
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("resolved_by", "user.id"))
    resolved_at: Optional[datetime] = None

    fall_event: Optional[FallEvent] = Relationship(back_populates="alerts")


class User(BaseModel, table=True):
    """
    A staff member. Passwords are owned by Supabase Auth: `password_hash` only holds a placeholder.
    `status` is pending until an admin approves the account; `role` then controls access.
    """
    __tablename__ = "user"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str = Field(default="supabase-auth")
    role: str = Field(default="none")                 # admin | doctor | nurse | receptionist | none
    auth_user_id: Optional[str] = Field(default=None, index=True, unique=True)   # Supabase user id (JWT "sub")
    status: str = Field(default="pending")            # pending | active | disabled
    last_login_at: Optional[datetime] = None


class AuditLog(BaseModel, table=True):
    """Who did what, when. Written for every change, login and patient-record open."""
    __tablename__ = "audit_log"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    actor_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("actor_id", "user.id"))
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    action: str = Field(index=True)                   # e.g. patient.admit, auth.login
    entity: Optional[str] = None                      # e.g. patient
    entity_id: Optional[str] = None
    detail: Optional[str] = None                      # short text, never secrets or free-text clinical notes
    ip: Optional[str] = None


class Doctor(BaseModel, table=True):
    __tablename__ = "doctor"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    name: str = Field(index=True)
    department: Optional[str] = None
    user_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("user_id", "user.id"))


class Patient(BaseModel, table=True):
    """
    A patient admitted for monitoring. DEMO DATA ONLY until real-patient use is authorised.

    camera_token_hash is the SHA-256 of the secret in the patient's camera QR code; the
    token itself is never stored, so it cannot be recovered from the database.
    """
    __tablename__ = "patient"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    patient_code: str = Field(index=True, unique=True)          # e.g. P-0001, safe to print
    name: str
    age: int
    condition: str
    doctor_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("doctor_id", "doctor.id"))
    room_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("room_id", "room.id"))
    bed_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("bed_id", "bed.id"))
    status: str = Field(default="admitted")                      # admitted | discharged
    admitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discharged_at: Optional[datetime] = None
    camera_token_hash: Optional[str] = Field(default=None, index=True)
    # The device registered to this patient (set when a phone first connects with their QR,
    # or when staff choose the Mac webcam). No secrets live here.
    camera_kind: Optional[str] = None                 # "phone" | "webcam" | None
    camera_index: Optional[int] = None                # webcam index
    camera_label: Optional[str] = None                # e.g. "iPhone (iOS 18)"
    camera_registered_at: Optional[datetime] = None
    # Demographics / contact (fictional in the demo). Age is kept for older rows and quick entry.
    sex: Optional[str] = None                         # female | male | other
    date_of_birth: Optional[date] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    allergies: Optional[str] = None


class AdtEvent(BaseModel, table=True):
    """Admission / transfer / discharge history of a patient (the patient row holds only the current stay)."""
    __tablename__ = "adt_event"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    patient_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("patient_id", "patient.id"))
    kind: str                                          # admitted | transferred | discharged | readmitted
    by_user_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("by_user_id", "user.id"))
    from_room_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("from_room_id", "room.id"))
    from_bed_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("from_bed_id", "bed.id"))
    to_room_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("to_room_id", "room.id"))
    to_bed_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("to_bed_id", "bed.id"))
    note: Optional[str] = None                         # short reason, never secrets
    summary: Optional[str] = None                      # discharge summary as JSON text


class DoctorSchedule(BaseModel, table=True):
    """A doctor's weekly clinic hours. Times are hospital wall-clock time ("HH:MM"), no timezone."""
    __tablename__ = "doctor_schedule"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    doctor_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("doctor_id", "doctor.id"))
    weekday: int                                       # 0 = Monday ... 6 = Sunday
    start_time: str
    end_time: str
    slot_minutes: int = Field(default=15)


class Appointment(BaseModel, table=True):
    """An outpatient (OPD) appointment. start_at / end_at are hospital wall-clock time, no timezone."""
    __tablename__ = "appointment"

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, sa_column=_pk_col())
    patient_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("patient_id", "patient.id"))
    doctor_id: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("doctor_id", "doctor.id"))
    start_at: datetime
    end_at: datetime
    status: str = Field(default="scheduled")           # scheduled | checked_in | in_consult | completed | cancelled | no_show
    reason: Optional[str] = None                       # short text, never clinical free text
    created_by: Optional[uuid.UUID] = Field(default=None, sa_column=_fk_col("created_by", "user.id"))
