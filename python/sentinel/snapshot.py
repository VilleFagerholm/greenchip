"""HudSnapshot / DashboardSnapshot JSON for the Room HUD (features 004–007)."""

from sentinel import config
from sentinel.alerts import AUDIBLE, CAPPED, NONE, SNOOZED, VISUAL
from sentinel.selftest import DISABLED, FAULT, MISSING, NO_DETAIL, OK, STALLED

_PART_UI = {
    OK: "ok",
    MISSING: "missing",
    DISABLED: "disabled",
    FAULT: "faulty",
    STALLED: "faulty",
    NO_DETAIL: "faulty",
}

_ALERT_UI = {
    NONE: "idle",
    "idle": "idle",
    "suspect": "suspect",
    VISUAL: "visual",
    AUDIBLE: "audible",
    SNOOZED: "snoozed",
    CAPPED: "capped",
}

PART_KEYS = ("thermo", "knob", "buzzer", "matrix", "camera", "microphone")

DASHBOARD_KEYS = (
    "temperature_c", "humidity_pct", "room_normal_c", "drop_c", "occupancy", "last_move_s",
    "people_present", "people_count", "sensitivity_c", "snooze_remaining_s", "signals", "alert",
    "draft_label", "draft_reason", "noise", "parts", "preview", "calibration", "today",
    "detections", "feedback", "uptime_s", "product_title", "activity_heatmap",
    "preview_zoom",
)


def _part_health(state: str) -> str:
    return _PART_UI.get(state, "faulty")


def _f(v):
    return None if v is None else float(v)


def build_snapshot(
    *,
    temperature_c: float | None,
    humidity_pct: float | None,
    occupancy: str,
    sensitivity_c: float,
    snooze_remaining_s: int,
    cold: bool,
    window: bool,
    noise: bool,
    alert: str,
    parts: dict[str, str],
    preview: str,
    uptime_s: float,
    room_normal_c: float | None = None,
    drop_c: float | None = None,
    last_move_s: float | None = None,
    people_present: bool | None = None,
    people_count: int = 0,
    draft_label: str = "ALL GOOD",
    draft_reason: str = "",
    noise_db: float | None = None,
    noise_median_db: float | None = None,
    noise_rise_db: float | None = None,
    noise_noisy: bool = False,
    noise_threshold_db: float = -35.0,
    noise_heatmap: dict | None = None,
    activity_heatmap: dict | None = None,
    calibration: dict | None = None,
    today: dict | None = None,
    detections: list | None = None,
    feedback: str = "",
    product_title: str = "Draft Sentinel",
    preview_zoom: float = 1.0,
) -> dict:
    """Return a JSON-ready HudSnapshot. Derived scalars only — never image bytes."""
    mapped_parts = {}
    for key in PART_KEYS:
        raw_key = "mic" if key == "microphone" else key
        mapped_parts[key] = _part_health(parts.get(raw_key, parts.get(key, MISSING)))
    heatmap = noise_heatmap
    if heatmap is None:
        heatmap = {
            "available": False,
            "window_s": float(config.HEATMAP_WINDOW_S),
            "bin_s": float(config.HEATMAP_BIN_S),
            "intensity_mode": "none",
            "bins": [],
            "label": config.HEATMAP_LABEL,
        }
    else:
        mode = heatmap.get("intensity_mode", "none")
        if mode not in ("rise", "absolute", "none"):
            mode = "none"
        bins = [max(0.0, min(1.0, float(v))) for v in (heatmap.get("bins") or [])]
        if not heatmap.get("available", False):
            bins = []
            mode = "none"
        heatmap = {
            "available": bool(heatmap.get("available", False)),
            "window_s": float(heatmap.get("window_s", config.HEATMAP_WINDOW_S)),
            "bin_s": float(heatmap.get("bin_s", config.HEATMAP_BIN_S)),
            "intensity_mode": mode,
            "bins": bins,
            "label": str(heatmap.get("label") or config.HEATMAP_LABEL),
        }
    cols, rows = int(config.ACTIVITY_GRID[0]), int(config.ACTIVITY_GRID[1])
    act = activity_heatmap
    if act is None or not act.get("available", False):
        activity = {
            "available": False,
            "cols": cols,
            "rows": rows,
            "cells": [],
            "acoustic_available": bool(act.get("acoustic_available", False)) if act else False,
            "acoustic_factor": 1.0,
            "label": config.ACTIVITY_LABEL,
        }
    else:
        raw_cells = act.get("cells") or []
        cells: list[list[float]] = []
        if raw_cells and isinstance(raw_cells[0], (list, tuple)):
            for row in raw_cells[:rows]:
                cells.append([max(0.0, min(1.0, float(v))) for v in list(row)[:cols]])
        else:
            flat = [max(0.0, min(1.0, float(v))) for v in raw_cells]
            for r in range(rows):
                cells.append(flat[r * cols:(r + 1) * cols])
        acoustic_ok = bool(act.get("acoustic_available", False))
        factor = float(act.get("acoustic_factor", 1.0))
        if not acoustic_ok:
            factor = 1.0
        factor = max(1.0, factor)
        activity = {
            "available": True,
            "cols": int(act.get("cols", cols)),
            "rows": int(act.get("rows", rows)),
            "cells": cells,
            "acoustic_available": acoustic_ok,
            "acoustic_factor": factor,
            "label": str(act.get("label") or config.ACTIVITY_LABEL),
        }
    return {
        "temperature_c": _f(temperature_c),
        "humidity_pct": _f(humidity_pct),
        "room_normal_c": _f(room_normal_c),
        "drop_c": _f(drop_c),
        "occupancy": occupancy,
        "last_move_s": None if last_move_s is None else float(last_move_s),
        "people_present": people_present,
        "people_count": int(people_count),
        "sensitivity_c": float(sensitivity_c),
        "snooze_remaining_s": int(snooze_remaining_s),
        "signals": {"cold": bool(cold), "window": bool(window), "noise": bool(noise)},
        "alert": _ALERT_UI.get(alert, alert),
        "draft_label": draft_label,
        "draft_reason": draft_reason,
        "noise": {
            "db": _f(noise_db),
            "median_db": _f(noise_median_db),
            "rise_db": _f(noise_rise_db),
            "noisy": bool(noise_noisy),
            "threshold_db": float(noise_threshold_db),
            "heatmap": heatmap,
        },
        "parts": mapped_parts,
        "preview": preview,
        "calibration": calibration,
        "today": today or {"events": 0, "minutes": 0.0, "degree_minutes": 0.0, "recent": []},
        "detections": list(detections or []),
        "feedback": feedback or "",
        "uptime_s": float(uptime_s),
        "product_title": product_title,
        "activity_heatmap": activity,
        "preview_zoom": float(preview_zoom),
    }
