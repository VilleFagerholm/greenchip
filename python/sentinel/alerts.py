"""Alert escalation and the heat-loss event lifecycle (constitution III; data-model.md AlertState)."""

from dataclasses import dataclass

from sentinel import config
from sentinel.events import HeatLossEvent
from sentinel.fusion import DRAFT, FusionResult
from sentinel.occupancy import OCCUPIED

NONE, VISUAL, AUDIBLE, CAPPED, SNOOZED = "none", "visual", "audible", "capped", "snoozed"


@dataclass(frozen=True)
class StepResult:
    level: str
    beep: bool
    finished: HeatLossEvent | None


class AlertEngine:
    def __init__(self):
        self.level = NONE
        self.event: HeatLossEvent | None = None
        self.draft_since_t: float | None = None
        self.last_beep_t: float | None = None
        self._capped = False
        self._clear_since_t: float | None = None
        self._last_t: float | None = None

    def _finish(self, t: float, reason: str) -> HeatLossEvent:
        e = self.event
        e.duration_s = int(round(t - self.draft_since_t))
        e.end_reason = reason
        self.event = None
        self.draft_since_t = None
        self.last_beep_t = None
        return e

    def step(self, t: float, fusion: FusionResult, drop_c: float, occupancy: str, snooze_active: bool,
             wall_iso: str, uptime_s: float, sensitivity_c: float) -> StepResult:
        dt = 0.0 if self._last_t is None else t - self._last_t
        self._last_t = t
        if self.event is not None:
            self.event.degree_minutes += max(drop_c, 0.0) * dt / 60
            self.event.max_drop_c = max(self.event.max_drop_c, drop_c)

        if fusion.state == DRAFT:
            self._clear_since_t = None
            if snooze_active:
                finished = self._finish(t, "snoozed") if self.event else None
                self.level = SNOOZED
                return StepResult(self.level, False, finished)
            if self._capped:
                self.level = CAPPED
                return StepResult(self.level, False, None)
            if self.event is None:
                self.event = HeatLossEvent(start=wall_iso, start_uptime_s=int(uptime_s),
                                           sensitivity_c=sensitivity_c, signals=sorted(fusion.signals),
                                           max_drop_c=max(drop_c, 0.0))
                self.draft_since_t = t
            elapsed = t - self.draft_since_t
            if elapsed >= config.MAX_ALERT_S:
                self._capped = True
                self.level = CAPPED
                return StepResult(self.level, False, self._finish(t, "timed_out"))
            if elapsed >= config.GRACE_S:
                self.level = AUDIBLE
                beep = self.last_beep_t is None or t - self.last_beep_t >= config.REPEAT_S
                if beep:
                    self.last_beep_t = t
                assert not beep or fusion.state == DRAFT  # FR-008: only a fused draft may beep
                return StepResult(self.level, beep, None)
            self.level = VISUAL
            return StepResult(self.level, False, None)

        # not a draft right now
        if occupancy == OCCUPIED and self.event is not None:
            self._capped = False
            self._clear_since_t = None
            self.level = NONE
            return StepResult(self.level, False, self._finish(t, "occupied"))
        if self._clear_since_t is None:
            self._clear_since_t = t
        cleared = t - self._clear_since_t >= config.CLEAR_CONFIRM_S
        if self.event is not None:
            if cleared:
                self.level = NONE
                return StepResult(self.level, False, self._finish(t, "closed"))
            return StepResult(self.level, False, None)
        if cleared or occupancy == OCCUPIED:
            self._capped = False
        if not self._capped:
            self.level = NONE
        return StepResult(self.level, False, None)

    def confirm_beep(self, played: bool) -> None:
        if played and self.event is not None:
            self.event.beeps += 1
