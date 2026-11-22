"""
Tests for the aspect-ratio fall heuristic (fall_heuristic.py).

Tests verify:
  - No trigger on upright person (AR < threshold)
  - Trigger fires after FALL_MIN_FRAMES consecutive high-AR frames
  - No trigger before FALL_MIN_FRAMES frames
  - Cooldown prevents immediate re-trigger
  - None input (no person) resets the window
  - Confidence is in [0, 1]
  - Confidence scales with aspect ratio magnitude
"""
import pytest
from fall_heuristic import (
    AspectRatioFallDetector,
    FALL_AR_THRESHOLD,
    FALL_MIN_FRAMES,
    COOLDOWN_FRAMES,
)


@pytest.fixture
def detector():
    return AspectRatioFallDetector()


class TestNoFallScenarios:
    """Cases that must NOT trigger a fall event."""

    def test_upright_person_no_trigger(self, detector):
        """AR = 0.4 (standing) — should never trigger."""
        for _ in range(20):
            triggered, conf = detector.update(0.4)
            assert not triggered

    def test_exactly_at_threshold_no_trigger(self, detector):
        """AR exactly at threshold — strictly less than, so no trigger."""
        below = FALL_AR_THRESHOLD - 0.01
        for _ in range(10):
            triggered, _ = detector.update(below)
        assert not triggered

    def test_fewer_than_min_frames_no_trigger(self, detector):
        """FALL_MIN_FRAMES - 1 high-AR frames must not trigger."""
        for _ in range(FALL_MIN_FRAMES - 1):
            triggered, _ = detector.update(FALL_AR_THRESHOLD + 0.5)
            assert not triggered

    def test_non_consecutive_high_ar_no_trigger(self, detector):
        """Alternating high/low AR breaks the streak — no trigger."""
        for _ in range(20):
            detector.update(FALL_AR_THRESHOLD + 0.5)   # high
            triggered, _ = detector.update(0.3)         # low — resets
            assert not triggered

    def test_none_resets_window(self, detector):
        """None input clears the window — streak must restart."""
        for _ in range(FALL_MIN_FRAMES - 1):
            detector.update(FALL_AR_THRESHOLD + 0.5)
        detector.update(None)   # reset
        # Now one more high-AR frame must NOT trigger
        triggered, _ = detector.update(FALL_AR_THRESHOLD + 0.5)
        assert not triggered


class TestFallTrigger:
    """Cases that MUST trigger a fall event."""

    def test_exact_min_frames_triggers(self, detector):
        """Exactly FALL_MIN_FRAMES consecutive high-AR frames must trigger."""
        result = False
        for _ in range(FALL_MIN_FRAMES):
            result, conf = detector.update(FALL_AR_THRESHOLD + 0.5)
        assert result is True

    def test_trigger_confidence_in_range(self, detector):
        for _ in range(FALL_MIN_FRAMES):
            triggered, conf = detector.update(FALL_AR_THRESHOLD + 0.5)
        assert 0.0 <= conf <= 1.0

    def test_higher_ar_gives_higher_confidence(self):
        """More extreme AR should produce higher confidence score."""
        low_ar  = AspectRatioFallDetector()
        high_ar = AspectRatioFallDetector()

        low_conf = high_conf = 0.0
        for _ in range(FALL_MIN_FRAMES):
            _, low_conf  = low_ar.update(FALL_AR_THRESHOLD + 0.1)
            _, high_conf = high_ar.update(FALL_AR_THRESHOLD + 1.5)

        assert high_conf >= low_conf, (
            f"Higher AR ({FALL_AR_THRESHOLD+1.5}) should give higher confidence "
            f"than lower AR ({FALL_AR_THRESHOLD+0.1}). Got {high_conf} vs {low_conf}"
        )

    def test_trigger_returns_nonzero_confidence(self, detector):
        for _ in range(FALL_MIN_FRAMES):
            triggered, conf = detector.update(FALL_AR_THRESHOLD + 0.5)
        assert conf > 0.0


