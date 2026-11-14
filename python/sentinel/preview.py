"""Development Preview Mode gate (constitution Principle I; feature 003).

Off at construction (every boot), impossible when not allowed, holds at most the latest
JPEG in memory and only while active. Never writes frames to disk.
"""

import threading

from sentinel import config

_EPSILON_S = 1e-6


class DevPreviewState:
    def __init__(self, allowed: bool, max_fps: int = config.PREVIEW_MAX_FPS):
        self.allowed = allowed
        self.active = False
        self._interval = 1.0 / max_fps
        self._last_accepted = float("-inf")
        self._frame: bytes | None = None
        self._lock = threading.Lock()

    @property
    def state_name(self) -> str:
        if not self.allowed:
            return "disabled"
        return "on" if self.active else "off"

    def turn_on(self) -> bool:
        with self._lock:
            if self.allowed:
                self.active = True
            return self.active

    def turn_off(self) -> bool:
        with self._lock:
            self.active = False
            self._frame = None
            self._last_accepted = float("-inf")
            return False

    def toggle(self) -> bool:
        return self.turn_off() if self.active else self.turn_on()

    def offer_frame(self, frame: bytes | None, now: float) -> bool:
        with self._lock:
            if not self.active or frame is None:
                return False
            if now - self._last_accepted + _EPSILON_S < self._interval:
                return False
            self._last_accepted = now
            self._frame = frame
            return True

    def latest_frame(self) -> bytes | None:
        with self._lock:
            return self._frame if self.active else None
