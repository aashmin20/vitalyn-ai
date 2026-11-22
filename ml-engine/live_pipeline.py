"""
live_pipeline.py — real-time fall detection from a camera (or video source).

One LiveSession = one camera. Two threads so slow inference never stalls video:

  capture   reads frames, keeps only the newest, draws the overlay from the most
            recent inference result and publishes a JPEG for the MJPEG stream.
  inference samples at SAMPLE_FPS (same rate the BiLSTM was trained on), runs the
            existing YOLOv8n-pose -> BiLSTM (+ aspect-ratio heuristic) pipeline and
            writes occupancy / fall events to the database.

Everything raised here is a *potential* fall and needs human verification.
No raw video is stored; only occupancy rows, fall events and alerts.

`source` may be a webcam index ("0"), a file path or a URL (RTSP/HTTP), so the
same code path is testable with a recorded video.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# OpenCV cannot show the macOS camera-permission prompt from a worker thread.
# Permission must already be granted to the app that launched the backend
# (see scripts/check_camera.py); this just silences the misleading retry message.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import cv2
import numpy as np

from pose_extractor import PoseExtractor, SAMPLE_FPS
from bilstm_model import FallClassifier
from fall_heuristic import PostureTransitionDetector, person_box
from streaming_detector import StreamingFallDetector, TARGET_SEQ_LEN
import db_writer

log = logging.getLogger("vitalyn.live")

STREAM_MAX_WIDTH = 640
JPEG_QUALITY = 70
OCCUPANCY_INTERVAL_S = 5.0     # one occupancy record per interval
OUTBOX_FLUSH_S = 15.0           # retry queued fall events this often
EVENT_MIN_GAP_S = 10.0         # merge BiLSTM + heuristic triggers closer than this
ALARM_OVERLAY_S = 10.0
MAX_READ_FAILURES = 30
MAX_RECONNECTS = 3
KPT_CONF_MIN = 0.3

# COCO-17 skeleton edges
_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
]


NETWORK_TIMEOUT_MS = 5000


def make_capture(source: Union[int, str]) -> "cv2.VideoCapture":
    """Open a camera index, file or network stream. Network streams get open/read
    timeouts so an unreachable phone fails in seconds instead of hanging the request."""
    if isinstance(source, str) and source.startswith("phone:"):
        # A phone browser streaming frames to this Mac (see phone_source.py).
        from phone_source import get_registry, closed_source
        return get_registry().get(source[len("phone:"):]) or closed_source()
    if isinstance(source, str) and "://" in source:
        return cv2.VideoCapture(
            source, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, NETWORK_TIMEOUT_MS,
             cv2.CAP_PROP_READ_TIMEOUT_MSEC, NETWORK_TIMEOUT_MS],
        )
    return cv2.VideoCapture(source)


def grab_snapshot(index: int, max_width: int = 480, warmup_s: float = 2.5) -> bytes:
    """One JPEG from camera `index`, held in memory only (never written to disk).
    Used by the 'identify cameras' step; cameras need a moment to warm up."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        raise CameraError(f"Cannot open camera {index}.")
    frame = None
    deadline = time.monotonic() + warmup_s
    while time.monotonic() < deadline:
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()
    if frame is None:
        raise CameraError(f"Camera {index} opened but gave no frames.")
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        raise CameraError("Could not encode snapshot.")
    return buf.tobytes()


class CameraError(RuntimeError):
    """The camera/source could not be opened or was lost."""


def parse_source(raw: Union[str, int]) -> Union[int, str]:
    if isinstance(raw, int):
        return raw
    raw = str(raw).strip()
    return int(raw) if raw.isdigit() else raw


