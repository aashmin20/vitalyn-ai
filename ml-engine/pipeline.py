"""
pipeline.py — Main ML inference pipeline.

Two complementary fall signals:

1. BiLSTM (trained model, vitalyn_fall_bilstm.pt):
   - Processes windows of 30 normalised keypoint frames
   - Short videos (< 30 sampled frames) are zero-padded at the start so the
     classifier always runs; a warning is stored on the job record.
   - Feature format matches training notebook exactly (YOLOv8n-pose, 6 FPS, normalised)

2. Aspect Ratio Heuristic (rule-based):
   - Detects horizontal bounding box (person fallen on floor, still visible)
   - Fires when person bbox w/h > 1.1 for ≥ 4 consecutive frames
   - Provides secondary signal when person IS detected but posture indicates fall

Both signals generate FallEvents with their respective confidence scores.
All events are labelled "potential_fall" and require human verification per AGENTS.md.

Short-video behaviour
---------------------
Minimum recommended duration: TARGET_SEQ_LEN / SAMPLE_FPS = 30 / 6 = 5 seconds.
Videos shorter than that are padded so the BiLSTM still runs, but a warning is
attached to the completed job so the UI can inform the user that results may be
less reliable.  The job is never failed solely because of video length.
"""
from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone
from typing import List, Optional

import cv2
import numpy as np

BACKEND_PATH = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_PATH)

from pose_extractor import PoseExtractor, TARGET_SEQ_LEN, SAMPLE_FPS
from bilstm_model import FallClassifier
from fall_heuristic import PostureTransitionDetector, person_box
from db_writer import (
    mark_job_started,
    mark_job_completed,
    mark_job_failed,
    update_job_progress,
    write_job_warning,
    get_job_room_id,
    get_job_patient_id,
    get_or_create_default_bed,
    write_occupancy_records,
    write_fall_events,
)
from streaming_detector import person_coverage
from config import (
    MIN_PERSON_COVERAGE,
    FALL_THRESHOLD,
    FALL_MIN_CONSECUTIVE_WINDOWS,
    FALL_COOLDOWN_WINDOWS,
)

log = logging.getLogger("vitalyn.pipeline")

WINDOW_STEP = 15

# Minimum sampled frames needed for a full BiLSTM window
MIN_FRAMES_FOR_BILSTM = TARGET_SEQ_LEN  # 30 frames ≈ 5 s at 6 fps


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

class _OccupancyFrame:
    __slots__ = ("status", "confidence")

    def __init__(self, status: str, confidence: float):
        self.status = status
        self.confidence = confidence


