"""
live_status.py — the fall-risk status shown to staff for a monitored patient, updated every sample.

Levels (code -> label):
    normal    -> "Normal activity"
    low       -> "Low fall risk — keep watching"
    medium    -> "Potential fall — check the patient"
    high      -> "FALL DETECTED — respond now"           (an alert was raised, or risk >= 75%)
    uncertain -> "Uncertain — Manual verification required"  (no usable signal yet / not in view)

RISK % = the higher of two measured signals, and the panel always says which one it is:
  * the retrained BiLSTM's fall probability (sigmoid output, mean of the last two 5 s windows), and
  * the posture score from fall_risk.py (horizontal x lower-than-resting-level, smoothed). This is a
    heuristic built from the keypoints, NOT a probability.
Both are also reported separately. Nothing is filled in or estimated: with neither signal available the
level is Uncertain and no percentage is shown. None of this is a clinical probability.

Band edges: LOW 25%, MEDIUM 45%, HIGH 75%. The BiLSTM's 35% "normal" edge was chosen on the 77
validation clips; the lower 25% edge is deliberately more sensitive (it surfaces weak signals as a
low-risk warning, not as an alert). An alert record is only created for HIGH.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, Optional

NORMAL = "normal"
LOW = "low"
MEDIUM = "medium"
HIGH = "high"
UNCERTAIN = "uncertain"

LABELS = {
    NORMAL: "Normal activity",
    LOW: "Low fall risk — keep watching",
    MEDIUM: "Potential fall — check the patient",
    HIGH: "FALL DETECTED — respond now",
    UNCERTAIN: "Uncertain — Manual verification required",
}

LOW_AT = 0.25
MEDIUM_AT = 0.45
HIGH_AT = 0.75
NORMAL_BELOW = 0.35            # kept for reference: the validation-chosen BiLSTM edge
SMOOTH_WINDOWS = 2             # same as the two-consecutive-window alert rule


def level_for(risk: float) -> str:
    if risk >= HIGH_AT:
        return HIGH
    if risk >= MEDIUM_AT:
        return MEDIUM
    if risk >= LOW_AT:
        return LOW
    return NORMAL


class StatusTracker:
    def __init__(self, fall_threshold: float, smooth: int = SMOOTH_WINDOWS):
        self.fall_threshold = fall_threshold
        self._probs: Deque[float] = deque(maxlen=smooth)
        self._last: Dict = self._result(UNCERTAIN, None, None, None, "Starting")

    def add_window(self, probability: Optional[float]) -> None:
        """Record a new BiLSTM window result (None when the window was not classified)."""
        if probability is None:
            self._probs.clear()            # a gap in valid predictions: do not average across it
        else:
            self._probs.append(float(probability))

    @property
    def fall_probability(self) -> Optional[float]:
        return sum(self._probs) / len(self._probs) if self._probs else None

    @staticmethod
    def _pct(x: Optional[float]) -> Optional[float]:
        return None if x is None else round(100.0 * float(x), 1)

    def _result(self, code: str, risk: Optional[float], prob: Optional[float], posture: Any, reason: str,
                risk_source: Optional[str] = None) -> Dict:
        fall_pct = self._pct(prob)
        out = {
            "code": code,
            "label": LABELS[code],
            "risk": self._pct(risk),
            "risk_source": risk_source,
            "fall_confidence": fall_pct,                                   # BiLSTM, as before
            "normal_confidence": None if fall_pct is None else round(100.0 - fall_pct, 1),
            "reason": reason,
            "source": "Risk = higher of the BiLSTM fall probability and the posture score",
            "posture": None,
        }
        if posture is not None and posture.drop is not None:
            out["posture"] = {
                "score": self._pct(posture.score),
                "reason": posture.reason,
                "horizontal": posture.horizontal,
                "drop": posture.drop,
                "angle": posture.angle,
            }
        return out

    def assess(self, *, alarm: bool, ready: bool, guarded: bool, person: bool, body_low: bool = False,
               alarm_source: Optional[str] = None, alarm_confidence: Optional[float] = None,
               posture: Any = None) -> Dict:
        """Status for this moment. `posture`: the latest fall_risk.PostureReading (or None).
        `body_low` is accepted for compatibility; the posture score now covers it."""
        prob = self.fall_probability
        model = None if (prob is None or guarded or not ready) else prob
        post = None if (posture is None or posture.drop is None) else float(posture.score)
        candidates = [(v, s) for v, s in ((model, "bilstm"), (post, "posture")) if v is not None]
        risk, source = max(candidates) if candidates else (None, None)

        if alarm:
            r = max([v for v in (risk, alarm_confidence) if v is not None], default=None)
            if alarm_source == "posture":
                why = "Raised by the posture check: lying well below the resting position for 2 s."
            elif alarm_source in ("context", "heuristic"):
                why = "Raised by the movement rule: a fast drop below the resting level that stayed down."
            else:
                why = "Raised by the BiLSTM: two windows in a row above its fall threshold."
            res = self._result(HIGH, r, prob, posture, why + " Check the patient now.", "alert")
            res["raised_by"] = alarm_source
        elif risk is None:
            if not person:
                why = "The patient is not clearly in view"
            elif not ready:
                why = "Collecting the first seconds of movement"
            else:
                why = "Waiting for the next model reading"
            res = self._result(UNCERTAIN, None, prob, posture, why)
        else:
            code = level_for(risk)
            if source == "posture":
                lead = f"Posture: {posture.reason.lower()}"
            else:
                lead = "BiLSTM fall probability"
            if code == NORMAL:
                why = "Movement looks like ordinary activity"
                if posture is not None and posture.horizontal >= 0.5 and (posture.drop or 0) < 0.4:
                    why = "Lying at the resting level (bed level), not lower"
            elif code == LOW:
                why = f"{lead} is slightly raised; keep watching"
            elif code == MEDIUM:
                why = f"{lead} suggests a possible fall; check the patient"
            else:
                why = f"{lead} is high; check the patient now"
            if not person and code == NORMAL:
                res = self._result(UNCERTAIN, None, prob, posture, "The patient is not clearly in view")
            else:
                res = self._result(code, risk, prob, posture, why, source)
        self._last = res
        return res

    @property
    def last(self) -> Dict:
        return self._last
