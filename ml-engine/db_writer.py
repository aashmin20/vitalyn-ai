"""
db_writer.py — Write ML results into the VITALYN SQLite database.

Shares the same DB file as the backend.  Uses SQLModel directly.
"""
from __future__ import annotations

import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any

BACKEND_PATH = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_PATH)

import logging

from sqlmodel import Session, select
from models import InferenceJob, OccupancyRecord, FallEvent, Alert, Bed, Room
from database import get_engine
import outbox

log = logging.getLogger("vitalyn.db_writer")


def _engine():
    """The engine shared with the API: local SQLite by default, Supabase when DATABASE_URL is set."""
    return get_engine()


# ── Job status helpers ───────────────────────────────────────────────────────

def mark_job_started(job_id: str) -> None:
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job:
            job.status     = "processing"
            job.started_at = datetime.now(timezone.utc)
            job.progress   = 0.0
            s.add(job); s.commit()


def update_job_progress(job_id: str, progress: float) -> None:
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job:
            job.progress = round(min(progress, 99.0), 1)
            s.add(job); s.commit()


def mark_job_completed(job_id: str) -> None:
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job:
            job.status       = "completed"
            job.progress     = 100.0
            job.completed_at = datetime.now(timezone.utc)
            s.add(job); s.commit()


def mark_job_failed(job_id: str, error: str) -> None:
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job:
            job.status        = "failed"
            job.error_message = str(error)[:500]
            job.completed_at  = datetime.now(timezone.utc)
            s.add(job); s.commit()


def write_job_warning(job_id: str, message: str) -> None:
    """
    Attach a warning message to a completed job without changing its status.
    Used when the pipeline succeeded but wants to inform the user of reduced
    reliability (e.g. short video, zero-padded keypoints).
    """
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job:
            job.error_message = str(message)[:500]
            s.add(job); s.commit()


def get_job_room_id(job_id: str) -> Optional[str]:
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job and job.room_id:
            return str(job.room_id)
    return None


def get_job_patient_id(job_id: str) -> Optional[str]:
    with Session(_engine()) as s:
        job = s.get(InferenceJob, uuid.UUID(job_id))
        if job and job.patient_id:
            return str(job.patient_id)
    return None


def get_first_bed_for_room(room_id: str) -> Optional[str]:
    with Session(_engine()) as s:
        beds = s.exec(
            select(Bed).where(Bed.room_id == uuid.UUID(room_id))
        ).all()
        active = [b for b in beds if b.status == "active"]
        if active:
            return str(active[0].id)
    return None


DEFAULT_BED_NUMBER = "1"


def get_or_create_default_bed(room_id: str) -> Optional[str]:
    """
    Return the room's first active bed, creating a default one if the room has
    none. Uploaded videos cover a whole room, so occupancy must still be
    attributed to a bed or the dashboard (which joins on Bed) would never see it.
    Returns None only if the room does not exist.
    """
    existing = get_first_bed_for_room(room_id)
    if existing:
        return existing

    with Session(_engine()) as s:
        if s.get(Room, uuid.UUID(room_id)) is None:
            return None
        bed = Bed(bed_number=DEFAULT_BED_NUMBER, room_id=uuid.UUID(room_id), status="active")
        s.add(bed)
        s.commit()
        s.refresh(bed)
        return str(bed.id)


# ── Result writers ───────────────────────────────────────────────────────────

def write_occupancy_records(
    job_id: str,
    bed_id: Optional[str],
    results: List[Any],      # list of objects with .status and .confidence
    video_start: datetime,
    fps: float,
    sample_rate: int,
) -> int:
    if not results:
        return 0

    engine = _engine()
    written = 0

    with Session(engine) as s:
        for i, r in enumerate(results):
            offset_secs = (i * sample_rate) / max(fps, 1.0)
            observed_at = video_start + timedelta(seconds=offset_secs)

            record = OccupancyRecord(
                bed_id=uuid.UUID(bed_id) if bed_id else None,
                inference_job_id=uuid.UUID(job_id),
                occupancy_status=r.status,
                confidence=float(r.confidence),
                observed_at=observed_at,
            )
            s.add(record)
            written += 1

        s.commit()

    return written


def _severity(confidence: float) -> str:
    return "high" if confidence >= 0.75 else "medium" if confidence >= 0.50 else "low"


def _add_event_and_alert(
    s: Session,
    job_id: str,
    room_id: Optional[str],
    bed_id: Optional[str],
    confidence: float,
    started_at: datetime,
    ended_at: datetime,
    event_id: Optional[str] = None,
    alert_id: Optional[str] = None,
    patient_id: Optional[str] = None,
) -> FallEvent:
    """Create one potential-fall event and its alert (shared by batch and live paths)."""
    event = FallEvent(
        id=uuid.UUID(event_id) if event_id else uuid.uuid4(),
        inference_job_id=uuid.UUID(job_id),
        room_id=uuid.UUID(room_id) if room_id else None,
        bed_id=uuid.UUID(bed_id) if bed_id else None,
        patient_id=uuid.UUID(patient_id) if patient_id else None,
        event_type="potential_fall",
        confidence=float(confidence),
        status="active",
        started_at=started_at,
        ended_at=ended_at,
    )
    s.add(event)
    s.flush()  # populate event.id before creating the alert
    s.add(Alert(
        id=uuid.UUID(alert_id) if alert_id else uuid.uuid4(),
        fall_event_id=event.id,
        alert_type="potential_fall",
        severity=_severity(confidence),
        status="active",
    ))
    return event


