"""
fall_context.py — context-aware potential-fall detector (descent, settling and location).

Why it exists: the posture rule in fall_heuristic.py only fires for "upright -> horizontal". In bed
settings many real falls start while the person is already lying (they roll or slide off the bed), and
ordinary bed activity (sitting up, turning, lying down) also changes the bounding box a lot. This
detector looks at WHERE the body is relative to where the person has been resting, HOW fast it got
there, and whether it STAYS there:

  1. Per-sample features come from confident keypoints only (anchor height, body scale), smoothed with a
     short median so single bad frames do not move them.
  2. REFERENCE LEVEL: the person's recent resting height (their bed level), taken from the older part of
     a rolling window.
  3. DESCENT: the body must have dropped by at least `min_drop` body-scales relative to that level,
     and a large part of the drop must happen quickly (`min_speed` body-scales within `speed_span`
     samples). Slow, deliberate lying down or sitting up never reaches the speed requirement.
  4. SETTLED: the body must then stay low and still for `settle_samples` consecutive samples. A dip that
     recovers (sitting, bending, reaching) is not reported.
  5. BED ZONE (optional): if the caller supplies a bed rectangle, a person who ends up inside it is not
     reported (lying in bed), and one who ends outside it after starting inside gets a higher score.

It returns a heuristic score in [0, 1] (not a probability) and the reasons. Every output is a POTENTIAL
fall that needs human review. Thresholds were chosen on a development split of FallVision clips and
checked on a held-out split (see docs/evaluation/FALL_DETECTION_IMPROVEMENT.md). The camera view
matters: "lower in the image" means closer to the floor for a side or oblique camera, and is much weaker
for a camera pointing straight down.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

import numpy as np

KPT_CONF_MIN = 0.3


@dataclass
class ContextConfig:
    window: int = 48                  # samples of history used for the reference level (about 8 s at 6 Hz)
    reference_gap: int = 12           # the newest samples are excluded from the reference level
    min_drop: float = 1.0             # body-scales the body must end up lower than the resting level
    min_speed: float = 0.6            # body-scales of descent that must happen within speed_span
    speed_span: int = 12              # samples
    settle_samples: int = 6           # consecutive samples that must stay low and still
    settle_tol: float = 0.45          # max height movement (body-scales) while settled
    min_valid: int = 4                # valid samples needed in the reference window
    cooldown: int = 60                # samples after an alert (10 s at 6 Hz)
    smooth: int = 3                   # median filter length on the per-sample height
    anchor: str = "bottom"            # "bottom" (lowest confident keypoint) or "centre"
    bed_overlap_suppress: float = 0.6  # share of the body inside the bed box that counts as "in bed"


def body_measures(kpts: Optional[np.ndarray], conf_min: float = KPT_CONF_MIN) -> Optional[Dict[str, float]]:
    """Height anchors and body scale from a (17, 3) pixel keypoint array, or None if too little is visible."""
    if kpts is None:
        return None
    ok = kpts[:, 2] >= conf_min
    if int(ok.sum()) < 5:
        return None
    pts = kpts[ok, :2]
    sh = kpts[[5, 6]][ok[[5, 6]], :2]
    hip = kpts[[11, 12]][ok[[11, 12]], :2]
    box_h = float(pts[:, 1].max() - pts[:, 1].min())
    box_w = float(pts[:, 0].max() - pts[:, 0].min())
    if len(sh) and len(hip):
        torso = float(np.linalg.norm(sh.mean(0) - hip.mean(0)))
    else:
        torso = 0.0
    return {
        "bottom": float(pts[:, 1].max()),
        "centre": float(pts[:, 1].mean()),
        "x": float(pts[:, 0].mean()),
        "torso": torso,
        "box_h": box_h,
        "box_w": box_w,
        "box": (float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())),
    }


def box_overlap(person: Tuple[float, float, float, float], zone: Tuple[float, float, float, float]) -> float:
    """Share of the person's box that lies inside the zone rectangle (x1, y1, x2, y2)."""
    px1, py1, px2, py2 = person
    zx1, zy1, zx2, zy2 = zone
    iw = max(0.0, min(px2, zx2) - max(px1, zx1))
    ih = max(0.0, min(py2, zy2) - max(py1, zy1))
    area = max((px2 - px1) * (py2 - py1), 1e-6)
    return (iw * ih) / area


