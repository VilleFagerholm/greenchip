"""Occupied / empty / unknown from recent camera movement (data-model.md OccupancyState)."""

from collections import deque

from sentinel import config
from sentinel.motion import MOTION, MotionSample

OCCUPIED, EMPTY, UNKNOWN = "occupied", "empty", "unknown"


class Occupancy:
    def __init__(self):
        self.last_movement_t: float | None = None
        self.healthy_since_t: float | None = None
        self._motion_times: deque[float] = deque()
        self._now = 0.0

    def update(self, t: float, sample: MotionSample | None, camera_ok: bool) -> None:
        self._now = t
        if not camera_ok:
            self.healthy_since_t = None
            self._motion_times.clear()
            return
        if self.healthy_since_t is None:
            self.healthy_since_t = t
        if sample is None or sample.kind != MOTION:
            return
        self._motion_times.append(sample.t)
        while self._motion_times and sample.t - self._motion_times[0] > config.MOVEMENT_WINDOW_S:
            self._motion_times.popleft()
        if len(self._motion_times) >= config.MOVEMENT_MIN_FRAMES:
            self.last_movement_t = sample.t

    def state(self, t: float | None = None) -> str:
        t = self._now if t is None else t
        if self.healthy_since_t is None:
            return UNKNOWN
        if self.last_movement_t is not None and t - self.last_movement_t < config.EMPTY_AFTER_S:
            return OCCUPIED
        if t - self.healthy_since_t >= config.EMPTY_AFTER_S:
            return EMPTY
        return UNKNOWN

    def moving_now(self, t: float | None = None) -> bool:
        t = self._now if t is None else t
        return self.last_movement_t is not None and t - self.last_movement_t <= config.MOVEMENT_WINDOW_S
