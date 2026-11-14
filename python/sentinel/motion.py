"""Frame-difference motion on downscaled grayscale frames (research R2, R3)."""

from dataclasses import dataclass

import numpy as np

from sentinel import config

STILL, MOTION, LIGHTING = "still", "motion", "lighting"


@dataclass(frozen=True)
class MotionSample:
    t: float
    fraction: float
    kind: str
    detail: float


def prepare(frame_bgr) -> np.ndarray:
    """Camera frame -> small blurred grayscale frame. The input frame is not kept."""
    import cv2

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, config.FRAME_SIZE, interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(small, (config.BLUR_KSIZE, config.BLUR_KSIZE), 0)


def compute(prev: np.ndarray, cur: np.ndarray, t: float) -> MotionSample:
    diff = np.abs(cur.astype(np.int16) - prev.astype(np.int16))
    fraction = float(np.count_nonzero(diff > config.PIXEL_DIFF_THRESHOLD)) / diff.size
    if fraction > config.LIGHTING_FRACTION:
        kind = LIGHTING
    elif fraction >= config.MOTION_MIN_FRACTION:
        kind = MOTION
    else:
        kind = STILL
    return MotionSample(t, fraction, kind, float(cur.std()))


def cell_motion_map(prev: np.ndarray, cur: np.ndarray, grid=config.GRID) -> list[list[int]]:
    """Full-frame motion per grid cell as digits 0-9, for choosing WINDOW_AREA (area finder)."""
    cols, rows = grid
    h, w = cur.shape
    changed = np.abs(cur.astype(np.int16) - prev.astype(np.int16)) > config.PIXEL_DIFF_THRESHOLD
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            cell = changed[r * h // rows:(r + 1) * h // rows, c * w // cols:(c + 1) * w // cols]
            row.append(min(9, int(round(cell.mean() * 30))))
        out.append(row)
    return out
