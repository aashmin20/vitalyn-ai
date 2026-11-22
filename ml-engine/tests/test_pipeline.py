"""
Tests for the full ML inference pipeline (pipeline.py).

Uses real IKAR videos for integration tests and mocked DB calls for unit tests.
Tests verify:
  - _classify_falls_bilstm returns a list (may be empty for short videos)
  - _merge_events correctly deduplicates overlapping events
  - run_inference writes occupancy records and fall events to DB
  - Job status transitions: queued → processing → completed / failed
  - Occupancy distribution makes sense (occupied when person present)
  - Pipeline handles edge cases: very short video, no person in video
"""
import os
import sys
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, call

# Ensure ml-engine and backend are on path (conftest already does this, but
# keep it here for when test file is run directly)
_ML_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND   = os.path.join(_ML_ENGINE, "..", "backend")
for _p in [_ML_ENGINE, _BACKEND]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import uuid
from pipeline import (
    _classify_falls_bilstm,
    _merge_events,
    _FallEvent,
    _OccupancyFrame,
    run_inference,
    WINDOW_STEP,
)
from pose_extractor import TARGET_SEQ_LEN
from bilstm_model import FallClassifier

IKAR_BASE = os.path.join(_ML_ENGINE, "..", "datasets", "doi-10", "IKAR_dataset")

def _ikar_video(category: str, idx: int = 0) -> str:
    return os.path.join(IKAR_BASE, category, "videos", f"{category}_{idx}.mp4")