class _FallEvent:
    __slots__ = ("start_frame", "end_frame", "confidence", "event_type")

    def __init__(self, start_frame: int, end_frame: int, confidence: float):
        self.start_frame = start_frame
        self.end_frame   = end_frame
        self.confidence  = confidence
        self.event_type  = "potential_fall"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_inference(job_id: str, video_path: str) -> bool:
    log.info("Starting inference for job %s — %s", job_id, video_path)
    try:
        mark_job_started(job_id)
        success = _run(job_id, video_path)
        if success:
            mark_job_completed(job_id)
            log.info("Job %s completed", job_id)
        return success
    except Exception as exc:
        log.exception("Job %s failed: %s", job_id, exc)
        mark_job_failed(job_id, str(exc))
        return False


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _run(job_id: str, video_path: str) -> bool:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    native_fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    video_start  = datetime.now(timezone.utc)

    # Sampling step — same as training notebook
    step = max(1, round(native_fps / SAMPLE_FPS))
    effective_fps = native_fps / step
    duration_secs = total_frames / native_fps if native_fps > 0 else 0.0
    min_duration  = MIN_FRAMES_FOR_BILSTM / SAMPLE_FPS  # 5.0 s

    log.info(
        "Video: %d frames @ %.1f fps, step=%d → %.1f effective fps, duration=%.1fs",
        total_frames, native_fps, step, effective_fps, duration_secs,
    )

    if duration_secs < min_duration:
        log.warning(
            "Short video (%.1fs < %.1fs minimum). Will zero-pad keypoints so "
            "BiLSTM still runs, but fall detection reliability is reduced.",
            duration_secs, min_duration,
        )

    pose        = PoseExtractor()
    clf         = FallClassifier()
    ar_detector = PostureTransitionDetector()

    room_id = get_job_room_id(job_id)
    patient_id = get_job_patient_id(job_id)
    bed_id  = get_or_create_default_bed(room_id) if room_id else None

    # ── Frame loop ──────────────────────────────────────────────────────────
    keypoint_stream: List[np.ndarray] = []
    occupancy_frames: List[_OccupancyFrame] = []
    ar_fall_events: List[_FallEvent] = []

    frame_idx = 0
    sampled   = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        if frame_idx % step != 0:
            continue

        sampled += 1

        if sampled % 50 == 0 and total_frames > 0:
            pct = min(90.0, (frame_idx / total_frames) * 100)
            update_job_progress(job_id, pct)

        kp, pix = pose.extract_frame_detailed(frame)

        if kp is not None:
            keypoint_stream.append(kp)
            occupancy_frames.append(_OccupancyFrame("occupied", 0.85))
        else:
            keypoint_stream.append(np.zeros(34, dtype=np.float32))
            occupancy_frames.append(_OccupancyFrame("vacant", 0.90))

        # Posture box from *pixel* keypoints (the normalised vector would distort
        # the aspect ratio by the video's own width/height).
        ar, box_h = person_box(pix)

        # Heuristic fall check per frame
        is_ar_fall, ar_conf = ar_detector.update(ar, box_h)
        if is_ar_fall:
            ar_fall_events.append(_FallEvent(
                start_frame=max(0, sampled - 4),
                end_frame=sampled,
                confidence=ar_conf,
            ))
            log.info("Posture-transition fall detected at sampled frame %d (conf=%.2f)", sampled, ar_conf)

    cap.release()

    if sampled == 0:
        raise RuntimeError("No frames could be read from video")

    occupied_count = sum(1 for f in occupancy_frames if f.status == "occupied")
    log.info("Sampled %d frames, %d with person detected", sampled, occupied_count)

    # ── Pad short keypoint stream so BiLSTM always runs ─────────────────────
    # Zero-pad at the start, matching pose_extractor and training notebook logic.
    warning_message: Optional[str] = None
    pad_needed = 0
    if len(keypoint_stream) < MIN_FRAMES_FOR_BILSTM:
        pad_needed = MIN_FRAMES_FOR_BILSTM - len(keypoint_stream)
        padding    = [np.zeros(34, dtype=np.float32)] * pad_needed
        keypoint_stream = padding + keypoint_stream
        warning_message = (
            f"Video is short ({duration_secs:.1f}s, {sampled} sampled frames). "
            f"Keypoints were zero-padded to {MIN_FRAMES_FOR_BILSTM} frames, so the "
            f"BiLSTM fall check is skipped for windows with too little person "
            f"coverage. Upload a video ≥{min_duration:.0f}s for reliable "
            f"fall detection."
        )
        log.warning(warning_message)

    # ── BiLSTM sliding-window fall classification ────────────────────────────
    # Frame indices from the BiLSTM refer to the padded stream; shift them back
    # so event times line up with the real video timeline.
    bilstm_fall_events = _shift_events(_classify_falls_bilstm(keypoint_stream, clf), pad_needed)
    log.info("BiLSTM fall events: %d  |  AR heuristic events: %d",
             len(bilstm_fall_events), len(ar_fall_events))

    # Merge both signals — deduplicate overlapping events
    all_fall_events = _merge_events(bilstm_fall_events + ar_fall_events)
    log.info("Total fall events after merge: %d", len(all_fall_events))

    # ── Bucket occupancy into per-second records ─────────────────────────────
    # Raw per-frame records are noisy for short clips. Group frames into
    # 1-second buckets and write the majority status per bucket.
    bucketed_occupancy = _bucket_occupancy(occupancy_frames, effective_fps)

    # ── Write to DB ─────────────────────────────────────────────────────────
    occ_written = write_occupancy_records(
        job_id=job_id,
        bed_id=bed_id,
        results=bucketed_occupancy,
        video_start=video_start,
        fps=1.0,       # one record per second after bucketing
        sample_rate=1,
    )
    log.info("Wrote %d occupancy records (%d raw frames bucketed)", occ_written, sampled)

    fall_written = write_fall_events(
        job_id=job_id,
        room_id=room_id,
        bed_id=bed_id,
        candidates=all_fall_events,
        video_start=video_start,
        fps=effective_fps,
        sample_rate=1,
        patient_id=patient_id,
    )
    log.info("Wrote %d fall events", fall_written)

    if warning_message:
        write_job_warning(job_id, warning_message)

    return True


# ---------------------------------------------------------------------------
# Occupancy bucketing — group raw per-frame records into 1-second buckets
# ---------------------------------------------------------------------------

