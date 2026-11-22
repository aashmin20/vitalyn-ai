"""Tests for the incremental BiLSTM fall detector (no model or camera needed)."""
import numpy as np

from streaming_detector import StreamingFallDetector, TARGET_SEQ_LEN, WINDOW_STEP


class ScriptedClassifier:
    """Returns pre-set probabilities, one per predict() call."""

    def __init__(self, probs, threshold=0.45):
        self._probs = list(probs)
        self._thr = threshold
        self.calls = 0

    def predict(self, seq):
        assert seq.shape == (TARGET_SEQ_LEN, 34)
        p = self._probs[min(self.calls, len(self._probs) - 1)]
        self.calls += 1
        return p, p >= self._thr


PERSON = np.full(34, 0.5, dtype=np.float32)   # a frame with a detected person
EMPTY = np.zeros(34, dtype=np.float32)        # no person / padding


def feed(det, n, frame=PERSON):
    signals = []
    for _ in range(n):
        s = det.push(frame)
        if s:
            signals.append(s)
    return signals


def test_no_prediction_until_window_full():
    clf = ScriptedClassifier([0.9])
    det = StreamingFallDetector(clf, min_consecutive=1)
    feed(det, TARGET_SEQ_LEN - 1)
    assert clf.calls == 0
    assert not det.ready
    assert det.window_fill == TARGET_SEQ_LEN - 1


def test_first_window_then_every_step():
    clf = ScriptedClassifier([0.1])
    det = StreamingFallDetector(clf)
    feed(det, TARGET_SEQ_LEN)
    assert clf.calls == 1
    feed(det, WINDOW_STEP - 1)
    assert clf.calls == 1
    feed(det, 1)
    assert clf.calls == 2


def test_requires_consecutive_windows():
    clf = ScriptedClassifier([0.9, 0.1, 0.9, 0.1])
    det = StreamingFallDetector(clf, min_consecutive=2)
    signals = feed(det, TARGET_SEQ_LEN + 3 * WINDOW_STEP)
    assert signals == []          # never two fall windows in a row


def test_signal_fires_on_onset_with_mean_confidence():
    clf = ScriptedClassifier([0.8, 0.9])
    det = StreamingFallDetector(clf, min_consecutive=2)
    signals = feed(det, TARGET_SEQ_LEN + WINDOW_STEP)
    assert len(signals) == 1
    assert signals[0].windows == 2
    assert abs(signals[0].confidence - 0.85) < 1e-6


def test_one_signal_per_event_then_cooldown():
    # long fall (4 windows), then normal, then another fall during cooldown, then after
    clf = ScriptedClassifier([0.9] * 4 + [0.1] + [0.9] * 3 + [0.1, 0.1, 0.1, 0.1] + [0.9] * 3)
    det = StreamingFallDetector(clf, min_consecutive=2, cooldown_windows=2)
    signals = feed(det, TARGET_SEQ_LEN + 14 * WINDOW_STEP)
    # first event once; the fall right after the gap is inside cooldown; a later one fires
    assert len(signals) == 2


def test_reset_clears_state():
    clf = ScriptedClassifier([0.9])
    det = StreamingFallDetector(clf, min_consecutive=1)
    feed(det, TARGET_SEQ_LEN)
    det.reset()
    assert det.window_fill == 0 and det.last_probability is None


# ── person-coverage guard ────────────────────────────────────────────────────

def test_empty_scene_never_calls_model_or_alarms():
    clf = ScriptedClassifier([0.96])          # the real model says 0.96 for all-zero input
    det = StreamingFallDetector(clf, min_consecutive=1)
    signals = feed(det, TARGET_SEQ_LEN + 4 * WINDOW_STEP, frame=EMPTY)
    assert signals == [] and clf.calls == 0
    assert det.guarded is True and det.last_probability is None


def test_low_coverage_window_is_guarded_even_with_some_person_frames():
    clf = ScriptedClassifier([0.96])
    det = StreamingFallDetector(clf, min_consecutive=1, min_coverage=0.8)
    feed(det, 10, frame=PERSON)
    signals = feed(det, 20, frame=EMPTY)       # only 10/30 frames have a person
    assert signals == [] and clf.calls == 0


def test_window_at_coverage_threshold_is_classified():
    clf = ScriptedClassifier([0.9])
    det = StreamingFallDetector(clf, min_consecutive=1, min_coverage=0.8)
    feed(det, 6, frame=EMPTY)                  # 24/30 = 0.8 coverage
    signals = feed(det, 24, frame=PERSON)
    assert clf.calls == 1 and len(signals) == 1 and det.guarded is False


def test_guarded_window_breaks_consecutive_run():
    clf = ScriptedClassifier([0.9, 0.9])
    det = StreamingFallDetector(clf, min_consecutive=2)
    feed(det, TARGET_SEQ_LEN)                          # window 1: fall
    feed(det, WINDOW_STEP, frame=EMPTY)                # window 2: buffer now half empty -> guarded
    signals = feed(det, WINDOW_STEP)                   # window 3 alone cannot satisfy 2-in-a-row
    assert signals == []


def test_person_coverage_helper():
    from streaming_detector import person_coverage
    w = np.zeros((4, 34), dtype=np.float32)
    w[:3] = 0.1
    assert person_coverage(w) == 0.75
    assert person_coverage(np.zeros((0, 34))) == 0.0
