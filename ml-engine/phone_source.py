"""
phone_source.py — a phone's browser camera as a live source.

The phone opens a VITALYN link, its browser captures the camera and sends JPEG
frames over a WebSocket (see backend/phone_gateway.py). Each link has a random
token; PhoneSource holds the newest frame for that token and exposes the small
subset of cv2.VideoCapture that live_pipeline uses (isOpened / read / get /
release), so the rest of the live pipeline does not care where frames come from.

Frames are kept in memory only (the newest one) and never written to disk.
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

SOURCE_PREFIX = "phone:"
LINK_TTL_S = 600            # an unused link expires after 10 minutes
MAX_FRAME_BYTES = 2_000_000  # reject oversized frames
MAX_PIXELS = 4_000_000


class PhoneSource:
    def __init__(self, token: str):
        self.token = token
        self.created_at = time.monotonic()
        self.connected = False
        self.ever_connected = False
        self.last_frame_at: Optional[float] = None
        self.frames_received = 0
        self._cond = threading.Condition()
        self._frame: Optional[np.ndarray] = None
        self._frame_id = 0
        self._read_id = 0
        self._closed = False

    # ── producer side (the WebSocket handler) ────────────────────────────────

    def set_connected(self, value: bool) -> None:
        with self._cond:
            self.connected = value
            if value:
                self.ever_connected = True
            self._cond.notify_all()

    def push_jpeg(self, data: bytes) -> bool:
        """Decode and store one JPEG frame. Returns False if it was rejected."""
        if not data or len(data) > MAX_FRAME_BYTES:
            return False
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0] * frame.shape[1] > MAX_PIXELS:
            return False
        with self._cond:
            self._frame = frame
            self._frame_id += 1
            self.frames_received += 1
            self.last_frame_at = time.monotonic()
            self._cond.notify_all()
        return True

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    # ── consumer side (cv2.VideoCapture-like) ────────────────────────────────

    def isOpened(self) -> bool:
        return not self._closed

    def read(self, timeout: float = 1.0) -> Tuple[bool, Optional[np.ndarray]]:
        """Newest unread frame, waiting up to `timeout` seconds."""
        with self._cond:
            if self._frame_id == self._read_id and not self._closed:
                self._cond.wait(timeout)
            if self._closed or self._frame is None or self._frame_id == self._read_id:
                return False, None
            self._read_id = self._frame_id
            return True, self._frame.copy()

    def get(self, _prop) -> float:
        return 0.0

    def release(self) -> None:
        # Not closed on release: the live loop may reconnect to the same link.
        pass

    def age_s(self) -> Optional[float]:
        return None if self.last_frame_at is None else time.monotonic() - self.last_frame_at


class PhoneRegistry:
    """Active phone links. Links that were never used expire after LINK_TTL_S."""

    def __init__(self, ttl_s: float = LINK_TTL_S):
        self._ttl = ttl_s
        self._lock = threading.Lock()
        self._sources: Dict[str, PhoneSource] = {}

    def create(self) -> PhoneSource:
        self.purge()
        token = secrets.token_urlsafe(16)
        source = PhoneSource(token)
        with self._lock:
            self._sources[token] = source
        return source

    def get(self, token: str) -> Optional[PhoneSource]:
        self.purge()
        with self._lock:
            return self._sources.get(token)

    def remove(self, token: str) -> None:
        with self._lock:
            source = self._sources.pop(token, None)
        if source:
            source.close()

    def purge(self) -> None:
        now = time.monotonic()
        with self._lock:
            stale = [t for t, s in self._sources.items()
                     if not s.ever_connected and now - s.created_at > self._ttl]
            dropped = [self._sources.pop(t) for t in stale]
        for s in dropped:
            s.close()

    def expires_in(self, token: str) -> Optional[int]:
        source = self._sources.get(token)
        if source is None:
            return None
        if source.ever_connected:
            return 0
        return max(0, int(self._ttl - (time.monotonic() - source.created_at)))


_registry = PhoneRegistry()


def get_registry() -> PhoneRegistry:
    return _registry


def closed_source() -> PhoneSource:
    s = PhoneSource("")
    s.close()
    return s
