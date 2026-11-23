"""
fall_risk.py — continuous, per-sample fall-risk signal from body posture ("lying lower than before").

Why it exists: the two alert paths that were measured on FallVision (the BiLSTM and the context rule
in fall_context.py) are deliberately strict. The context rule needs a FAST drop, and its alerts are
held back when the BiLSTM (trained on bed scenes) is confident the movement is normal. A person who
lies down on the floor slowly in front of a desk or laptop camera therefore raised nothing at all.

This module does not replace those paths. It adds a graded signal that is updated on every analysed
sample (6 per second) and is shown to staff as a risk level, so lower-confidence situations are
visible instead of silently ignored:

  * HORIZONTAL: how close the torso (shoulder centre -> hip centre) is to horizontal, or, when the
    torso is not visible, how much wider than tall the visible body is.
  * LOWER THAN BEFORE: how far the shoulders are below the person's own recent resting level, in
    units of their torso length. The resting level is the median height over the last ~20 s
    (excluding the newest 1 s) and is FROZEN while the risk is raised, so a person who stays on the
    floor does not become the new "normal".

  posture score = horizontal x lower-than-before, plus a smaller term for being very low while
  upright-ish (sitting slumped on the floor). It is smoothed with a short exponential average.

BED versus FLOOR (what the data supports): lying in bed keeps the body at the level where the
patient has been resting, so the "lower than before" factor stays near 0 and the score stays low even
though the body is horizontal. Lying on the floor after sitting or standing is both horizontal AND
much lower, so the score rises. If the patient was already lying on the floor when monitoring started,
there is no "before" to compare with and this signal cannot tell; a configured bed zone would be needed.
The camera view matters: "lower in the image" means closer to the floor for a side or oblique camera.

The score is a HEURISTIC in [0, 1] built from measured keypoints. It is NOT a probability and NOT
clinically validated. Every raised level is a potential event that needs human review.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

import numpy as np

KPT_CONF_MIN = 0.3


@dataclass
class RiskConfig:
    ref_window: int = 120            # samples of history for the resting level (20 s at 6 Hz)
    ref_gap: int = 6                 # newest samples excluded from the resting level (1 s)
    min_ref: int = 6                 # valid samples needed before the resting level is trusted (1 s)
    drop_start: float = 0.4          # torso-lengths below resting level where "lower" starts to count
    drop_full: float = 1.6           # ... and where it counts fully
    angle_start: float = 35.0        # torso degrees from vertical where "horizontal" starts to count
    angle_full: float = 65.0         # ... and where it counts fully
    aspect_start: float = 1.0        # body width / height where "horizontal" starts (torso not visible)
    aspect_full: float = 1.8
    collapse_weight: float = 0.6     # weight of "very low but not horizontal" (slumped on the floor)
    collapse_start: float = 1.0
    collapse_full: float = 2.0
    ema: float = 0.35                # smoothing per sample (about 0.5 s time constant at 6 Hz)
    freeze_at: float = 0.3           # freeze the resting level while the smoothed score is above this
    unfreeze_drop: float = 0.3       # ... until the body is back within this of the resting level


@dataclass
class PostureReading:
    score: float                     # smoothed heuristic score, 0..1 (NOT a probability)
    raw: float                       # this sample's unsmoothed score
    horizontal: float                # 0..1
    drop: Optional[float]            # torso-lengths below the resting level (None: no level yet)
    angle: Optional[float]           # torso degrees from vertical (None: torso not visible)
    reason: str


def _ramp(x: float, start: float, full: float) -> float:
    if full <= start:
        return 1.0 if x >= full else 0.0
    return float(min(1.0, max(0.0, (x - start) / (full - start))))


def _measures(kpts: Optional[np.ndarray]):
    """(centre_y, torso_length, torso_angle_deg or None, aspect) from (17, 3) pixel keypoints, or None."""
    if kpts is None:
        return None
    ok = kpts[:, 2] >= KPT_CONF_MIN
    if int(ok.sum()) < 5:
        return None
    pts = kpts[ok, :2]
    w = float(pts[:, 0].max() - pts[:, 0].min())
    h = float(pts[:, 1].max() - pts[:, 1].min())
    aspect = w / max(h, 1.0)
    sh = kpts[[5, 6]][ok[[5, 6]], :2]
    hip = kpts[[11, 12]][ok[[11, 12]], :2]
    angle, torso = None, 0.0
    if len(sh) and len(hip):
        v = sh.mean(0) - hip.mean(0)
        torso = float(np.hypot(v[0], v[1]))
        if torso >= 8:
            angle = math.degrees(math.atan2(abs(float(v[0])), abs(float(v[1]))))
    # Height anchor: the shoulder centre (visible in almost every view, including a desk camera that
    # cannot see the hips), else the mean of the visible keypoints.
    centre = float(sh.mean(0)[1]) if len(sh) else float(pts[:, 1].mean())
    shoulder_w = float(np.linalg.norm(sh[0] - sh[1])) if len(sh) == 2 else 0.0
    if torso >= 8:
        scale = torso
    elif shoulder_w >= 8:
        scale = 1.2 * shoulder_w                    # torso is roughly 1.2 shoulder widths
    else:
        scale = 0.45 * h
    return centre, max(scale, 1.0), angle, aspect


class FloorPostureMonitor:
    """Call update(pixel_keypoints or None) once per analysed sample; read the returned PostureReading."""

    def __init__(self, cfg: Optional[RiskConfig] = None):
        self.cfg = cfg or RiskConfig()
        self.reset()

    def reset(self) -> None:
        c = self.cfg
        self._ys: Deque[float] = deque(maxlen=c.ref_window)
        self._scales: Deque[float] = deque(maxlen=c.ref_window)
        self._frozen: Optional[tuple] = None          # (resting level, scale) while the risk is raised
        self.score = 0.0
        self.last = PostureReading(0.0, 0.0, 0.0, None, None, "Waiting for the person")

    def _reference(self) -> Optional[tuple]:
        if self._frozen is not None:
            return self._frozen
        c = self.cfg
        ys = [y for y in list(self._ys)[: max(0, len(self._ys) - c.ref_gap)] if not np.isnan(y)]
        sc = [s for s in list(self._scales)[: max(0, len(self._scales) - c.ref_gap)] if not np.isnan(s)]
        if len(ys) < c.min_ref or len(sc) < c.min_ref:
            return None
        return float(np.median(ys)), float(np.median(sc))

    def update(self, kpts: Optional[np.ndarray]) -> PostureReading:
        c = self.cfg
        m = _measures(kpts)
        if m is None:
            self._ys.append(np.nan)
            self._scales.append(np.nan)
            # Nobody measurable: decay slowly rather than drop to zero (the person may be hidden on the floor).
            self.score *= 0.97
            self.last = PostureReading(round(self.score, 4), 0.0, 0.0, None, None, "Person not clearly visible")
            return self.last

        centre, scale, angle, aspect = m
        self._ys.append(centre)
        self._scales.append(scale)
        if angle is not None:
            horizontal = _ramp(angle, c.angle_start, c.angle_full)
        else:
            horizontal = _ramp(aspect, c.aspect_start, c.aspect_full)

        ref = self._reference()
        drop = None
        raw = 0.0
        if ref is not None:
            level, L = ref
            drop = (centre - level) / L                      # image y grows downwards: positive = lower
            low = _ramp(drop, c.drop_start, c.drop_full)
            collapse = c.collapse_weight * _ramp(drop, c.collapse_start, c.collapse_full)
            raw = max(horizontal * low, collapse)

        self.score = (1 - c.ema) * self.score + c.ema * raw

        # Freeze the resting level while the risk is raised; release once the body is back up.
        if self._frozen is None and ref is not None and self.score >= c.freeze_at:
            self._frozen = ref
        elif self._frozen is not None and drop is not None and drop < c.unfreeze_drop and self.score < c.freeze_at:
            self._frozen = None

        if ref is None:
            reason = "Learning the person's resting position"
        elif raw >= 0.5 and horizontal >= 0.5:
            reason = "Lying lower than the resting position (floor level)"
        elif raw >= 0.5:
            reason = "Body far below the resting position"
        elif horizontal >= 0.5:
            reason = "Lying at the resting level (bed level)"
        elif drop is not None and drop >= c.drop_start:
            reason = "Body lower than the resting position"
        else:
            reason = "Upright or at the resting position"
        self.last = PostureReading(round(self.score, 4), round(raw, 4), round(horizontal, 3),
                                   None if drop is None else round(drop, 3),
                                   None if angle is None else round(angle, 1), reason)
        return self.last