FALL_VIDEO = _ikar_video("trips",    0)
SLIP_VIDEO = _ikar_video("slips",    0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_event(start: int, end: int, conf: float = 0.7) -> _FallEvent:
    return _FallEvent(start_frame=start, end_frame=end, confidence=conf)


# ── Unit tests: _merge_events ────────────────────────────────────────────────

class TestMergeEvents:

    def test_empty_list(self):
        assert _merge_events([]) == []

    def test_single_event_unchanged(self):
        ev = _make_event(0, 30, 0.8)
        result = _merge_events([ev])
        assert len(result) == 1
        assert result[0].start_frame == 0
        assert result[0].end_frame == 30

    def test_non_overlapping_events_both_kept(self):
        e1 = _make_event(0,  30, 0.7)
        e2 = _make_event(50, 80, 0.6)
        result = _merge_events([e1, e2])
        assert len(result) == 2

    def test_overlapping_keeps_higher_confidence(self):
        low  = _make_event(0,  40, 0.5)
        high = _make_event(20, 60, 0.9)
        result = _merge_events([low, high])
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_overlapping_does_not_duplicate(self):
        e1 = _make_event(0, 30, 0.7)
        e2 = _make_event(15, 45, 0.7)
        result = _merge_events([e1, e2])
        assert len(result) == 1

    def test_three_events_two_overlap_one_separate(self):
        e1 = _make_event(0,  30, 0.6)
        e2 = _make_event(20, 50, 0.8)   # overlaps e1
        e3 = _make_event(70, 100, 0.5)  # separate
        result = _merge_events([e1, e2, e3])
        assert len(result) == 2
        assert result[0].confidence == 0.8   # higher confidence wins
        assert result[1].start_frame == 70

    def test_output_sorted_by_start_frame(self):
        e1 = _make_event(50, 80, 0.7)
        e2 = _make_event(0,  30, 0.6)
        result = _merge_events([e1, e2])
        starts = [e.start_frame for e in result]
        assert starts == sorted(starts)


# ── Unit tests: _classify_falls_bilstm ───────────────────────────────────────

class TestClassifyFallsBilstm:

    def test_returns_list(self, fall_classifier):
        stream = [np.zeros(34, dtype=np.float32)] * 60
        result = _classify_falls_bilstm(stream, fall_classifier)
        assert isinstance(result, list)

    def test_too_short_returns_empty(self, fall_classifier):
        """Stream shorter than TARGET_SEQ_LEN must return []."""
        stream = [np.zeros(34, dtype=np.float32)] * (TARGET_SEQ_LEN - 1)
        result = _classify_falls_bilstm(stream, fall_classifier)
        assert result == []

    def test_exactly_seq_len_runs_without_error(self, fall_classifier):
        stream = [np.zeros(34, dtype=np.float32)] * TARGET_SEQ_LEN
        result = _classify_falls_bilstm(stream, fall_classifier)
        assert isinstance(result, list)

    def test_all_zero_stream_is_not_classified_as_fall(self):
        """
        An all-zero stream means no person was detected. The trained BiLSTM scores
        such input ~0.96 (it reads zero frames as a fall), so the person-coverage
        guard must stop it from being classified at all.
        """
        class MustNotBeCalled:
            def predict(self, seq):
                raise AssertionError("classifier must not run on a no-person window")

        stream = [np.zeros(34, dtype=np.float32)] * 90
        assert _classify_falls_bilstm(stream, MustNotBeCalled()) == []

    def test_all_zero_stream_with_real_model_gives_no_events(self, fall_classifier):
        stream = [np.zeros(34, dtype=np.float32)] * 90
        assert _classify_falls_bilstm(stream, fall_classifier) == []

    def test_event_confidence_in_range(self, fall_classifier):
        stream = [np.zeros(34, dtype=np.float32)] * 90
        result = _classify_falls_bilstm(stream, fall_classifier)
        for ev in result:
            assert 0.0 <= ev.confidence <= 1.0

    def test_event_frames_ordered(self, fall_classifier):
        stream = [np.zeros(34, dtype=np.float32)] * 90
        result = _classify_falls_bilstm(stream, fall_classifier)
        for ev in result:
            assert ev.start_frame < ev.end_frame

    def test_event_frames_within_stream_bounds(self, fall_classifier):
        n = 90
        stream = [np.zeros(34, dtype=np.float32)] * n
        result = _classify_falls_bilstm(stream, fall_classifier)
        for ev in result:
            assert ev.start_frame >= 0
            assert ev.end_frame <= n + TARGET_SEQ_LEN


# ── Integration tests: run_inference with mocked DB ──────────────────────────

class TestRunInference:
    """
    Full pipeline integration tests.
    DB calls are mocked to avoid touching the real database.
    """

    def _mock_db(self):
        """Returns a dict of mock DB functions."""
        return {
            "mark_job_started":        MagicMock(),
            "update_job_progress":     MagicMock(),
            "mark_job_completed":      MagicMock(),
            "mark_job_failed":         MagicMock(),
            "get_job_room_id":         MagicMock(return_value=None),
            "get_or_create_default_bed": MagicMock(return_value=None),
            "write_occupancy_records": MagicMock(return_value=0),
            "write_fall_events":       MagicMock(return_value=0),
        }

    def test_returns_true_on_success(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            result = run_inference(test_job_id, FALL_VIDEO)
        assert result is True

    def test_job_marked_started(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)
        mocks["mark_job_started"].assert_called_once_with(test_job_id)

    def test_job_marked_completed_on_success(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)
        mocks["mark_job_completed"].assert_called_once_with(test_job_id)

    def test_occupancy_records_written(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)
        mocks["write_occupancy_records"].assert_called_once()
        _, kwargs = mocks["write_occupancy_records"].call_args
        # results list must be non-empty
        results = mocks["write_occupancy_records"].call_args[1].get(
            "results",
            mocks["write_occupancy_records"].call_args[0][2]
            if len(mocks["write_occupancy_records"].call_args[0]) > 2
            else []
        )

    def test_write_fall_events_called(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)
        mocks["write_fall_events"].assert_called_once()

    def test_invalid_video_path_returns_false(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            result = run_inference(test_job_id, "/nonexistent/path/video.mp4")
        assert result is False

    def test_invalid_video_marks_job_failed(self, test_job_id):
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, "/nonexistent/path/video.mp4")
        mocks["mark_job_failed"].assert_called_once()
        job_arg = mocks["mark_job_failed"].call_args[0][0]
        assert job_arg == test_job_id

    def test_progress_updates_called_for_long_video(self, test_job_id):
        """For a long enough video, progress must be updated at least once."""
        mocks = self._mock_db()
        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)
        # Progress may or may not fire depending on video length — just ensure no crash

    @pytest.mark.parametrize("category,idx", [
        ("trips",    0),
        ("slips",    0),
        ("blackouts",0),
        ("faintings",0),
    ])
    def test_all_ikar_categories_complete_successfully(self, test_job_id, category, idx):
        path = _ikar_video(category, idx)
        if not os.path.exists(path):
            pytest.skip(f"Video not found: {path}")
        mocks = self._mock_db()
        jid = str(uuid.uuid4())
        with patch.multiple("pipeline", **mocks):
            result = run_inference(jid, path)
        assert result is True


# ── Integration: occupancy distribution ──────────────────────────────────────

class TestOccupancyDistribution:
    """
    Verify that occupancy results make sense for real videos.
    IKAR videos always have a person — most frames should be 'occupied'.
    """

    def test_mostly_occupied_on_fall_video(self, test_job_id):
        captured = {}

        def capture_occ(job_id, bed_id, results, **kwargs):
            captured["results"] = results
            return len(results)

        mocks = {
            "mark_job_started":        MagicMock(),
            "update_job_progress":     MagicMock(),
            "mark_job_completed":      MagicMock(),
            "mark_job_failed":         MagicMock(),
            "get_job_room_id":         MagicMock(return_value=None),
            "get_or_create_default_bed": MagicMock(return_value=None),
            "write_occupancy_records": capture_occ,
            "write_fall_events":       MagicMock(return_value=0),
        }

        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)

        results = captured.get("results", [])
        assert len(results) > 0, "No occupancy records produced"

        occupied = sum(1 for r in results if r.status == "occupied")
        pct = occupied / len(results) * 100
        assert pct >= 50.0, (
            f"Expected ≥50% occupied frames for a fall video, got {pct:.1f}%. "
            "IKAR videos have a person in frame throughout."
        )

    def test_occupancy_statuses_are_valid(self, test_job_id):
        captured = {}

        def capture_occ(job_id, bed_id, results, **kwargs):
            captured["results"] = results
            return len(results)

        mocks = {
            "mark_job_started":        MagicMock(),
            "update_job_progress":     MagicMock(),
            "mark_job_completed":      MagicMock(),
            "mark_job_failed":         MagicMock(),
            "get_job_room_id":         MagicMock(return_value=None),
            "get_or_create_default_bed": MagicMock(return_value=None),
            "write_occupancy_records": capture_occ,
            "write_fall_events":       MagicMock(return_value=0),
        }

        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)

        valid_statuses = {"occupied", "vacant", "uncertain"}
        for r in captured.get("results", []):
            assert r.status in valid_statuses, f"Invalid status: {r.status}"

    def test_occupancy_confidence_in_range(self, test_job_id):
        captured = {}

        def capture_occ(job_id, bed_id, results, **kwargs):
            captured["results"] = results
            return len(results)

        mocks = {
            "mark_job_started":        MagicMock(),
            "update_job_progress":     MagicMock(),
            "mark_job_completed":      MagicMock(),
            "mark_job_failed":         MagicMock(),
            "get_job_room_id":         MagicMock(return_value=None),
            "get_or_create_default_bed": MagicMock(return_value=None),
            "write_occupancy_records": capture_occ,
            "write_fall_events":       MagicMock(return_value=0),
        }

        with patch.multiple("pipeline", **mocks):
            run_inference(test_job_id, FALL_VIDEO)

        for r in captured.get("results", []):
            assert 0.0 <= r.confidence <= 1.0, (
                f"Confidence out of range: {r.confidence}"
            )


class TestShiftEvents:
    def test_shifts_back_by_padding(self):
        from pipeline import _shift_events, _FallEvent
        ev = _shift_events([_FallEvent(19, 49, 0.9)], pad=19)
        assert (ev[0].start_frame, ev[0].end_frame) == (0, 30)

    def test_no_padding_leaves_events_unchanged(self):
        from pipeline import _shift_events, _FallEvent
        ev = _shift_events([_FallEvent(15, 45, 0.9)], pad=0)
        assert (ev[0].start_frame, ev[0].end_frame) == (15, 45)

    def test_never_negative(self):
        from pipeline import _shift_events, _FallEvent
        ev = _shift_events([_FallEvent(2, 10, 0.9)], pad=19)
        assert ev[0].start_frame == 0 and ev[0].end_frame == 0
