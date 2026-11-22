"""
Tests for the database writer (db_writer.py).

Uses an in-memory SQLite test database — does NOT touch the production vitalyn.db.
Tests verify:
  - Job status transitions (started / progress / completed / failed)
  - Occupancy records are written correctly
  - Fall events and alerts are created together
  - Severity is derived correctly from confidence
  - Room/bed lookups work
"""
import sys
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlmodel import create_engine, Session, SQLModel, select

# Make backend models importable
BACKEND = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
ML_ENGINE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)
sys.path.insert(0, ML_ENGINE)

from models import Room, Bed, InferenceJob, OccupancyRecord, FallEvent, Alert


# ── Test DB fixture ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(test_engine):
    with Session(test_engine) as s:
        yield s


@pytest.fixture
def db_writer_with_test_engine(test_engine, monkeypatch):
    """Patches db_writer._engine() to return the in-memory test engine."""
    import db_writer
    monkeypatch.setattr(db_writer, "_engine", lambda: test_engine)
    return db_writer


@pytest.fixture
def seeded_room_bed_job(session, test_engine):
    """Creates a Room, Bed, and queued InferenceJob. Returns their IDs."""
    room = Room(room_number=f"T{uuid.uuid4().hex[:4]}", floor="1")
    session.add(room)
    session.commit()
    session.refresh(room)

    bed = Bed(room_id=room.id, bed_number="B01")
    session.add(bed)
    session.commit()
    session.refresh(bed)

    job = InferenceJob(
        room_id=room.id,
        video_filename="test.mp4",
        video_path="/tmp/test.mp4",
        status="queued",
        progress=0.0,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    return str(room.id), str(bed.id), str(job.id)


# ── Job status transitions ────────────────────────────────────────────────────

class TestJobStatusTransitions:

    def test_mark_job_started(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, _, job_id = seeded_room_bed_job
        db_writer_with_test_engine.mark_job_started(job_id)
        job = session.get(InferenceJob, uuid.UUID(job_id))
        session.refresh(job)
        assert job.status == "processing"
        assert job.started_at is not None
        assert job.progress == 0.0

    def test_update_job_progress(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, _, job_id = seeded_room_bed_job
        db_writer_with_test_engine.update_job_progress(job_id, 55.0)
        job = session.get(InferenceJob, uuid.UUID(job_id))
        session.refresh(job)
        assert job.progress == 55.0

    def test_progress_capped_at_99(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, _, job_id = seeded_room_bed_job
        db_writer_with_test_engine.update_job_progress(job_id, 150.0)
        job = session.get(InferenceJob, uuid.UUID(job_id))
        session.refresh(job)
        assert job.progress <= 99.0

    def test_mark_job_completed(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, _, job_id = seeded_room_bed_job
        db_writer_with_test_engine.mark_job_completed(job_id)
        job = session.get(InferenceJob, uuid.UUID(job_id))
        session.refresh(job)
        assert job.status == "completed"
        assert job.progress == 100.0
        assert job.completed_at is not None

    def test_mark_job_failed(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, _, job_id = seeded_room_bed_job
        db_writer_with_test_engine.mark_job_failed(job_id, "OpenCV read error")
        job = session.get(InferenceJob, uuid.UUID(job_id))
        session.refresh(job)
        assert job.status == "failed"
        assert "OpenCV" in job.error_message
        assert job.completed_at is not None

    def test_error_message_truncated_at_500(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, _, job_id = seeded_room_bed_job
        long_msg = "x" * 1000
        db_writer_with_test_engine.mark_job_failed(job_id, long_msg)
        job = session.get(InferenceJob, uuid.UUID(job_id))
        session.refresh(job)
        assert len(job.error_message) <= 500


# ── Room/Bed lookups ──────────────────────────────────────────────────────────

class TestLookups:

    def test_get_job_room_id_returns_string(self, db_writer_with_test_engine, seeded_room_bed_job):
        room_id, _, job_id = seeded_room_bed_job
        result = db_writer_with_test_engine.get_job_room_id(job_id)
        assert result == room_id

    def test_get_job_room_id_nonexistent_returns_none(self, db_writer_with_test_engine):
        result = db_writer_with_test_engine.get_job_room_id(str(uuid.uuid4()))
        assert result is None

    def test_get_first_bed_for_room_returns_string(self, db_writer_with_test_engine, seeded_room_bed_job):
        room_id, bed_id, _ = seeded_room_bed_job
        result = db_writer_with_test_engine.get_first_bed_for_room(room_id)
        assert result == bed_id

    def test_get_first_bed_for_room_no_beds_returns_none(self, db_writer_with_test_engine, session):
        empty_room = Room(room_number=f"E{uuid.uuid4().hex[:4]}", floor="99")
        session.add(empty_room)
        session.commit()
        session.refresh(empty_room)
        result = db_writer_with_test_engine.get_first_bed_for_room(str(empty_room.id))
        assert result is None

    def test_default_bed_created_when_room_has_none(self, db_writer_with_test_engine, session):
        room = Room(room_number=f"D{uuid.uuid4().hex[:4]}", floor="1")
        session.add(room)
        session.commit()
        session.refresh(room)
        bed_id = db_writer_with_test_engine.get_or_create_default_bed(str(room.id))
        assert bed_id is not None
        # Second call reuses the same bed rather than creating another
        assert db_writer_with_test_engine.get_or_create_default_bed(str(room.id)) == bed_id

    def test_default_bed_reuses_existing_bed(self, db_writer_with_test_engine, seeded_room_bed_job):
        room_id, bed_id, _ = seeded_room_bed_job
        assert db_writer_with_test_engine.get_or_create_default_bed(room_id) == bed_id

    def test_default_bed_unknown_room_returns_none(self, db_writer_with_test_engine):
        assert db_writer_with_test_engine.get_or_create_default_bed(str(uuid.uuid4())) is None


# ── Occupancy records ─────────────────────────────────────────────────────────

class TestWriteOccupancyRecords:

    def _make_frames(self, statuses):
        class Frame:
            def __init__(self, s, c):
                self.status = s
                self.confidence = c
        return [Frame(s, 0.85) for s in statuses]

    def test_records_written_count(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, bed_id, job_id = seeded_room_bed_job
        frames = self._make_frames(["occupied", "vacant", "occupied"])
        n = db_writer_with_test_engine.write_occupancy_records(
            job_id=job_id,
            bed_id=bed_id,
            results=frames,
            video_start=datetime.now(timezone.utc),
            fps=6.0,
            sample_rate=1,
        )
        assert n == 3

    def test_records_stored_in_db(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, bed_id, job_id = seeded_room_bed_job
        frames = self._make_frames(["occupied", "vacant"])
        db_writer_with_test_engine.write_occupancy_records(
            job_id=job_id, bed_id=bed_id,
            results=frames,
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        records = session.exec(
            select(OccupancyRecord).where(
                OccupancyRecord.inference_job_id == uuid.UUID(job_id)
            )
        ).all()
        assert len(records) >= 2

    def test_occupancy_statuses_preserved(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        _, bed_id, job_id = seeded_room_bed_job
        frames = self._make_frames(["occupied", "vacant", "uncertain"])
        db_writer_with_test_engine.write_occupancy_records(
            job_id=job_id, bed_id=bed_id,
            results=frames,
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        records = session.exec(
            select(OccupancyRecord).where(
                OccupancyRecord.inference_job_id == uuid.UUID(job_id)
            )
        ).all()
        statuses = {r.occupancy_status for r in records}
        assert "occupied"  in statuses
        assert "vacant"    in statuses
        assert "uncertain" in statuses

    def test_empty_results_writes_nothing(self, db_writer_with_test_engine, seeded_room_bed_job):
        _, bed_id, job_id = seeded_room_bed_job
        n = db_writer_with_test_engine.write_occupancy_records(
            job_id=job_id, bed_id=bed_id,
            results=[],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        assert n == 0

    def test_null_bed_id_allowed(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        """Bed ID can be None when no bed is configured for the room."""
        _, _, job_id = seeded_room_bed_job

        class Frame:
            status = "occupied"
            confidence = 0.8

        n = db_writer_with_test_engine.write_occupancy_records(
            job_id=job_id, bed_id=None,
            results=[Frame()],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        assert n == 1


# ── Fall events and alerts ────────────────────────────────────────────────────

class TestWriteFallEvents:

    def _make_candidate(self, start, end, conf):
        class C:
            start_frame = start
            end_frame = end
            confidence = conf
            event_type = "potential_fall"
        return C()

    def test_fall_event_and_alert_created(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, job_id = seeded_room_bed_job
        c = self._make_candidate(0, 30, 0.80)
        n = db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=[c],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        assert n == 1

        events = session.exec(
            select(FallEvent).where(FallEvent.inference_job_id == uuid.UUID(job_id))
        ).all()
        assert len(events) >= 1

        event_id = events[-1].id
        alerts = session.exec(
            select(Alert).where(Alert.fall_event_id == event_id)
        ).all()
        assert len(alerts) == 1

    def test_high_confidence_gives_high_severity(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, job_id = seeded_room_bed_job
        c = self._make_candidate(0, 30, 0.85)
        db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=[c],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        events = session.exec(
            select(FallEvent).where(FallEvent.inference_job_id == uuid.UUID(job_id))
        ).all()
        event_id = events[-1].id
        alert = session.exec(select(Alert).where(Alert.fall_event_id == event_id)).first()
        assert alert.severity == "high"

    def test_medium_confidence_gives_medium_severity(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, job_id = seeded_room_bed_job
        c = self._make_candidate(0, 30, 0.60)
        db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=[c],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        events = session.exec(
            select(FallEvent).where(FallEvent.inference_job_id == uuid.UUID(job_id))
        ).all()
        event_id = events[-1].id
        alert = session.exec(select(Alert).where(Alert.fall_event_id == event_id)).first()
        assert alert.severity == "medium"

    def test_low_confidence_gives_low_severity(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, job_id = seeded_room_bed_job
        c = self._make_candidate(0, 30, 0.30)
        db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=[c],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        events = session.exec(
            select(FallEvent).where(FallEvent.inference_job_id == uuid.UUID(job_id))
        ).all()
        event_id = events[-1].id
        alert = session.exec(select(Alert).where(Alert.fall_event_id == event_id)).first()
        assert alert.severity == "low"

    def test_alert_status_is_active(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, job_id = seeded_room_bed_job
        c = self._make_candidate(0, 30, 0.75)
        db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=[c],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        events = session.exec(
            select(FallEvent).where(FallEvent.inference_job_id == uuid.UUID(job_id))
        ).all()
        event_id = events[-1].id
        alert = session.exec(select(Alert).where(Alert.fall_event_id == event_id)).first()
        assert alert.status == "active"

    def test_multiple_candidates_multiple_events(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, job_id = seeded_room_bed_job
        candidates = [
            self._make_candidate(0,  30, 0.8),
            self._make_candidate(60, 90, 0.7),
        ]
        n = db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=candidates,
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        assert n == 2

    def test_empty_candidates_writes_nothing(self, db_writer_with_test_engine, seeded_room_bed_job):
        room_id, bed_id, job_id = seeded_room_bed_job
        n = db_writer_with_test_engine.write_fall_events(
            job_id=job_id, room_id=room_id, bed_id=bed_id,
            candidates=[],
            video_start=datetime.now(timezone.utc),
            fps=6.0, sample_rate=1,
        )
        assert n == 0


# ── Live camera helpers ───────────────────────────────────────────────────────

class TestLiveHelpers:

    def test_create_live_job_is_live_and_linked(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, _, _ = seeded_room_bed_job
        job_id = db_writer_with_test_engine.create_live_job(room_id, "0")
        job = session.get(InferenceJob, uuid.UUID(job_id))
        assert job.status == "live" and job.video_path == "camera:0"
        assert str(job.room_id) == room_id

    def test_live_fall_event_creates_event_and_alert(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, _ = seeded_room_bed_job
        job_id = db_writer_with_test_engine.create_live_job(room_id, "0")
        now = datetime.now(timezone.utc)
        event_id = db_writer_with_test_engine.write_live_fall_event(job_id, room_id, bed_id, 0.9, now)
        event = session.get(FallEvent, uuid.UUID(event_id))
        assert event.status == "active" and event.event_type == "potential_fall"
        alerts = session.exec(select(Alert).where(Alert.fall_event_id == event.id)).all()
        assert len(alerts) == 1 and alerts[0].severity == "high"

    def test_live_occupancy_row_written(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, bed_id, _ = seeded_room_bed_job
        job_id = db_writer_with_test_engine.create_live_job(room_id, "0")
        db_writer_with_test_engine.write_live_occupancy(job_id, bed_id, "occupied", 0.8, datetime.now(timezone.utc))
        rows = session.exec(select(OccupancyRecord).where(OccupancyRecord.inference_job_id == uuid.UUID(job_id))).all()
        assert len(rows) == 1 and rows[0].occupancy_status == "occupied"

    def test_orphaned_live_jobs_are_failed(self, db_writer_with_test_engine, seeded_room_bed_job, session):
        room_id, _, _ = seeded_room_bed_job
        job_id = db_writer_with_test_engine.create_live_job(room_id, "0")
        assert db_writer_with_test_engine.fail_orphaned_live_jobs() >= 1
        session.expire_all()
        assert session.get(InferenceJob, uuid.UUID(job_id)).status == "failed"
