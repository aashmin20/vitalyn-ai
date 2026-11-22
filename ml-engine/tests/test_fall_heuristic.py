"""Tests for the posture-transition fall heuristic (fall_heuristic.py)."""
import pytest


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
