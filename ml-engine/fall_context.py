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
    # Defaults: min_drop, min_speed, settle_samples and settle_tol were chosen on the FallVision DEV
    # split (fall_eval.py tune). anchor="max" was chosen because "bottom" alone missed most standing
    # falls in the IKAR videos (feet are already on the floor). See docs/evaluation/FALL_DETECTION_IMPROVEMENT.md.
    window: int = 48                  # samples of history used for the reference level (about 8 s at 6 Hz)
    reference_gap: int = 12           # the newest samples are excluded from the reference level
    min_drop: float = 0.7             # body-scales the body must end up lower than the resting level
    min_speed: float = 0.3            # body-scales of descent that must happen within speed_span
    speed_span: int = 12              # samples
    settle_samples: int = 4           # consecutive samples that must stay low and still
    settle_tol: float = 0.7           # max height movement (body-scales) while settled
    min_valid: int = 4                # valid samples needed in the reference window
    cooldown: int = 60                # samples after an alert (10 s at 6 Hz)
    smooth: int = 3                   # median filter length on the per-sample height
    anchor: str = "max"               # "bottom" (lowest keypoint), "centre" (mean keypoint) or "max" (larger drop of the two)
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
        anchors = ("bottom", "centre") if c.anchor == "max" else (c.anchor,)
        self._ys: Dict[str, Deque[float]] = {a: deque(maxlen=c.window) for a in anchors}   # smoothed heights
        self._raws: Dict[str, Deque[float]] = {a: deque(maxlen=max(1, c.smooth)) for a in anchors}
        self._scale: Deque[float] = deque(maxlen=c.window)
        self._in_bed: Deque[Optional[float]] = deque(maxlen=c.window)
        self._cooldown = 0
        self._latched = False                                  # one alert per descent

    # ---- helpers ----------------------------------------------------------------------
    def _evaluate(self, y: np.ndarray, L: float):
        """(drop, speed) if this height track shows a fast descent that has settled low, "low" if the
        body is low but not (yet) a qualifying fall, or None if it is not low at all."""
        c = self.cfg
        n = len(y)
        if n < c.reference_gap + c.settle_samples:
            return None
        recent = y[-c.settle_samples:]
        if np.any(np.isnan(recent)):
            return None
        older = y[: n - c.reference_gap]
        older = older[~np.isnan(older)]
        if len(older) < c.min_valid:
            return None
        drop = (float(np.median(recent)) - float(np.median(older))) / L          # image y grows downwards
        if drop < c.min_drop:
            return None
        if (recent.max() - recent.min()) / L > c.settle_tol:                    # still moving: not settled
            return "low"
        speed = 0.0
        for i in range(n - 1):
            if np.isnan(y[i]):
                continue
            w = y[i + 1: i + 1 + c.speed_span]
            w = w[~np.isnan(w)]
            if len(w):
                speed = max(speed, (float(w.max()) - float(y[i])) / L)
        if speed < c.min_speed:
            return "low"                                                         # slow: deliberate, not a fall
        return (drop, speed)

    def _body_scale(self) -> Optional[float]:
        s = [v for v in self._scale if v and v > 0]
        return float(np.median(s)) if len(s) >= 3 else None

    def update(self, kpts: Optional[np.ndarray], bed_zone: Optional[Tuple[float, float, float, float]] = None
               ) -> Optional[ContextSignal]:
        c = self.cfg
        m = body_measures(kpts)
        if m is None:
            for a in self._ys:
                self._raws[a].append(np.nan)
                self._ys[a].append(np.nan)
            self._scale.append(np.nan)
            self._in_bed.append(None)
        else:
            for a in self._ys:
                self._raws[a].append(m[a])
                vals = [v for v in self._raws[a] if not np.isnan(v)]
                self._ys[a].append(float(np.median(vals)))
            scale = m["torso"] if m["torso"] >= 8 else 0.45 * m["box_h"]
            self._scale.append(max(scale, 1.0))
            self._in_bed.append(box_overlap(m["box"], bed_zone) if bed_zone is not None else None)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        L = self._body_scale()
        if L is None:
            return None
        best: Optional[Tuple[float, float]] = None
        any_low = False
        for a in self._ys:
            res = self._evaluate(np.array(self._ys[a], dtype=float), L)
            if res == "low":
                any_low = True
            elif isinstance(res, tuple) and (best is None or res[0] > best[0]):
                best = res
        if not any_low and best is None:
            self._latched = False            # nobody is low any more: the next descent may alert again
        if best is None or self._latched:
            return None
        drop, speed = best
        n = len(self._in_bed)

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


# ── calibrated confidence and the pipeline-facing wrapper ─────────────────────────────

# Logistic calibration of the heuristic score, fitted on the DEV split of FallVision alerts
# (fall_eval.py calibrate). It estimates how often an alert like this was a real fall on that data.
# It is NOT a clinical probability and will differ on other cameras and rooms.
# Fit: 155 DEV alerts (66% in fall clips). TEST: 81 alerts, Brier 0.257 (raw) -> 0.211 (calibrated).
# The slope is small, so the score separates real from false alerts only weakly: the calibrated
# value is close to the overall share of real alerts (about two in three).
CAL_A = 0.1927
CAL_B = 0.5724


def calibrated(score: float) -> float:
    if CAL_A is None or CAL_B is None:
        return round(float(score), 4)
    return round(float(1.0 / (1.0 + np.exp(-(CAL_A * score + CAL_B)))), 4)


class RuleFallDetector:
    """The rule-based check the live and batch pipelines run beside the BiLSTM.

    update(pixel_keypoints) -> (confidence, source) on a new potential fall, else None.
    mode "context" uses ContextualFallDetector; "legacy" uses the old posture-transition rule;
    "off" disables the rule-based check (the BiLSTM alone decides).
    """

    def __init__(self, mode: str = "context", cfg: Optional[ContextConfig] = None):
        from fall_heuristic import PostureTransitionDetector, person_box
        self.mode = mode if mode in ("context", "legacy", "off") else "context"
        self._context = ContextualFallDetector(cfg)
        self._legacy = PostureTransitionDetector()
        self._box = person_box

    def update(self, kpts: Optional[np.ndarray]) -> Optional[Tuple[float, str]]:
        if self.mode == "off":
            return None
        if self.mode == "legacy":
            ar, h = self._box(kpts, KPT_CONF_MIN)
            fired, conf = self._legacy.update(ar, h)
            return (conf, "heuristic") if fired else None
        sig = self._context.update(kpts)
        return (calibrated(sig.score), "context") if sig is not None else None
