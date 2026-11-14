"""Calm local feedback lines for the dashboard (no identity, no cloud)."""

from sentinel.alerts import AUDIBLE, CAPPED, SNOOZED, VISUAL
from sentinel.occupancy import EMPTY, OCCUPIED


def feedback_message(occupancy: str, alert: str, people_count: int = 0) -> str:
    if alert in (AUDIBLE, VISUAL, CAPPED):
        return "Heat may be escaping — check the window."
    if alert == SNOOZED:
        return "Snoozed. We'll stay quiet for a bit."
    if alert == "suspect":
        return "One heat-loss signal — watching quietly."
    if occupancy == OCCUPIED or people_count > 0:
        return "There you are!"
    if occupancy == EMPTY:
        return "Room looks empty. Monitoring for drafts."
    return "System response will appear here"
