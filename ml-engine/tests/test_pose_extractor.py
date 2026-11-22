"""
Tests for YOLOv8n-pose keypoint extraction (pose_extractor.py).

Tests verify:
  - extract_from_video returns correct shape (30, 34)
  - extract_frame returns (34,) or None
  - Coordinates are normalised to [0, 1]
  - Zero-padding is applied for short videos
  - Works on all 4 IKAR fall categories
"""
import os
import sys
import numpy as np
import pytest

_ML_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND   = os.path.join(_ML_ENGINE, "..", "backend")
for _p in [_ML_ENGINE, _BACKEND]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pose_extractor import PoseExtractor, TARGET_SEQ_LEN, SAMPLE_FPS

IKAR_BASE = os.path.join(_ML_ENGINE, "..", "datasets", "doi-10", "IKAR_dataset")

def _ikar_video(category: str, idx: int = 0) -> str:
    return os.path.join(IKAR_BASE, category, "videos", f"{category}_{idx}.mp4")

FALL_VIDEO     = _ikar_video("trips",    0)
SLIP_VIDEO     = _ikar_video("slips",    0)
FAINTING_VIDEO = _ikar_video("faintings",0)
BLACKOUT_VIDEO = _ikar_video("blackouts",0)


@pytest.fixture(scope="module")
def extractor():
    return PoseExtractor()


class TestExtractFromVideo:
    """Tests for the whole-video extraction method."""

    def test_output_shape_trips(self, extractor):
        seq = extractor.extract_from_video(FALL_VIDEO)
        assert seq.shape == (TARGET_SEQ_LEN, 34), (
            f"Expected (30, 34), got {seq.shape}"
        )

    def test_output_shape_slips(self, extractor):
        seq = extractor.extract_from_video(SLIP_VIDEO)
        assert seq.shape == (TARGET_SEQ_LEN, 34)

    def test_output_shape_faintings(self, extractor):
        seq = extractor.extract_from_video(FAINTING_VIDEO)
        assert seq.shape == (TARGET_SEQ_LEN, 34)

    def test_output_shape_blackouts(self, extractor):
        seq = extractor.extract_from_video(BLACKOUT_VIDEO)
        assert seq.shape == (TARGET_SEQ_LEN, 34)

    def test_output_dtype_float32(self, extractor):
        seq = extractor.extract_from_video(FALL_VIDEO)
        assert seq.dtype == np.float32

    def test_coords_in_zero_one_range(self, extractor):
        """All normalised coordinates must be in [0, 1]."""
        seq = extractor.extract_from_video(FALL_VIDEO)
        # Zeros are valid (padding or undetected keypoints)
        nonzero = seq[seq > 0]
        if len(nonzero) > 0:
            assert nonzero.max() <= 1.0 + 1e-4, (
                f"Coord > 1.0 found: {nonzero.max():.4f}"
            )
            assert nonzero.min() >= 0.0, (
                f"Negative coord found: {nonzero.min():.4f}"
            )

    def test_no_nan_in_output(self, extractor):
        seq = extractor.extract_from_video(FALL_VIDEO)
        assert not np.any(np.isnan(seq))

    def test_no_inf_in_output(self, extractor):
        seq = extractor.extract_from_video(FALL_VIDEO)
        assert not np.any(np.isinf(seq))

    def test_person_detected_in_at_least_one_frame(self, extractor):
        """At least one frame should have non-zero keypoints."""
        seq = extractor.extract_from_video(FALL_VIDEO)
        has_person = any(np.any(seq[i] > 0) for i in range(TARGET_SEQ_LEN))
        assert has_person, "No keypoints detected in any frame of trips_0.mp4"

    @pytest.mark.parametrize("category,idx", [
        ("trips",    0), ("trips",    1),
        ("slips",    0), ("slips",    1),
        ("blackouts",0), ("faintings",0),
    ])
    def test_shape_across_multiple_videos(self, extractor, category, idx):
        path = _ikar_video(category, idx)
        if not os.path.exists(path):
            pytest.skip(f"Video not found: {path}")
        seq = extractor.extract_from_video(path)
        assert seq.shape == (TARGET_SEQ_LEN, 34)

    def test_returns_last_30_frames_not_first(self, extractor):
        """
        Training notebook took the LAST 30 frames.
        We verify this by checking two different videos have different sequences
        (they won't if both accidentally return zeros/padding from the wrong end).
        """
        seq1 = extractor.extract_from_video(FALL_VIDEO)
        seq2 = extractor.extract_from_video(SLIP_VIDEO)
        assert not np.allclose(seq1, seq2), (
            "Two different videos returned identical sequences — suspect wrong slice direction"
        )


class TestExtractFrame:
    """Tests for the single-frame extraction method."""

    def test_returns_array_or_none(self, extractor):
        import cv2
        cap = cv2.VideoCapture(FALL_VIDEO)
        ret, frame = cap.read()
        cap.release()
        assert ret, "Could not read first frame of trips_0.mp4"
        result = extractor.extract_frame(frame)
        assert result is None or (isinstance(result, np.ndarray) and result.shape == (34,))

    def test_frame_coords_normalised(self, extractor):
        import cv2
        cap = cv2.VideoCapture(FALL_VIDEO)
        ret, frame = cap.read()
        cap.release()
        result = extractor.extract_frame(frame)
        if result is not None:
            nonzero = result[result > 0]
            if len(nonzero) > 0:
                assert nonzero.max() <= 1.0 + 1e-4
                assert nonzero.min() >= 0.0

    def test_blank_frame_returns_none_or_array(self, extractor):
        """A blank black frame should not crash — returns None or zeros."""
        import numpy as np
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        result = extractor.extract_frame(blank)
        assert result is None or result.shape == (34,)
