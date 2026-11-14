"""The SENTINEL developer status line (contracts/logs-and-files.md)."""

FIELDS = ("occ", "last_move", "motion", "cam", "temp", "normal", "drop", "sens", "cold", "win",
          "cells", "noise", "loud", "state", "alert", "snooze", "parts")


def _fmt(key: str, value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "1" if value else "0"
    if key == "last_move":
        return f"{int(value)}s"
    if key == "motion":
        return f"{value:.3f}"
    if isinstance(value, float):
        return f"{round(value, 1) + 0.0:.1f}"  # + 0.0 turns -0.0 into 0.0
    return str(value)


def format_status(values: dict) -> str:
    return "SENTINEL " + " ".join(f"{k}={_fmt(k, values.get(k))}" for k in FIELDS)