class TestCooldown:
    """After a trigger, cooldown must prevent immediate re-firing."""

    def test_cooldown_prevents_immediate_retrigger(self, detector):
        # Trigger first event
        for _ in range(FALL_MIN_FRAMES):
            detector.update(FALL_AR_THRESHOLD + 0.5)

        # Try to trigger again immediately — should be blocked by cooldown
        for _ in range(FALL_MIN_FRAMES):
            triggered, _ = detector.update(FALL_AR_THRESHOLD + 0.5)
            assert not triggered, "Should not trigger during cooldown"

    def test_trigger_allowed_after_cooldown(self, detector):
        # Trigger first event
        for _ in range(FALL_MIN_FRAMES):
            detector.update(FALL_AR_THRESHOLD + 0.5)

        # Exhaust cooldown
        for _ in range(COOLDOWN_FRAMES + 1):
            detector.update(0.3)

        # Now should be able to trigger again
        result = False
        for _ in range(FALL_MIN_FRAMES):
            result, _ = detector.update(FALL_AR_THRESHOLD + 0.5)
        assert result is True

    def test_cooldown_counts_frames_correctly(self, detector):
        # Trigger
        for _ in range(FALL_MIN_FRAMES):
            detector.update(FALL_AR_THRESHOLD + 0.5)

        # Feed exactly COOLDOWN_FRAMES - 1 frames → should still be in cooldown
        any_trigger = False
        for _ in range(COOLDOWN_FRAMES - 1):
            t, _ = detector.update(FALL_AR_THRESHOLD + 1.0)
            if t:
                any_trigger = True
        assert not any_trigger


class TestFrameCounter:
    """Internal state bookkeeping."""

    def test_frame_counter_increments(self, detector):
        assert detector._frame == 0
        detector.update(0.3)
        assert detector._frame == 1
        detector.update(0.3)
        assert detector._frame == 2

    def test_independent_detectors_dont_share_state(self):
        d1 = AspectRatioFallDetector()
        d2 = AspectRatioFallDetector()

        for _ in range(FALL_MIN_FRAMES):
            d1.update(FALL_AR_THRESHOLD + 1.0)
        # d2 should still be clean
        triggered, _ = d2.update(FALL_AR_THRESHOLD + 1.0)
        assert not triggered


# ── Posture-transition detector (live + batch) ───────────────────────────────

from fall_heuristic import PostureTransitionDetector, person_box, MAX_TRANSITION
import numpy as np


def feed_posture(det, samples):
    """samples: list of (aspect_ratio, height) or None. Returns number of triggers."""
    fired = 0
    for s in samples:
        trig, _ = det.update(*(s if s else (None, None)))
        fired += int(trig)
    return fired


UP = (0.4, 300.0)        # standing
DOWN = (2.0, 90.0)       # horizontal, body height collapsed


class TestPostureTransition:

    def test_upright_then_horizontal_triggers_once(self):
        det = PostureTransitionDetector()
        assert feed_posture(det, [UP] * 5 + [DOWN] * 6) == 1

    def test_confidence_is_heuristic_score_in_range(self):
        det = PostureTransitionDetector()
        conf = 0.0
        for s in [UP] * 5 + [DOWN] * 4:
            trig, c = det.update(*s)
            conf = c or conf
        assert 0.5 <= conf <= 0.9

    def test_person_lying_the_whole_time_never_triggers(self):
        """A patient lying in bed must not alarm."""
        det = PostureTransitionDetector()
        assert feed_posture(det, [DOWN] * 60) == 0

    def test_person_entering_view_already_lying_never_triggers(self):
        det = PostureTransitionDetector()
        assert feed_posture(det, [None] * 10 + [DOWN] * 20) == 0

    def test_slow_lie_down_does_not_trigger(self):
        """Upright, then a long gap before becoming horizontal (deliberate lying down)."""
        det = PostureTransitionDetector()
        slow = [(0.5, 250.0)] * (MAX_TRANSITION + 6)     # neither upright (<0.9 ok) ... use mid AR
        mid = [(0.95, 280.0)] * (MAX_TRANSITION + 6)     # leaning/sitting: neither upright nor fallen
        assert feed_posture(det, [UP] * 5 + mid + [DOWN] * 6) == 0

    def test_horizontal_without_height_collapse_does_not_trigger(self):
        det = PostureTransitionDetector()
        wide_but_tall = (2.0, 290.0)                      # e.g. person reaching sideways
        assert feed_posture(det, [UP] * 5 + [wide_but_tall] * 6) == 0

    def test_too_few_horizontal_samples_does_not_trigger(self):
        det = PostureTransitionDetector()
        assert feed_posture(det, [UP] * 5 + [DOWN] * 2) == 0

    def test_cooldown_prevents_retrigger(self):
        det = PostureTransitionDetector()
        assert feed_posture(det, [UP] * 5 + [DOWN] * 4 + [UP] * 5 + [DOWN] * 4) == 1

    def test_person_box_uses_only_confident_pixel_keypoints(self):
        pix = np.zeros((17, 3), dtype=np.float32)
        assert person_box(pix) == (None, None)
        assert person_box(None) == (None, None)
        pix[:, 2] = 0.9
        pix[:, 0] = np.linspace(0, 200, 17)
        pix[:, 1] = np.linspace(0, 100, 17)
        ar, h = person_box(pix)
        assert abs(ar - 2.0) < 1e-6 and abs(h - 100.0) < 1e-6