def draw_overlay(
    frame: np.ndarray,
    pixel_kpts: Optional[np.ndarray],
    status_text: str,
    alarm: bool,
) -> np.ndarray:
    out = frame.copy()
    if pixel_kpts is not None:
        for a, b in _EDGES:
            if pixel_kpts[a, 2] >= KPT_CONF_MIN and pixel_kpts[b, 2] >= KPT_CONF_MIN:
                cv2.line(out, (int(pixel_kpts[a, 0]), int(pixel_kpts[a, 1])),
                         (int(pixel_kpts[b, 0]), int(pixel_kpts[b, 1])), (80, 220, 120), 2)
        for x, y, c in pixel_kpts:
            if c >= KPT_CONF_MIN:
                cv2.circle(out, (int(x), int(y)), 3, (60, 160, 255), -1)

    colour = (40, 40, 220) if alarm else (30, 30, 30)
    cv2.rectangle(out, (0, 0), (out.shape[1], 28), colour, -1)
    cv2.putText(out, status_text, (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA)
    if alarm:
        cv2.rectangle(out, (0, 0), (out.shape[1] - 1, out.shape[0] - 1), (40, 40, 220), 4)
    return out


MAX_SESSIONS = int(os.getenv("VITALYN_MAX_SESSIONS", "3"))


class SessionLimitError(RuntimeError):
    """Too many cameras are being monitored at once for this machine."""


class CameraInUseError(RuntimeError):
    """That physical camera is already used by another monitoring session."""


class AlreadyMonitoredError(RuntimeError):
    """This patient (or room) already has a running session."""


# One pose model and one fall classifier are shared by every session (memory on an 8 GB Mac),
# and a lock serialises their use: the models are not safe to call from several threads at once.
_inference_lock = threading.Lock()
_shared: Dict[str, Any] = {}


class _LockedPose:
    def __init__(self, pose):
        self._pose = pose

    def extract_frame_detailed(self, frame):
        with _inference_lock:
            return self._pose.extract_frame_detailed(frame)


class _LockedClassifier:
    def __init__(self, clf):
        self._clf = clf

    def predict(self, sequence):
        with _inference_lock:
            return self._clf.predict(sequence)


def shared_pose():
    with _inference_lock:
        if "pose" not in _shared:
            _shared["pose"] = PoseExtractor()
        pose = _shared["pose"]
    return _LockedPose(pose)


def shared_classifier():
    with _inference_lock:
        if "clf" not in _shared:
            _shared["clf"] = FallClassifier()
        clf = _shared["clf"]
    return _LockedClassifier(clf)


class LiveSession:
    def __init__(
        self,
        room_id: str,
        source: Union[str, int] = 0,
        *,
        pose: Any = None,
        classifier: Any = None,
        detector: Any = None,
        sample_fps: float = SAMPLE_FPS,
        db: Any = db_writer,
        patient_id: Optional[str] = None,
    ):
        self.room_id = room_id
        self.patient_id = patient_id
        self.source = parse_source(source)
        self._pose = pose or shared_pose()
        self._clf = classifier or shared_classifier()
        self._db = db

        self._detector = detector or StreamingFallDetector(self._clf)
        self._sample_fps = sample_fps
        self._ar = PostureTransitionDetector()

        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_file = isinstance(self.source, str) and os.path.exists(self.source)

        # shared state
        self._lock = threading.Lock()
        self._frame_cv = threading.Condition()
        self._raw_frame: Optional[np.ndarray] = None
        self._jpeg: Optional[bytes] = None
        self._frame_id = 0
        self._overlay_kpts: Optional[np.ndarray] = None
        self._person = False
        self._alarm_until = 0.0
        self._subscribers: List["queue.Queue[dict]"] = []
        self.on_event: Optional[Any] = None      # set by the manager: relays events from every session

        self.state = "idle"
        self.error: Optional[str] = None
        self.job_id: Optional[str] = None
        self.bed_id: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.frames_captured = 0
        self.samples = 0
        self.capture_fps = 0.0
        self.inference_fps = 0.0
        self.events_count = 0
        self.last_event: Optional[Dict[str, Any]] = None
        self._last_event_mono = -1e9

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.state = "starting"
        self._cap = self._open()
        self.job_id = self._db.create_live_job(self.room_id, str(self.source), self.patient_id)
        self.bed_id = self._db.get_or_create_default_bed(self.room_id)
        self.started_at = datetime.now(timezone.utc)
        self.state = "live"
        self._publish({"type": "status", "state": self.state})

        for target, name in ((self._capture_loop, "live-capture"),
                             (self._inference_loop, "live-inference")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        log.info("Live session started: room=%s source=%s job=%s",
                 self.room_id, self.source, self.job_id)

    def stop(self) -> None:
        if self.state in ("stopped",):
            return
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if isinstance(self.source, str) and self.source.startswith("phone:"):
            from phone_source import get_registry
            get_registry().remove(self.source[len("phone:"):])     # the phone link dies with the session
        if self.job_id:
            if self.state == "error":
                self._db.mark_job_failed(self.job_id, self.error or "Live session error")
            else:
                self._db.mark_job_completed(self.job_id)
        if self.state != "error":
            self.state = "stopped"
        self._publish({"type": "status", "state": self.state, "error": self.error})
        with self._frame_cv:
            self._frame_cv.notify_all()
        log.info("Live session stopped (job %s)", self.job_id)

    @property
    def running(self) -> bool:
        return self.state in ("starting", "live")

    # ── source handling ──────────────────────────────────────────────────────

    def _open(self) -> cv2.VideoCapture:
        cap = make_capture(self.source)
        if not cap.isOpened():
            cap.release()
            hint = ""
            if isinstance(self.source, str) and self.source.startswith("phone:"):
                hint = " The phone link has expired or was never opened. Create a new phone link."
            elif isinstance(self.source, str) and "://" in self.source:
                hint = (" Check that the phone/camera app is streaming, the URL is correct and "
                        "the phone is on the same Wi-Fi as this Mac.")
            elif isinstance(self.source, int):
                hint = (" On macOS the app that launched the backend (e.g. Terminal) "
                        "needs Camera permission: run `python3 scripts/check_camera.py` "
                        "from that app once, allow access, then restart the backend.")
            self.state = "error"
            self.error = f"Cannot open camera source {self.source!r}.{hint}"
            raise CameraError(self.error)
        return cap

    # ── capture thread ───────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        cap = self._cap
        native_fps = (cap.get(cv2.CAP_PROP_FPS) or 0) if cap else 0
        frame_period = 1.0 / native_fps if (self._is_file and native_fps > 0) else 0.0
        failures = 0
        reconnects = 0
        t_fps = time.monotonic()
        n_fps = 0

        while not self._stop.is_set():
            tick = time.monotonic()
            ok, frame = cap.read() if cap else (False, None)
            if not ok or frame is None:
                if self._is_file:
                    self._finish("Video source ended.")
                    return
                failures += 1
                if failures >= MAX_READ_FAILURES:
                    if reconnects >= MAX_RECONNECTS:
                        self._fail("Camera disconnected (no frames).")
                        return
                    reconnects += 1
                    log.warning("Camera read failing, reconnect %d/%d", reconnects, MAX_RECONNECTS)
                    cap.release()
                    time.sleep(1.0)
                    cap = make_capture(self.source)
                    self._cap = cap
                    failures = 0
                time.sleep(0.03)
                continue
            failures = 0

            self.frames_captured += 1
            n_fps += 1
            now = time.monotonic()
            if now - t_fps >= 1.0:
                self.capture_fps = round(n_fps / (now - t_fps), 1)
                t_fps, n_fps = now, 0

            with self._lock:
                self._raw_frame = frame
                kpts = self._overlay_kpts
                alarm = now < self._alarm_until
                text = self._status_text(alarm)

            shown = draw_overlay(frame, kpts, text, alarm)
            h, w = shown.shape[:2]
            if w > STREAM_MAX_WIDTH:
                shown = cv2.resize(shown, (STREAM_MAX_WIDTH, int(h * STREAM_MAX_WIDTH / w)))
            ok_enc, buf = cv2.imencode(".jpg", shown, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok_enc:
                with self._frame_cv:
                    self._jpeg = buf.tobytes()
                    self._frame_id += 1
                    self._frame_cv.notify_all()

            if frame_period:
                time.sleep(max(0.0, frame_period - (time.monotonic() - tick)))

    def _detector_len(self) -> int:
        return getattr(self._detector, "_seq_len", TARGET_SEQ_LEN)

    def _status_text(self, alarm: bool) -> str:
        if alarm:
            return "POTENTIAL FALL - human review required"
        if not self._detector.ready:
            return (f"Warming up {self._detector.window_fill}/{self._detector_len()}"
                    f" | {'person' if self._person else 'no person'}")
        if getattr(self._detector, "guarded", False):
            return "Fall model paused - person not in view"
        return "Person detected" if self._person else "No person in view"

    # ── inference thread ─────────────────────────────────────────────────────

    def _inference_loop(self) -> None:
        period = 1.0 / self._sample_fps
        occ_start = time.monotonic()
        last_flush = time.monotonic()
        occ_total = 0
        occ_person = 0
        t_fps = time.monotonic()
        n_fps = 0

        while not self._stop.is_set():
            tick = time.monotonic()
            with self._lock:
                frame = None if self._raw_frame is None else self._raw_frame.copy()
            if frame is None:
                time.sleep(0.05)
                continue

            try:
                vec, pix = self._pose.extract_frame_detailed(frame)
            except Exception as exc:  # keep the session alive on a bad frame
                log.exception("Pose extraction failed: %s", exc)
                time.sleep(period)
                continue

            person = vec is not None
            self.samples += 1
            with self._lock:
                self._overlay_kpts = pix
                self._person = person

            occ_total += 1
            occ_person += 1 if person else 0

            signal = self._detector.push(vec if person else np.zeros(34, dtype=np.float32))
            if signal is not None:
                self._raise_fall(signal.confidence, "bilstm")

            ar, box_h = person_box(pix, KPT_CONF_MIN)
            is_ar, ar_conf = self._ar.update(ar, box_h)
            if is_ar:
                self._raise_fall(ar_conf, "heuristic")

            now = time.monotonic()
            n_fps += 1
            if now - t_fps >= 2.0:
                self.inference_fps = round(n_fps / (now - t_fps), 1)
                t_fps, n_fps = now, 0

            if now - last_flush >= OUTBOX_FLUSH_S:
                last_flush = now
                flush = getattr(self._db, "flush_outbox", None)
                if flush is not None:
                    try:
                        flush()
                    except Exception as exc:
                        log.warning("Outbox flush failed: %s", exc)

            if now - occ_start >= OCCUPANCY_INTERVAL_S and occ_total:
                self._write_occupancy(occ_person, occ_total)
                occ_start, occ_total, occ_person = now, 0, 0

            time.sleep(max(0.0, period - (time.monotonic() - tick)))

        if occ_total:
            self._write_occupancy(occ_person, occ_total)

    def _write_occupancy(self, person_samples: int, total: int) -> None:
        # Status is the majority of sampled frames; confidence is the share of
        # frames in the interval that agree with it (a measured fraction, not a model score).
        occupied = person_samples * 2 >= total
        agree = person_samples if occupied else total - person_samples
        try:
            self._db.write_live_occupancy(
                self.job_id, self.bed_id,
                "occupied" if occupied else "vacant",
                round(agree / total, 4),
                datetime.now(timezone.utc),
            )
        except Exception as exc:
            log.error("Failed to write live occupancy: %s", exc)

    def _raise_fall(self, confidence: float, source: str) -> None:
        now = time.monotonic()
        if now - self._last_event_mono < EVENT_MIN_GAP_S:
            return
        self._last_event_mono = now
        detected_at = datetime.now(timezone.utc)
        try:
            event_id = self._db.write_live_fall_event(
                self.job_id, self.room_id, self.bed_id, confidence, detected_at, self.patient_id,
            )
        except Exception as exc:
            log.error("Failed to write live fall event: %s", exc)
            return
        self.events_count += 1
        self.last_event = {
            "id": event_id,
            "confidence": confidence,
            "source": source,
            "detected_at": detected_at.isoformat().replace("+00:00", "Z"),
        }
        with self._lock:
            self._alarm_until = now + ALARM_OVERLAY_S
        self._publish({"type": "fall_detected", **self.last_event})
        log.warning("POTENTIAL FALL (%s, conf=%.2f) event=%s", source, confidence, event_id)

    # ── termination helpers ──────────────────────────────────────────────────

    def _finish(self, message: str) -> None:
        log.info(message)
        threading.Thread(target=self.stop, daemon=True).start()

    def _fail(self, message: str) -> None:
        log.error(message)
        self.error = message
        self.state = "error"
        threading.Thread(target=self.stop, daemon=True).start()

    # ── outputs ──────────────────────────────────────────────────────────────

    def next_jpeg(self, last_id: int, timeout: float = 1.0) -> tuple[Optional[bytes], int]:
        """Block until a frame newer than last_id exists (or timeout)."""
        with self._frame_cv:
            if self._frame_id <= last_id:
                self._frame_cv.wait(timeout)
            return self._jpeg, self._frame_id

    def subscribe(self) -> "queue.Queue[dict]":
        q: "queue.Queue[dict]" = queue.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[dict]") -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _publish(self, message: Dict[str, Any]) -> None:
        message = {**message, "patient_id": self.patient_id, "job_id": self.job_id}
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except queue.Full:
                pass
        if self.on_event is not None:
            try:
                self.on_event(message)
            except Exception:
                log.exception("Event relay failed")

    def status(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "source": "phone link" if str(self.source).startswith("phone:") else str(self.source),
            "room_id": self.room_id,
            "patient_id": self.patient_id,
            "job_id": self.job_id,
            "started_at": self.started_at.isoformat().replace("+00:00", "Z") if self.started_at else None,
            "capture_fps": self.capture_fps,
            "inference_fps": self.inference_fps,
            "frames_captured": self.frames_captured,
            "samples": self.samples,
            "person_detected": self._person,
            "window_fill": self._detector.window_fill,
            "window_required": self._detector_len(),
            "last_probability": self._detector.last_probability,
            "model_guarded": bool(getattr(self._detector, "guarded", False)),
            "events_count": self.events_count,
            "last_event": self.last_event,
            "error": self.error,
        }


# ── process-wide manager (one camera at a time on an 8 GB machine) ───────────

class LiveManager:
    """
    Runs several monitoring sessions at once, one per patient (or per room for ad-hoc sessions).
    Limits: MAX_SESSIONS cameras in total, and a physical camera can serve only one session.
    """

    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self._sessions: Dict[str, LiveSession] = {}
        self._last: Optional[LiveSession] = None
        self._subscribers: List["queue.Queue[dict]"] = []

    @staticmethod
    def _key(room_id: str, patient_id: Optional[str]) -> str:
        return patient_id or f"room:{room_id}"

    def _running(self) -> List[LiveSession]:
        return [s for s in self._sessions.values() if s.running]

    def start(self, room_id: str, source: Union[str, int] = 0, **kwargs) -> LiveSession:
        patient_id = kwargs.get("patient_id")
        key = self._key(room_id, patient_id)
        with self._lock:
            existing = self._sessions.get(key)
            if existing is not None and existing.running:
                raise AlreadyMonitoredError("This patient is already being monitored." if patient_id
                                            else "This room already has a live session.")
            running = self._running()
            if len(running) >= self.max_sessions:
                raise SessionLimitError(
                    f"At most {self.max_sessions} cameras can be monitored at once on this machine. "
                    "Stop one first, or raise VITALYN_MAX_SESSIONS."
                )
            parsed = parse_source(source)
            if isinstance(parsed, int):
                clash = next((s for s in running if s.source == parsed), None)
                if clash is not None:
                    raise CameraInUseError("That camera is already used by another monitored patient.")
            session = LiveSession(room_id, source, **kwargs)
            session.on_event = self._relay
            session.start()                  # raises CameraError if the source can't be opened
            self._sessions[key] = session
            self._last = session
            return session

    def get(self, patient_id: str) -> Optional[LiveSession]:
        s = self._sessions.get(patient_id)
        return s if s is not None and s.running else None

    def running_sessions(self) -> List[LiveSession]:
        return self._running()

    @property
    def session(self) -> Optional[LiveSession]:
        """The most recently started running session (kept for single-camera callers)."""
        running = self._running()
        if not running:
            return self._last
        return self._last if self._last in running else running[-1]

    def stop(self, patient_id: Optional[str] = None) -> bool:
        """Stop one patient's session, or every running session when no patient is given."""
        with self._lock:
            targets = [self._sessions[patient_id]] if patient_id in self._sessions else [] if patient_id else self._running()
            targets = [s for s in targets if s.running]
        for s in targets:
            s.stop()
        return bool(targets)

    # events from every session (fall alarms must reach the dashboard whichever patient is on screen)
    def subscribe(self) -> "queue.Queue[dict]":
        q: "queue.Queue[dict]" = queue.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[dict]") -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _relay(self, message: Dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except queue.Full:
                pass

    def status(self) -> Dict[str, Any]:
        sessions = [s.status() for s in self._running()]
        if not sessions:
            return {"state": "idle", "sessions": [], "max_sessions": self.max_sessions}
        # Top-level fields describe the most recent session, so older single-camera callers keep working.
        primary = next((st for st in sessions if st.get("job_id") == getattr(self._last, "job_id", None)), sessions[-1])
        return {**primary, "sessions": sessions, "max_sessions": self.max_sessions}


_manager = LiveManager()


def get_manager() -> LiveManager:
    return _manager