@dataclass
class ContextSignal:
    score: float                      # heuristic, 0..1, NOT a probability
    drop: float                       # body-scales lower than the resting level
    speed: float                      # fastest descent within speed_span, body-scales
    reasons: Dict[str, float] = field(default_factory=dict)


class ContextualFallDetector:
    """Call update(kpts) once per analysed sample (None when no person). Returns a ContextSignal on a new alert."""

    def __init__(self, cfg: Optional[ContextConfig] = None):
        self.cfg = cfg or ContextConfig()
        self.reset()

    def reset(self) -> None:
        c = self.cfg
        self._y: Deque[float] = deque(maxlen=c.window)        # smoothed anchor height, NaN when unknown
        self._raw: Deque[float] = deque(maxlen=max(1, c.smooth))
        self._scale: Deque[float] = deque(maxlen=c.window)
        self._in_bed: Deque[Optional[float]] = deque(maxlen=c.window)
        self._cooldown = 0
        self._latched = False                                  # one alert per descent

    # ---- helpers ----------------------------------------------------------------------
    def _body_scale(self) -> Optional[float]:
        s = [v for v in self._scale if v and v > 0]
        return float(np.median(s)) if len(s) >= 3 else None

    def update(self, kpts: Optional[np.ndarray], bed_zone: Optional[Tuple[float, float, float, float]] = None
               ) -> Optional[ContextSignal]:
        c = self.cfg
        m = body_measures(kpts)
        if m is None:
            self._raw.append(np.nan)
            self._y.append(np.nan)
            self._scale.append(np.nan)
            self._in_bed.append(None)
        else:
            self._raw.append(m[c.anchor])
            vals = [v for v in self._raw if not np.isnan(v)]
            self._y.append(float(np.median(vals)))
            scale = m["torso"] if m["torso"] >= 8 else 0.45 * m["box_h"]
            self._scale.append(max(scale, 1.0))
            self._in_bed.append(box_overlap(m["box"], bed_zone) if bed_zone is not None else None)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        n = len(self._y)
        if n < c.reference_gap + c.settle_samples:
            return None
        y = np.array(self._y, dtype=float)
        L = self._body_scale()
        if L is None:
            return None

        recent = y[-c.settle_samples:]
        if np.any(np.isnan(recent)):
            return None
        older = y[: n - c.reference_gap]
        older = older[~np.isnan(older)]
        if len(older) < c.min_valid:
            return None

        reference = float(np.median(older))
        level = float(np.median(recent))
        drop = (level - reference) / L                                   # image y grows downwards
        if drop < c.min_drop:
            self._latched = False
            return None
        if self._latched:
            return None
        if (recent.max() - recent.min()) / L > c.settle_tol:             # still moving: not settled yet
            return None

        # How fast did the descent happen? Largest rise of y within speed_span samples.
        span = c.speed_span
        speed = 0.0
        for i in range(n - 1):
            if np.isnan(y[i]):
                continue
            w = y[i + 1: i + 1 + span]
            w = w[~np.isnan(w)]
            if len(w):
                speed = max(speed, (float(w.max()) - float(y[i])) / L)
        if speed < c.min_speed:
            return None                                                  # slow movement: deliberate, not a fall

        reasons: Dict[str, float] = {}
        overlap = [v for v in list(self._in_bed)[-c.settle_samples:] if v is not None]
        if overlap:
            now_in_bed = float(np.mean(overlap))
            earlier = [v for v in list(self._in_bed)[: n - c.reference_gap] if v is not None]
            before_in_bed = float(np.mean(earlier)) if earlier else None
            reasons["in_bed_now"] = now_in_bed
            if now_in_bed >= c.bed_overlap_suppress:
                return None                                              # lying on the bed is not a fall
            if before_in_bed is not None:
                reasons["in_bed_before"] = before_in_bed

        score = 0.4 + 0.3 * min(1.0, (drop - c.min_drop) / 1.5) + 0.3 * min(1.0, (speed - c.min_speed) / 1.5)
        if reasons.get("in_bed_before", 0.0) >= c.bed_overlap_suppress:
            score = min(1.0, score + 0.1)                                # left the bed and stayed down
        self._latched = True
        self._cooldown = c.cooldown
        return ContextSignal(score=round(float(score), 4), drop=round(drop, 3), speed=round(speed, 3), reasons=reasons)
