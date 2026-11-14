"""Parse sketch notifications (contracts/bridge-rpc.md)."""

from dataclasses import dataclass

KNOB_SNOOZE_ON = 1
KNOB_SNOOZE_OFF = 2
KNOB_CALIBRATE = 3
KNOB_SUMMARY = 4
KNOB_EVENTS = (KNOB_SNOOZE_ON, KNOB_SNOOZE_OFF, KNOB_CALIBRATE, KNOB_SUMMARY)


@dataclass(frozen=True)
class McuState:
    thermo_ok: bool
    temp_c: float | None
    humidity_pct: float | None
    knob_ok: bool
    buzzer_ok: bool
    sensitivity_c: float
    snooze_remaining_s: int
    matrix_ok: bool
    uptime_s: int


def parse_mcu_state(args) -> McuState | None:
    if len(args) != 9:
        return None
    try:
        thermo, temp_x100, hum_x10, knob, buzzer, sens_x10, snooze, matrix, uptime = (int(a) for a in args)
    except (TypeError, ValueError):
        return None
    thermo_ok = thermo == 1
    return McuState(
        thermo_ok=thermo_ok,
        temp_c=temp_x100 / 100 if thermo_ok else None,
        humidity_pct=hum_x10 / 10 if thermo_ok else None,
        knob_ok=knob == 1,
        buzzer_ok=buzzer == 1,
        sensitivity_c=round(sens_x10 / 10, 1),
        snooze_remaining_s=max(0, snooze),
        matrix_ok=matrix == 1,
        uptime_s=uptime,
    )


def parse_knob_event(kind) -> int | None:
    try:
        kind = int(kind)
    except (TypeError, ValueError):
        return None
    return kind if kind in KNOB_EVENTS else None


class ResetDetector:
    """Detects a microcontroller restart: its uptime goes backwards."""

    def __init__(self):
        self._last: int | None = None

    def update(self, uptime_s: int) -> bool:
        reset = self._last is not None and uptime_s < self._last
        self._last = uptime_s
        return reset