def write_fall_events(
    job_id: str,
    room_id: Optional[str],
    bed_id: Optional[str],
    candidates: List[Any],   # objects with .start_frame, .end_frame, .confidence
    video_start: datetime,
    fps: float,
    sample_rate: int,
    patient_id: Optional[str] = None,
) -> int:
    if not candidates:
        return 0

    engine = _engine()
    written = 0

    with Session(engine) as s:
        for c in candidates:
            start_secs = (c.start_frame * sample_rate) / max(fps, 1.0)
            end_secs   = (c.end_frame   * sample_rate) / max(fps, 1.0)
            started_at = video_start + timedelta(seconds=start_secs)
            ended_at   = video_start + timedelta(seconds=end_secs)

            _add_event_and_alert(
                s,
                job_id=job_id,
                room_id=room_id,
                bed_id=bed_id,
                confidence=float(c.confidence),
                started_at=started_at,
                ended_at=ended_at,
                patient_id=patient_id,
            )
            written += 1

        s.commit()

    return written


# ── Live camera helpers ──────────────────────────────────────────────────────

def create_live_job(room_id: str, source_label: str, patient_id: Optional[str] = None) -> str:
    """Create an InferenceJob representing a live camera session; returns its id."""
    now = datetime.now(timezone.utc)
    with Session(_engine()) as s:
        job = InferenceJob(
            room_id=uuid.UUID(room_id),
            patient_id=uuid.UUID(patient_id) if patient_id else None,
            video_filename=f"Live camera ({source_label})",
            video_path=f"camera:{source_label}",
            status="live",
            progress=0.0,
            started_at=now,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        return str(job.id)


def write_live_occupancy(
    job_id: str,
    bed_id: Optional[str],
    status: str,
    confidence: float,
    observed_at: datetime,
) -> None:
    with Session(_engine()) as s:
        s.add(OccupancyRecord(
            bed_id=uuid.UUID(bed_id) if bed_id else None,
            inference_job_id=uuid.UUID(job_id),
            occupancy_status=status,
            confidence=float(confidence),
            observed_at=observed_at,
        ))
        s.commit()


def _write_fall_event_now(payload: dict) -> str:
    """Insert the event + alert described by `payload`. Idempotent on the event id."""
    with Session(_engine()) as s:
        if s.get(FallEvent, uuid.UUID(payload["event_id"])) is not None:
            return payload["event_id"]
        _add_event_and_alert(
            s,
            payload["job_id"], payload.get("room_id"), payload.get("bed_id"),
            payload["confidence"],
            started_at=datetime.fromisoformat(payload["detected_at"]),
            ended_at=datetime.fromisoformat(payload["detected_at"]),
            event_id=payload["event_id"], alert_id=payload["alert_id"],
            patient_id=payload.get("patient_id"),
        )
        s.commit()
    return payload["event_id"]


def write_live_fall_event(
    job_id: str,
    room_id: Optional[str],
    bed_id: Optional[str],
    confidence: float,
    detected_at: datetime,
    patient_id: Optional[str] = None,
) -> str:
    """
    Persist a live potential fall (real wall-clock time). Returns the event id.
    If the database is unreachable the event is queued locally and replayed later
    (flush_outbox), so an alert is never silently lost.
    """
    payload = {
        "event_id": str(uuid.uuid4()),
        "alert_id": str(uuid.uuid4()),
        "job_id": job_id,
        "room_id": room_id,
        "bed_id": bed_id,
        "patient_id": patient_id,
        "confidence": float(confidence),
        "detected_at": detected_at.isoformat(),
    }
    try:
        return _write_fall_event_now(payload)
    except Exception as exc:
        outbox.enqueue("fall_event", payload)
        log.error("Database unavailable; fall event %s queued locally: %s", payload["event_id"], exc)
        return payload["event_id"]


def flush_outbox() -> int:
    """Replay queued fall events. Returns how many were written."""
    if outbox.pending() == 0:
        return 0

    def handler(kind: str, payload: dict) -> None:
        if kind == "fall_event":
            _write_fall_event_now(payload)

    return outbox.flush(handler)


def outbox_pending() -> int:
    return outbox.pending()


def fail_orphaned_live_jobs() -> int:
    """Called at backend start: a job still 'live' belongs to a dead process."""
    with Session(_engine()) as s:
        jobs = s.exec(select(InferenceJob).where(InferenceJob.status == "live")).all()
        for j in jobs:
            j.status = "failed"
            j.error_message = "Live session ended: backend restarted."
            j.completed_at = datetime.now(timezone.utc)
            s.add(j)
        s.commit()
        return len(jobs)
