"""
Shared pytest fixtures for VITALYN ML engine tests.
"""
import os as _os
import tempfile as _tempfile

# Test safety net: never touch a real database (backend/.env may point at Supabase).
_tmp = _tempfile.mkdtemp(prefix="vitalyn-mltests-")
_os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test_app.db"
_os.environ["VITALYN_OUTBOX_PATH"] = _os.path.join(_tmp, "outbox.db")


import sys
import os
import uuid
import pytest
import numpy as np

# Make ml-engine and backend importable
ML_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND   = os.path.join(ML_ENGINE, "..", "backend")
sys.path.insert(0, ML_ENGINE)
sys.path.insert(0, BACKEND)

IKAR_BASE = os.path.join(ML_ENGINE, "..", "datasets", "doi-10", "IKAR_dataset")

# ── Path helpers ─────────────────────────────────────────────────────────────

def ikar_video(category: str, idx: int = 0) -> str:
    return os.path.join(IKAR_BASE, category, "videos", f"{category}_{idx}.mp4")

def ikar_label(category: str, idx: int = 0) -> str:
    return os.path.join(IKAR_BASE, category, "labels", f"{category}_{idx}.json")

FALL_VIDEO    = ikar_video("trips",    0)
SLIP_VIDEO    = ikar_video("slips",    0)
FAINTING_VIDEO= ikar_video("faintings",0)
BLACKOUT_VIDEO= ikar_video("blackouts",0)

# ── Synthetic helpers ─────────────────────────────────────────────────────────

def make_standing_sequence(n: int = 30) -> np.ndarray:
    """
    Synthetic keypoint sequence for a standing person.
    x coords clustered at 0.5, y coords spread from 0.1 (head) to 0.9 (feet).
    Shape: (n, 34)
    """
    seq = np.zeros((n, 34), dtype=np.float32)
    for i in range(n):
        seq[i, :17] = 0.5 + np.random.randn(17) * 0.03   # x ≈ centre
        seq[i, 17:] = np.linspace(0.1, 0.9, 17) + np.random.randn(17) * 0.02
    return seq

def make_fallen_sequence(n: int = 30) -> np.ndarray:
    """
    Synthetic keypoint sequence for a fallen (horizontal) person.
    x coords spread across frame, y coords all similar (person flat).
    """
    seq = np.zeros((n, 34), dtype=np.float32)
    for i in range(n):
        seq[i, :17] = np.linspace(0.2, 0.8, 17) + np.random.randn(17) * 0.03
        seq[i, 17:] = 0.5 + np.random.randn(17) * 0.03   # y ≈ 0.5
    return seq

def make_zero_sequence(n: int = 30) -> np.ndarray:
    """All-zeros: no person detected in any frame."""
    return np.zeros((n, 34), dtype=np.float32)

def make_transition_sequence(n: int = 30) -> np.ndarray:
    """
    First half standing, second half fallen — simulates a fall in progress.
    """
    seq = np.zeros((n, 34), dtype=np.float32)
    half = n // 2
    # Standing frames
    for i in range(half):
        seq[i, :17] = 0.5 + np.random.randn(17) * 0.03
        seq[i, 17:] = np.linspace(0.1, 0.9, 17)
    # Fallen frames
    for i in range(half, n):
        seq[i, :17] = np.linspace(0.2, 0.8, 17)
        seq[i, 17:] = 0.5 + np.random.randn(17) * 0.03
    return seq

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fall_classifier():
    """Loads the BiLSTM once per test session (slow ~2s)."""
    from bilstm_model import FallClassifier
    return FallClassifier()

@pytest.fixture(scope="session")
def pose_extractor():
    """Loads YOLOv8n-pose once per test session."""
    from pose_extractor import PoseExtractor
    return PoseExtractor()

@pytest.fixture
def test_job_id():
    return str(uuid.uuid4())

@pytest.fixture
def standing_seq():
    np.random.seed(0)
    return make_standing_sequence()

@pytest.fixture
def fallen_seq():
    np.random.seed(0)
    return make_fallen_sequence()

@pytest.fixture
def zero_seq():
    return make_zero_sequence()

@pytest.fixture
def transition_seq():
    np.random.seed(0)
    return make_transition_sequence()


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    """The throwaway test database needs its tables (the shared engine points at it)."""
    from sqlmodel import SQLModel
    import models  # noqa: F401  (registers the tables)
    from database import engine
    SQLModel.metadata.create_all(engine)
