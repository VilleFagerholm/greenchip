"""RAM-only acoustic energy strip: coarse time bins of derived loudness/rise (feature 006).

Single intensity channel over time — not a room floor-plan and not a multi-band spectrum.
Audio chunks are never stored; only normalized 0–1 intensities for the Room HUD.
"""

from __future__ import annotations

import math
from collections import deque

from sentinel import config


def _clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else float(x))


def intensity_from_sample(
    level_db: float | None,
    rise_db: float | None,
    baseline_ready: bool,
) -> tuple[float, str, float | None]:
    """Return (intensity 0–1, mode, raw value used)."""
    if baseline_ready and rise_db is not None:
        full = float(config.HEATMAP_RISE_FULL_DB) or 1.0
        return _clamp01(float(rise_db) / full), "rise", float(rise_db)
    if level_db is None:
        return 0.0, "absolute", None
    quiet = float(config.HEATMAP_ABS_QUIET_DB)
    loud = float(config.HEATMAP_ABS_LOUD_DB)
    span = loud - quiet
    if span <= 0:
        return 0.0, "absolute", float(level_db)
    return _clamp01((float(level_db) - quiet) / span), "absolute", float(level_db)


class EnergyHeatmap:
    """Bounded in-memory window of coarse energy bins for the HUD strip."""

    def __init__(
        self,
        window_s: float | None = None,
        bin_s: float | None = None,
        label: str | None = None,
    ):
        self.window_s = float(config.HEATMAP_WINDOW_S if window_s is None else window_s)
        self.bin_s = float(config.HEATMAP_BIN_S if bin_s is None else bin_s)
        self.label = config.HEATMAP_LABEL if label is None else label
        self.available = False
        self._bins: deque[dict] = deque()
        self._open: dict | None = None
        self._last_mode = "none"

    @property
    def max_bins(self) -> int:
        return max(1, int(math.ceil(self.window_s / self.bin_s)))

    def set_available(self, ok: bool) -> None:
        self.available = bool(ok)
        if not self.available:
            self._bins.clear()
            self._open = None
            self._last_mode = "none"

    def update(
        self,
        t: float,
        level_db: float | None,
        rise_db: float | None,
        baseline_ready: bool,
    ) -> None:
        """Advance the open bin when available; ignore samples when unavailable."""
        if not self.available:
            return
        intensity, mode, raw = intensity_from_sample(level_db, rise_db, baseline_ready)
        self._last_mode = mode
        bin_start = math.floor(t / self.bin_s) * self.bin_s
        t_end = bin_start + self.bin_s
        if self._open is None or self._open["t_end"] != t_end:
            if self._open is not None:
                self._bins.append(self._open)
            self._open = {
                "t_end": t_end,
                "intensity": intensity,
                "raw": raw,
                "mode": mode,
            }
        else:
            if intensity > self._open["intensity"]:
                self._open["intensity"] = intensity
                self._open["raw"] = raw
                self._open["mode"] = mode
        self._trim(t)

    def _trim(self, t: float) -> None:
        cutoff = t - self.window_s
        while self._bins and self._bins[0]["t_end"] < cutoff:
            self._bins.popleft()
        # Keep at most max_bins completed + current open handled in to_snapshot
        while len(self._bins) > self.max_bins:
            self._bins.popleft()

    def to_snapshot(self) -> dict:
        if not self.available:
            return {
                "available": False,
                "window_s": self.window_s,
                "bin_s": self.bin_s,
                "intensity_mode": "none",
                "bins": [],
                "label": self.label,
            }
        rows = list(self._bins)
        if self._open is not None:
            rows = rows + [self._open]
        if len(rows) > self.max_bins + 1:
            rows = rows[-(self.max_bins + 1) :]
        mode = self._open["mode"] if self._open is not None else self._last_mode
        if not rows:
            mode = self._last_mode if self._last_mode != "none" else "absolute"
        return {
            "available": True,
            "window_s": self.window_s,
            "bin_s": self.bin_s,
            "intensity_mode": mode if mode in ("rise", "absolute") else "absolute",
            "bins": [_clamp01(b["intensity"]) for b in rows],
            "label": self.label,
        }
