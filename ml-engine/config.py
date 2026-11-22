"""
ML Engine configuration — all tunable parameters in one place.
"""
import os

# ── Paths ───────────────────────────────────────────────────────────────────
ML_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR   = os.path.join(ML_ENGINE_DIR, "..", "backend")

BILSTM_MODEL_PATH = os.path.join(ML_ENGINE_DIR, "vitalyn_fall_bilstm.pt")
BACKEND_DB_PATH   = os.path.abspath(os.path.join(BACKEND_DIR, "vitalyn.db"))

# ── Pose model ──────────────────────────────────────────────────────────────
# YOLOv8n-pose: lightest pose model (~7 MB), 17 COCO keypoints per person.
# 17 keypoints × (x, y) = 34 features — matches BiLSTM input size exactly.
POSE_MODEL      = os.getenv("VITALYN_POSE_MODEL", "yolov8n-pose.pt")
POSE_CONF       = float(os.getenv("VITALYN_POSE_CONF", "0.40"))
NUM_KEYPOINTS   = 17
FEATURE_DIM     = NUM_KEYPOINTS * 2   # 34

# ── BiLSTM architecture (must match trained checkpoint) ──────────────────────
BILSTM_INPUT_SIZE  = 34
BILSTM_HIDDEN_SIZE = 64
BILSTM_NUM_LAYERS  = 2
BILSTM_FC1_OUT     = 32

# ── Sequence / sliding window ────────────────────────────────────────────────
# Number of consecutive frames fed to the BiLSTM as one sequence.
# Shorter = more sensitive, more FP. 30 frames ≈ 1 s at 30 fps.
SEQUENCE_LENGTH = int(os.getenv("VITALYN_SEQ_LEN", "30"))

# Step size between successive windows (overlap = SEQUENCE_LENGTH - STEP)
WINDOW_STEP = int(os.getenv("VITALYN_WIN_STEP", "15"))

# ── Fall classification threshold ───────────────────────────────────────────
# Sigmoid output from BiLSTM.  >threshold → fall.
# Lowered slightly from 0.5 to bias toward recall (miss no falls).
FALL_THRESHOLD = float(os.getenv("VITALYN_FALL_THRESH", "0.45"))

# Minimum windows in a row that must exceed threshold before an event fires
# (prevents single-window false positives)
FALL_MIN_CONSECUTIVE_WINDOWS = int(os.getenv("VITALYN_FALL_MIN_WIN", "2"))

# Minimum share of frames in a window that must contain a detected person before
# the BiLSTM is allowed to decide. The model reads zero-filled frames (no person /
# padding) as a fall (all-zero input -> ~0.96), so windows with too little person
# coverage are not classified at all.
MIN_PERSON_COVERAGE = float(os.getenv("VITALYN_MIN_PERSON_COVERAGE", "0.8"))

# After a fall event fires, skip this many windows before allowing another
FALL_COOLDOWN_WINDOWS = int(os.getenv("VITALYN_FALL_COOLDOWN", "4"))

# ── Video processing ─────────────────────────────────────────────────────────
# Process every Nth frame to reduce memory on 8 GB RAM.
# At 30 fps, FRAME_SAMPLE=1 gives one keypoint vector per frame.
FRAME_SAMPLE_RATE = int(os.getenv("VITALYN_FRAME_SAMPLE", "1"))

# ── Occupancy (YOLO-pose person presence logic) ──────────────────────────────
# If a person keypoint centroid is detected in the frame → occupied.
# No explicit bed bbox needed: for hospital upload, full frame = room.
OCCUPANCY_CONF = float(os.getenv("VITALYN_OCC_CONF", "0.40"))

# ── Logging ──────────────────────────────────────────────────────────────────
import logging

def configure_logging(level: str = "INFO") -> None:
    """Call once at process start to set up vitalyn.* logger."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(name)-25s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy ultralytics output
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
