"""
fall_heuristic.py — Rule-based temporal fall detection.

Used as a secondary signal alongside the BiLSTM: PostureTransitionDetector flags a person
who goes from upright to horizontal quickly with a collapse in body height.

This is explicitly labelled as a heuristic, not a trained classifier.
Both this and the BiLSTM output are reported transparently in the pipeline.
"""
from __future__ import annotations

from collections import deque
from typing import Optional, Tuple
import numpy as np

# ---------------------------------------------------------------------------
# Posture-transition detector (used by the live and batch pipelines)
# ---------------------------------------------------------------------------

UPRIGHT_AR        = 0.9    # person clearly upright below this width/height
FALLEN_AR         = 1.0    # person clearly horizontal at/above this
MIN_UPRIGHT       = 3      # consecutive upright samples that establish a baseline
MIN_FALLEN        = 3      # consecutive horizontal samples needed to confirm
MAX_TRANSITION    = 12     # samples (~2 s at 6 fps) from upright to horizontal
MIN_HEIGHT_DROP   = 0.35   # body height must shrink by this fraction vs baseline
TRANSITION_COOLDOWN = 30   # samples (~5 s) after a trigger


class PostureTransitionDetector:
    """
    Flags a potential fall only when a person who was UPRIGHT becomes HORIZONTAL
    within a short time and their body height collapses.

    A static horizontal posture never triggers it, so a patient lying in bed, or
    someone who walks into view already lying down, is not reported. It is still
    a rule of thumb, not a validated classifier: it assumes a roughly side/front
    view, and a fast deliberate lie-down can look like a fall.

    Call update(aspect_ratio, height) once per sampled frame; pass None, None when
    no person is visible. `confidence` is a heuristic score in [0.5, 0.9], not a
    probability.
    """

    def __init__(self):
        self._upright_run = 0
        self._upright_heights: deque = deque(maxlen=MIN_UPRIGHT)
        self._baseline: Optional[float] = None
        self._since_upright = 0
        self._fallen_run = 0
        self._cooldown = 0

    def reset(self) -> None:
        self.__init__()

    def update(self, aspect_ratio: Optional[float], height: Optional[float]) -> Tuple[bool, float]:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False, 0.0

        if aspect_ratio is None or height is None:
            self._upright_run = 0
            self._fallen_run = 0
            if self._baseline is not None:
                self._since_upright += 1
            return False, 0.0

        if aspect_ratio < UPRIGHT_AR:
            self._upright_run += 1
            self._upright_heights.append(height)
            if self._upright_run >= MIN_UPRIGHT:
                self._baseline = float(np.median(list(self._upright_heights)))
                self._since_upright = 0
        else:
            self._upright_run = 0
            self._upright_heights.clear()
            if self._baseline is not None:
                self._since_upright += 1

        self._fallen_run = self._fallen_run + 1 if aspect_ratio >= FALLEN_AR else 0

        if (
            self._baseline is not None
            and self._fallen_run >= MIN_FALLEN
            and self._since_upright <= MAX_TRANSITION + MIN_FALLEN
        ):
            drop = 1.0 - (height / max(self._baseline, 1e-6))
            if drop >= MIN_HEIGHT_DROP:
                conf = 0.5 + 0.4 * min(1.0, (drop - MIN_HEIGHT_DROP) / 0.4)
                self._baseline = None
                self._fallen_run = 0
                self._cooldown = TRANSITION_COOLDOWN
                return True, round(conf, 4)

        # Baseline too old to explain what we see now: forget it.
        if self._baseline is not None and self._since_upright > MAX_TRANSITION + MIN_FALLEN:
            self._baseline = None
        return False, 0.0


def person_box(pixel_kpts: Optional[np.ndarray], conf_min: float = 0.3):
    """(aspect_ratio, height_px) of the confident keypoints in pixels, or (None, None)."""
    if pixel_kpts is None:
        return None, None
    pts = pixel_kpts[pixel_kpts[:, 2] >= conf_min]
    if len(pts) < 5:
        return None, None
    w = float(pts[:, 0].max() - pts[:, 0].min())
    h = float(pts[:, 1].max() - pts[:, 1].min())
    return w / max(h, 1.0), h
