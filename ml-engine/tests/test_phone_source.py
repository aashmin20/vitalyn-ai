"""PhoneSource / registry and the live pipeline fed by a phone link."""
import threading
import time

import cv2
import numpy as np
import pytest

from phone_source import PhoneSource, PhoneRegistry, closed_source
from live_pipeline import LiveSession, make_capture
from streaming_detector import StreamingFallDetector
from tests.test_live_pipeline import FakePose, FakeClassifier, FakeDB


def jpeg(value=128, w=64, h=48):
    ok, buf = cv2.imencode(".jpg", np.full((h, w, 3), value, dtype=np.uint8))
    assert ok
    return buf.tobytes()


def test_push_and_read_returns_newest_frame_once():
    s = PhoneSource("t")
    assert s.push_jpeg(jpeg(10)) and s.push_jpeg(jpeg(200))
    ok, frame = s.read(timeout=0.1)
    assert ok and frame.shape == (48, 64, 3) and frame.mean() > 150      # newest frame wins
    assert s.read(timeout=0.05) == (False, None)                         # already consumed
    assert s.frames_received == 2


def test_rejects_garbage_and_oversized_frames():
    s = PhoneSource("t")
    assert s.push_jpeg(b"") is False
    assert s.push_jpeg(b"not a jpeg") is False
    assert s.push_jpeg(b"\xff" * 2_500_000) is False
    assert s.frames_received == 0


def test_read_blocks_until_frame_arrives():
    s = PhoneSource("t")
    threading.Timer(0.1, lambda: s.push_jpeg(jpeg())).start()
    ok, frame = s.read(timeout=2.0)
    assert ok and frame is not None


def test_close_unblocks_and_reports_closed():
    s = PhoneSource("t")
    assert s.isOpened()
    threading.Timer(0.05, s.close).start()
    assert s.read(timeout=2.0) == (False, None)
    assert not s.isOpened()
    assert not closed_source().isOpened()


def test_registry_create_get_remove():
    r = PhoneRegistry()
    s = r.create()
    assert r.get(s.token) is s and len(s.token) >= 16
    r.remove(s.token)
    assert r.get(s.token) is None and not s.isOpened()


def test_unused_links_expire_but_used_links_do_not():
    r = PhoneRegistry(ttl_s=0.05)
    unused, used = r.create(), r.create()
    used.set_connected(True)
    time.sleep(0.1)
    assert r.get(unused.token) is None
    assert r.get(used.token) is used


def test_make_capture_resolves_phone_links(monkeypatch):
    import phone_source
    reg = PhoneRegistry()
    monkeypatch.setattr(phone_source, "_registry", reg)
    s = reg.create()
    assert make_capture(f"phone:{s.token}") is s
    assert not make_capture("phone:does-not-exist").isOpened()


def test_live_session_runs_on_phone_frames_and_ends_link(monkeypatch):
    import phone_source
    reg = PhoneRegistry()
    monkeypatch.setattr(phone_source, "_registry", reg)
    src = reg.create()
    src.set_connected(True)
    stop = threading.Event()

    def phone():
        while not stop.is_set():
            src.push_jpeg(jpeg(90, 320, 240))
            time.sleep(0.05)

    threading.Thread(target=phone, daemon=True).start()
    clf = FakeClassifier(0.05)
    det = StreamingFallDetector(clf, seq_len=4, step=2, min_consecutive=1, cooldown_windows=1)
    db = FakeDB()
    s = LiveSession("room", f"phone:{src.token}", pose=FakePose(), classifier=clf, detector=det, sample_fps=20, db=db)
    s.start()
    try:
        t0 = time.time()
        while s.samples < 8 and time.time() - t0 < 10:
            time.sleep(0.1)
        assert s.samples >= 8 and s.status()["person_detected"] is True
        assert s.status()["source"] == "phone link"          # token is not exposed
    finally:
        stop.set()
        s.stop()
    assert reg.get(src.token) is None                        # link dies with the session
    assert db.completed == ["job-1"]


def test_unknown_phone_link_cannot_start():
    s = LiveSession("room", "phone:nope", pose=FakePose(), classifier=FakeClassifier(0.1), db=FakeDB())
    from live_pipeline import CameraError
    with pytest.raises(CameraError) as e:
        s.start()
    assert "phone link" in str(e.value).lower()
