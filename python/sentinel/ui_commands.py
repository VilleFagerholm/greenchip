"""Clamp/validate dashboard operator commands (contracts/ui-commands.md)."""

from sentinel import config


def clamp_sensitivity(value) -> float | None:
    try:
        v = round(float(value), 1)
    except (TypeError, ValueError):
        return None
    if not config.SENS_MIN_C <= v <= config.SENS_MAX_C:
        return None
    return v


def clamp_noise_threshold(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not config.NOISE_THRESHOLD_MIN_DB <= v <= config.NOISE_THRESHOLD_MAX_DB:
        return None
    return v


def clamp_confidence(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= v <= 1.0:
        return None
    return v
