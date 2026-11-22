"""LiveSession tests using a synthetic video file as the source and fake model/DB."""
import os
import time
import numpy as np
import cv2
import pytest

from live_pipeline import (
    LiveSession, LiveManager, CameraError, parse_source, draw_overlay,
)
from streaming_detector import StreamingFallDetector


class FakePose:
    """Always 'sees' a person; keypoints spread wide and flat so AR is high."""

    def __init__(self, person=True):
        self.person = person

    def extract_frame_detailed(self, frame):
        if not self.person:
            return None, None
        pix = np.zeros((17, 3), dtype=np.float32)
        pix[:, 0] = np.linspace(20, 300, 17)
        pix[:, 1] = 100.0 + np.arange(17) * 0.5
        pix[:, 2] = 0.9
        vec = np.zeros(34, dtype=np.float32)
        vec[0::2] = pix[:, 0] / 320
        vec[1::2] = pix[:, 1] / 240
        return vec, pix


class FakeClassifier:
    def __init__(self, prob):
        self.prob = prob

    def predict(self, seq):
        return self.prob, self.prob >= 0.45


class FakeDB:
    def __init__(self):
        self.occupancy, self.events, self.completed, self.failed = [], [], [], []

    def create_live_job(self, room_id, label, patient_id=None):
        self.patient_ids = getattr(self, 'patient_ids', []) + [patient_id]
        return "job-1"
    def get_or_create_default_bed(self, room_id): return "bed-1"
    def bed_for_session(self, room_id, patient_id=None): return "bed-1"
    def write_live_occupancy(self, job, bed, status, conf, at): self.occupancy.append((status, conf))
    def write_live_fall_event(self, job, room, bed, conf, at, patient_id=None):
        self.events.append(conf); self.event_patients = getattr(self, 'event_patients', []) + [patient_id]
        return f"evt-{len(self.events)}"
    def mark_job_completed(self, job): self.completed.append(job)
    def mark_job_failed(self, job, msg): self.failed.append((job, msg))


@pytest.fixture
def video(tmp_path):
    path = str(tmp_path / "clip.mp4")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
    for i in range(50):  # 2.5 s
        w.write(np.full((240, 320, 3), i * 4 % 255, dtype=np.uint8))
    w.release()
    return path


def make_session(video, prob, person=True, db=None):
    clf = FakeClassifier(prob)
    det = StreamingFallDetector(clf, seq_len=4, step=2, min_consecutive=1, cooldown_windows=1)
    return LiveSession(
        "room-1", video, pose=FakePose(person), classifier=clf, detector=det,
        sample_fps=20, db=db or FakeDB(),
    )


def wait_stopped(s, timeout=15):
    t0 = time.time()
    while s.state != "stopped" and time.time() - t0 < timeout:
        time.sleep(0.05)
    assert s.state == "stopped", s.status()


def test_parse_source():
    assert parse_source("0") == 0
    assert parse_source(2) == 2
    assert parse_source("rtsp://cam/stream") == "rtsp://cam/stream"


def test_draw_overlay_does_not_mutate_input():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    out = draw_overlay(frame, None, "hello", alarm=True)
    assert frame.sum() == 0 and out.sum() > 0


def test_unopenable_source_raises_and_reports(tmp_path):
    s = LiveSession("r", str(tmp_path / "missing.mp4"), pose=FakePose(), classifier=FakeClassifier(0.1), db=FakeDB())
    with pytest.raises(CameraError):
        s.start()
    assert s.state == "error" and "Cannot open" in s.error


def test_fall_signal_creates_event_and_publishes(video):
    db = FakeDB()
    s = make_session(video, prob=0.95, db=db)
    q = s.subscribe()
    s.start()
    wait_stopped(s)
    assert db.events, "expected at least one fall event"
    assert s.events_count == len(db.events) == 1      # gap rule merges repeated triggers
    assert s.last_event["id"] == "evt-1"
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    assert any(m["type"] == "fall_detected" for m in msgs)
    assert db.completed == ["job-1"] and not db.failed


def test_no_fall_when_classifier_says_normal(video):
    db = FakeDB()
    s = make_session(video, prob=0.05, db=db)
    s.start()
    wait_stopped(s)
    # the flat-pose heuristic may still fire; the BiLSTM path must not
    assert all(e < 0.95 for e in db.events)


def test_occupancy_written_and_vacant_when_no_person(video):
    db = FakeDB()
    s = make_session(video, prob=0.05, person=False, db=db)
    s.start()
    wait_stopped(s)
    assert db.occupancy and all(status == "vacant" for status, _ in db.occupancy)
    assert db.events == []


def test_jpeg_frames_are_produced(video):
    s = make_session(video, prob=0.05)
    s.start()
    jpeg, fid = s.next_jpeg(0, timeout=3)
    assert jpeg is not None and jpeg[:2] == b"\xff\xd8" and fid > 0
    wait_stopped(s)


def test_manager_rejects_second_session(video):
    m = LiveManager()
    clf = FakeClassifier(0.05)
    kw = dict(pose=FakePose(), classifier=clf, sample_fps=20, db=FakeDB())
    m.start("room", video, **kw)
    with pytest.raises(RuntimeError):
        m.start("room", video, **kw)
    m.stop()
    assert m.status()["state"] in ("idle", "live")


