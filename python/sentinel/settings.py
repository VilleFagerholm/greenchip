"""settings.json: sensitivity and the closed-window reference (derived values only)."""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from sentinel import config
from sentinel.window_watch import WindowReference

log = logging.getLogger("sentinel.settings")
VERSION = 1


@dataclass
class Settings:
    sensitivity_c: float = config.SENS_DEFAULT_C
    window_reference: WindowReference | None = None
    noise_threshold_db: float = config.DEFAULT_NOISE_THRESHOLD_DB


def clamp_sensitivity(value) -> float:
    try:
        v = round(float(value), 1)
    except (TypeError, ValueError):
        return config.SENS_DEFAULT_C
    if not config.SENS_MIN_C <= v <= config.SENS_MAX_C:
        return config.SENS_DEFAULT_C
    return v


def clamp_noise_threshold(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return config.DEFAULT_NOISE_THRESHOLD_DB
    if not config.NOISE_THRESHOLD_MIN_DB <= v <= config.NOISE_THRESHOLD_MAX_DB:
        return config.DEFAULT_NOISE_THRESHOLD_DB
    return v


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "settings.json"


def load(data_dir: Path) -> Settings:
    path = settings_path(data_dir)
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError("not an object")
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as exc:
        log.warning("settings.json unreadable (%s); using defaults", exc)
        return Settings()
    ref = raw.get("window_reference")
    return Settings(
        sensitivity_c=clamp_sensitivity(raw.get("sensitivity_c", config.SENS_DEFAULT_C)),
        window_reference=WindowReference.from_dict(ref) if ref else None,
        noise_threshold_db=clamp_noise_threshold(
            raw.get("noise_threshold_db", config.DEFAULT_NOISE_THRESHOLD_DB)),
    )


def save(data_dir: Path, settings: Settings) -> None:
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "version": VERSION,
        "sensitivity_c": clamp_sensitivity(settings.sensitivity_c),
        "window_reference": settings.window_reference.to_dict() if settings.window_reference else None,
        "noise_threshold_db": clamp_noise_threshold(settings.noise_threshold_db),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body))
    os.replace(tmp, path)
