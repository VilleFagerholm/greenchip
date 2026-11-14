"""RAM-only activity/movement density grid (feature 007; default ACTIVITY_GRID 12×8).

Spatial axis comes from camera cell motion. Acoustic energy is a room-wide multiplier
only — never per-cell sound location, never temperature, never PCM/frames.
"""

from __future__ import annotations

import math

from sentinel import config


def _clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else float(x))


class ActivityDensity:
    def __init__(
        self,
        cols: int | None = None,
        rows: int | None = None,
        half_life_s: float | None = None,
        acoustic_max: float | None = None,
        label: str | None = None,
    ):
        self.cols = int(config.ACTIVITY_GRID[0] if cols is None else cols)
        self.rows = int(config.ACTIVITY_GRID[1] if rows is None else rows)
        self.half_life_s = float(
            config.ACTIVITY_DECAY_HALFLIFE_S if half_life_s is None else half_life_s
        )
        self.acoustic_max = float(
            config.ACTIVITY_ACOUSTIC_MAX if acoustic_max is None else acoustic_max
        )
        self.label = config.ACTIVITY_LABEL if label is None else label
        self._density = [[0.0] * self.cols for _ in range(self.rows)]
        self._last_t: float | None = None
        self.camera_available = False
        self.acoustic_available = False
        self.acoustic_factor = 1.0

    def set_camera_available(self, ok: bool) -> None:
        self.camera_available = bool(ok)
        if not self.camera_available:
            self._density = [[0.0] * self.cols for _ in range(self.rows)]
            self._last_t = None

    def set_acoustic(self, available: bool, intensity_0_1: float = 0.0) -> None:
        self.acoustic_available = bool(available)
        if not self.acoustic_available:
            self.acoustic_factor = 1.0
            return
        i = _clamp01(intensity_0_1)
        # Map intensity 0→1 onto factor 1→ACTIVITY_ACOUSTIC_MAX
        self.acoustic_factor = 1.0 + i * max(0.0, self.acoustic_max - 1.0)

    def _decay(self, t: float) -> None:
        if self._last_t is None or self.half_life_s <= 0:
            self._last_t = t
            return
        dt = max(0.0, t - self._last_t)
        self._last_t = t
        if dt <= 0:
            return
        # density *= 0.5 ** (dt / half_life)
        scale = math.pow(0.5, dt / self.half_life_s)
        for r in range(self.rows):
            for c in range(self.cols):
                self._density[r][c] = _clamp01(self._density[r][c] * scale)

    def note_cells(self, t: float, grid: list[list[float]]) -> None:
        """Raise densities from a rows×cols float grid in [0, 1] (or compatible)."""
        if not self.camera_available:
            return
        self._decay(t)
        for r in range(self.rows):
            if r >= len(grid):
                break
            row = grid[r]
            for c in range(self.cols):
                if c >= len(row):
                    break
                sample = _clamp01(float(row[c]))
                if sample > self._density[r][c]:
                    self._density[r][c] = sample

    def display_cells(self) -> list[list[float]]:
        factor = self.acoustic_factor if self.acoustic_available else 1.0
        return [
            [_clamp01(self._density[r][c] * factor) for c in range(self.cols)]
            for r in range(self.rows)
        ]

    def to_snapshot(self) -> dict:
        if not self.camera_available:
            return {
                "available": False,
                "cols": self.cols,
                "rows": self.rows,
                "cells": [],
                "acoustic_available": self.acoustic_available,
                "acoustic_factor": 1.0 if not self.acoustic_available else float(self.acoustic_factor),
                "label": self.label,
            }
        return {
            "available": True,
            "cols": self.cols,
            "rows": self.rows,
            "cells": self.display_cells(),
            "acoustic_available": self.acoustic_available,
            "acoustic_factor": float(self.acoustic_factor if self.acoustic_available else 1.0),
            "label": self.label,
        }