def test_camera_disconnect_ends_in_error_and_fails_job(monkeypatch, tmp_path):
    """A source that opens but then never delivers frames -> error state, job failed."""
    import live_pipeline

    class DeadCapture:
        def isOpened(self): return True
        def read(self): return False, None
        def get(self, prop): return 0
        def release(self): pass

    monkeypatch.setattr(live_pipeline.cv2, "VideoCapture", lambda src: DeadCapture())
    monkeypatch.setattr(live_pipeline, "MAX_READ_FAILURES", 2)
    monkeypatch.setattr(live_pipeline, "MAX_RECONNECTS", 1)
    db = FakeDB()
    s = LiveSession("room", 0, pose=FakePose(), classifier=FakeClassifier(0.1), db=db)
    s.start()
    t0 = time.time()
    while s.state != "error" and time.time() - t0 < 15:
        time.sleep(0.1)
    assert s.state == "error" and "disconnected" in s.error
    t0 = time.time()
    while not db.failed and time.time() - t0 < 10:
        time.sleep(0.1)
    assert db.failed and db.failed[0][0] == "job-1"


def test_session_attributes_job_and_events_to_the_patient(video):
    db = FakeDB()
    clf = FakeClassifier(0.95)
    det = StreamingFallDetector(clf, seq_len=4, step=2, min_consecutive=1, cooldown_windows=1)
    s = LiveSession("room-1", video, pose=FakePose(), classifier=clf, detector=det, sample_fps=20, db=db,
                    patient_id="patient-123")
    s.start()
    wait_stopped(s)
    assert db.patient_ids == ["patient-123"]
    assert db.event_patients and set(db.event_patients) == {"patient-123"}
    assert s.status()["patient_id"] == "patient-123"


# ── several patients at once ─────────────────────────────────────────────────

import live_pipeline
from live_pipeline import AlreadyMonitoredError, CameraInUseError, SessionLimitError


def _kw(db=None, prob=0.05):
    return dict(pose=FakePose(), classifier=FakeClassifier(prob), sample_fps=20, db=db or FakeDB())


def test_two_patients_are_monitored_at_the_same_time(video):
    m = LiveManager(max_sessions=3)
    a = m.start("room-1", video, patient_id="A", **_kw())
    b = m.start("room-2", video, patient_id="B", **_kw())
    assert a.running and b.running and a is not b
    assert m.get("A") is a and m.get("B") is b and len(m.running_sessions()) == 2
    st = m.status()
    assert st["state"] == "live" and {s["patient_id"] for s in st["sessions"]} == {"A", "B"}
    m.stop()
    assert m.running_sessions() == []


def test_stopping_one_patient_leaves_the_other_running(video):
    m = LiveManager()
    m.start("r1", video, patient_id="A", **_kw())
    m.start("r2", video, patient_id="B", **_kw())
    assert m.stop(patient_id="A") is True
    assert m.get("A") is None and m.get("B") is not None
    assert m.stop(patient_id="A") is False                      # already stopped
    assert m.stop(patient_id="nobody") is False
    m.stop()


def test_same_patient_cannot_be_started_twice(video):
    m = LiveManager()
    m.start("r1", video, patient_id="A", **_kw())
    with pytest.raises(AlreadyMonitoredError):
        m.start("r1", video, patient_id="A", **_kw())
    m.stop()


def test_session_limit_is_enforced(video):
    m = LiveManager(max_sessions=2)
    m.start("r1", video, patient_id="A", **_kw())
    m.start("r2", video, patient_id="B", **_kw())
    with pytest.raises(SessionLimitError) as e:
        m.start("r3", video, patient_id="C", **_kw())
    assert "At most 2" in str(e.value)
    m.stop(patient_id="A")
    m.start("r3", video, patient_id="C", **_kw())              # a free slot works again
    m.stop()


class _BlankCamera:
    def isOpened(self): return True
    def get(self, p): return 0
    def release(self): pass
    def read(self):
        time.sleep(0.03)
        return True, np.zeros((120, 160, 3), dtype=np.uint8)


def test_one_physical_camera_serves_only_one_patient(monkeypatch):
    monkeypatch.setattr(live_pipeline, "make_capture", lambda src: _BlankCamera())
    m = LiveManager()
    m.start("r1", 1, patient_id="A", **_kw())
    with pytest.raises(CameraInUseError):
        m.start("r2", 1, patient_id="B", **_kw())
    m.start("r2", 2, patient_id="B", **_kw())                   # a different camera is fine
    m.stop()


def test_events_from_every_session_reach_one_feed_tagged_with_the_patient(video):
    m = LiveManager()
    q = m.subscribe()
    m.start("r1", video, patient_id="A", **_kw(prob=0.95))
    m.start("r2", video, patient_id="B", **_kw(prob=0.95))
    deadline = time.time() + 15
    seen = set()
    while time.time() < deadline and seen != {"A", "B"}:
        try:
            msg = q.get(timeout=1)
        except Exception:
            continue
        if msg["type"] == "fall_detected":
            seen.add(msg["patient_id"])
    m.unsubscribe(q)
    m.stop()
    assert seen == {"A", "B"}


def test_models_are_shared_and_serialised():
    p1, p2 = live_pipeline.shared_pose(), live_pipeline.shared_pose()
    assert p1._pose is p2._pose                                  # one pose model for every session
    assert live_pipeline.shared_classifier()._clf is live_pipeline.shared_classifier()._clf
