from fastapi import HTTPException, Depends, APIRouter, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.responses import FileResponse
from typing import List, Optional
from sqlmodel import Session, select, func
from datetime import datetime, timezone
import uuid
import os
import sys
import shutil
import threading
import logging

from models import Room, Bed, InferenceJob, OccupancyRecord, FallEvent, Alert, Patient, User
import audit
from auth import AuthUser, current_user, require_roles
from database import get_session
from permissions import ADMIN, CLINICAL

log = logging.getLogger("vitalyn.routes")

# ML engine path — added to sys.path so pipeline can be imported
ML_ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "ml-engine")


def _run_inference_background(job_id: str, video_path: str) -> None:
    """
    Runs in a daemon thread after video upload.
    Imports pipeline lazily so the backend starts even if ML deps aren't present.
    """
    try:
        if ML_ENGINE_PATH not in sys.path:
            sys.path.insert(0, ML_ENGINE_PATH)
        from pipeline import run_inference
        run_inference(job_id, video_path)
    except Exception as exc:
        log.error("Background inference failed for job %s: %s", job_id, exc)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])


def _utc_iso(dt: datetime) -> str:
    """ISO-8601 in UTC with a 'Z' suffix. SQLite returns naive datetimes that
    are stored as UTC; without the suffix browsers would parse them as local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Room endpoints
# ---------------------------------------------------------------------------

@router.get("/rooms", response_model=List[Room])
def list_rooms(session: Session = Depends(get_session)):
    return session.exec(select(Room)).all()


@router.post("/rooms", response_model=Room, dependencies=[Depends(require_roles(*ADMIN))])
def create_room(room: Room, session: Session = Depends(get_session)):
    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@router.get("/rooms/{room_id}", response_model=Room)
def get_room(room_id: uuid.UUID, session: Session = Depends(get_session)):
    room = session.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.get("/rooms/{room_id}/beds", response_model=List[Bed])
def list_room_beds(room_id: uuid.UUID, session: Session = Depends(get_session)):
    return session.exec(select(Bed).where(Bed.room_id == room_id)).all()


# ---------------------------------------------------------------------------
# Bed endpoints
# ---------------------------------------------------------------------------

@router.get("/beds", response_model=List[Bed])
def list_beds(session: Session = Depends(get_session)):
    return session.exec(select(Bed)).all()


@router.post("/beds", response_model=Bed, dependencies=[Depends(require_roles(*ADMIN))])
def create_bed(bed: Bed, session: Session = Depends(get_session)):
    session.add(bed)
    session.commit()
    session.refresh(bed)
    return bed


@router.get("/beds/{bed_id}", response_model=Bed)
def get_bed(bed_id: uuid.UUID, session: Session = Depends(get_session)):
    bed = session.get(Bed, bed_id)
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    return bed


@router.get("/beds/{bed_id}/occupancy", response_model=List[OccupancyRecord], dependencies=[Depends(require_roles(*CLINICAL))])
def get_bed_occupancy(bed_id: uuid.UUID, session: Session = Depends(get_session)):
    return session.exec(
        select(OccupancyRecord)
        .where(OccupancyRecord.bed_id == bed_id)
        .order_by(OccupancyRecord.observed_at.desc())
    ).all()


# ---------------------------------------------------------------------------
# Video upload endpoint
# ---------------------------------------------------------------------------

@router.post("/videos/upload", dependencies=[Depends(require_roles(*CLINICAL))])
def upload_video(
    room_id: str = Form(...),
    patient_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    allowed = {".mp4", ".avi", ".mov", ".mkv"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    try:
        room_uuid = uuid.UUID(room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room_id format")

    room = session.get(Room, room_uuid)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    patient_uuid = None
    if patient_id:
        from models import Patient
        try:
            patient_uuid = uuid.UUID(patient_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
        patient = session.get(Patient, patient_uuid)
        if patient is None or patient.status != "admitted":
            raise HTTPException(status_code=404, detail="Admitted patient not found")

    job_id = uuid.uuid4()
    safe_filename = f"{job_id}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job = InferenceJob(
        id=job_id,
        room_id=room_uuid,
        patient_id=patient_uuid,
        video_filename=file.filename,
        video_path=dest_path,
        status="queued",
        progress=0.0,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Kick off ML inference in a background thread
    t = threading.Thread(
        target=_run_inference_background,
        args=(str(job_id), dest_path),
        daemon=True,
    )
    t.start()

    return {
        "job_id": str(job.id),
        "status": job.status,
        "message": "Video uploaded. Inference started.",
    }


@router.get("/videos/{job_id}/stream", dependencies=[Depends(require_roles(*CLINICAL))])
def stream_video(job_id: uuid.UUID, session: Session = Depends(get_session)):
    """Serve the original uploaded video file for the browser player."""
    job = session.get(InferenceJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not os.path.exists(job.video_path):
        raise HTTPException(status_code=404, detail="Video file not found on disk")
    return FileResponse(job.video_path, media_type="video/mp4")


# ---------------------------------------------------------------------------
# Inference job endpoints
# ---------------------------------------------------------------------------

@router.get("/jobs", response_model=List[InferenceJob], dependencies=[Depends(require_roles(*CLINICAL))])
def list_jobs(session: Session = Depends(get_session)):
    return session.exec(select(InferenceJob).order_by(InferenceJob.created_at.desc())).all()


@router.post("/jobs", response_model=InferenceJob, dependencies=[Depends(require_roles(*ADMIN))])
def create_job(job: InferenceJob, session: Session = Depends(get_session)):
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.get("/jobs/{job_id}", response_model=InferenceJob, dependencies=[Depends(require_roles(*CLINICAL))])
def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(InferenceJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/results", dependencies=[Depends(require_roles(*CLINICAL))])
def get_job_results(job_id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(InferenceJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    occupancy_records = session.exec(
        select(OccupancyRecord).where(OccupancyRecord.inference_job_id == job_id)
    ).all()

    fall_events = session.exec(
        select(FallEvent).where(FallEvent.inference_job_id == job_id)
    ).all()

    return {
        "job": job,
        "occupancy_records": occupancy_records,
        "fall_events": fall_events,
    }


# ---------------------------------------------------------------------------
# Occupancy endpoints
# ---------------------------------------------------------------------------

@router.get("/occupancy/current")
def get_current_occupancy(session: Session = Depends(get_session)):
    """
    Latest occupancy record per bed, joined with bed and room details.
    Returns a list of dicts: {bed_id, bed_number, room_number, occupancy_status, confidence, observed_at}
    """
    # Get all records with bed and room details
    all_records = session.exec(
        select(OccupancyRecord, Bed, Room)
        .join(Bed, OccupancyRecord.bed_id == Bed.id)
        .join(Room, Bed.room_id == Room.id)
        .order_by(OccupancyRecord.observed_at.desc())
    ).all()

    # Keep only the latest record per bed (first occurrence after desc sort)
    seen_beds: set = set()
    result = []
    for row in all_records:
        bid = str(row.OccupancyRecord.bed_id) if row.OccupancyRecord.bed_id else None
        if bid and bid not in seen_beds:
            seen_beds.add(bid)
            result.append({
                "bed_id": bid,
                "bed_number": row.Bed.bed_number,
                "room_number": row.Room.room_number,
                "room_id": str(row.Bed.room_id) if row.Bed.room_id else None,
                "occupancy_status": row.OccupancyRecord.occupancy_status,
                "confidence": row.OccupancyRecord.confidence,
                "observed_at": _utc_iso(row.OccupancyRecord.observed_at),
            })
    return result


@router.get("/occupancy/history", response_model=List[OccupancyRecord], dependencies=[Depends(require_roles(*CLINICAL))])
def get_occupancy_history(session: Session = Depends(get_session)):
    return session.exec(
        select(OccupancyRecord).order_by(OccupancyRecord.observed_at.desc())
    ).all()


@router.post("/occupancy/records", response_model=OccupancyRecord, dependencies=[Depends(require_roles(*ADMIN))])
def create_occupancy_record(record: OccupancyRecord, session: Session = Depends(get_session)):
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Fall event endpoints
# ---------------------------------------------------------------------------

@router.get("/events/falls", response_model=List[FallEvent], dependencies=[Depends(require_roles(*CLINICAL))])
def list_fall_events(session: Session = Depends(get_session)):
    return session.exec(
        select(FallEvent).order_by(FallEvent.created_at.desc())
    ).all()


@router.post("/events/falls", response_model=FallEvent, dependencies=[Depends(require_roles(*ADMIN))])
def create_fall_event(event: FallEvent, session: Session = Depends(get_session)):
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("/events/falls/{event_id}", response_model=FallEvent, dependencies=[Depends(require_roles(*CLINICAL))])
def get_fall_event(event_id: uuid.UUID, session: Session = Depends(get_session)):
    event = session.get(FallEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/events/falls/{event_id}/resolve", response_model=FallEvent, dependencies=[Depends(require_roles(*CLINICAL))])
def resolve_fall_event(
    event_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    user: AuthUser = Depends(require_roles(*CLINICAL)),
):
    resolved_by = user.uuid
    event = session.get(FallEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now = datetime.now(timezone.utc)
    event.status = "resolved"
    event.resolved_at = now
    event.resolved_by = resolved_by
    session.add(event)

    # Resolving the event closes its still-open alerts so the two never disagree.
    for alert in session.exec(select(Alert).where(Alert.fall_event_id == event_id)).all():
        if alert.status != "resolved":
            alert.status = "resolved"
            alert.resolved_by = resolved_by
            alert.resolved_at = now
            session.add(alert)
    audit.record(session, user, "fall_event.resolve", "fall_event", event.id, None, request)
    session.commit()
    session.refresh(event)
    return event


# ---------------------------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=List[Alert], dependencies=[Depends(require_roles(*CLINICAL))])
def list_alerts(session: Session = Depends(get_session)):
    return session.exec(
        select(Alert).order_by(Alert.created_at.desc())
    ).all()


@router.post("/alerts", response_model=Alert, dependencies=[Depends(require_roles(*ADMIN))])
def create_alert(alert: Alert, session: Session = Depends(get_session)):
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


@router.get("/alerts/{alert_id}", response_model=Alert, dependencies=[Depends(require_roles(*CLINICAL))])
def get_alert(alert_id: uuid.UUID, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/alerts/{alert_id}/acknowledge", response_model=Alert, dependencies=[Depends(require_roles(*CLINICAL))])
def acknowledge_alert(
    alert_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    user: AuthUser = Depends(require_roles(*CLINICAL)),
):
    acknowledged_by = user.uuid
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "acknowledged"
    alert.acknowledged_by = acknowledged_by
    alert.acknowledged_at = datetime.now(timezone.utc)
    session.add(alert)

    # Keep the underlying fall event's lifecycle in step with its alert.
    event = session.get(FallEvent, alert.fall_event_id) if alert.fall_event_id else None
    if event and event.status == "active":
        event.status = "acknowledged"
        session.add(event)
    audit.record(session, user, "alert.acknowledge", "alert", alert.id, None, request)
    session.commit()
    session.refresh(alert)
    return alert


@router.patch("/alerts/{alert_id}/resolve", response_model=Alert, dependencies=[Depends(require_roles(*CLINICAL))])
def resolve_alert(
    alert_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    user: AuthUser = Depends(require_roles(*CLINICAL)),
):
    resolved_by = user.uuid
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.now(timezone.utc)
    alert.status = "resolved"
    alert.resolved_by = resolved_by
    alert.resolved_at = now
    session.add(alert)

    event = session.get(FallEvent, alert.fall_event_id) if alert.fall_event_id else None
    if event and event.status != "resolved":
        event.status = "resolved"
        event.resolved_by = resolved_by
        event.resolved_at = now
        session.add(event)
    audit.record(session, user, "alert.resolve", "alert", alert.id, None, request)
    session.commit()
    session.refresh(alert)
    return alert


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------

@router.get("/dashboard/overview")
def get_dashboard_overview(session: Session = Depends(get_session)):
    """Bed counts come from ADMISSIONS (who is assigned to which bed), the same source as the ward
    board. Camera-detected presence is reported separately and never overrides an admission."""
    beds = session.exec(select(Bed)).all()
    total_beds = len(beds)
    occupied_ids = {
        p.bed_id for p in session.exec(
            select(Patient).where(Patient.status == "admitted", Patient.bed_id.is_not(None))
        ).all()
    }
    occupied_beds = sum(1 for b in beds if b.id in occupied_ids)
    vacant_beds = sum(1 for b in beds if b.id not in occupied_ids and b.status in ("active", "available"))
    not_ready_beds = total_beds - occupied_beds - vacant_beds          # cleaning / maintenance
    occupied_percentage = round((occupied_beds / total_beds) * 100, 1) if total_beds > 0 else 0.0

    # Camera view: latest occupancy record per bed (only beds with a live/uploaded camera have one).
    seen_beds: set = set()
    camera_occupied = camera_uncertain = 0
    for r in session.exec(select(OccupancyRecord).order_by(OccupancyRecord.observed_at.desc())).all():
        bid = str(r.bed_id) if r.bed_id else None
        if bid and bid not in seen_beds:
            seen_beds.add(bid)
            camera_occupied += r.occupancy_status == "occupied"
            camera_uncertain += r.occupancy_status == "uncertain"
    uncertain_beds = camera_uncertain

    active_fall_events = session.exec(
        select(func.count(FallEvent.id)).where(FallEvent.status == "active")
    ).one()

    active_alerts = session.exec(
        select(func.count(Alert.id)).where(Alert.status == "active")
    ).one()

    return {
        "total_beds": int(total_beds),
        "occupied_beds": occupied_beds,
        "vacant_beds": vacant_beds,
        "uncertain_beds": uncertain_beds,
        "not_ready_beds": not_ready_beds,
        "camera_occupied_beds": camera_occupied,
        "occupied_percentage": occupied_percentage,
        "active_fall_events": int(active_fall_events),
        "active_alerts": int(active_alerts),
    }


@router.get("/dashboard/occupancy-trends", dependencies=[Depends(require_roles(*CLINICAL))])
def get_occupancy_trends(session: Session = Depends(get_session)):
    records = session.exec(
        select(OccupancyRecord, Bed)
        .join(Bed, OccupancyRecord.bed_id == Bed.id)
        .order_by(OccupancyRecord.observed_at.asc())
    ).all()

    return [
        {
            "observed_at": _utc_iso(r.OccupancyRecord.observed_at),
            "occupancy_status": r.OccupancyRecord.occupancy_status,
            "confidence": r.OccupancyRecord.confidence,
            "bed_id": str(r.OccupancyRecord.bed_id),
            "bed_number": r.Bed.bed_number,
        }
        for r in records
    ]


@router.get("/dashboard/event-summary", dependencies=[Depends(require_roles(*CLINICAL))])
def get_event_summary(session: Session = Depends(get_session)):
    total_events = session.exec(select(func.count(FallEvent.id))).one()
    active_events = session.exec(
        select(func.count(FallEvent.id)).where(FallEvent.status == "active")
    ).one()
    acknowledged_events = session.exec(
        select(func.count(FallEvent.id)).where(FallEvent.status == "acknowledged")
    ).one()
    resolved_events = session.exec(
        select(func.count(FallEvent.id)).where(FallEvent.status == "resolved")
    ).one()

    return {
        "total_events": total_events,
        "active_events": active_events,
        "acknowledged_events": acknowledged_events,
        "resolved_events": resolved_events,
    }
