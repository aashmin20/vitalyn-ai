"""
live_status.py — the three-way status shown to staff for a monitored patient.

    "Normal bed activity" | "Potential fall detected" | "Uncertain — Manual verification required"

The percentages are the retrained BiLSTM's own output: fall % = P(fall) from the sigmoid, averaged over
the last two windows (the same two windows the alert rule uses, which keeps the display steady), and
normal % = 100 - fall %. They are model outputs on FallVision-like data, not clinical probabilities.
When the model has no valid prediction (warming up, or too few frames with a person), no percentage is
shown and the status is Uncertain. Nothing is ever filled in or estimated.

Bands (chosen on the 77 validation clips, docs/evaluation/FALL_DETECTION_IMPROVEMENT.md):
  fall probability < 0.35            -> Normal  (84% of normal windows, 24% of fall-clip windows)
  0.35 <= probability < threshold    -> Uncertain
  an alert raised in the last 10 s   -> Potential fall detected
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Optional

NORMAL = "normal"
UNCERTAIN = "uncertain"
FALL = "potential_fall"

LABELS = {
    NORMAL: "Normal bed activity",
    UNCERTAIN: "Uncertain — Manual verification required",
    FALL: "Potential fall detected",
}

NORMAL_BELOW = 0.35            # validation-chosen lower edge of the uncertain band
SMOOTH_WINDOWS = 2             # same as the two-consecutive-window alert rule


class StatusTracker:
    def __init__(self, fall_threshold: float, normal_below: float = NORMAL_BELOW, smooth: int = SMOOTH_WINDOWS):
        self.fall_threshold = fall_threshold
        self.normal_below = normal_below
        self._probs: Deque[float] = deque(maxlen=smooth)
        self._last: Dict = self._result(UNCERTAIN, None, "Starting")

    def add_window(self, probability: Optional[float]) -> None:
        """Record a new BiLSTM window result (None when the window was not classified)."""
        if probability is None:
            self._probs.clear()            # a gap in valid predictions: do not average across it
        else:
            self._probs.append(float(probability))

    @property
    def fall_probability(self) -> Optional[float]:
        return sum(self._probs) / len(self._probs) if self._probs else None

    def _result(self, code: str, prob: Optional[float], reason: str) -> Dict:
        fall_pct = None if prob is None else round(100.0 * prob, 1)
        return {
            "code": code,
            "label": LABELS[code],
            "fall_confidence": fall_pct,
            "normal_confidence": None if fall_pct is None else round(100.0 - fall_pct, 1),
            "reason": reason,
            "source": "BiLSTM fall probability (model output, mean of last 2 windows)",
        }

    def assess(self, *, alarm: bool, ready: bool, guarded: bool, person: bool, body_low: bool = False,
               alarm_source: Optional[str] = None) -> Dict:
        """Status for this moment. `body_low`: the context rule sees the body well below its resting
        level but has not (yet) confirmed a fall. `alarm_source`: which detector raised the alert."""
        prob = self.fall_probability
        if alarm:
            if alarm_source in ("context", "heuristic"):
                why = ("Raised by the movement rule: the body dropped below its resting level and stayed down. "
                       "The percentages below are the BiLSTM's own view, which may disagree.")
            else:
                why = "Raised by the BiLSTM: two windows in a row above its fall threshold."
            res = self._result(FALL, prob, why + " Check the patient.")
            res["raised_by"] = alarm_source
        elif not ready:
            res = self._result(UNCERTAIN, None, "Collecting the first 5 seconds of movement")
        elif guarded or not person:
            res = self._result(UNCERTAIN, None, "The patient is not clearly in view")
        elif prob is None:
            res = self._result(UNCERTAIN, None, "Waiting for the next model window")
        elif body_low:
            res = self._result(UNCERTAIN, prob, "Body is lower than its resting position; verify")
        elif prob >= self.normal_below:
            res = self._result(UNCERTAIN, prob, "Model is not confident either way")
        else:
            res = self._result(NORMAL, prob, "Movement looks like ordinary bed activity")
        self._last = res
        return res

    @property
    def last(self) -> Dict:
        return self._last