def _bucket_occupancy(
    frames: List[_OccupancyFrame],
    fps: float,
) -> List[_OccupancyFrame]:
    """
    Collapse per-frame occupancy into one record per second.
    Each bucket takes the majority status and the mean confidence of that status.
    Returns at least one record even for very short clips.
    """
    if not frames:
        return []

    frames_per_bucket = max(1, round(fps))
    buckets: List[_OccupancyFrame] = []

    for start in range(0, len(frames), frames_per_bucket):
        bucket = frames[start: start + frames_per_bucket]

        occupied = [f for f in bucket if f.status == "occupied"]
        vacant   = [f for f in bucket if f.status == "vacant"]

        if len(occupied) >= len(vacant):
            status = "occupied"
            conf   = float(np.mean([f.confidence for f in occupied])) if occupied else 0.85
        else:
            status = "vacant"
            conf   = float(np.mean([f.confidence for f in vacant])) if vacant else 0.90

        buckets.append(_OccupancyFrame(status, round(conf, 4)))

    return buckets


# ---------------------------------------------------------------------------
# BiLSTM sliding-window classifier
# ---------------------------------------------------------------------------

def _classify_falls_bilstm(
    keypoint_stream: List[np.ndarray],
    classifier: FallClassifier,
) -> List[_FallEvent]:
    n = len(keypoint_stream)
    # Caller pads to at least TARGET_SEQ_LEN, so this should always pass.
    if n < TARGET_SEQ_LEN:
        log.warning("_classify_falls_bilstm: stream too short (%d < %d), skipping", n, TARGET_SEQ_LEN)
        return []

    # Count how many windows the stream produces.
    # When only one window exists (short/padded video) we lower the consecutive
    # threshold to 1 so the guard doesn't silently swallow the only result.
    total_windows = len(range(0, n - TARGET_SEQ_LEN + 1, WINDOW_STEP))
    min_consecutive = 1 if total_windows == 1 else FALL_MIN_CONSECUTIVE_WINDOWS

    fall_events: List[_FallEvent] = []
    consecutive_pos = 0
    cooldown        = 0
    in_event        = False
    event_start     = 0
    event_probs: List[float] = []

    for start in range(0, n - TARGET_SEQ_LEN + 1, WINDOW_STEP):
        seq = np.stack(keypoint_stream[start: start + TARGET_SEQ_LEN])
        if person_coverage(seq) < MIN_PERSON_COVERAGE:
            # The BiLSTM reads zero-filled frames (no person / padding) as a fall,
            # so a window without enough person frames is not classified at all.
            prob, is_fall = 0.0, False
        else:
            prob, is_fall = classifier.predict(seq)

        if cooldown > 0:
            cooldown -= 1
            continue

        if is_fall:
            consecutive_pos += 1
            event_probs.append(prob)
            if not in_event and consecutive_pos >= min_consecutive:
                in_event    = True
                event_start = start
        else:
            if in_event:
                mean_conf = float(np.mean(event_probs))
                fall_events.append(_FallEvent(
                    start_frame=event_start,
                    end_frame=start + TARGET_SEQ_LEN,
                    confidence=round(mean_conf, 4),
                ))
                cooldown = FALL_COOLDOWN_WINDOWS
            in_event        = False
            consecutive_pos = 0
            event_probs     = []

    if in_event and event_probs:
        fall_events.append(_FallEvent(
            start_frame=event_start,
            end_frame=n,
            confidence=round(float(np.mean(event_probs)), 4),
        ))

    return fall_events


def _shift_events(events: List[_FallEvent], pad: int) -> List[_FallEvent]:
    """Convert padded-stream frame indices to real sampled-frame indices."""
    if pad <= 0:
        return events
    for e in events:
        e.start_frame = max(0, e.start_frame - pad)
        e.end_frame = max(e.start_frame, e.end_frame - pad)
    return events


# ---------------------------------------------------------------------------
# Merge overlapping events from multiple signals
# ---------------------------------------------------------------------------

def _merge_events(events: List[_FallEvent]) -> List[_FallEvent]:
    """Remove overlapping events, keeping the highest-confidence one."""
    if not events:
        return []

    events_sorted = sorted(events, key=lambda e: e.start_frame)
    merged: List[_FallEvent] = []
    current = events_sorted[0]

    for ev in events_sorted[1:]:
        if ev.start_frame <= current.end_frame:
            # Overlapping — keep higher confidence
            if ev.confidence > current.confidence:
                current = ev
        else:
            merged.append(current)
            current = ev

    merged.append(current)
    return merged
