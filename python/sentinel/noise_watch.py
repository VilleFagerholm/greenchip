"""Outdoor-noise signal: the room's background loudness rises and stays up (research R12).

Audio chunks are reduced to one loudness number and dropped; nothing is recorded, and no
speech or sound classification is done (constitution I).
"""

from collections import deque
from statistics import median

import numpy as np

from sentinel import config


def rms_dbfs(samples: np.ndarray) -> float:
    """RMS level of int16 samples in dB relative to full scale."""
    if samples.size == 0:
        return config.SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64))))) / 32768.0
    if rms <= 0.0:
        return config.SILENCE_DBFS
    return max(config.SILENCE_DBFS, 20.0 * float(np.log10(rms)))


class NoiseWatch:
    def __init__(self):
        self._chunks: deque[tuple[float, float]] = deque()
        self._history: deque[tuple[float, float]] = deque()
        self.floor_db: float | None = None
        self.baseline_db: float | None = None
        self.last_db: float | None = None
        self.signal = False
        self._loud_since_t: float | None = None
        self._quiet_since_t: float | None = None

    @property
    def rise_db(self) -> float | None:
        if self.floor_db is None or self.baseline_db is None:
            return None
        return self.floor_db - self.baseline_db

    def median_db(self, t: float, window_s: float | None = None) -> float | None:
        window_s = config.NOISE_UI_MEDIAN_S if window_s is None else window_s
        vals = [v for ts, v in self._chunks if t - ts <= window_s]
        return float(median(vals)) if vals else None

    def add_chunk(self, t: float, level_dbfs: float) -> None:
        self.last_db = level_dbfs
        self._chunks.append((t, level_dbfs))
        while t - self._chunks[0][0] > config.NOISE_FLOOR_WINDOW_S:
            self._chunks.popleft()

    def update(self, t: float, freeze: bool) -> None:
        """Once per second. freeze: room occupied, signal on, or an alert running."""
        if not self._chunks:
            return
        self.floor_db = float(np.percentile([v for _, v in self._chunks], config.NOISE_FLOOR_PERCENTILE))
        if not freeze:
            self._history.append((t, self.floor_db))
            while t - self._history[0][0] > config.NOISE_BASELINE_WINDOW_S:
                self._history.popleft()
            if t - self._history[0][0] >= config.NOISE_BASELINE_MIN_S:
                self.baseline_db = median(v for _, v in self._history)

        rise = self.rise_db
        threshold = config.NOISE_RISE_DB - (config.NOISE_HYSTERESIS_DB if self.signal else 0.0)
        if rise is not None and rise >= threshold:
            self._quiet_since_t = None
            if self._loud_since_t is None:
                self._loud_since_t = t
            if t - self._loud_since_t >= config.NOISE_PERSIST_S:
                self.signal = True
        else:
            self._loud_since_t = None
            if self._quiet_since_t is None:
                self._quiet_since_t = t
            if self.signal and t - self._quiet_since_t >= config.NOISE_CLEAR_S:
                self.signal = False

    def reset(self) -> None:
        self.__init__()
