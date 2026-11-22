"""
streaming_detector.py — incremental BiLSTM sliding-window fall detection.

Same decision rules as pipeline._classify_falls_bilstm (window length, step,
FALL_THRESHOLD via the classifier, FALL_MIN_CONSECUTIVE_WINDOWS, cooldown), but
fed one keypoint vector at a time so a live camera can use it.

Difference from the batch version: an alert is raised at event *onset* (as soon
as the required number of consecutive fall windows is reached) instead of when
the event ends, because a live system must not wait for the person to get up.

Every signal is only a *potential* fall and needs human review.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Protocol

import numpy as np

from config import (
    FALL_MIN_CONSECUTIVE_WINDOWS,
    FALL_COOLDOWN_WINDOWS,
    MIN_PERSON_COVERAGE,
)

TARGET_SEQ_LEN = 30
WINDOW_STEP = 15


def person_coverage(window: np.ndarray) -> float:
    """Share of frames in a (seq_len, 34) window with any non-zero keypoint.
    All-zero rows are frames with no detected person (or padding)."""
    if len(window) == 0:
        return 0.0
    return float(np.mean(np.any(window != 0, axis=1)))


class _Classifier(Protocol):
    def predict(self, sequence: np.ndarray) -> tuple[float, bool]: ...


@dataclass
class FallSignal:
    confidence: float          # mean BiLSTM probability over the windows that triggered
    windows: int               # number of consecutive fall windows seen


class StreamingFallDetector:
    def __init__(
        self,
        classifier: _Classifier,
        seq_len: int = TARGET_SEQ_LEN,
        step: int = WINDOW_STEP,
        min_consecutive: int = FALL_MIN_CONSECUTIVE_WINDOWS,
        cooldown_windows: int = FALL_COOLDOWN_WINDOWS,
        min_coverage: float = MIN_PERSON_COVERAGE,
    ):
        self._clf = classifier
        self._seq_len = seq_len
        self._step = step
        self._min_consecutive = min_consecutive
        self._cooldown_windows = cooldown_windows
        self._min_coverage = min_coverage
        self.guarded = False          # True when the last window lacked person coverage

        self._buf: Deque[np.ndarray] = deque(maxlen=seq_len)
        self._since_eval = 0
        self._consecutive = 0
        self._cooldown = 0
        self._in_event = False
        self._probs: List[float] = []
        self.last_probability: Optional[float] = None

    @property
    def window_fill(self) -> int:
        """How many of the required frames are buffered (0..seq_len)."""
        return len(self._buf)

    @property
    def ready(self) -> bool:
        return len(self._buf) >= self._seq_len

    def push(self, keypoints: np.ndarray) -> Optional[FallSignal]:
        """
        Add one 34-value keypoint vector (zeros if no person). Returns a
        FallSignal when a new potential fall begins, otherwise None.
        """
        self._buf.append(np.asarray(keypoints, dtype=np.float32))
        if not self.ready:
            return None

        # First evaluation as soon as the buffer is full, then every `step` samples.
        if self._since_eval > 0 and self._since_eval < self._step:
            self._since_eval += 1
            return None
        self._since_eval = 1

        window = np.stack(self._buf)
        if person_coverage(window) < self._min_coverage:
            # Not enough person frames: the model would be reading zeros. Treat as
            # "no fall" and do not call the classifier.
            self.guarded = True
            self.last_probability = None
            prob, is_fall = 0.0, False
        else:
            self.guarded = False
            prob, is_fall = self._clf.predict(window)
            self.last_probability = float(prob)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        if is_fall:
            self._consecutive += 1
            self._probs.append(float(prob))
            if not self._in_event and self._consecutive >= self._min_consecutive:
                self._in_event = True
                return FallSignal(
                    confidence=round(float(np.mean(self._probs)), 4),
                    windows=self._consecutive,
                )
        else:
            if self._in_event:
                self._cooldown = self._cooldown_windows
            self._in_event = False
            self._consecutive = 0
            self._probs = []
        return None

    def reset(self) -> None:
        self._buf.clear()
        self._since_eval = 0
        self._consecutive = 0
        self._cooldown = 0
        self._in_event = False
        self._probs = []
        self.last_probability = None
        self.guarded = False
