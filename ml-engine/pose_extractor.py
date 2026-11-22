"""
pose_extractor.py — YOLOv8n-pose keypoint extraction.

Exactly replicates the preprocessing from the training notebook:
  - Sample frames at 6 FPS (step = round(native_fps / 6))
  - For each sampled frame, extract 17 COCO keypoints normalised to [0,1]
  - Feature vector: [x0/w, y0/h, x1/w, y1/h, ..., x16/w, y16/h]  (34 values, interleaved)
  - Build a window of exactly 30 frames:
      - If more than 30 collected → take the LAST 30
      - If fewer than 30 → pad with zeros at the START

The BiLSTM was trained on this exact format.
"""
from __future__ import annotations

import numpy as np
from typing import Optional, List, Tuple
from ultralytics import YOLO
import torch
import cv2

from config import POSE_MODEL, POSE_CONF, NUM_KEYPOINTS, FEATURE_DIM

TARGET_SEQ_LEN = 30
SAMPLE_FPS = 6


class PoseExtractor:
    """
    Extracts a fixed (30, 34) keypoint sequence from a video,
    matching the training notebook exactly.
    """

    def __init__(self):
        self._model: Optional[YOLO] = None

    def _load(self) -> YOLO:
        if self._model is None:
            self._model = YOLO(POSE_MODEL)
        return self._model

    @property
    def device(self) -> str:
        return "mps" if torch.backends.mps.is_available() else "cpu"

    def extract_from_video(self, video_path: str) -> np.ndarray:
        """
        Process an entire video and return shape (30, 34).
        Matches extract_keypoint_sequence() from the training notebook exactly.
        """
        model = self._load()
        cap = cv2.VideoCapture(video_path)
        native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, round(native_fps / SAMPLE_FPS))

        sequence: List[List[float]] = []
        idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % step == 0:
                h, w = frame.shape[:2]
                results = model.predict(
                    frame,
                    conf=0.25,          # exactly as in notebook
                    verbose=False,
                    device=self.device,
                )
                frame_coords = [0.0] * 34
                if (results and
                        results[0].keypoints is not None and
                        len(results[0].keypoints.data) > 0):
                    kpts = results[0].keypoints.data[0].cpu().numpy()
                    coords = []
                    for kp in kpts[:17]:
                        # Normalise x/w, y/h — exact notebook code
                        coords.extend([float(kp[0]) / max(1, w),
                                       float(kp[1]) / max(1, h)])
                    if len(coords) == 34:
                        frame_coords = coords
                sequence.append(frame_coords)
            idx += 1

        cap.release()

        # Pad or slice — exact notebook logic
        if len(sequence) < TARGET_SEQ_LEN:
            pad = [[0.0] * 34] * (TARGET_SEQ_LEN - len(sequence))
            sequence = pad + sequence
        else:
            sequence = sequence[-TARGET_SEQ_LEN:]

        return np.array(sequence, dtype=np.float32)  # (30, 34)

    def extract_frame_detailed(
        self, frame: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Like extract_frame, but also returns the raw pixel keypoints (17, 3) =
        (x, y, confidence) for drawing a skeleton overlay. (None, None) if no person.
        """
        model = self._load()
        h, w = frame.shape[:2]
        results = model.predict(
            frame, conf=0.25, verbose=False, device=self.device,
        )
        if (not results or
                results[0].keypoints is None or
                len(results[0].keypoints.data) == 0):
            return None, None

        kpts = results[0].keypoints.data[0].cpu().numpy()
        coords = []
        for kp in kpts[:17]:
            coords.extend([float(kp[0]) / max(1, w),
                           float(kp[1]) / max(1, h)])
        if len(coords) != 34:
            return None, None
        return np.array(coords, dtype=np.float32), kpts[:17]

    def extract_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract a single (34,) normalised keypoint vector from one frame.
        Returns None if no person detected.
        Used by the streaming frame-by-frame pipeline.
        """
        vec, _ = self.extract_frame_detailed(frame)
        return vec
