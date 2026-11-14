"""Part status, Thermo fault rules, and the SELFTEST line (data-model.md PartStatus)."""

from dataclasses import dataclass

from sentinel import config

PARTS = ("thermo", "knob", "buzzer", "matrix", "camera", "mic")
OK, MISSING, FAULT, STALLED, NO_DETAIL, DISABLED = "ok", "missing", "fault", "stalled", "no_detail", "disabled"
FAULT_BITS = {"thermo": 1, "knob": 2, "buzzer": 4, "camera": 8, "mic": 16}
LETTERS = {"thermo": "T", "knob": "K", "buzzer": "B", "matrix": "M", "camera": "C", "mic": "A"}


@dataclass
class PartStatus:
    part: str
    state: str = MISSING
    since_s: float = 0.0


class Parts:
    def __init__(self, now: float = 0.0):
        self._items = {p: PartStatus(p, MISSING, now) for p in PARTS}

    def set(self, part: str, state: str, now: float) -> None:
        item = self._items[part]
        if item.state != state:
            item.state = state
            item.since_s = now

    def state(self, part: str) -> str:
        return self._items[part].state

    def ok(self, part: str) -> bool:
        return self._items[part].state == OK

    def faults_mask(self) -> int:
        return sum(bit for part, bit in FAULT_BITS.items()
                   if not self.ok(part) and self.state(part) != DISABLED)

    def code(self) -> str:
        return "".join(f"{LETTERS[p]}{1 if self.ok(p) else 0}" for p in PARTS
                       if self.state(p) != DISABLED)

    def selftest_line(self) -> str:
        return "SELFTEST " + " ".join(f"{p}={self.state(p)}" for p in PARTS)


class ThermoRules:
    """Thermo is faulty when out of range or when the value has not changed for THERMO_FROZEN_S."""

    def __init__(self):
        self._last: float | None = None
        self._changed_at: float | None = None

    def check(self, temp_c: float | None, now: float) -> str:
        if temp_c is None:
            self._last = self._changed_at = None
            return MISSING
        if temp_c != self._last:
            self._last = temp_c
            self._changed_at = now
        if not config.THERMO_MIN_C <= temp_c <= config.THERMO_MAX_C:
            return FAULT
        if now - self._changed_at >= config.THERMO_FROZEN_S:
            return FAULT
        return OK
