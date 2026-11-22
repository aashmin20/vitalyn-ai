"""Fall events must survive a database outage: queue locally, replay once it is back."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import db_writer
import outbox
from models import Alert, FallEvent, InferenceJob, Room


@pytest.fixture
def engine(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_writer, "_engine", lambda: eng)
    monkeypatch.setattr(outbox, "OUTBOX_PATH", str(tmp_path / "outbox.db"))
    return eng


@pytest.fixture
def job_id(engine):
    with Session(engine) as s:
        room = Room(room_number=f"R{uuid.uuid4().hex[:4]}", floor="1")
        s.add(room); s.commit(); s.refresh(room)
        job = InferenceJob(room_id=room.id, video_filename="live", video_path="camera:0", status="live")
        s.add(job); s.commit(); s.refresh(job)
        return str(job.id)


def count(engine, model):
    with Session(engine) as s:
        return len(s.exec(select(model)).all())


def test_outbox_enqueue_pending_flush_order():
    outbox.enqueue("k", {"n": 1}); outbox.enqueue("k", {"n": 2})
    assert outbox.pending() == 2
    seen = []
    assert outbox.flush(lambda kind, p: seen.append(p["n"])) == 2
    assert seen == [1, 2] and outbox.pending() == 0


def test_flush_stops_at_first_failure_and_keeps_the_rest():
    outbox.enqueue("k", {"n": 1}); outbox.enqueue("k", {"n": 2})
    def boom(kind, p): raise RuntimeError("db down")
    assert outbox.flush(boom) == 0 and outbox.pending() == 2


def test_event_is_written_normally_when_database_is_up(engine, job_id):
    eid = db_writer.write_live_fall_event(job_id, None, None, 0.9, datetime.now(timezone.utc))
    assert count(engine, FallEvent) == 1 and count(engine, Alert) == 1 and outbox.pending() == 0
    with Session(engine) as s:
        assert str(s.exec(select(FallEvent)).one().id) == eid


def test_event_is_queued_when_database_is_down_then_replayed(engine, job_id, monkeypatch):
    real_engine = engine

    def down():
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(db_writer, "_engine", down)
    eid = db_writer.write_live_fall_event(job_id, None, None, 0.8, datetime.now(timezone.utc))
    assert outbox.pending() == 1 and db_writer.outbox_pending() == 1
    assert db_writer.flush_outbox() == 0 and outbox.pending() == 1       # still down: kept

    monkeypatch.setattr(db_writer, "_engine", lambda: real_engine)       # database is back
    assert db_writer.flush_outbox() == 1 and outbox.pending() == 0
    with Session(real_engine) as s:
        ev = s.exec(select(FallEvent)).one()
        assert str(ev.id) == eid                                          # same id as returned earlier
        assert len(s.exec(select(Alert).where(Alert.fall_event_id == ev.id)).all()) == 1


def test_replaying_the_same_event_twice_does_not_duplicate(engine, job_id):
    payload = {"event_id": str(uuid.uuid4()), "alert_id": str(uuid.uuid4()), "job_id": job_id,
               "room_id": None, "bed_id": None, "confidence": 0.7,
               "detected_at": datetime.now(timezone.utc).isoformat()}
    db_writer._write_fall_event_now(payload)
    db_writer._write_fall_event_now(payload)
    assert count(engine, FallEvent) == 1 and count(engine, Alert) == 1


def test_patient_id_is_stored_and_survives_the_outbox(engine, job_id, monkeypatch):
    from models import Patient
    with Session(engine) as s:
        pat = Patient(patient_code="P-0001", name="Demo", age=70, condition="x")
        s.add(pat); s.commit(); s.refresh(pat)
        pid = str(pat.id)

    db_writer.write_live_fall_event(job_id, None, None, 0.9, datetime.now(timezone.utc), pid)
    with Session(engine) as s:
        assert str(s.exec(select(FallEvent)).one().patient_id) == pid

    real = engine
    monkeypatch.setattr(db_writer, "_engine", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    db_writer.write_live_fall_event(job_id, None, None, 0.8, datetime.now(timezone.utc), pid)   # queued
    monkeypatch.setattr(db_writer, "_engine", lambda: real)
    assert db_writer.flush_outbox() == 1
    with Session(engine) as s:
        assert {str(e.patient_id) for e in s.exec(select(FallEvent)).all()} == {pid}
