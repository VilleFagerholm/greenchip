"""Window-area change signal and calibration (research R4, data-model.md WindowWatch).

The summary is GRID cells of contrast-normalised mean brightness: far too coarse to show a
person, and the only camera-derived value that is ever saved.
"""

from dataclasses import dataclass

import numpy as np

from sentinel import config

READY, SETUP_NEEDED, CALIBRATING = "ready", "setup_needed", "calibrating"
WAITING, CAPTURING, DONE, FAILED = 0, 1, 2, 3  # show_calibration phases


@dataclass(frozen=True)
class WindowReference:
    area: tuple[float, float, float, float]
    cells: tuple[float, ...]
    captured_at: str

    def to_dict(self) -> dict:
        return {"area": list(self.area), "cells": [round(c, 4) for c in self.cells],
                "captured_at": self.captured_at}

    @classmethod
    def from_dict(cls, d) -> "WindowReference | None":
        try:
            area = tuple(float(v) for v in d["area"])
            cells = tuple(float(v) for v in d["cells"])
            captured_at = str(d["captured_at"])
        except (KeyError, TypeError, ValueError):
            return None
        if len(area) != 4 or len(cells) != config.GRID[0] * config.GRID[1]:
            return None
        return cls(area, cells, captured_at)

    def matches_config(self) -> bool:
        return np.allclose(self.area, config.WINDOW_AREA)


def summarize(gray: np.ndarray, area=config.WINDOW_AREA, grid=config.GRID) -> np.ndarray | None:
    h, w = gray.shape
    x0, y0, x1, y1 = area
    crop = gray[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].astype(np.float32)
    cols, rows = grid
    if crop.shape[0] < rows or crop.shape[1] < cols:
        return None
    std = float(crop.std())
    if std < config.MIN_AREA_STD:
        return None
    ch, cw = crop.shape
    means = [crop[r * ch // rows:(r + 1) * ch // rows, c * cw // cols:(c + 1) * cw // cols].mean()
             for r in range(rows) for c in range(cols)]
    return (np.array(means, dtype=np.float32) - crop.mean()) / std


class WindowWatch:
    def __init__(self, reference: WindowReference | None = None):
        self.set_reference(reference)

    def set_reference(self, reference: WindowReference | None) -> None:
        self.reference = reference if reference is not None and reference.matches_config() else None
        self._ref = None if self.reference is None else np.array(self.reference.cells, dtype=np.float32)
        self.signal = False
        self.changed_cells = 0
        self.changed_since_t: float | None = None
        self._unchanged_since_t: float | None = None

    @property
    def status(self) -> str:
        return READY if self.reference is not None else SETUP_NEEDED

    def update(self, t: float, summary: np.ndarray | None, moving_now: bool) -> None:
        if self._ref is None or moving_now or summary is None:
            return
        self.changed_cells = int(np.count_nonzero(np.abs(summary - self._ref) > config.CELL_DIFF_THRESHOLD))
        if self.changed_cells >= config.MIN_CHANGED_CELLS:
            self._unchanged_since_t = None
            if self.changed_since_t is None:
                self.changed_since_t = t
            if t - self.changed_since_t >= config.WINDOW_PERSIST_S:
                self.signal = True
        else:
            self.changed_since_t = None
            if self._unchanged_since_t is None:
                self._unchanged_since_t = t
            if self.signal and t - self._unchanged_since_t >= config.WINDOW_CLEAR_S:
                self.signal = False


class Calibration:
    """Wait for stillness, then average the summary into a new closed-window reference."""

    def __init__(self, t: float):
        self.started_t = t
        self.phase = WAITING
        self.seconds = int(config.CALIB_STILL_S)
        self.reference: WindowReference | None = None
        self._still_since_t: float | None = None
        self._capture_since_t: float | None = None
        self._samples: list[np.ndarray] = []

    @property
    def finished(self) -> bool:
        return self.phase in (DONE, FAILED)

    def update(self, t: float, summary: np.ndarray | None, moving_now: bool, captured_at: str) -> int:
        if self.finished:
            return self.phase
        if moving_now:
            self.phase, self._still_since_t, self._capture_since_t = WAITING, None, None
            self._samples.clear()
        if self.phase == WAITING:
            if t - self.started_t >= config.CALIB_TIMEOUT_S:
                self.phase = FAILED
                return self.phase
            if not moving_now and self._still_since_t is None:
                self._still_since_t = t
            still = 0.0 if self._still_since_t is None else t - self._still_since_t
            self.seconds = max(0, int(round(config.CALIB_STILL_S - still)))
            if still >= config.CALIB_STILL_S:
                self.phase, self._capture_since_t = CAPTURING, t
        if self.phase == CAPTURING:
            if summary is not None:
                self._samples.append(summary)
            if t - self._capture_since_t >= config.CALIB_CAPTURE_S:
                if not self._samples:
                    self.phase = FAILED
                else:
                    cells = tuple(float(v) for v in np.mean(self._samples, axis=0))
                    self.reference = WindowReference(tuple(config.WINDOW_AREA), cells, captured_at)
                    self.phase = DONE
        return self.phase
