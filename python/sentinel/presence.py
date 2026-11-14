"""Lightweight people present / absent / unknown (feature 005). No identity, no count required."""

from sentinel import config


class PresenceState:
    """Short-hold present/absent for HUD + occupancy assist."""

    def __init__(self, hold_s: float | None = None):
        self.hold_s = config.PRESENCE_HOLD_S if hold_s is None else float(hold_s)
        self._camera_ok = False
        self._seen_at: float | None = None

    def set_camera_ok(self, ok: bool) -> None:
        self._camera_ok = bool(ok)
        if not ok:
            self._seen_at = None

    def note(self, t: float) -> None:
        """Record a positive presence signal at monotonic time t."""
        if not self._camera_ok:
            return
        self._seen_at = t

    def clear_if_expired(self, t: float) -> None:
        if self._seen_at is not None and t - self._seen_at > self.hold_s:
            self._seen_at = None

    @property
    def present(self) -> bool | None:
        """True / False / None(unknown when camera not OK)."""
        if not self._camera_ok:
            return None
        return self._seen_at is not None
